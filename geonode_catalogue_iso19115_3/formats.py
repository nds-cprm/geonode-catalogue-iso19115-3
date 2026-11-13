"""
Metadata formats of the catalogue.

GeoNode 5.0.x only knows ISO 19139 (``gmd``). Here the core table is extended
with ISO 19115-3, and the format written to ``metadata_xml`` comes from
``settings.CATALOGUE_DEFAULT_FORMAT``.
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from lxml import etree

from geonode.catalogue.backends.generic import METADATA_FORMATS as CORE_METADATA_FORMATS

from .constants import ISO19115_3, ISO19139, METADATA_TEMPLATES, PYCSW_PROFILES  # noqa: F401

# format name -> (typename, namespace/outputschema)
METADATA_FORMATS = {
    **CORE_METADATA_FORMATS,
    ISO19115_3: ("mdb:MD_Metadata", "http://standards.iso.org/iso/19115/-3/mdb/2.0"),
}


def default_format():
    fmt = getattr(settings, "CATALOGUE_DEFAULT_FORMAT", ISO19115_3)
    if fmt not in METADATA_TEMPLATES:
        raise ImproperlyConfigured(
            f"Invalid CATALOGUE_DEFAULT_FORMAT: {fmt!r}. Use one of {', '.join(METADATA_TEMPLATES)}."
        )
    return fmt


def default_typename():
    return METADATA_FORMATS[default_format()][0]


def default_schema():
    return METADATA_FORMATS[default_format()][1]


def md_metadata_class(fmt=None):
    """OWSLib class that reads the format (``owslib.iso`` or ``owslib.iso3``)."""
    if (fmt or default_format()) == ISO19115_3:
        from owslib.iso3 import MD_Metadata
    else:
        from owslib.iso import MD_Metadata
    return MD_Metadata


def format_of_xml(xml):
    """Format name from the root element of an XML document, or ``None``."""
    if not xml:
        return None
    try:
        root = etree.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    except (etree.XMLSyntaxError, ValueError):
        return None
    namespace = etree.QName(root).namespace
    for name, (_typename, schema) in METADATA_FORMATS.items():
        if schema == namespace and name in METADATA_TEMPLATES:
            return name
    return None


def csw_format_fields(instance):
    """
    Values of ``csw_typename`` and ``csw_schema`` for the XML stored by the resource.

    The pycsw ``iso19115p3`` profile only returns the stored XML when
    ``csw_typename == 'mdb:MD_Metadata'`` (and ``apiso`` only when it is
    ``gmd:MD_Metadata``), so these fields must follow the format. XML uploaded
    by a user and preserved keeps its own format.
    """
    fmt = None
    if getattr(instance, "metadata_uploaded", False) and getattr(instance, "metadata_uploaded_preserve", False):
        fmt = format_of_xml(getattr(instance, "metadata_xml", None))
    typename, schema = METADATA_FORMATS[fmt or default_format()]
    return {"csw_typename": typename, "csw_schema": schema}
