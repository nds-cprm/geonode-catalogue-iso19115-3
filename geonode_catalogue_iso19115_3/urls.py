"""
URLs of the app. They must come before ``geonode.urls`` so that
``/catalogue/csw`` resolves here::

    from geonode.urls import urlpatterns
    from geonode_catalogue_iso19115_3.urls import urlpatterns as catalogue_urlpatterns

    urlpatterns[0:0] = catalogue_urlpatterns

GeoNode's ``reverse("csw_global_dispatch")`` keeps returning the same address.
"""

from django.urls import re_path

from . import views

urlpatterns = [
    re_path(r"^catalogue/csw$", views.csw_global_dispatch, name="iso19115_3_csw"),
]
