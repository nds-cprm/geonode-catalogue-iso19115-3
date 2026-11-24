"""
ISO 19115-3 (2018) support for the GeoNode 5 CSW catalogue, as a separate Django app.

The app overrides parts of ``geonode.catalogue`` without changing GeoNode itself:

- the metadata format written to ``ResourceBase.metadata_xml`` is configurable
  (ISO 19115-3 or ISO 19139), see ``formats``;
- a catalogue backend (``CATALOGUE["default"]["ENGINE"]``), see ``backends.pycsw_local``;
- its own ``/catalogue/csw`` view, see ``views``;
- XSD validation of the generated XML, see ``validation``.
"""

__version__ = "0.3.0"
