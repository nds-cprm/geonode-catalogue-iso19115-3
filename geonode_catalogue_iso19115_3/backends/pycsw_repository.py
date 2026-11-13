"""
pycsw repository (``repository.source``, set in ``config.py``).

Inherits from the GeoNode 5.0.x ``GeoNodeRepository`` and fixes ``GetDomain``.
In GeoNode, ``query_domain`` aggregates over ``ResourceBase.objects``, a
django-polymorphic queryset. django-polymorphic fails on positional aggregates
(``annotate(Count(field))`` and ``aggregate(Min(field), Max(field))``) with
``AttributeError: 'NoneType' object has no attribute 'name'``, because of the
``filter=None`` of ``Aggregate``. pycsw swallows the exception, so every
``GetDomain`` comes back empty.

Here the query uses a plain Django ``QuerySet`` over the same model, with named
aggregates and ordered by value. When upgrading GeoNode, compare with
``geonode/catalogue/backends/pycsw_plugin.py``.
"""

from django.db.models import Count, Max, Min, QuerySet

from geonode.base.models import ResourceBase
from geonode.catalogue.backends.pycsw_plugin import GeoNodeRepository as CoreGeoNodeRepository


def _text(value):
    return None if value is None else str(value)


class GeoNodeRepository(CoreGeoNodeRepository):
    def query_domain(self, domain, typenames, domainquerytype="list", count=False):
        """Values of a property (GetDomain)"""
        objects = self._get_repo_filter(QuerySet(model=ResourceBase))

        if domainquerytype == "range":
            bounds = objects.aggregate(min_value=Min(domain), max_value=Max(domain))
            return [(_text(bounds["min_value"]), _text(bounds["max_value"]))]

        values = objects.exclude(**{f"{domain}__isnull": True}).order_by(domain)
        if count:
            return [
                (_text(row[domain]), row["n"]) for row in values.values(domain).annotate(n=Count("pk")).order_by(domain)
            ]
        return [(_text(value),) for value in values.values_list(domain, flat=True).distinct()]
