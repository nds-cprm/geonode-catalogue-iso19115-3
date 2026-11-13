"""
Filters for the set of resources delivered by the CSW endpoint.

A filter is a callable that receives the queryset of resources the user is
allowed to see and returns a narrower queryset. The view applies it to the list
of authorized IDs it injects into the pycsw filter, so it holds for every
operation (GetRecords, GetRecordById, GetDomain) and every user.

The filter is chosen with ``settings.CATALOGUE_CSW_DATASET_FILTER``: a dotted
path, a callable, or ``None`` (the default: no extra filter, like GeoNode).

The pycsw repository filter (``PYCSW["CONFIGURATION"]["repository"]["filter"]``)
is not used for this because it also applies to the internal calls of
``catalogue_post_save``: resources outside the criteria would no longer get
their XML generated.
"""

from django.conf import settings
from django.db.models import Case, Exists, ExpressionWrapper, F, IntegerField, OuterRef, Q, Value, When
from django.utils.module_loading import import_string

from geonode.base.models import ResourceBase


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
