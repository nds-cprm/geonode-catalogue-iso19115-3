"""
Validates the ``metadata_xml`` stored in the resources against the XSD of its format.

    python manage.py validate_metadata_xml [--id 1 --id 2] [--max-errors 5]

Resources in a format without an XSD (today only ISO 19115-3 has one) are
counted as skipped. Exits with status 1 when any XML is invalid.
"""

from django.core.management.base import BaseCommand, CommandError

from geonode.base.models import ResourceBase

from ...formats import format_of_xml
from ...validation import SCHEMA_ROOTS, SchemaNotAvailable, validate_xml


class Command(BaseCommand):
    help = "Validates the metadata XML of the resources against the XSD of its format."

    def add_arguments(self, parser):
        parser.add_argument("--id", action="append", type=int, dest="ids", help="Resource ID (can be repeated).")
        parser.add_argument("--max-errors", type=int, default=5, help="Errors shown per resource (default: 5).")

    def handle(self, *args, **options):
        resources = ResourceBase.objects.non_polymorphic().exclude(metadata_xml__isnull=True).exclude(metadata_xml="")
        if options["ids"]:
            resources = resources.filter(id__in=options["ids"])

        valid = invalid = skipped = 0
        for resource in resources.only("id", "title", "metadata_xml").order_by("id").iterator():
            fmt = format_of_xml(resource.metadata_xml)
            if fmt not in SCHEMA_ROOTS:
                skipped += 1
                continue
            try:
                errors = validate_xml(resource.metadata_xml, fmt)
            except SchemaNotAvailable as err:
                raise CommandError(str(err))
            if not errors:
                valid += 1
                continue
            invalid += 1
            self.stdout.write(self.style.ERROR(f"[{resource.id}] {resource.title}: {len(errors)} error(s)"))
            for error in errors[: options["max_errors"]]:
                self.stdout.write(f"    {error}")

        self.stdout.write(f"valid: {valid}  invalid: {invalid}  skipped (no XSD): {skipped}")
        if invalid:
            raise SystemExit(1)
