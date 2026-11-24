"""
Regenerates the ``metadata_xml`` of the resources of every type.

    python manage.py regenerate_metadata_xml [--type map --type document] [--id 1 --id 2] [--outdated] [--dry-run]

GeoNode's ``regenerate_xml`` (5.0.x) only goes through datasets, and GeoNode only
regenerates the XML by itself when a dataset or document is saved (maps and
GeoApps only through the resource manager). After installing the app or changing
``CATALOGUE_DEFAULT_FORMAT``, the other resources keep the old format. This
command calls ``catalogue_post_save`` for each resource, as ``regenerate_xml``
does for datasets, which also refreshes ``csw_typename``/``csw_schema`` and the
metadata links.

``--type`` filters by ``resource_type`` (``dataset``, ``document``, ``map``,
``dashboard``, ``geostory``...), or by the model of ``polymorphic_ctype`` when
``resource_type`` is empty (``ResourceBase.save()`` only fills it from the second
save, so resources created outside the resource manager may not have it).
``--outdated`` skips the resources whose stored XML is already in the default
format, and the ones with uploaded XML kept with "preserve", which are never
regenerated. Exits with status 1 when any resource fails.
"""

from django.core.management.base import BaseCommand
from django.db.models import Q

from geonode.base.models import ResourceBase
from geonode.catalogue.models import catalogue_post_save

from ...formats import default_format, format_of_xml


class Command(BaseCommand):
    help = "Regenerates the metadata XML of resources of every type (GeoNode's regenerate_xml only covers datasets)."

    def add_arguments(self, parser):
        parser.add_argument("--id", action="append", type=int, dest="ids", help="Resource ID (can be repeated).")
        parser.add_argument(
            "--type", action="append", dest="types", help="resource_type: dataset, document, map... (can be repeated)."
        )
        parser.add_argument(
            "--outdated",
            action="store_true",
            help="Only resources whose stored XML is not in the default format (CATALOGUE_DEFAULT_FORMAT).",
        )
        parser.add_argument("--dry-run", action="store_true", help="List the resources without changing them.")

    def handle(self, *args, **options):
        target = default_format()
        resources = ResourceBase.objects.non_polymorphic().order_by("id")
        if options["ids"]:
            resources = resources.filter(id__in=options["ids"])
        if options["types"]:
            empty_type = Q(resource_type__isnull=True) | Q(resource_type="")
            resources = resources.filter(
                Q(resource_type__in=options["types"]) | (empty_type & Q(polymorphic_ctype__model__in=options["types"]))
            )

        done = failed = skipped = 0
        for resource in resources.iterator():
            current = format_of_xml(resource.metadata_xml)
            if options["outdated"] and (
                current == target or (resource.metadata_uploaded and resource.metadata_uploaded_preserve)
            ):
                skipped += 1
                continue
            label = f"[{resource.id}] {resource.resource_type or '-'} {resource.title!r} ({current or 'no XML'})"
            if options["dry_run"]:
                self.stdout.write(f"would regenerate {label}")
                done += 1
                continue
            try:
                instance = resource.get_real_instance()
                catalogue_post_save(instance=instance, sender=instance.__class__)
            except Exception as err:
                failed += 1
                self.stdout.write(self.style.ERROR(f"{label}: {err}"))
                continue
            done += 1
            self.stdout.write(f"regenerated {label}")

        verb = "to regenerate" if options["dry_run"] else "regenerated"
        self.stdout.write(f"format: {target}  {verb}: {done}  failed: {failed}  skipped: {skipped}")
        if failed:
            raise SystemExit(1)
