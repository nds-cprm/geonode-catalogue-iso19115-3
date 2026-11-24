from geonode.base.models import ResourceBase

from .formats import csw_format_fields


def sync_csw_format(sender, instance, raw=False, **kwargs):
    """
    Keeps ``csw_typename`` and ``csw_schema`` in line with the catalogue format on
    every resource ``save()``.

    Covers the metadata editor, which saves the ``ResourceBase`` without going
    through ``catalogue_post_save`` (connected only to ``Dataset`` and ``Document``).
    After GeoNode 5.0.3 (``5.0.x`` branch) the editor then calls
    ``update_csw_metadata``, which regenerates ``metadata_xml``; in 5.0.3 it only
    saves, so the XML is regenerated on the next ``catalogue_post_save`` or by
    ``regenerate_xml``. Every other path goes through ``CatalogueBackend.create_record``. A ``save`` with
    ``update_fields`` that leaves these fields out does not write them, but
    ``create_record`` fixes them on the next ``catalogue_post_save``.
    """
    if raw or not isinstance(instance, ResourceBase):
        return
    for name, value in csw_format_fields(instance).items():
        setattr(instance, name, value)
