"""
pycsw configuration used by the backend and by the CSW view.

In GeoNode 5.0.x the configuration is built with ``dict(settings, **CONFIGURATION)``:

- the copy is shallow, so ``repository`` is the very dictionary of the
  ``pycsw_local`` module, and the core view changes its filter in place: state
  shared between requests;
- the module defaults win over the settings, ``profiles`` included, which makes
  it impossible to enable the ``iso19115p3`` profile from the settings.

Here every call returns a new dictionary, deep-merged, with the settings winning
over the defaults, the profiles needed by the supported formats, and the
repository with the fixed ``GetDomain``.
"""

import copy

from django.conf import settings

from geonode.catalogue.backends.pycsw_local import CONFIGURATION as CORE_CONFIGURATION

from .constants import APP_NAME, PYCSW_PROFILES

CORE_REPOSITORY = "geonode.catalogue.backends.pycsw_plugin.GeoNodeRepository"
REPOSITORY = f"{APP_NAME}.backends.pycsw_repository.GeoNodeRepository"


def _deep_merge(base, override):
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def build_pycsw_config():
    config = _deep_merge(copy.deepcopy(CORE_CONFIGURATION), copy.deepcopy(settings.PYCSW["CONFIGURATION"]))
    profiles = config.get("profiles") or ()
    if isinstance(profiles, str):
        profiles = [p.strip() for p in profiles.split(",") if p.strip()]
    config["profiles"] = set(profiles) | PYCSW_PROFILES
    # repository with the fixed GetDomain, unless the settings point to another one
    if config["repository"].get("source") == CORE_REPOSITORY:
        config["repository"]["source"] = REPOSITORY
    return config
