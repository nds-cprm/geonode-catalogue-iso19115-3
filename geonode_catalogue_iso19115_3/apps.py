from django.apps import AppConfig
from django.conf import settings
from django.core.checks import Warning, register

from .constants import APP_NAME, ENGINE


class CatalogueISO19115_3Config(AppConfig):
    name = APP_NAME
    label = APP_NAME
    verbose_name = "GeoNode catalogue - ISO 19115-3"
    default = True

    def ready(self):
        from django.db.models.signals import pre_save

        from .formats import default_format
        from .signals import sync_csw_format

        default_format()  # validates CATALOGUE_DEFAULT_FORMAT at startup
        pre_save.connect(sync_csw_format, dispatch_uid=f"{APP_NAME}_sync_csw_format")


@register()
def check_catalogue_settings(app_configs, **kwargs):
    from .formats import METADATA_TEMPLATES, default_format

    messages = []
    engine = settings.CATALOGUE["default"]["ENGINE"]
    if engine != ENGINE:
        messages.append(
            Warning(
                f"CATALOGUE['default']['ENGINE'] is {engine!r}: the {default_format()!r} format and the fixes of "
                f"{APP_NAME} do not apply to catalogue_post_save.",
                hint=f"Set CATALOGUE['default']['ENGINE'] = {ENGINE!r}.",
                id=f"{APP_NAME}.W001",
            )
        )
    expected = METADATA_TEMPLATES[default_format()]
    if settings.CATALOG_METADATA_TEMPLATE != expected:
        messages.append(
            Warning(
                f"CATALOG_METADATA_TEMPLATE ({settings.CATALOG_METADATA_TEMPLATE!r}) is not the default template of "
                f"the {default_format()!r} format ({expected!r}). Its XML must have the root element of that format.",
                hint=(
                    f"If the template extends the default one, silence this warning with "
                    f"SILENCED_SYSTEM_CHECKS = ['{APP_NAME}.W002']."
                ),
                id=f"{APP_NAME}.W002",
            )
        )
    return messages
