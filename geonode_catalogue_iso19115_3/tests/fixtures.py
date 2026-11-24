"""Test data: a complete fictitious dataset."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Polygon

from geonode.base.models import ResourceBase
from geonode.catalogue.models import catalogue_post_save
from geonode.layers.models import Dataset

FICTITIOUS = {
    "title": "Geological Map of the Example Range Sheet",
    "abstract": "Fictitious geological map at 1:250,000, used by the catalogue tests.",
    "purpose": "Exercise the metadata XML generation with every field filled in.",
    "data_quality_statement": "Compiled from fictitious field surveys (2020-2024).",
    "supplemental_information": "Fictitious data: do not use for any real purpose.",
    "constraints_other": "Free use, with attribution.",
    "doi": "10.99999/geonode-catalogue.example",
    "edition": "2nd edition",
    "bbox": (-48.0, -16.0, -47.0, -15.0),  # x0, y0, x1, y1 (EPSG:4326)
    "keywords": ["geology", "lithostratigraphy"],
    "region": "Brazil",
    "thesaurus_label": "Granite",
}


def create_fictitious_dataset(name="geological_map_example", subtype="vector", approved=True):
    """
    Creates, through the real GeoNode flow (``resource_manager.create``), a
    fictitious dataset with every field the metadata templates use. Only the
    synchronization with GeoServer is mocked, because there is no GeoServer in
    the tests.
    """
    from geonode.base.models import (
        License,
        Link,
        Region,
        RestrictionCodeType,
        SpatialRepresentationType,
        Thesaurus,
        ThesaurusKeyword,
        ThesaurusKeywordLabel,
        TopicCategory,
    )
    from geonode.resource.manager import resource_manager

    owner, _ = get_user_model().objects.get_or_create(
        username="example_geologist",
        defaults=dict(
            first_name="Maria",
            last_name="Example",
            email="maria.example@example.org",
            organization="Fictitious Geological Survey",
            position="Geoscience researcher",
            voice="+55 21 0000-0000",
            fax="+55 21 0000-0001",
            delivery="100 Example Avenue",
            city="Rio de Janeiro",
            area="RJ",
            zipcode="22000-000",
            country="BRA",
            is_superuser=True,
        ),
    )
    category, _ = TopicCategory.objects.get_or_create(
        identifier="geoscientificInformation",
        defaults=dict(description="Geoscientific information", gn_description="Geoscientific information"),
    )
    license_, _ = License.objects.get_or_create(
        identifier="cc-by-4.0",
        defaults=dict(
            name="Creative Commons Attribution 4.0",
            abbreviation="CC-BY-4.0",
            url="https://creativecommons.org/licenses/by/4.0/",
            description="Allows use with attribution.",
        ),
    )
    restriction, _ = RestrictionCodeType.objects.get_or_create(
        identifier="otherRestrictions", defaults=dict(description="other restrictions", gn_description="Other")
    )
    representation, _ = SpatialRepresentationType.objects.get_or_create(
        identifier="vector" if subtype == "vector" else "grid",
        defaults=dict(description=subtype, gn_description=subtype),
    )
    region, _ = Region.objects.get_or_create(code="BRA", defaults=dict(name=FICTITIOUS["region"]))
    thesaurus, _ = Thesaurus.objects.get_or_create(
        identifier="example-geoscience",
        defaults=dict(title="Fictitious geoscience thesaurus", date="2024-01-01", description="Fictitious"),
    )
    tkeyword, _ = ThesaurusKeyword.objects.get_or_create(
        thesaurus=thesaurus, alt_label="granite", defaults=dict(about="https://example.org/thesaurus/granite")
    )
    ThesaurusKeywordLabel.objects.get_or_create(
        keyword=tkeyword, lang="en", defaults=dict(label=FICTITIOUS["thesaurus_label"])
    )

    x0, y0, x1, y1 = FICTITIOUS["bbox"]
    polygon = Polygon.from_bbox((x0, y0, x1, y1))
    polygon.srid = 4326
    with mock.patch("geonode.geoserver.manager.sync_instance_with_geoserver", return_value=None):
        dataset = resource_manager.create(
            None,
            resource_type=Dataset,
            defaults=dict(
                owner=owner,
                name=name,
                title=FICTITIOUS["title"] + ("" if subtype == "vector" else " (raster)"),
                abstract=FICTITIOUS["abstract"],
                purpose=FICTITIOUS["purpose"],
                data_quality_statement=FICTITIOUS["data_quality_statement"],
                supplemental_information=FICTITIOUS["supplemental_information"],
                constraints_other=FICTITIOUS["constraints_other"],
                restriction_code_type=restriction,
                doi=FICTITIOUS["doi"],
                edition=FICTITIOUS["edition"],
                language="eng",
                date_type="publication",
                maintenance_frequency="asNeeded",
                category=category,
                license=license_,
                spatial_representation_type=representation,
                subtype=subtype,
                workspace="geonode",
                alternate=f"geonode:{name}",
                srid="EPSG:4326",
                bbox_polygon=polygon,
                ll_bbox_polygon=polygon,
                is_approved=approved,
                is_published=approved,
            ),
        )

    # with RESOURCE_PUBLISHING or ADMIN_MODERATE_UPLOADS, the resource manager resets
    # is_approved/is_published on creation; the test needs the requested state
    ResourceBase.objects.filter(pk=dataset.pk).update(is_approved=approved, is_published=approved)

    dataset.keywords.add(*FICTITIOUS["keywords"])
    dataset.tkeywords.add(tkeyword)
    dataset.regions.add(region)
    base = f"https://geoserver.example.org/geoserver/ows?layers=geonode:{name}"
    Link.objects.get_or_create(
        resource=dataset,
        link_type="data",
        extension="zip",
        defaults=dict(name="Zipped Shapefile", mime="SHAPE-ZIP", url=f"{base}&outputFormat=SHAPE-ZIP"),
    )
    Link.objects.get_or_create(
        resource=dataset,
        link_type="OGC:WMS",
        extension="html",
        defaults=dict(name=name, mime="text/html", url=f"{base}&service=WMS"),
    )
    # regenerates the XML with the keywords, regions and links added after creation
    dataset.refresh_from_db()
    catalogue_post_save(instance=dataset, sender=Dataset)
    dataset.refresh_from_db()
    return dataset
