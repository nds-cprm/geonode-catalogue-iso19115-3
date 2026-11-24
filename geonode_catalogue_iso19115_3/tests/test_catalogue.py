import copy
import os
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.utils import translation
from lxml import etree

from geonode.base.models import ResourceBase
from geonode.catalogue import get_catalogue
from geonode.catalogue.models import catalogue_post_save, update_csw_metadata
from geonode.layers.models import Dataset

from geonode_catalogue_iso19115_3 import views
from geonode_catalogue_iso19115_3.config import build_pycsw_config
from geonode_catalogue_iso19115_3.constants import ENGINE, ISO19115_3, ISO19139, METADATA_TEMPLATES
from geonode_catalogue_iso19115_3.formats import METADATA_FORMATS, format_of_xml
from geonode_catalogue_iso19115_3.validation import validate_xml

from geonode_catalogue_iso19115_3.tests.fixtures import FICTITIOUS, create_fictitious_dataset

CATALOGUE_SETTINGS = {"default": {**settings.CATALOGUE["default"], "ENGINE": ENGINE}}
COMPLETE_FILTER = "geonode_catalogue_iso19115_3.filters.published_datasets_with_complete_metadata"

MDB = METADATA_FORMATS[ISO19115_3][1]
GMD = METADATA_FORMATS[ISO19139][1]

NS = {
    "mdb": MDB,
    "mri": "http://standards.iso.org/iso/19115/-3/mri/1.0",
    "mrd": "http://standards.iso.org/iso/19115/-3/mrd/1.0",
    "mrl": "http://standards.iso.org/iso/19115/-3/mrl/2.0",
    "mcc": "http://standards.iso.org/iso/19115/-3/mcc/1.0",
    "cit": "http://standards.iso.org/iso/19115/-3/cit/2.0",
    "gex": "http://standards.iso.org/iso/19115/-3/gex/1.0",
    "gco": "http://standards.iso.org/iso/19115/-3/gco/1.0",
}


TEST_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")


def format_settings(fmt, template=None):
    """
    Everything the tests depend on, so they also run with the settings of any
    GeoNode project that has the app installed (``manage.py test geonode_catalogue_iso19115_3``).
    """
    return override_settings(
        CATALOGUE=CATALOGUE_SETTINGS,
        CATALOGUE_DEFAULT_FORMAT=fmt,
        CATALOG_METADATA_TEMPLATE=template or METADATA_TEMPLATES[fmt],
        CATALOGUE_CSW_DATASET_FILTER=None,
    )


def extension_templates_settings():
    """TEMPLATES with the templates of the extension tests in DIRS."""
    templates = copy.deepcopy(settings.TEMPLATES)
    templates[0]["DIRS"] = [TEST_TEMPLATES_DIR, *templates[0].get("DIRS", [])]
    return override_settings(TEMPLATES=templates)


def texts(root, path):
    return [(e.text or "").strip() for e in root.xpath(path, namespaces=NS)]


def stored(dataset):
    return ResourceBase.objects.values("csw_typename", "csw_schema", "metadata_xml").get(pk=dataset.pk)


def stored_root(dataset):
    return etree.fromstring(stored(dataset)["metadata_xml"].encode("utf-8"))


def csw(user, **params):
    request = RequestFactory().get("/catalogue/csw", {"service": "CSW", "version": "2.0.2", **params})
    request.user = user
    return views.csw_global_dispatch(request)


class CatalogueTestBase(TestCase):
    """Common user and helpers; no tests of its own."""

    def setUp(self):
        self.owner = get_user_model().objects.filter(is_superuser=True).first() or get_user_model().objects.create(
            username="catalogue_admin", is_superuser=True
        )

    def minimal_dataset(self, name):
        return Dataset.objects.create(
            owner=self.owner,
            name=name,
            title=f"Title {name}",
            abstract="Abstract",
            subtype="vector",
            alternate=f"geonode:{name}",
            workspace="geonode",
            bbox_polygon="SRID=4326;POLYGON((-50 -20,-50 -10,-40 -10,-40 -20,-50 -20))",
            srid="EPSG:4326",
        )


class PycswConfigTest(TestCase):
    def test_config_is_fresh_on_each_call(self):
        first = build_pycsw_config()
        first["repository"]["filter"] += " AND id = 1"
        self.assertEqual(build_pycsw_config()["repository"]["filter"], "uuid IS NOT NULL")

    def test_settings_win_and_profiles(self):
        config = build_pycsw_config()
        self.assertEqual(config["server"]["maxrecords"], settings.PYCSW["CONFIGURATION"]["server"]["maxrecords"])
        self.assertIn("home", config["server"])  # core default kept
        self.assertTrue({"apiso", "ebrim", "iso19115p3"} <= config["profiles"])
        self.assertEqual(
            config["repository"]["source"], "geonode_catalogue_iso19115_3.backends.pycsw_repository.GeoNodeRepository"
        )


class FormatTest(CatalogueTestBase):
    def test_iso19115_3(self):
        with format_settings(ISO19115_3):
            dataset = self.minimal_dataset("ds_mdb")
            catalogue_post_save(instance=dataset, sender=Dataset)
            values = stored(dataset)
            self.assertEqual(values["csw_typename"], "mdb:MD_Metadata")
            self.assertEqual(values["csw_schema"], MDB)
            self.assertEqual(format_of_xml(values["metadata_xml"]), ISO19115_3)

            record = get_catalogue().get_record(dataset.uuid)
            self.assertEqual(record.identification[0].title, dataset.title)
            self.assertIn(ISO19115_3, [name for _mime, name, _url in record.links["metadata"]])

            # the stored XML is returned as is by the iso19115p3 profile...
            root = etree.fromstring(
                csw(
                    self.owner, request="GetRecordById", id=dataset.uuid, outputschema=MDB, elementsetname="full"
                ).content
            )
            self.assertIsNotNone(root.find(f"{{{MDB}}}MD_Metadata"))
            # ...and apiso still delivers ISO 19139, built from the columns
            root = etree.fromstring(
                csw(
                    self.owner, request="GetRecordById", id=dataset.uuid, outputschema=GMD, elementsetname="full"
                ).content
            )
            self.assertIsNotNone(root.find(f"{{{GMD}}}MD_Metadata"))

    def test_iso19139_and_format_switch(self):
        with format_settings(ISO19139):
            dataset = self.minimal_dataset("ds_gmd")
            catalogue_post_save(instance=dataset, sender=Dataset)
            self.assertEqual(stored(dataset)["csw_typename"], "gmd:MD_Metadata")
            self.assertEqual(format_of_xml(stored(dataset)["metadata_xml"]), ISO19139)
            self.assertIsNotNone(get_catalogue().get_record(dataset.uuid))

        # metadata editor path: save() + update_csw_metadata(), without catalogue_post_save
        with format_settings(ISO19115_3):
            resource = ResourceBase.objects.get(pk=dataset.pk)
            resource.save()
            update_csw_metadata(resource)
            self.assertEqual(stored(dataset)["csw_typename"], "mdb:MD_Metadata")
            self.assertEqual(format_of_xml(stored(dataset)["metadata_xml"]), ISO19115_3)

    def test_minimal_iso19115_3_is_valid(self):
        """A resource without contacts still gets the mandatory mdb:contact (its owner)."""
        with format_settings(ISO19115_3):
            dataset = self.minimal_dataset("ds_xsd_min")
            catalogue_post_save(instance=dataset, sender=Dataset)
        errors = validate_xml(stored(dataset)["metadata_xml"], ISO19115_3)
        self.assertEqual(errors, [], "\n".join(errors))


class TemplateExtensionTest(CatalogueTestBase):
    """Projects extend the templates and fill the spatial_resolution block."""

    def test_spatial_resolution_block(self):
        cases = (
            (ISO19115_3, "geonode_catalogue_iso19115_3_tests/full_metadata_iso19115-3_with_scale.xml"),
            (ISO19139, "geonode_catalogue_iso19115_3_tests/full_metadata_iso19139_with_scale.xml"),
        )
        for fmt, template in cases:
            with self.subTest(fmt=fmt), extension_templates_settings(), format_settings(fmt, template):
                dataset = self.minimal_dataset(f"ds_scale_{fmt.lower().replace('-', '_')}")
                catalogue_post_save(instance=dataset, sender=Dataset)
                xml = stored(dataset)["metadata_xml"]
                self.assertIn("250000", xml)
                if fmt == ISO19115_3:
                    errors = validate_xml(xml, ISO19115_3)
                    self.assertEqual(errors, [], "\n".join(errors))

    def test_block_is_empty_by_default(self):
        with format_settings(ISO19115_3):
            dataset = self.minimal_dataset("ds_no_scale")
            catalogue_post_save(instance=dataset, sender=Dataset)
        self.assertNotIn("spatialResolution", stored(dataset)["metadata_xml"])


class FictitiousDatasetTest(TestCase):
    """A complete fictitious dataset, from creation to the CSW."""

    def test_created_through_resource_manager(self):
        with format_settings(ISO19115_3):
            dataset = create_fictitious_dataset()
        resource = ResourceBase.objects.get(pk=dataset.pk)
        self.assertEqual(resource.csw_typename, "mdb:MD_Metadata")
        self.assertEqual(format_of_xml(resource.metadata_xml), ISO19115_3)
        # set_missing_info creates the mandatory contacts from the owner
        self.assertTrue(dataset.contactrole_set.exists())
        self.assertTrue(resource.link_set.filter(link_type="metadata", name=ISO19115_3).exists())

    def test_iso19115_3_content(self):
        # thesaurus labels are written in the active language of whoever saves the resource
        with format_settings(ISO19115_3), translation.override("en"):
            dataset = create_fictitious_dataset()
        root = stored_root(dataset)
        ident = "mdb:identificationInfo/mri:MD_DataIdentification"

        title = texts(root, f"{ident}/mri:citation/cit:CI_Citation/cit:title/gco:CharacterString")
        self.assertEqual(title, [dataset.title])
        self.assertIn(FICTITIOUS["abstract"], texts(root, f"{ident}/mri:abstract/gco:CharacterString"))
        self.assertEqual(texts(root, f"{ident}/mri:purpose/gco:CharacterString"), [FICTITIOUS["purpose"]])

        keywords = texts(root, f"{ident}/mri:descriptiveKeywords/mri:MD_Keywords/mri:keyword/gco:CharacterString")
        for expected in FICTITIOUS["keywords"] + [FICTITIOUS["region"], FICTITIOUS["thesaurus_label"]]:
            self.assertIn(expected, keywords)

        bbox = root.xpath(f"{ident}/mri:extent//gex:EX_GeographicBoundingBox", namespaces=NS)[0]
        x0, y0, x1, y1 = FICTITIOUS["bbox"]
        for tag, value in (
            ("westBoundLongitude", x0),
            ("eastBoundLongitude", x1),
            ("southBoundLatitude", y0),
            ("northBoundLatitude", y1),
        ):
            self.assertAlmostEqual(float(texts(bbox, f"gex:{tag}/gco:Decimal")[0]), value)

        self.assertIn(FICTITIOUS["doi"], etree.tostring(root, encoding="unicode"))
        constraints = texts(root, f"{ident}/mri:resourceConstraints//gco:CharacterString")
        self.assertIn(FICTITIOUS["constraints_other"], constraints)
        self.assertEqual(
            texts(root, "mdb:resourceLineage/mrl:LI_Lineage/mrl:statement/gco:CharacterString"),
            [FICTITIOUS["data_quality_statement"]],
        )
        emails = texts(root, "mdb:contact//cit:electronicMailAddress/gco:CharacterString")
        self.assertIn("maria.example@example.org", emails)

        urls = texts(root, "mdb:distributionInfo//mrd:onLine/cit:CI_OnlineResource/cit:linkage/gco:CharacterString")
        self.assertTrue(any("SHAPE-ZIP" in u for u in urls), urls)
        self.assertTrue(any("service=WMS" in u for u in urls), urls)

    def test_iso19115_3_is_valid_for_all_variants(self):
        variants = [
            ("vector, light license", "vector", {"ENABLED": True, "METADATA": "light"}),
            ("vector, verbose license", "vector", {"ENABLED": True, "METADATA": "verbose"}),
            ("raster, no license in the XML", "raster", {"ENABLED": True, "METADATA": "never"}),
        ]
        for i, (label, subtype, licenses) in enumerate(variants):
            with self.subTest(label), format_settings(ISO19115_3), override_settings(LICENSES=licenses):
                dataset = create_fictitious_dataset(name=f"example_{i}", subtype=subtype)
                errors = validate_xml(stored(dataset)["metadata_xml"], ISO19115_3)
                self.assertEqual(errors, [], "\n".join(errors))

    def test_iso19139_content(self):
        from owslib.iso import MD_Metadata

        with format_settings(ISO19139):
            dataset = create_fictitious_dataset()
        record = MD_Metadata(stored_root(dataset))
        self.assertEqual(record.identification[0].title, dataset.title)
        self.assertIn("geology", [k.name for kw in record.identification[0].keywords for k in kw.keywords])


class CswFilterTest(TestCase):
    GET_RECORDS = dict(
        request="GetRecords",
        typenames="mdb:MD_Metadata",
        resulttype="results",
        elementsetname="full",
        outputschema=MDB,
        maxrecords="50",
    )

    def _ids(self, response):
        self.assertEqual(response.status_code, 200)
        root = etree.fromstring(response.content)
        return texts(root, "//mdb:MD_Metadata/mdb:metadataIdentifier/mcc:MD_Identifier/mcc:code/gco:CharacterString")

    def test_no_extra_filter_by_default(self):
        with format_settings(ISO19115_3):
            published = create_fictitious_dataset()
            draft = create_fictitious_dataset(name="draft_example", approved=False)
            ids = self._ids(csw(published.owner, **self.GET_RECORDS))
        self.assertIn(published.uuid, ids)
        self.assertIn(draft.uuid, ids)

    def test_published_datasets_with_complete_metadata(self):
        with format_settings(ISO19115_3), override_settings(CATALOGUE_CSW_DATASET_FILTER=COMPLETE_FILTER):
            published = create_fictitious_dataset()
            draft = create_fictitious_dataset(name="draft_example", approved=False)
            ids = self._ids(csw(published.owner, **self.GET_RECORDS))
        self.assertIn(published.uuid, ids)
        self.assertNotIn(draft.uuid, ids)

    def test_clauses_are_anded(self):
        request = RequestFactory().get("/catalogue/csw")
        request.user = get_user_model().objects.create(username="csw_user")
        with override_settings(GROUP_PRIVATE_RESOURCES=True):
            where = views._repository_filter(request, "uuid IS NOT NULL", None)
        self.assertNotIn(" OR (id", where)
        self.assertTrue(where.startswith("(uuid IS NOT NULL) AND (id"))
        self.assertIn("group_id", where)


class GetDomainTest(CatalogueTestBase):
    def test_get_domain_lists_values_with_counts(self):
        with format_settings(ISO19115_3), override_settings(
            PYCSW={**settings.PYCSW, "CONFIGURATION": {
                **settings.PYCSW["CONFIGURATION"],
                "server": {**settings.PYCSW["CONFIGURATION"]["server"], "domainquerytype": "list"},
            }}
        ):
            for name in ("ds_dom_a", "ds_dom_b"):
                catalogue_post_save(instance=self.minimal_dataset(name), sender=Dataset)
            response = csw(self.owner, request="GetDomain", propertyname="dc:title")
        root = etree.fromstring(response.content)
        values = [v.text for v in root.iter("{http://www.opengis.net/cat/csw/2.0.2}Value")]
        self.assertIn("Title ds_dom_a (1)", values)
        self.assertIn("Title ds_dom_b (1)", values)

    def test_repository_query_domain(self):
        from geonode_catalogue_iso19115_3.backends.pycsw_repository import GeoNodeRepository

        for name in ("ds_rng_a", "ds_rng_b"):
            self.minimal_dataset(name)
        repo = GeoNodeRepository.__new__(GeoNodeRepository)
        repo.filter = "title IN ('Title ds_rng_a', 'Title ds_rng_b')"

        self.assertEqual(repo.query_domain("title", None, "range"), [("Title ds_rng_a", "Title ds_rng_b")])
        self.assertEqual(
            repo.query_domain("title", None, "list", count=True), [("Title ds_rng_a", 1), ("Title ds_rng_b", 1)]
        )
        self.assertEqual(repo.query_domain("title", None, "list"), [("Title ds_rng_a",), ("Title ds_rng_b",)])


class MetadataXslTest(TestCase):
    """``/showmetadata/xsl/<id>``: redirect with ISO 19115-3, GeoNode view otherwise."""

    def get(self, **settings_kwargs):
        request = RequestFactory().get("/showmetadata/xsl/7")
        request.user = get_user_model().objects.filter(is_superuser=True).first()
        with mock.patch("geonode.catalogue.metadataxsl.views.prefix_xsl_line", return_value="core") as core:
            with override_settings(**settings_kwargs):
                return views.metadata_xsl(request, "7"), core

    def test_redirects_to_metadata_page_with_iso19115_3(self):
        response, core = self.get(CATALOGUE_DEFAULT_FORMAT=ISO19115_3)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/metadata/7")
        core.assert_not_called()

    def test_configured_route(self):
        response, _core = self.get(CATALOGUE_DEFAULT_FORMAT=ISO19115_3, CATALOGUE_XSL_REDIRECT="metadata_embed")
        self.assertEqual(response["Location"], "/metadata/7/embed")

    def test_falls_back_to_geonode_view(self):
        cases = {
            "ISO 19139": {"CATALOGUE_DEFAULT_FORMAT": ISO19139},
            "redirect disabled": {"CATALOGUE_DEFAULT_FORMAT": ISO19115_3, "CATALOGUE_XSL_REDIRECT": None},
            "missing route": {"CATALOGUE_DEFAULT_FORMAT": ISO19115_3, "CATALOGUE_XSL_REDIRECT": "no_such_route"},
        }
        for label, settings_kwargs in cases.items():
            with self.subTest(label):
                response, core = self.get(**settings_kwargs)
                self.assertEqual(response, "core")
                core.assert_called_once()
