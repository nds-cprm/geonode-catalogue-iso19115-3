"""
Filters for the set of resources delivered by the CSW endpoint.

The view narrows the queryset of resources the user is allowed to see in two
steps, and injects the resulting IDs into the pycsw filter, so both steps hold
for every operation (GetRecords, GetRecordById, GetDomain) and every user:

1. ``settings.PYCSW["FILTER"]`` (see ``pycsw_filter``), the GeoNode setting,
   by default approved and published datasets;
2. ``settings.CATALOGUE_CSW_DATASET_FILTER``, for what a dictionary cannot
   express: a callable that receives the queryset and returns a narrower one,
   given as a dotted path, a callable, or ``None`` (the default: no extra filter).

The pycsw repository filter (``PYCSW["CONFIGURATION"]["repository"]["filter"]``)
is not used for this because it also applies to the internal calls of
``catalogue_post_save``: resources outside the criteria would no longer get
their XML generated.
"""

from django.conf import settings
from django.db.models import Case, Exists, ExpressionWrapper, F, IntegerField, OuterRef, Q, Value, When
from django.utils.module_loading import import_string

from geonode.base.models import ResourceBase


# default of PYCSW["FILTER"] in geonode/catalogue/backends/pycsw_plugin.py (GeoNode 5.0.x)
CORE_PYCSW_FILTER = {"resource_type__in": ["dataset"]}

# default of the app: GeoNode's, delivering only approved and published resources
DEFAULT_PYCSW_FILTER = {**CORE_PYCSW_FILTER, "is_approved": True, "is_published": True}


def pycsw_filter():
    """
    ``settings.PYCSW["FILTER"]``: keyword arguments of ``ResourceBase.objects.filter()``.

    GeoNode applies it only in ``GeoNodeRepository.query()`` (``GetRecords``),
    with the default ``CORE_PYCSW_FILTER``. The CSW view of the app applies it
    to the authorized set too, so it also holds for ``GetRecordById`` and
    ``GetDomain``, with the default ``DEFAULT_PYCSW_FILTER`` (approved and
    published datasets). Since the view narrows the set of every operation,
    ``GetRecords`` follows the default of the app too.

    A ``PYCSW["FILTER"]`` in the settings replaces the default as a whole, so it
    must repeat ``is_approved``/``is_published`` to keep them. ``{}`` delivers
    every resource the user can view.
    """
    return settings.PYCSW.get("FILTER", DEFAULT_PYCSW_FILTER)


def get_dataset_filter():
    """The filter configured in ``CATALOGUE_CSW_DATASET_FILTER``, or ``None``."""
    value = getattr(settings, "CATALOGUE_CSW_DATASET_FILTER", None)
    if isinstance(value, str):
        return import_string(value)
    return value


def _filled(field):
    """Text field filled in, like the ``if field`` of metadata_completeness."""
    return Q(**{f"{field}__isnull": False}) & ~Q(**{field: ""})


def _point(condition):
    return Case(When(condition, then=Value(1)), default=Value(0), output_field=IntegerField())


_OTHER_RESTRICTIONS = Q(restriction_code_type__identifier="otherRestrictions")


def with_metadata_completeness(queryset):
    """
    Annotates ``md_filled`` and ``md_required``, reproducing in SQL the
    ``ResourceBase.metadata_completeness`` property (geonode/base/models.py).
    If the property changes in GeoNode, this function must follow.
    """
    regions = ResourceBase.regions.through.objects.filter(resourcebase_id=OuterRef("pk"))
    filled = (
        _point(_filled("abstract"))
        + _point(_filled("category__identifier"))
        + _point(_filled("data_quality_statement"))
        + _point(Q(date__isnull=False))
        + _point(_filled("date_type"))
        + _point(_filled("language"))
        + _point(Q(license__isnull=False) & ~Q(license__name="Not Specified"))
        + _point(Exists(regions))
        + _point(_filled("title"))
        + _point(_OTHER_RESTRICTIONS & _filled("constraints_other"))
    )
    required = Value(9) + _point(_OTHER_RESTRICTIONS)
    return queryset.annotate(md_filled=filled, md_required=required)


def published_datasets_with_complete_metadata(queryset):
    """
    Datasets that are approved, published and whose metadata completeness is
    above ``settings.CSW_MIN_METADATA_COMPLETENESS`` (default: 60%).

    Enable it with::

        CATALOGUE_CSW_DATASET_FILTER = (
            "geonode_catalogue_iso19115_3.filters.published_datasets_with_complete_metadata"
        )
    """
    minimum = getattr(settings, "CSW_MIN_METADATA_COMPLETENESS", 60)
    return (
        with_metadata_completeness(queryset.filter(resource_type="dataset", is_approved=True, is_published=True))
        .annotate(
            md_margin=ExpressionWrapper(
                F("md_filled") * 100 - Value(minimum) * F("md_required"), output_field=IntegerField()
            )
        )
        .filter(md_margin__gt=0)
    )
