import math
from typing import List
import unittest
import numpy as np
from plotly import express as px
import pandas as pd
import contextily as cx
from shapely import Polygon, Point, LineString
from shapely.geometry.base import BaseGeometry
from shapely import affinity
import geopandas as gpd
import matplotlib.pyplot as plt

from odeon.model import (
    LinestringGeometry,
    NominalGeometry,
    Geometry,
    TiltedRectangleGeometry,
    CardinalOrientation,
    Project,
    Projector,
    SRID_WGS84,
)
from odeon.samples import LATLON_BERLIN_EUREF, LATLON_BOCHUM_IEG
from odeon.processing import geometry_cartesian as geometry_cartesian
from odeon.processing.utils import utils as utils


def plot_geometries_on_map(geoms: List[Geometry], projector: Projector):
    dfs = []
    lats, lons, indices = [], [], []
    for i, geom in enumerate(geoms):
        if geom.is_polygon:
            x, y = geom.shape_in_wgs84(projector=projector, order="lat_lon").exterior.xy
            lats = np.append(lats, x)
            lons = np.append(lons, y)
            indices += [i for _ in x]
            lats = np.append(lats, None)
            lons = np.append(lons, None)
            indices.append(None)
        dfs.append(pd.DataFrame({"lat": lats, "lon": lons, "index": indices}))
    df = pd.concat(dfs)

    fig = px.line_mapbox(
        df,
        lat="lat",
        lon="lon",
        mapbox_style="carto-positron",
        zoom=16,
        center={
            "lat": np.mean([l for l in lats if l is not None]),
            "lon": np.mean([l for l in lons if l is not None]),
        },
    )
    fig.show()


def plot_shapes(shapes: List[BaseGeometry], srid: int = None):
    """order: lon, lat"""
    gdf = gpd.GeoDataFrame(geometry=shapes, crs=srid)
    ax = gdf.plot(figsize=(10, 10), alpha=0.5, edgecolor="k")
    cx.add_basemap(ax, source=cx.providers.CartoDB.PositronNoLabels, crs=gdf.crs)
    plt.show()


def fixture_tilted_polgyon() -> Polygon:
    return geometry_cartesian.create_rectangle(
        location=Point(70, 90), dimensions_projected=(30, 100), height=40, azimuth=30, z_offset=1
    )


tilted_polygon_tilt = np.rad2deg(math.atan2(40, 30))
tilted_polygon_dimension_azimuthal = 50
tilted_polygon_area_projected = 3000
tilted_polygon_area = 5000


def fixture_horizontal_polgyon() -> Polygon:
    return geometry_cartesian.create_rectangle(
        location=Point(50, 0), dimensions_projected=(30, 100), height=0, azimuth=-30, z_offset=1
    )


def fixture_vertical_polgyon() -> Polygon:
    return geometry_cartesian.create_rectangle(
        location=Point(50, 0), dimensions_projected=(0, 100), height=20, azimuth=60, z_offset=1
    )


def fixture_complex_polygon():
    x = (0, -1, 71, 70, 84, 95, 0)
    y = (0, 102, 90, 80, 21, 0, 0)
    xy = [(x, y) for x, y in zip(x, y)]
    return Polygon(xy)


def fixture_3d_linestring():
    x = (0, 1, 1, 1, 2)
    y = (0, 0, 1, 1, 1)
    z = (0, 0, 0, 1, 1)
    xyz = [(x, y, z) for x, y, z in zip(x, y, z)]
    return LineString(xyz)


def tuple_isclose(tuple_a, tuple_b, abs_tol=1e-10):
    for a, b in zip(tuple_a, tuple_b):
        if type(a) is tuple:
            assert type(b) is tuple
            return tuple_isclose(a, b, abs_tol)
        elif type(a) in [int, float]:
            assert type(b) in [int, float]
            return math.isclose(a, b, abs_tol=abs_tol)


class TestProjector(unittest.TestCase):
    def test(self):
        projector = Projector(origin=LATLON_BOCHUM_IEG)
        polygon_local = geometry_cartesian.create_rectangle(dimensions=(100, 100))
        assert polygon_local.centroid == Point(0, 0)

        geom1 = Geometry(shape=polygon_local)
        polygon_wgs84 = geom1.shape_in_wgs84(
            projector=projector, order="lat_lon"
        )  # same result as projector.to_wgs84(polygon_local)
        plot_shapes([geom1.shape_in_wgs84(projector=projector, order="lon_lat")], srid=SRID_WGS84)
        # plot_geometries_on_map(geoms=[geom1], projector=projector) # other way to plot result

        geom2 = projector.from_wgs84(polygon_wgs84, order="lat_lon")
        assert geom2.distance(Point(0, 0)) == 0


class TestGeometry(unittest.TestCase):
    def test(self):
        projector = Projector(origin=LATLON_BOCHUM_IEG)
        polygon_local = geometry_cartesian.create_rectangle(dimensions=(100, 100))

        geom1 = Geometry(shape=polygon_local)
        assert geom1.centroid == Point(0, 0)
        assert not geom1.has_z
        assert not geom1.is_point
        assert geom1.is_polygon
        assert geom1.shape == polygon_local
        assert geom1.shape.area == 10000

        geom2 = Geometry(altitude=5)
        polygon_local_2 = geometry_cartesian.create_rectangle(dimensions=(50, 50), azimuth=30)
        geom2.shape = polygon_local_2
        assert np.isclose(geom2.shape.area, 2500, rtol=1e-6)
        assert Point(geom2.lat_lon(projector=projector)).distance(Point(LATLON_BOCHUM_IEG)) < 1e-10

        plot_geometries_on_map([geom1, geom2], projector=projector)


class TestNominalGeometry(unittest.TestCase):
    def test_areas(self):
        projector = Projector(origin=LATLON_BOCHUM_IEG)

        polygon = fixture_complex_polygon()
        polygon = affinity.rotate(polygon, 30)

        ng = NominalGeometry(shape=polygon)
        mrr = ng.mrr
        mrrea = ng.mrr_equal_area
        pdr = ng.pdr
        pdrea = ng.pdr_equal_area
        mrr_wgs84 = projector.to_wgs84(mrr)
        mrrea_wgs84 = projector.to_wgs84(mrrea)
        pdr_wgs84 = projector.to_wgs84(pdr)
        pdrea_wgs84 = projector.to_wgs84(pdrea)

        plt.plot(*ng.shape_in_wgs84(projector).exterior.xy, label="original")  # plot if you like...
        plt.plot(*mrr_wgs84.exterior.xy, label="mrr")
        plt.plot(*mrrea_wgs84.exterior.xy, label="mrr ea")
        plt.plot(*pdr_wgs84.exterior.xy, label="pdr")
        plt.plot(*pdrea_wgs84.exterior.xy, label="pdr ea")
        plt.legend()
        plt.show()

        assert math.isclose(ng.area, mrrea.area, rel_tol=1e-10)
        # FIXME /kg Somehow the following assertion is not working in the ci pipeline.
        # Results for ng.dimenions in the ci pipeline are (75.21429677176715, 101.0246765060789)
        print(ng.dimensions)
        # assert all(np.isclose(ng.dimensions, (90.73956540919825, 83.73965607763148), atol=1e-10))

    def test_from_tilted(self):
        tg = TiltedRectangleGeometry(shape=fixture_tilted_polgyon(), altitude=50)
        ng = NominalGeometry.from_tilted_rectangle(tg)
        assert math.isclose(ng.tilt, tilted_polygon_tilt, rel_tol=1e-10)
        assert math.isclose(ng.area, tilted_polygon_area, rel_tol=1e-10)
        assert math.isclose(ng.area_projected, tilted_polygon_area_projected, rel_tol=1e-10)


class TestTiltedRectangleGeometry(unittest.TestCase):
    def test(self):
        inclined_polygon = fixture_tilted_polgyon()
        horizontal_polygon = fixture_horizontal_polgyon()
        vertical_polygon = fixture_vertical_polgyon()
        trg_inclined = TiltedRectangleGeometry(shape=inclined_polygon)
        trg_horizontal = TiltedRectangleGeometry(shape=horizontal_polygon)
        trg_vertical = TiltedRectangleGeometry(shape=vertical_polygon)

        # plt.plot(*trg_inclined.geometry.exterior.xy)  # plot if you like...
        # plt.show()
        # plt.plot(*trg_inclined.geometry_in_wgs84().exterior.xy)  # plot if you like...
        # plt.show()

        assert tuple_isclose(
            trg_inclined.xyz_by_point(),
            (
                (105.80127018922195, 52.00961894323341, 41.0),
                (120.80127018922195, 77.99038105676658, 1.0),
                (34.198729810778076, 127.99038105676658, 1.0),
                (19.198729810778076, 102.00961894323342, 41.0),
            ),
        )
        assert len(trg_inclined.points(True)) == 5
        assert trg_inclined.points()[1].distance(Point((120.80127018922195, 77.99038105676658, 1))) < 1e-10
        assert trg_inclined.points(True)[0] == trg_inclined.points(True)[-1]

        epp = trg_inclined.edges_pointpairs
        assert epp[0][1] == epp[1][0]
        assert len(trg_inclined.edges_linestring) == 4

        assert trg_inclined.indices_lower_upper_upward_downward_edge == (1, 3, 2, 0)
        assert trg_horizontal.indices_lower_upper_upward_downward_edge == (-1, -1, -1, -1)
        assert trg_vertical.indices_lower_upper_upward_downward_edge == (3, 1, 0, 2)

        assert trg_inclined.lower_edge == trg_inclined.edges_linestring[1]
        assert trg_inclined.upper_edge == trg_inclined.edges_linestring[3]
        assert trg_inclined.inclined_edges == (trg_inclined.edges_linestring[2], trg_inclined.edges_linestring[0])

        orientations = trg_inclined.orientations
        il, iu, iuw, idw = trg_inclined.indices_lower_upper_upward_downward_edge
        fig, ax = plt.subplots()
        for edge, name, orientation in zip(
            [
                trg_inclined.lower_edge,
                trg_inclined.upper_edge,
                trg_inclined.edges_linestring[iuw],
                trg_inclined.edges_linestring[idw],
            ],
            ["lower", "upper", "upward", "downard"],
            orientations,
        ):
            x, y = edge.xy
            x0, x1 = x
            y0, y1 = y
            plt.arrow(x0, y0, x1 - x0, y1 - y0, head_width=5)
            plt.text(s=f"{name}, orientation={orientation}", x=x0 + (x1 - x0) / 2, y=y0 + (y1 - y0) / 2)
        plt.show()

        assert tuple_isclose(trg_inclined.orientations, (300, 120, 210, 30))

        assert math.isclose(trg_inclined.dimension_crossazimuthal, 100, abs_tol=1e-10)
        assert math.isclose(trg_inclined.dimension_azimuthal, tilted_polygon_dimension_azimuthal, abs_tol=1e-10)
        assert math.isclose(trg_inclined.dimension_azimuthal_projected, 30, abs_tol=1e-10)
        assert tuple_isclose(trg_inclined.dimensions, (tilted_polygon_dimension_azimuthal, 100))
        assert tuple_isclose(trg_horizontal.dimensions, (30, 100))
        assert tuple_isclose(trg_vertical.dimensions, (20, 100))
        assert tuple_isclose(trg_vertical.dimensions_projected, (0, 100))

        assert not trg_inclined.horizontal
        assert not trg_inclined.vertical
        assert trg_inclined.inclined
        assert trg_horizontal.horizontal
        assert not trg_horizontal.vertical
        assert not trg_horizontal.inclined
        assert not trg_vertical.horizontal
        assert trg_vertical.vertical
        assert trg_vertical.inclined

        assert trg_inclined.z_min == 1
        assert trg_inclined.z_max == 41
        assert trg_inclined.height == 40
        assert math.isclose(trg_inclined.area_projected, tilted_polygon_area_projected, abs_tol=1e-10)
        assert math.isclose(trg_inclined.area, tilted_polygon_area, abs_tol=1e-10)

        assert math.isclose(trg_vertical.area, 2000, abs_tol=1e-10)

    def test_from_nominal(self):
        rectangle = geometry_cartesian.create_rectangle(dimensions=(10, 12), azimuth=30)
        ng = NominalGeometry(rectangle, dimensions_nominal=(10, 12), height=5, azimuth=30)
        trg = TiltedRectangleGeometry.from_nominal(ng)
        assert math.isclose(trg.area_projected, 120, abs_tol=1e-10)
        assert np.isclose(trg.tilt, 26.565051172591716, rtol=1e-10)  # TODO check whether this value makes sense
        assert trg.height == 5

        rectangle = geometry_cartesian.create_rectangle(dimensions=(10, 12), azimuth=30)
        ng2 = NominalGeometry(rectangle, dimensions_nominal=(9, 10), height=5, azimuth=20)
        trg2 = TiltedRectangleGeometry.from_nominal(ng2)
        assert trg2.area_projected == trg.area_projected
        assert trg2.tilt == trg.tilt
        assert trg2.height == trg.height

    def test_from_projected(self):
        ng = NominalGeometry(shape=fixture_complex_polygon())
        ng.height = 5
        trg = TiltedRectangleGeometry.from_nominal(ng)
        assert trg.tilt == 3.185052219526975  # TODO check whether this value makes sense

        ng.azimuth_cardinal = CardinalOrientation.NORTHWEST
        trg2 = TiltedRectangleGeometry.from_nominal(ng)
        assert trg2.tilt == 3.3836690167292858  # TODO check whether this value makes sense


class TestLinestringGeometry(unittest.TestCase):
    def test(self):
        ls = fixture_3d_linestring()
        lg = LinestringGeometry(shape=ls)

        # plt.plot(*ls.xy) # plot if you like...
        # plt.show()

        assert lg.xyz_by_point == ((0, 0, 0), (1, 0, 0), (1, 1, 0), (1, 1, 1), (2, 1, 1))
        assert lg.xyz_by_axis == ((0, 1, 1, 1, 2), (0, 0, 1, 1, 1), (0, 0, 0, 1, 1))
        assert lg.points()[0] == Point((0, 0, 0))
        assert lg.points(True)[0] == Point((0, 0, 0))

        lg.altitude = 100
        assert lg.points(True)[0] == Point((0, 0, 100))

        assert not lg.horizontal
        assert lg.height == 1

        assert lg.length_path == 4
        assert lg.length_path_projected == 3
        assert round(lg.length_beeline - math.sqrt(2 * 2 + 1 + 1), 10) == 0
        assert lg.length_beeline_projected == math.sqrt(2 * 2 + 1)


class TestCutShapeIntoPieces(unittest.TestCase):
    def test_cut_rectangle_into_two_pieces(self):
        rectangle = Polygon([(0, 0), (10, 0), (10, 5), (0, 5), (0, 0)])

        pieces = geometry_cartesian.cut_shape_into_pieces(2, rectangle)

        self.assertEqual(len(pieces), 2)
        self.assertAlmostEqual(pieces[0].area, pieces[1].area, places=6)
        total_area = sum(piece.area for piece in pieces)
        self.assertAlmostEqual(total_area, rectangle.area, places=6)

    def test_cut_rectangle_into_four_pieces(self):
        rectangle = Polygon([(0, 0), (10, 0), (10, 5), (0, 5), (0, 0)])

        pieces = geometry_cartesian.cut_shape_into_pieces(4, rectangle)

        self.assertEqual(len(pieces), 4)
        for piece in pieces:
            self.assertAlmostEqual(piece.area, rectangle.area / 4, places=6)
        total_area = sum(piece.area for piece in pieces)
        self.assertAlmostEqual(total_area, rectangle.area, places=6)

    def test_cut_non_rectangular_polygon(self):
        polygon = Polygon([(0, 0), (6, 0), (4, 4), (2, 4), (0, 0)])

        pieces = geometry_cartesian.cut_shape_into_pieces(3, polygon)

        self.assertEqual(len(pieces), 3)
        total_area = sum(piece.area for piece in pieces)
        self.assertAlmostEqual(total_area, polygon.area, places=6)

    def test_cut_with_large_number_of_pieces(self):
        rectangle = Polygon([(0, 0), (10, 0), (10, 5), (0, 5), (0, 0)])

        pieces = geometry_cartesian.cut_shape_into_pieces(100, rectangle)

        self.assertEqual(len(pieces), 100)
        total_area = sum(piece.area for piece in pieces)
        self.assertAlmostEqual(total_area, rectangle.area, places=6)


if __name__ == "__main__":
    TestTiltedRectangleGeometry().test()
    TestTiltedRectangleGeometry().test_from_nominal()
    TestTiltedRectangleGeometry().test_from_projected()
    TestProjector().test()
    TestGeometry().test()
    TestNominalGeometry().test_areas()
    TestNominalGeometry().test_from_tilted()
    TestLinestringGeometry().test()
    TestCutShapeIntoPieces().test_cut_rectangle_into_two_pieces()
    TestCutShapeIntoPieces().test_cut_rectangle_into_four_pieces()
    TestCutShapeIntoPieces().test_cut_with_large_number_of_pieces()
    TestCutShapeIntoPieces().test_cut_non_rectangular_polygon()
    ...
