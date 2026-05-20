import unittest
from shapely.geometry import Point, Polygon

from odeon.model import (
    Building,
    CardinalOrientation,
    FootprintNominalBuildingGeometry,
    NominalGeometry,
    Projector,
    Roof,
    RoofType,
    Wall,
)
from odeon.processing.building_geometry import footprint_nominal_to_roofed_cuboid


def fixture_single_building_geometry():
    footprint_wgs84 = Polygon(
        [
            [7.2735922, 51.4462248],
            [7.2734215, 51.4461268],
            [7.2733817, 51.4461533],
            [7.2733426, 51.44614],
            [7.2732929, 51.4461231],
            [7.273162, 51.4460586],
            [7.2732947, 51.445927],
            [7.2735008, 51.445997],
            [7.2737249, 51.4461731],
            [7.2736368, 51.4461738],
            [7.2736282, 51.4461837],
            [7.2735922, 51.4461248],
        ]
    )
    projector = Projector(origin=Point(51.4462248, 7.2735922))
    footprint_local = projector.from_wgs84(footprint_wgs84, order="lon_lat")
    footprint_geometry = NominalGeometry(shape=footprint_local)
    return projector, footprint_geometry


class TestBuildingGeometry(unittest.TestCase):

    @unittest.skip("requires Vista for plotting")
    def test1(self):        
        from vista.incide_ancient import Incide
        projector, footprint_geometry = fixture_single_building_geometry()
        b = Building()
        fnbg = FootprintNominalBuildingGeometry(
            footprint=footprint_geometry,
            roof_type=RoofType.GABLE,
            eaves_height=10,
            roof_height=10,
            overhang_length=0.5,
            overhang_width=0.8,
            altitude=44,
            ridge_orientation_cardinal=CardinalOrientation.EAST,
            window_wall_factor=(0.2, 0.4),
            window_roof_factor={CardinalOrientation.EAST: 0.2, CardinalOrientation.WEST: 0.5},
            door_factor={CardinalOrientation.NORTH: 0.2},
        )
        b.building_geometry_nominal = fnbg
        footprint_nominal_to_roofed_cuboid(b)
        assert len(b.building_elements) == 14  # Floor, 4 xWall, 2x Roof, Door, 6x Windows == Subelements
        assert [
            len(be.sub_elements) == 1 for be in b.building_elements if isinstance(be, (Wall, Roof))
        ]  # 1 Window for every Wall and Roof
        Incide.plot_buildings_3d_pyvista(b, normals=True)
        Incide.plot_polygons_on_map(
            geoms=[footprint_geometry, *b.building_geometry_cuboid.geometries], projector=projector
        )


if __name__ == "__main__":
    TestBuildingGeometry().test1()
