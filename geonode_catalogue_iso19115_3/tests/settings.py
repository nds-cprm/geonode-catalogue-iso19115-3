"""
Settings to run the tests from this repository, on top of the GeoNode settings::

    DJANGO_SETTINGS_MODULE=geonode_catalogue_iso19115_3.tests.settings \\
        python -m django test geonode_catalogue_iso19115_3

Inside a GeoNode project that has the app installed, these settings are not
needed: ``python manage.py test geonode_catalogue_iso19115_3`` runs the same
tests with the project settings, because every test sets what it depends on.

GeoNode 5.0.x must be installed, and DATABASE_URL must point to a PostGIS
database (the test runner creates and drops its own test database).
"""

from geonode.settings import *  # noqa: F401,F403
from geonode.settings import CATALOGUE, INSTALLED_APPS

from geonode_catalogue_iso19115_3.constants import ENGINE, ISO19115_3, METADATA_TEMPLATES

INSTALLED_APPS += ("geonode_catalogue_iso19115_3",)

CATALOGUE["default"]["ENGINE"] = ENGINE
CATALOGUE_DEFAULT_FORMAT = ISO19115_3
CATALOG_METADATA_TEMPLATE = METADATA_TEMPLATES[ISO19115_3]
