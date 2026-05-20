from typing import Literal

import numpy as np
import pyproj
import math
from shapely.geometry import LineString, Point, Polygon, MultiPolygon
from shapely.geometry.base import BaseGeometry, BaseMultipartGeometry
from shapely.ops import transform

from .base_geometry import Projector, CardinalOrientation, SRID_WGS84

from ..processing.geometry_cartesian import (
    edge_azimuths,
    edge_lengths,
    distance3d,
    scale_shape,
    create_rectangle,
    is_tilted_rectangle,
    shape2d_to_shape3d,
    shape3d_to_shape2d,
    transform_rectangle_z_keep_xy,
    closest_direction_index,
    principal_direction_rectangle,
)

X_INDEX = 0
Y_INDEX = 1
Z_INDEX = 2



class Geometry:

    _shape: BaseGeometry = None
    altitude: float = None  # [m] geodetic altitude (meters above sea level)

    def __init__(self, shape: BaseGeometry = None, altitude: float = None):
        """
        Parameters
        ----------
        shape : BaseGeometry
            The shape as shapely `BaseGeometry` object. Coordinate order is always
            (Easting, Northing, [z])
        altitude : float
            Geodetic altitude in meters above sea level. This is not the same as
            z coordinate of the shape, which is the height above the local
            ground.
        """
        if shape is not None:
            self.shape = shape  # call setter for any transformations
        self.altitude = altitude

    @property
    def centroid(self) -> Point | None:
        return self._shape.centroid if self._shape is not None else None

    @property
    def is_point(self) -> bool:
        return isinstance(self._shape, Point)

    @property
    def is_polygon(self) -> bool:
        return isinstance(self._shape, Polygon)

    @property
    def has_z(self):
        return self._shape.has_z if self._shape is not None else False

    @property
    def shape(self) -> BaseGeometry | None:
        return self._shape

    @shape.setter
    def shape(self, shape: BaseGeometry):
        assert isinstance(shape, BaseGeometry)
        self._shape = shape

    @property
    def polygon(self) -> Polygon | None:
        """
        Return the shape if it's a polygon, else None.
        """
        if self.is_polygon:
            return self.shape

    @polygon.setter
    def polygon(self, polygon: Polygon):
        assert isinstance(polygon, Polygon)
        self.shape = polygon

    def shape_in_crs(self, to_srid: int, projector: Projector, order: Literal["lon_lat", "lat_lon"] = "lat_lon"):
        return projector.to_crs(self._shape, to_srid=to_srid, order=order)

    def shape_in_wgs84(self, projector: Projector, order: Literal["lon_lat", "lat_lon"] = "lat_lon"):
        return self.shape_in_crs(SRID_WGS84, projector=projector, order=order)

    def lon_lat(self, projector: Projector) -> tuple[float, float]:
        return projector.lon_lat(self._shape)

    def lat_lon(self, projector: Projector) -> tuple[float, float]:
        return projector.lat_lon(self._shape)

    @property
    def longitude_latitude_linestring(self):
        # TODO more fitting for LinestringGeometry?
        proj = pyproj.CRS(f"EPSG:{self.__SRID}")
        proj_wgs84 = pyproj.CRS(f"EPSG:{SRID_WGS84}")
        projector = pyproj.Transformer.from_crs(proj, proj_wgs84, always_xy=True).transform
        if isinstance(self._shape, LineString):
            coords_wgs84 = transform(projector, self._shape)
            return coords_wgs84.coords.xy
        else:
            print("Object isn't a linestring")


class MultiGeometry(Geometry):

    _shape: BaseMultipartGeometry = None

    @property
    def is_multipolygon(self) -> bool:
        return isinstance(self._shape, MultiPolygon)


class NominalGeometry(Geometry):
    dimensions_nominal: tuple[float, float] = (None, None)  # [m]
    dimensions_projected_nominal: tuple[float, float] = (None, None)  # [m]
    area_nominal: float = None  # [m²]
    area_projected_nominal: float = None  # [m²]
    height: float = None  # [m]
    tilt: float = None  # [°]
    azimuth: float = None  # [°] deviation from North in clockwise direction
    azimuth_cardinal: CardinalOrientation = None

    def __init__(
        self,
        shape: Point | Polygon = None,
        altitude: float = None,  # [m]
        dimensions_nominal: tuple[float, float] = (None, None),  # [m]
        dimensions_projected_nominal: tuple[float, float] = (None, None),  # [m]
        area_nominal: float = None,  # [m²]
        area_projected_nominal: float = None,  # [m²]
        height: float = None,  # [m]
        tilt: float = None,  # [°]
        azimuth: float = None,  # [°] deviation from North in clockwise direction
        azimuth_cardinal: CardinalOrientation = None,
    ):
        super().__init__(shape, altitude)
        self.dimensions_nominal = dimensions_nominal
        self.dimensions_projected_nominal = dimensions_projected_nominal
        self.area_nominal = area_nominal
        self.area_projected_nominal = area_projected_nominal
        self.height = height
        self.tilt = tilt
        self.azimuth = azimuth
        self.azimuth_cardinal = azimuth_cardinal

    def set_longitude_latitude(self, longitude_latitude: tuple[float, float]):
        raise NotImplementedError()
        # TODO update
        centroid_wgs84 = Point(longitude_latitude[0], longitude_latitude[1])
        proj = pyproj.CRS(f"EPSG:{self.srid}")
        proj_wgs84 = pyproj.CRS(f"EPSG:{SRID_WGS84}")
        projector = pyproj.Transformer.from_crs(proj_wgs84, proj, always_xy=True).transform
        centroid = transform(projector, centroid_wgs84)
        self.shape = centroid

    @Geometry.shape.setter
    def shape(self, shape: Point | Polygon):
        assert isinstance(
            shape, (Point, Polygon, MultiPolygon)
        )  # /kg I added a MultiPolygon because somne sites were MPs. Maybe that was not the intent here?
        shape = shape3d_to_shape2d(shape)
        self._shape = shape

    @property
    def mrr(self):
        if isinstance(self._shape, Polygon):
            return self._shape.minimum_rotated_rectangle

    @property
    def mrr_equal_area(self):
        if isinstance(self._shape, Polygon):
            mrr = self._shape.minimum_rotated_rectangle
            scale_fac = np.real(math.sqrt(self.area_projected / mrr.area))
            mrr_scaled = scale_shape(mrr, scale_fac)
            return mrr_scaled

    @property
    def pdr(self):
        """
        principal direction rectangle
        """
        if isinstance(self._shape, Polygon):
            return principal_direction_rectangle(self._shape, equal_area=False)

    @property
    def pdr_equal_area(self):
        """
        principal direction rectangle
        """
        if isinstance(self._shape, Polygon):
            return principal_direction_rectangle(self._shape, equal_area=True)

    @property
    def dimensions(self):
        if isinstance(self._shape, Polygon):
            mrr = self.mrr_equal_area
            lengths = edge_lengths(mrr)
            return lengths[0], lengths[1]
        else:
            return self.dimensions_nominal

    @property
    def dimensions_projected(self):
        if isinstance(self._shape, Polygon):
            return self.dimensions
        else:
            return self.dimensions_projected_nominal

    @property
    def area(self):
        if self.area_nominal is not None:
            return self.area_nominal
        elif self.is_polygon:
            return self._shape.area
        elif all(self.dimensions_nominal):
            return self.dimensions_nominal[0] * self.dimensions_nominal[1]
        else:
            return None

    @property
    def area_projected(self):
        if self.area_projected_nominal is not None:
            return self.area_projected_nominal
        elif isinstance(self._shape, Polygon):
            return self.area

    @classmethod
    def from_tilted_rectangle(cls, tilted_rectangle: "TiltedRectangleGeometry"):
        obj = cls()
        obj._shape = tilted_rectangle.shape
        obj.altitude = tilted_rectangle.altitude
        obj.height = tilted_rectangle.height
        obj.tilt = tilted_rectangle.tilt
        obj.azimuth = tilted_rectangle.azimuth
        obj.dimensions_projected_nominal = tilted_rectangle.dimensions_projected
        obj.area_nominal = tilted_rectangle.area
        obj.area_projected_nominal = tilted_rectangle.area_projected
        return obj


class TiltedRectangleGeometry(Geometry):
    __z_min = None
    __z_max = None
    __edges_pointpairs = None
    __edges_linestring = None
    __orientations = None  # [m]
    __dimensions = None  # [m]
    __dimensions_projected = None  # [m²]
    __indices_lower_upper_upward_downward_edge = None

    def __init__(self, shape: Polygon = None, altitude: float = None):
        super().__init__(shape, altitude)
        self.__z_min = None
        self.__z_max = None
        self.__edges_pointpairs = None
        self.__edges_linestring = None
        self.__orientations = None
        self.__dimensions = None
        self.__dimensions_projected = None
        self.__indices_lower_upper_upward_downward_edge = None

    @Geometry.shape.setter
    def shape(self, shape: Polygon):
        if self._shape is not None:
            raise Exception(f"can't alter shape of {self.__class__.__name__}")
        else:
            assert is_tilted_rectangle(shape)
            # TODO transform to 3d if not already?
            self._shape = shape

    def xyz_by_point(self, repeat_first_point: bool = False) -> list[tuple[float, float, float]]:
        """
        return `((x1, y1, z1), (x2, y2, z2), (x3, y3, z3), (x4, y4, z4),
        (x1, y1, z1))`
        """
        pointtuples = tuple(self._shape.exterior.coords)
        if not repeat_first_point:
            pointtuples = pointtuples[:-1]
        return pointtuples

    def xyz_by_axis(self, repeat_first_point: bool = False) -> tuple[list[float], list[float], list[float]]:
        """
        return `((x1, x2, x3, x4, [x1]), (y1, y2, y3, y4, [y1]),
        (z1, z2, z3, z4, [z1]))`
        """
        pointtuples = self.xyz_by_point(repeat_first_point)
        return tuple(tuple(point[i] for point in pointtuples) for i in [X_INDEX, Y_INDEX, Z_INDEX])

    def points(self, repeat_first_point: bool = False) -> list[Point]:
        return [Point(pt) for pt in self.xyz_by_point(repeat_first_point)]

    def vertices(self, repeat_first_point: bool = False) -> np.array:
        res = np.array(self._shape.exterior.coords)
        if not repeat_first_point:
            res = res[:-1]
        return res

    @property
    def edges_pointpairs(self) -> list[tuple[Point, Point]]:
        if self.__edges_pointpairs is None:
            points = self.points(True)
            self.__edges_pointpairs = [(p1, p2) for p1, p2 in zip(points[:-1], points[1:])]
        return self.__edges_pointpairs

    @property
    def edges_linestring(self) -> list[LineString]:
        if self.__edges_linestring is None:
            pointtuples = self.edges_pointpairs
            self.__edges_linestring = [LineString(pt) for pt in pointtuples]
        return self.__edges_linestring

    @property
    def edges_vectors(self) -> list[np.array]:
        pointtuples = [np.array(x) for x in self._shape.exterior.coords]  # length = 5
        return [p2 - p1 for p1, p2 in zip(pointtuples[:-1], pointtuples[1:])]

    @property
    def z_min(self) -> float:
        if self.__z_min is None:
            zs = self.xyz_by_axis()[Z_INDEX]
            self.__z_min = min(zs)
        return self.__z_min

    @property
    def z_centroid(self) -> float:
        return (self.z_min + self.z_max) / 2

    @property
    def z_max(self) -> float:
        if self.__z_max is None:
            zs = self.xyz_by_axis()[Z_INDEX]
            self.__z_max = max(zs)
        return self.__z_max

    @property
    def centroid3d(self) -> Point:
        assert not self.centroid.has_z
        return shape2d_to_shape3d(self.centroid, z=self.z_centroid)

    @property
    def indices_lower_upper_upward_downward_edge(self) -> tuple[int, int, tuple[int, int]]:
        """
        return indices of lower edge, upper edge, upward inclined edge,
        downward inclined edge. Will return `(-1, -1, -1, -1)` if rectangle is
        horizontal
        """
        if self.__indices_lower_upper_upward_downward_edge is None:
            if self.horizontal:
                self.__indices_lower_upper_upward_downward_edge = (-1, -1, -1, -1)
            else:
                edges_pointpairs = self.edges_pointpairs
                zmin, zmax = self.z_min, self.z_max
                for i, pp in enumerate(edges_pointpairs):
                    p0 = list(*pp[0].coords)
                    p1 = list(*pp[1].coords)
                    if p0[Z_INDEX] == p1[Z_INDEX] == zmin:
                        ilower = i
                    elif p0[Z_INDEX] == p1[Z_INDEX] == zmax:
                        iupper = i
                    elif p0[Z_INDEX] == zmin and p1[Z_INDEX] == zmax:
                        iupward = i
                    elif p0[Z_INDEX] == zmax and p1[Z_INDEX] == zmin:
                        idownward = i
                self.__indices_lower_upper_upward_downward_edge = (ilower, iupper, iupward, idownward)
        return self.__indices_lower_upper_upward_downward_edge

    @property
    def lower_edge(self):
        """
        return linestring with two points as in the polygon that has same z
        in both points and where z equals the minimum z of the polygon. Will
        return `None` if rectangle is horizontal
        """
        i = self.indices_lower_upper_upward_downward_edge[0]
        if i > -1:
            return self.edges_linestring[i]

    @property
    def upper_edge(self):
        """
        return linestring with two points as in the polygon that has same z
        in both points and where z equals the maximum z of the polygon. Will
        return `None` if rectangle is horizontal
        """
        i = self.indices_lower_upper_upward_downward_edge[1]
        if i > -1:
            return self.edges_linestring[i]

    @property
    def horizontal_edges(self) -> list[LineString]:
        """
        Will return all edges if rectangle is horizontal
        """
        i = self.indices_lower_upper_upward_downward_edge[:2]
        if i[0] > -1:
            edges = self.edges_linestring
            return edges[i[0]], edges[i[1]]
        else:
            return self.edges_linestring

    @property
    def inclined_edges(self) -> list[LineString]:
        """
        Will return empty list if rectangle is horizontal
        """
        i = self.indices_lower_upper_upward_downward_edge[2:]
        if i[0] > -1:
            edges = self.edges_linestring
            return edges[i[0]], edges[i[1]]
        else:
            return []

    @property
    def orientations(self):
        """
        return orientation of lower edge, upper edge, upward inclined edge,
        downward inclined edge
        """
        if self.__orientations is None:
            azs = edge_azimuths(self._shape)
            if self.horizontal:
                self.__orientations = azs
            else:
                indices = self.indices_lower_upper_upward_downward_edge
                self.__orientations = tuple(
                    azs[i] for i in indices
                )  # TODO make sure that azimuth is the right one, not baz
        return self.__orientations

    @property
    def vertical(self):
        _, _, iupward, idownward = self.indices_lower_upper_upward_downward_edge
        edges = self.edges_linestring
        return edges[iupward].length == 0 and edges[idownward].length == 0

    @property
    def horizontal(self):
        return self.z_max == self.z_min

    @property
    def inclined(self):
        """= `not is_horizontal"""
        return not self.horizontal

    @property
    def height(self):
        return self.z_max - self.z_min

    @property
    def dimensions(self):
        """
        if tilted, first value is (3D) azimuthal dimension, second is
        crossazimuthal.For verticals, especially, first value is height, second
        is width. Otherwise, first value is length of first edge, second of
        second edge
        """
        if self.__dimensions is None:
            res = self.dimensions_projected
            if self.vertical:
                res = self.height, res[1]
            elif not self.horizontal:
                res = np.real(math.sqrt(res[0] ** 2 + self.height**2)), res[1]
            self.__dimensions = res
        return self.__dimensions

    @property
    def dimensions_projected(self):
        """
        if tilted, first value is (projected, 2D) azimuthal dimension, second
        is crossazimuthal. For verticals, especially, first value will be 0,
        second is width. otherwise, first value is length of first edge, second
        of second edge
        """
        if self.__dimensions_projected is None:
            i, _, _, j = self.indices_lower_upper_upward_downward_edge
            if self.horizontal:
                i = 1
                j = 0
            elif self.vertical:
                lengths = edge_lengths(self.edges_linestring[i])
                self.__dimensions_projected = 0, lengths[0]
            lengths = edge_lengths(self.shape)
            res = lengths[j], lengths[i]
            self.__dimensions_projected = res
        return self.__dimensions_projected

    @property
    def dimension_azimuthal(self) -> float | None:
        """
        dimension of inclined edges in 3D. will return None if rectangle is
        horizontal
        """
        if not self.horizontal:
            return self.dimensions[0]

    @property
    def dimension_azimuthal_projected(self) -> float | None:
        """
        dimension of inclined edges projected on horizontal plane. will return
        None if rectangle is horizontal
        """
        if not self.horizontal:
            return self.dimensions_projected[0]

    @property
    def dimension_crossazimuthal(self) -> float | None:
        """
        dimension of horizontal edges. will return None if rectangle is
        horizontal
        """
        if not self.horizontal:
            return self.dimensions_projected[1]

    @property
    def tilt(self):
        """
        in degrees
        """
        if self.horizontal:
            return 0
        elif self.vertical:
            return 90
        else:
            return np.real(math.degrees(np.real(math.asin(self.height / self.dimension_azimuthal))))

    @property
    def azimuth(self):
        """
        Geographic azimuth (deviation from true North) - not the angle to x
        axis in EPSG:3035!
        """
        if self.vertical:
            line = self.normal_linestring(length=100)
            az = edge_azimuths(geometry=line)[0]
            return az
        return self.orientations[3]  # 3 is azimuth of downward edge

    @property
    def normal_vector(self) -> np.array:
        """
        get xyz of analytical normal in EPSG:3035.
        This normal depends on the order of coordinates in the rectangle.
        Actually I'm not sure whether this is legal or should be done in a
        geographic CRS instead. Might carry larger errors at CRS borders
        """
        v01, v12, *_ = self.edges_vectors
        normal = np.cross(v01, v12)
        normal = normal / np.linalg.norm(normal)
        return normal

    @property
    def azimuth_tilt_vector(self) -> np.array:
        azimuth = self.azimuth
        inclination = 90 - self.tilt
        x = np.sin(np.deg2rad(azimuth)) * np.cos(np.deg2rad(inclination))
        y = np.cos(np.deg2rad(azimuth)) * np.cos(np.deg2rad(inclination))
        z = np.sin(np.deg2rad(inclination))
        return np.array([x, y, z])

    def normal_linestring(self, length: float = 1) -> LineString:
        """
        return a linestring from 3d centroid in direction of normal with `length`
        """
        normal = self.normal_vector * length
        p0 = self.centroid
        p0z = self.z_centroid
        line = LineString(
            [
                Point(p0.x, p0.y, p0z),
                Point(p0.x + normal[0] * length, p0.y + normal[1] * length, p0z + normal[2] * length),
            ]
        )
        return line

    def set_vertical_approximate_azimuth(self, approximate_azimuth: float):
        if self.vertical:
            a = self.azimuth
            b = self.azimuth + 180
            if closest_direction_index(approximate_azimuth, a, b) == 1:  # = need to flip
                self.shape = self.shape.reverse()

    @property
    def area(self):
        dimensions = self.dimensions
        return dimensions[0] * dimensions[1]

    @property
    def area_projected(self):
        dimensions = self.dimensions_projected
        return dimensions[0] * dimensions[1]

    @classmethod
    def from_nominal(cls, nominal: NominalGeometry, use_pdr: bool = True) -> "TiltedRectangleGeometry":
        # TODO match azimuth if vertical
        obj = cls()
        obj.altitude = nominal.altitude
        if nominal.azimuth is not None:
            azimuth = nominal.azimuth
        elif nominal.azimuth_cardinal is not None:
            azimuth = nominal.azimuth_cardinal.degrees
        else:
            azimuth = 0
        if nominal.is_point:
            dimension_azimuthal = nominal.dimensions[0] or math.sqrt(nominal.area)
            dimension_crossazimuthal = nominal.dimensions[1] or math.sqrt(nominal.area)
            rectangle = create_rectangle(
                centroid_in_result_srid=nominal.centroid,
                dimensions_projected=(dimension_azimuthal, dimension_crossazimuthal),
                azimuth=azimuth,
                height=nominal.height,
                tilt=nominal.tilt,
                force3d=True,
                result_srid=3035,
            )
        elif nominal.is_polygon:
            tilt = 0 if (nominal.tilt is None and nominal.height is None) else nominal.tilt
            rectangle = transform_rectangle_z_keep_xy(
                rectangle=nominal.pdr_equal_area if use_pdr else nominal.mrr_equal_area,
                tilt=tilt,
                height=nominal.height,
                azimuth=azimuth,
                azimuth_cardinal=nominal.azimuth_cardinal,
            )
            assert is_tilted_rectangle(rectangle)
        else:
            raise TypeError()
        obj.shape = rectangle
        return obj

    @classmethod
    def from_shapely_polygon_2d(cls, polygon: Polygon, use_pdr: bool = True) -> "TiltedRectangleGeometry":
        ng = NominalGeometry(shape=polygon)
        obj = cls()
        shape = ng.pdr_equal_area if use_pdr else ng.mrr_equal_area
        obj.shape = shape2d_to_shape3d(shape, z=0)
        return obj

    @classmethod
    def from_generic(cls, geometry: Geometry, use_pdr: bool = True) -> "TiltedRectangleGeometry":
        assert geometry.is_polygon
        ng = NominalGeometry(shape=geometry.polygon)
        obj = cls()
        shape = ng.pdr_equal_area if use_pdr else ng.mrr_equal_area
        obj.shape = shape2d_to_shape3d(shape, z=0)
        obj.altitude = geometry.altitude
        return obj


class LinestringGeometry(Geometry):
    def __init__(self, shape: LineString = None, altitude: float = None):
        super().__init__(shape, altitude)

    @Geometry.shape.setter
    def shape(self, shape: LineString):
        assert isinstance(shape, LineString)
        self._shape = shape

    @property
    def xyz_by_point(self) -> list[tuple[float, float, float]]:
        """
        return `((x1, y1, z1), (x2, y2, z2), ...)`
        """
        return tuple(self._shape.coords)

    @property
    def xyz_by_axis(self) -> tuple[list[float], list[float], list[float]]:
        """
        return `((x1, x2, ...), (y1, y2, ...), (z1, z2, ...))`
        """
        pointtuples = self.xyz_by_point
        return tuple(tuple(point[i] for point in pointtuples) for i in [X_INDEX, Y_INDEX, Z_INDEX])

    def points(self, apply_altitude: bool = False) -> list[Point]:
        xyz = self.xyz_by_point
        dz = (apply_altitude and self.altitude) or 0
        return [Point(tuple((pt[X_INDEX], pt[Y_INDEX], pt[Z_INDEX] + dz))) for pt in xyz]

    @property
    def edges_pointpairs(self) -> list[tuple[Point, Point]]:
        """
        without applying altitude
        """
        points = self.points()
        return [(p1, p2) for p1, p2 in zip(points[:-1], points[1:])]

    @property
    def edges_linestring(self) -> list[LineString]:
        pointtuples = self.edges_pointpairs
        return [LineString(pt) for pt in pointtuples]

    @property
    def z_min(self) -> float:
        """
        without applying altitude
        """
        zs = self.xyz_by_axis[Z_INDEX]
        return min(zs)

    @property
    def z_max(self) -> float:
        """
        without applying altitude
        """
        zs = self.xyz_by_axis[Z_INDEX]
        return max(zs)

    @property
    def horizontal(self):
        return self.z_max == self.z_min

    @property
    def height(self):
        return self.z_max - self.z_min

    @property
    def length_path(self):
        """sum of lengths of edge parts, considering z"""
        pps = self.edges_pointpairs
        if pps:
            res = 0
            for pp in pps:
                res += distance3d(pp[0], pp[1])
            return res

    @property
    def length_path_projected(self):
        """sum of length of edge parts, ignoring z"""
        pps = self.edges_pointpairs
        if pps:
            res = 0
            for pp in pps:
                res += pp[0].distance(pp[1])
            return res

    @property
    def length_beeline(self):
        """
        istance between first and last point of linestring, considering z
        """
        points = self.points()
        return distance3d(points[0], points[-1])

    @property
    def length_beeline_projected(self):
        """
        distance between first and last point of linestring, ignoring z
        """
        points = self.points()
        return points[0].distance(points[-1])
