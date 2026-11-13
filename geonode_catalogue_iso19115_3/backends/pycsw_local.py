"""
Catalogue backend (``CATALOGUE["default"]["ENGINE"]``).

Inherits from the GeoNode 5.0.x ``pycsw_local`` backend and replaces what is
hard-coded to ISO 19139 there:

- the ``outputschema`` and the OWSLib ``MD_Metadata`` class follow
  ``CATALOGUE_DEFAULT_FORMAT``;
- the metadata links include ISO 19115-3;
- the pycsw configuration comes from ``config.build_pycsw_config()``;
- ``create_record``, called by ``catalogue_post_save`` on every path (signal,
  ``set_resource_links``, ``regenerate_xml``...), writes ``csw_typename`` and
  ``csw_schema`` according to the format.

Fixes compared to GeoNode:

- the ``Catalogue`` object lives on the instance; the core ``__init__`` stores it
  on the class (``GenericCatalogueBackend.__init__(CatalogueBackend, self, ...)``),
  so it is shared by every instance;
- ``search_records`` called ``.items()`` on a list and passed ``keywords`` twice.

``get_record``, ``search_records`` and ``_csw_local_dispatch`` are adapted
copies from GeoNode 5.0.x: when upgrading GeoNode, compare them with
``geonode/catalogue/backends/pycsw_local.py``.
"""

import os

from owslib.etree import etree as dlxml
from pycsw import server
from shapely.errors import ShapelyError

from geonode.catalogue.backends import pycsw_local as core
from geonode.catalogue.backends.generic import Catalogue as GenericCatalogue

from ..config import build_pycsw_config
from ..formats import METADATA_FORMATS, csw_format_fields, default_format, default_schema, md_metadata_class

CSW_NAMESPACE = "http://www.opengis.net/cat/csw/2.0.2"


class Catalogue(GenericCatalogue):
    def urls_for_uuid(self, uuid):
        """GetRecordById URLs of a record, one per format."""
        return [
            ("text/xml", mformat, self.url_for_uuid(uuid, METADATA_FORMATS[mformat][1])) for mformat in self.formats
        ]

    def metadatarecord2dict(self, rec):
        result = super().metadatarecord2dict(rec)
        if result is not None:
            url = self.url_for_uuid(rec.identifier, default_schema())
            result["metadata_links"] = [("text/xml", default_format(), url)]
        return result


class CatalogueBackend(core.CatalogueBackend):
    def __init__(self, *args, **kwargs):
        self.catalogue = Catalogue(*args, **kwargs)
        self.catalogue.formats = list(METADATA_FORMATS)
        self.catalogue.local = True

    def create_record(self, item):
        from geonode.base.models import ResourceBase

        fields = csw_format_fields(item)
        ResourceBase.objects.filter(pk=item.pk).update(**fields)
        for name, value in fields.items():
            setattr(item, name, value)

    def get_record(self, uuid):
        results = self._csw_local_dispatch(identifier=uuid)
        if len(results) < 1:
            return None

        result = dlxml.fromstring(results).find(f"{{{default_schema()}}}MD_Metadata")
        if result is None:
            return None

        record = md_metadata_class()(result)
        record.keywords = []
        identification = getattr(record, "identification", None)
        if identification and hasattr(identification[0], "keywords"):
            for kw in identification[0].keywords:
                record.keywords.extend([_kw.name for _kw in kw.keywords])

        record.links = {}
        record.links["metadata"] = self.catalogue.urls_for_uuid(uuid)
        record.links["download"] = self.catalogue.extract_links(record)
        return record

    def search_records(self, keywords, start, limit, bbox):
        with self.catalogue:
            lresults = self._csw_local_dispatch(keywords, start + 1, limit, bbox)
            e = dlxml.fromstring(lresults)

            MD_Metadata = md_metadata_class()
            self.catalogue.records = [MD_Metadata(x) for x in e.findall(f"//{{{default_schema()}}}MD_Metadata")]
            results = [self.catalogue.metadatarecord2dict(doc) for doc in self.catalogue.records]

            search_results = e.find(f"{{{CSW_NAMESPACE}}}SearchResults")
            return {
                "rows": results,
                "total": search_results.attrib.get("numberOfRecordsMatched"),
                "next_page": search_results.attrib.get("nextRecord"),
            }

    def _csw_local_dispatch(self, keywords=None, start=0, limit=10, bbox=None, identifier=None):
        """HTTP-less CSW"""
        mdict = build_pycsw_config()

        # fake HTTP environment variable
        os.environ["QUERY_STRING"] = ""

        csw = server.Csw(mdict, version="2.0.2")
        csw.requesttype = "GET"

        if identifier is None:  # GetRecords
            csw.kvp = {
                "service": "CSW",
                "version": "2.0.2",
                "elementsetname": "full",
                "typenames": [METADATA_FORMATS[f][0] for f in self.catalogue.formats],
                "resulttype": "results",
                "constraintlanguage": "CQL_TEXT",
                "outputschema": default_schema(),
                "constraint": None,
                "startposition": start,
                "maxrecords": limit,
            }
            response = csw.getrecords2()
        else:  # GetRecordById
            csw.kvp = {
                "service": "CSW",
                "version": "2.0.2",
                "request": "GetRecordById",
                "id": identifier,
                "outputschema": default_schema(),
            }
            # pycsw still fails on empty geometries (same workaround as GeoNode)
            try:
                response = csw.dispatch()
            except ShapelyError:
                return []

        if isinstance(response, list):  # pycsw 2.0+
            response = response[1]

        return response
