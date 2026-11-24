# geonode-catalogue-iso19115-3

Django app that overrides the [GeoNode](https://geonode.org/) 5 CSW catalogue to support the ISO 19115-3 (2018) metadata format.

GeoNode 5.0.x writes and serves metadata only as ISO 19139 (`gmd`), and has no extension point to change that. This app adds ISO 19115-3 (`mdb` 2.0) without patching GeoNode. It provides:

- a configurable metadata format for the XML stored in each resource (`ISO19115-3_2018` or `ISO`, that is ISO 19139);
- a catalogue backend and a `/catalogue/csw` view that serve both formats through pycsw;
- a redirect of GeoNode's "ISO with XSL" metadata link, whose stylesheet only reads ISO 19139;
- validation of the generated XML against the official XSD, with an offline copy of the schemas;
- fixes for several problems of the GeoNode 5.0.x catalogue (see [Differences from GeoNode](#differences-from-geonode)).

It was extracted from [OpenGeoSGB](https://github.com/nds-cprm/opengeosgb), the GeoNode instance of the Geological Survey of Brazil.

## Requirements

- GeoNode 5.0.x (tested with the `5.0.x` branch) and the pycsw, OWSLib and lxml versions it installs (`geonode-pycsw` 3.0.0b1, `OWSLib` 0.34.1).
- PostgreSQL/PostGIS, as in any GeoNode install.

GeoNode is not declared as a package dependency on purpose: it is usually installed from git, and declaring it would make pip try to replace that install.

## Installation

```bash
pip install git+https://github.com/nds-cprm/geonode-catalogue-iso19115-3.git@main
```

In a [geonode-project](https://github.com/GeoNode/geonode-project) based project, add that line to `requirements.txt`, after GeoNode.

### Settings

Add to the project settings (for example `local_settings.py`, after `from geonode.settings import *`):

```python
from geonode_catalogue_iso19115_3.constants import ENGINE, ISO19115_3, METADATA_TEMPLATES

INSTALLED_APPS += ("geonode_catalogue_iso19115_3",)

CATALOGUE["default"]["ENGINE"] = os.getenv("CATALOGUE_ENGINE", ENGINE)
CATALOGUE_DEFAULT_FORMAT = os.getenv("CATALOGUE_DEFAULT_FORMAT", ISO19115_3)
CATALOG_METADATA_TEMPLATE = os.getenv("CATALOG_METADATA_TEMPLATE", METADATA_TEMPLATES[CATALOGUE_DEFAULT_FORMAT])

# optional: GetDomain returns every value with its count instead of only min/max
PYCSW["CONFIGURATION"]["server"]["domainquerytype"] = "list"
```

`geonode_catalogue_iso19115_3.constants` has no dependencies, so it can be imported from a settings module.

### URLs

The app has its own `/catalogue/csw` and `/showmetadata/xsl/<id>` views, which must come before GeoNode's. In the project `urls.py`:

```python
from geonode.urls import urlpatterns
from geonode_catalogue_iso19115_3.urls import urlpatterns as catalogue_urlpatterns

urlpatterns[0:0] = catalogue_urlpatterns
```

### Existing resources

Records keep the format they were generated in. After installing the app or changing `CATALOGUE_DEFAULT_FORMAT`, regenerate them:

```bash
python manage.py regenerate_xml
python manage.py validate_metadata_xml
```

## Settings reference

| Setting | Default | Effect |
|---|---|---|
| `CATALOGUE["default"]["ENGINE"]` | GeoNode's `pycsw_local` | Must be `geonode_catalogue_iso19115_3.backends.pycsw_local`. With another value the format and the fixes do not apply to the XML generation, and `manage.py check` warns. |
| `CATALOGUE_DEFAULT_FORMAT` | `ISO19115-3_2018` | Format of the XML written to `metadata_xml` and returned by the catalogue: `ISO19115-3_2018` or `ISO` (ISO 19139). An invalid value stops Django from starting. |
| `CATALOG_METADATA_TEMPLATE` | GeoNode's ISO 19139 template | Template that generates the XML. Use the template of the chosen format (`METADATA_TEMPLATES[...]`) or one that extends it. |
| `CATALOGUE_CSW_DATASET_FILTER` | `None` | Extra filter for the set delivered by the CSW: a dotted path or a callable. See [CSW filters](#csw-filters). |
| `CSW_MIN_METADATA_COMPLETENESS` | `60` | Minimum metadata completeness (%) used by the `published_datasets_with_complete_metadata` filter. |
| `CATALOGUE_XSL_REDIRECT` | `"metadata"` | Route the "ISO with XSL" link redirects to when the format is ISO 19115-3, reversed with `pk`. `None` keeps the GeoNode view. See ["ISO with XSL" link](#iso-with-xsl-link). |
| `CATALOGUE_METADATA_SCHEMAS_DIR` | the package `schemas/` directory | Directory with the XSD files used for validation. |
| `PYCSW["CONFIGURATION"]` | GeoNode's | Merged in depth over GeoNode's `pycsw_local` defaults; the settings win. The `apiso`, `ebrim` and `iso19115p3` profiles are always enabled. |

## How the metadata XML is generated

GeoNode generates the XML and stores it in the `metadata_xml` field of the resource; pycsw reads that field to answer the CSW.

1. When a dataset or document is saved, GeoNode calls `catalogue_post_save`. The same happens in `regenerate_xml`, in `set_all_datasets_metadata` and when GeoServer updates the resource links.
2. The backend of the app writes `csw_typename` and `csw_schema` according to the format: `mdb:MD_Metadata` for ISO 19115-3, `gmd:MD_Metadata` for ISO 19139. The metadata editor saves the resource without that path, so a `pre_save` receiver does the same.
3. The XML is rendered with `CATALOG_METADATA_TEMPLATE` and stored in `metadata_xml`. XML uploaded by a user with the "preserve" option is kept as is, and `csw_typename` follows the format of that XML.
4. GeoNode creates one metadata link per format offered by the catalogue, ISO 19115-3 included.

`csw_typename` must match the stored XML: the pycsw `iso19115p3` profile only returns the stored XML when `csw_typename` is `mdb:MD_Metadata`, and `apiso` only when it is `gmd:MD_Metadata`. Otherwise pycsw builds the record from the database columns.

What the CSW returns, by `outputschema`:

| `outputschema` | Result |
|---|---|
| `http://standards.iso.org/iso/19115/-3/mdb/2.0` | ISO 19115-3: the stored XML, when it is in this format. |
| `http://www.isotc211.org/2005/gmd` | ISO 19139, built by pycsw from the columns when the stored XML is ISO 19115-3. |
| `http://www.opengis.net/cat/csw/2.0.2` and others | Dublin Core, ebRIM, FGDC etc., built by pycsw. |

```
/catalogue/csw?service=CSW&version=2.0.2&request=GetRecordById&id=<uuid>&elementsetname=full&outputschema=http://standards.iso.org/iso/19115/-3/mdb/2.0
/catalogue/csw?service=CSW&version=2.0.2&request=GetDomain&propertyname=dc:title
```

## "ISO with XSL" link

GeoNode (`geonode.catalogue.metadataxsl`) adds to every dataset and document a metadata link named "ISO with XSL", at `/showmetadata/xsl/<id>`. That view generates the XML with `CATALOG_METADATA_TEMPLATE` and adds an `<?xml-stylesheet?>` line pointing to `/static/metadataxsl/metadata.xsl`, which the browser applies. The stylesheet only reads ISO 19139 (`gmd:MD_Metadata`), so with ISO 19115-3 the page comes out empty. Browsers are also removing XSLT support (Chrome from November 2026).

The app replaces that route, keeping its name (`prefix_xsl_line`), so the links GeoNode creates keep the same address:

- with `CATALOGUE_DEFAULT_FORMAT = "ISO19115-3_2018"`, it redirects (302) to the route named by `CATALOGUE_XSL_REDIRECT`, reversed with `pk`. The default, `metadata`, is the metadata page of geonode-mapstore-client (`/metadata/<pk>`);
- with ISO 19139, with `CATALOGUE_XSL_REDIRECT = None`, or when the route does not exist, it calls the GeoNode view.

The metadata page of geonode-mapstore-client 5.0.x does not check the permission to view the resource. The redirect does not expose anything new, because the page can be opened directly, but a project can point `CATALOGUE_XSL_REDIRECT` to a page of its own, or override the `metadata` route.

## CSW filters

For every request, the view builds the pycsw filter from these clauses, always joined with `AND`:

- the record has a UUID;
- the user can view the resource (for anonymous requests, the anonymous user permissions);
- the resource passes `CATALOGUE_CSW_DATASET_FILTER`, when set;
- with `GROUP_PRIVATE_RESOURCES`, the resource does not belong to a private group the user is not a member of (not applied to superusers);
- with `CATALOGUE["default"]["ALTERNATES_ONLY"]`, the resource has an `alternate`.

The filter holds for every operation (`GetRecords`, `GetRecordById`, `GetDomain`) and does not affect the XML generation.

A dataset filter is a callable that receives the queryset of resources the user can view and returns a narrower one. The app ships one, which delivers only approved and published datasets whose metadata completeness is above `CSW_MIN_METADATA_COMPLETENESS`:

```python
CATALOGUE_CSW_DATASET_FILTER = "geonode_catalogue_iso19115_3.filters.published_datasets_with_complete_metadata"
CSW_MIN_METADATA_COMPLETENESS = 60
```

The completeness is computed in SQL, reproducing the `ResourceBase.metadata_completeness` property of GeoNode.

## Templates

The templates live in `templates/geonode_catalogue_iso19115_3/`, with names of their own: a `catalogue/full_metadata.xml` inside the app would lose to GeoNode's because of the app order.

- `full_metadata_iso19115-3.xml`: ISO 19115-3 (`mdb` 2.0), valid against the XSD. `mdb:contact` is mandatory, so a resource without contacts uses its owner as `pointOfContact`.
- `_iso19115-3_responsibility.xml`: one contact (`cit:CI_Responsibility`), used in `mdb:contact` and `mri:pointOfContact`.
- `full_metadata_iso19139.xml`: copy of the GeoNode 5.0.x ISO 19139 template, with the same extension block.

### Extending the templates

Both templates have an empty `{% block spatial_resolution %}`, at the position of `spatialResolution` in the data identification. A project fills it by extending the template. For example, to publish a scale stored in a GeoNode sparse field named `scale` (`{"id": <denominator>, ...}`):

```xml
{% extends "geonode_catalogue_iso19115_3/full_metadata_iso19115-3.xml" %}
{% block spatial_resolution %}{% if metadata.scale.id %}
      <mri:spatialResolution>
        <mri:MD_Resolution>
          <mri:equivalentScale>
            <mri:MD_RepresentativeFraction>
              <mri:denominator>
                <gco:Integer>{{ metadata.scale.id }}</gco:Integer>
              </mri:denominator>
            </mri:MD_RepresentativeFraction>
          </mri:equivalentScale>
        </mri:MD_Resolution>
      </mri:spatialResolution>
{% endif %}{% endblock %}
```

Then point `CATALOG_METADATA_TEMPLATE` to that template, and silence the check that warns about a non-default template with `SILENCED_SYSTEM_CHECKS = ["geonode_catalogue_iso19115_3.W002"]`. The template context has `layer` (the resource), `metadata` (the schema instance built by GeoNode's metadata manager, sparse fields included), `SITEURL` and `LICENSES_METADATA`.

More blocks can be added the same way where projects need them.

## XSD validation

`geonode_catalogue_iso19115_3.validation.validate_xml(xml, fmt)` returns the list of errors of the XML against the official schema of the format (empty when valid). Today only ISO 19115-3 has a schema configured (`mdb/2.0/mdb.xsd`).

The schemas are shipped in `schemas/`: 131 XSD files from isotc211.org, opengis.net (GML) and w3.org, mirrored by `host/path` with `schemaLocation` rewritten as relative paths, so validation does not need the network (the ISO server is slow and sometimes times out). Do not edit these files by hand; refresh them with `fetch_metadata_schemas`.

Validation checks the structure (element order, mandatory elements, types and attributes). It does not check codelist values such as `CI_RoleCode` or `MD_ScopeCode`.

## Management commands

| Command | Purpose |
|---|---|
| `regenerate_xml [-i ID] [-l NAME] [-d]` | GeoNode command. Regenerates the XML and the metadata links; without filters, of every resource. |
| `validate_metadata_xml [--id ID] [--max-errors N]` | Validates the stored `metadata_xml` of the resources and lists the errors of each one. Exits with status 1 when any XML is invalid. Resources in a format without XSD are counted as skipped. |
| `fetch_metadata_schemas [--output DIR] [--cache DIR]` | Downloads the XSD files again. Without `--output`, into `CATALOGUE_METADATA_SCHEMAS_DIR` or the package `schemas/` directory. |

## Differences from GeoNode

Besides the configurable format, the app fixes these problems of the GeoNode 5.0.x catalogue:

| Problem in GeoNode 5.0.x | In the app |
|---|---|
| The pycsw configuration is a shallow copy. The view changes the permission filter in a dictionary shared by the module, so with threaded workers a request can use the filter of another user. | The configuration is built again on every use, deep-merged. |
| The `pycsw_local` defaults win over the settings, `profiles` included, so the `iso19115p3` profile cannot be enabled. | The settings win, and the `apiso`, `ebrim` and `iso19115p3` profiles are always on. |
| For authenticated users the filter becomes `(...) OR (id IN ...)`, so the group and `ALTERNATES_ONLY` filters added afterwards no longer apply to them. | Clauses joined with `AND` only, each in parentheses. |
| The view redirects when `CATALOGUE_ENGINE` is not exactly GeoNode's `pycsw_local`. | The view accepts the backend of the app and GeoNode's. |
| Every `GetDomain` comes back empty: django-polymorphic fails on the repository aggregates (`AttributeError: 'NoneType' object has no attribute 'name'`) and pycsw hides the error. | Own repository, which queries without django-polymorphic. |
| The backend stores the `Catalogue` object on the class, shared by every instance, and `search_records` calls `.items()` on a list. | The `Catalogue` lives on the instance, and the search is fixed. |

## Upgrading GeoNode

Parts of the app are adapted copies of GeoNode code. Compare each one with the original in the new version:

| In the app | In GeoNode |
|---|---|
| `backends/pycsw_local.py` (`get_record`, `search_records`, `_csw_local_dispatch`) | `geonode/catalogue/backends/pycsw_local.py` |
| `backends/pycsw_repository.py` (`query_domain`) | `geonode/catalogue/backends/pycsw_plugin.py` |
| `views.py` (`csw_global_dispatch`) | `geonode/catalogue/views.py` |
| `views.py` (`metadata_xsl`) and `urls.py` | `geonode/catalogue/metadataxsl/` (view `prefix_xsl_line`, route in `geonode/urls.py`) |
| `filters.py` (`with_metadata_completeness`) | `ResourceBase.metadata_completeness` in `geonode/base/models.py` |
| `templates/geonode_catalogue_iso19115_3/full_metadata_iso19139.xml` | `geonode/catalogue/templates/catalogue/full_metadata.xml` |

When GeoNode fixes one of the problems above, the corresponding copy can be removed.

## Tests

The tests ship with the app (`geonode_catalogue_iso19115_3/tests/`) and need a PostGIS database. In a GeoNode project that has the app installed, they run with the project settings:

```bash
python manage.py test geonode_catalogue_iso19115_3
```

Every test sets what it depends on (format, template, engine, CSW filter), so the project configuration does not change the result. This also checks that the app works with the rest of the project installed.

From this repository, use the settings shipped for that:

```bash
pip install -e .
DJANGO_SETTINGS_MODULE=geonode_catalogue_iso19115_3.tests.settings \
DATABASE_URL=postgis://user:password@localhost:5432/geonode \
GEODATABASE_URL=postgis://user:password@localhost:5432/geonode_data \
python -m django test geonode_catalogue_iso19115_3
```

They cover the XML generation in both formats, the format switch through the metadata editor, the CSW responses, `GetDomain`, the CSW filters, the pycsw configuration, the template extension block and XSD validation.

`tests/fixtures.py` (`create_fictitious_dataset()`) creates a complete fictitious dataset through `resource_manager.create`, as in the real flow, with every field the templates use; only the GeoServer synchronization is mocked. To cover a new template field, add it to that dataset.

## Layout

```
geonode_catalogue_iso19115_3/
├── apps.py                  # app config, pre_save receiver and system checks
├── constants.py             # format names, templates, engine (importable from settings)
├── formats.py               # format table and the csw_typename/csw_schema rule
├── config.py                # pycsw configuration, built on every use
├── backends/
│   ├── pycsw_local.py       # catalogue backend (CATALOGUE ENGINE)
│   └── pycsw_repository.py  # pycsw repository with the fixed GetDomain
├── views.py, urls.py        # /catalogue/csw
├── filters.py               # CSW dataset filters
├── signals.py               # csw_typename/csw_schema on save
├── validation.py            # XSD validation
├── schemas/                 # offline copy of the XSD files
├── management/commands/     # fetch_metadata_schemas, validate_metadata_xml
├── templates/geonode_catalogue_iso19115_3/
└── tests/
    ├── test_catalogue.py
    ├── fixtures.py          # complete fictitious dataset
    ├── settings.py          # only to run the tests from this repository
    └── templates/           # templates of the extension tests
```

## License

GPL-3.0-or-later, like GeoNode. The XSD files in `schemas/` are published by ISO/TC 211, the OGC and the W3C under their own terms.
