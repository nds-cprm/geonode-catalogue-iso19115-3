"""
The ``/catalogue/csw`` endpoint, and ``/showmetadata/xsl/<id>`` (see ``metadata_xsl``).

Own version of ``geonode.catalogue.views.csw_global_dispatch`` (GeoNode 5.0.x).
Wrapping the core view is not enough, because it redirects whenever
``CATALOGUE["default"]["ENGINE"]`` is not exactly
``geonode.catalogue.backends.pycsw_local``.

Differences from GeoNode:

- the pycsw configuration is new for every request (``build_pycsw_config``),
  without the ``repository`` dictionary shared between threads, and already
  includes the ``iso19115p3`` profile;
- the filter clauses are joined with ``AND`` only. In GeoNode an authenticated
  user gets ``(...) OR (id IN ...)``, so the ``ALTERNATES_ONLY`` and
  ``GROUP_PRIVATE_RESOURCES`` filters added afterwards no longer apply to them;
- the authorized set goes through the configured dataset filter
  (``filters.get_dataset_filter``).

When upgrading GeoNode, compare with ``geonode/catalogue/views.py``.
"""

import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import NoReverseMatch, reverse
from django.views.decorators.csrf import csrf_exempt
from guardian.shortcuts import get_objects_for_user
from pycsw import server

import geonode.catalogue.views as core_views
from geonode.base.auth import get_or_create_token
from geonode.groups.models import GroupProfile

from .config import build_pycsw_config
from .constants import ENGINE
from .filters import get_dataset_filter

LOCAL_ENGINES = (ENGINE, "geonode.catalogue.backends.pycsw_local")

# marks "use the filter from the settings"
_FROM_SETTINGS = object()


def _authorized_ids(request, dataset_filter):
    """IDs of the resources the user can see, after ``dataset_filter``."""
    username = str(request.user) if request.user else "AnonymousUser"
    profile = get_user_model().objects.filter(username=username).first()
    if profile is None:
        return []
    resources = get_objects_for_user(profile, "base.view_resourcebase")
    if dataset_filter:
        resources = dataset_filter(resources)
    return list(resources.values_list("id", flat=True))


def _group_ids(request):
    """Groups of the user plus the non-private groups (GROUP_PRIVATE_RESOURCES)."""
    groups_ids = []
    if request.user and request.user.is_authenticated:
        groups_ids.extend(request.user.groups.values_list("id", flat=True))
        try:
            groups_ids.extend(g["group"] for g in request.user.group_list_all().values("group") if "group" in g)
        except Exception:
            pass
    groups_ids.extend(GroupProfile.objects.exclude(access="private").values_list("group", flat=True))
    return sorted({g for g in groups_ids if g is not None})


def _repository_filter(request, base_filter, dataset_filter):
    clauses = [base_filter] if base_filter else []

    authorized_ids = _authorized_ids(request, dataset_filter)
    if authorized_ids:
        clauses.append(f"id IN ({', '.join(str(i) for i in authorized_ids)})")
    else:
        clauses.append("id = -9999")

    if settings.CATALOGUE["default"].get("ALTERNATES_ONLY"):
        clauses.append("alternate IS NOT NULL")

    is_admin = bool(request.user and request.user.is_superuser)
    if not is_admin and settings.GROUP_PRIVATE_RESOURCES:
        groups_ids = _group_ids(request)
        if groups_ids:
            clauses.append(f"(group_id IS NULL OR group_id IN ({', '.join(str(g) for g in groups_ids)}))")
        else:
            clauses.append("group_id IS NULL")

    return " AND ".join(f"({c})" for c in clauses)


@csrf_exempt
def csw_global_dispatch(request, dataset_filter=_FROM_SETTINGS):
    """pycsw wrapper. ``dataset_filter=None`` disables the configured filter."""
    if settings.CATALOGUE["default"]["ENGINE"] not in LOCAL_ENGINES:
        return HttpResponseRedirect(settings.CATALOGUE["default"]["URL"])

    if dataset_filter is _FROM_SETTINGS:
        dataset_filter = get_dataset_filter()

    mdict = build_pycsw_config()

    access_token = None
    if request and request.user:
        access_token = get_or_create_token(request.user)
        if access_token and access_token.is_expired():
            access_token = None

    absolute_uri = f"{request.build_absolute_uri()}"
    query_string = f"{request.META['QUERY_STRING']}"
    env = request.META.copy()

    if access_token:
        env.update({"access_token": access_token.token})
        if "access_token" not in query_string:
            absolute_uri = f"{absolute_uri}&access_token={access_token.token}"
            query_string = f"{query_string}&access_token={access_token.token}"

    env.update(
        {
            # root of the core app, where pycsw looks for its static resources
            "local.app_root": os.path.dirname(core_views.__file__),
            "REQUEST_URI": absolute_uri,
            "QUERY_STRING": query_string,
        }
    )

    mdict["repository"]["filter"] = _repository_filter(request, mdict["repository"].get("filter"), dataset_filter)

    csw = server.Csw(mdict, env, version="2.0.2")
    content = csw.dispatch_wsgi()

    # pycsw >= 2.0: [http_status_code, content]
    if isinstance(content, list):
        content = content[1]

    return HttpResponse(content, content_type=csw.contenttype)


def metadata_xsl(request, id):
    """
    The ``/showmetadata/xsl/<id>`` endpoint, behind GeoNode's "ISO with XSL" metadata link.

    GeoNode (``geonode.catalogue.metadataxsl``) serves the XML generated with
    ``CATALOG_METADATA_TEMPLATE`` with an ``<?xml-stylesheet?>`` line pointing to
    its ``metadata.xsl``, which the browser applies. That stylesheet only reads
    ISO 19139 (``gmd:MD_Metadata``), so with ISO 19115-3 the page comes out empty.

    When the format is ISO 19115-3, this view redirects (302) to the route named by
    ``CATALOGUE_XSL_REDIRECT`` (default ``"metadata"``, the metadata page of
    geonode-mapstore-client), reversed with ``pk``. Otherwise, when the setting is
    ``None`` or the route does not exist, it falls back to the GeoNode view.
    """
    from .formats import ISO19115_3, default_format

    route = getattr(settings, "CATALOGUE_XSL_REDIRECT", "metadata")
    if route and default_format() == ISO19115_3:
        try:
            return HttpResponseRedirect(reverse(route, kwargs={"pk": id}))
        except NoReverseMatch:
            pass

    from geonode.catalogue.metadataxsl import views as metadataxsl_views

    return metadataxsl_views.prefix_xsl_line(request, id)
