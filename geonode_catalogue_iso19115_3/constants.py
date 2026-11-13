"""Constants with no dependencies, so they can be imported from a settings module."""

APP_NAME = "geonode_catalogue_iso19115_3"
ENGINE = f"{APP_NAME}.backends.pycsw_local"

ISO19139 = "ISO"
ISO19115_3 = "ISO19115-3_2018"

# formats that can be written to metadata_xml -> default template
METADATA_TEMPLATES = {
    ISO19139: f"{APP_NAME}/full_metadata_iso19139.xml",
    ISO19115_3: f"{APP_NAME}/full_metadata_iso19115-3.xml",
}

# pycsw profiles needed to read and return each format
PYCSW_PROFILES = {"apiso", "ebrim", "iso19115p3"}
