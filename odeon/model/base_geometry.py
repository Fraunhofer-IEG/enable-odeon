from enum import Enum
from typing import Literal, Callable

import pyproj
from shapely.geometry import Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform
import logging

from odeon.processing.utils.utils import typeerror_if_not_isinstance

logger = logging.getLogger(name=f"enable.{__name__}")

SRID_WGS84 = 4326
SRID_OSM = SRID_WGS84


KEY_GEOM = "geometry"

TOLERANCE = 1e-10  # points closer than this will be regarded equal


class CardinalOrientation(Enum):
    NORTH = ("N", 0)
    NORTHEAST = ("NE", 45)
    EAST = ("E", 90)
    SOUTHEAST = ("SE", 135)
    SOUTH = ("S", 180)
    SOUTHWEST = ("SW", 225)
    WEST = ("W", 270)
    NORTHWEST = ("NW", 315)

    def __init__(self, letter, degrees):
        self.letter = letter
        self.degrees = degrees

    @classmethod
    def by_letter(cls, letter):
        return next((o for n, o in CardinalOrientation.__members__.items() if o.letter == letter), None)

    @classmethod
    def by_closest_degrees(cls, degrees):
        degrees = degrees % 360
        orientations_deviations = {o: (o.degrees - degrees) % 360 for n, o in CardinalOrientation.__members__.items()}
        min_deviation = min(orientations_deviations.values())
        return next(o for o, d in orientations_deviations.items() if d == min_deviation)


class Projector:
    """
    A class that manages coordinate reference systems (CRS). The Projector...

    - can create a local CRS at a given location
    - stores projections between this local CRS and other CRS to speed up
      projections
    - projects geometries based on these stored projections
    """

    _origin: Point = None  # in EPSG:4326, order: lat, lon

    # transformers from the local system to another CRS:
    _transformers_to: dict[int, pyproj.Transformer]

    # transformer from another CRS to the local system:
    _transformers_from: dict[int, pyproj.Transformer]

    def __init__(
        self,
        origin: tuple[float, float] | Point | Polygon,
        order: Literal["lat_lon", "lon_lat"] = "lat_lon",
    ):
        """
        Create a new projector.

        This will create a local coordinate reference system (CRS) that can (and
        will automatically) be used in a Project.

        The local CRS is a pair of rectangular axes in North and East direction
        with unit m.

        Note that with growing distance from the origin, the validity of the CRS
        will decrease, i.e. angles, areas and distances will be slightly flawed.
        This should only become relevant in the order of hundreds of kilometers.

        Parameters
        ----------
        origin : tuple[float, float] | Point | Polygon
            location in EPSG:4326 (WGS84). coordinate order depends on
            `order`
        order : Literal["lat_lon", "lon_lat"]
            expected coordinate order of `origin` (longitude/latitude)

        Examples
        --------
        - `Point(52, 7)` is most probably latitude, longitude.
        - `Point(7, 52)` is most probably longitude, latitude
        """
        self.__proj_str = None
        self._transformers_from = {}
        self._transformers_to = {}
        if isinstance(origin, (tuple, list)):
            origin = Point(origin)
        elif isinstance(origin, Polygon):
            minx, miny, maxx, maxy = origin.bounds
            origin = Point(minx, miny)
        elif not isinstance(origin, Point):
            raise TypeError("origin must be a Point, Polygon or tuple of (x, y) coordinates")

        if order not in ["lat_lon", "lon_lat"]:
            raise ValueError("order must be either 'lat_lon' or 'lon_lat'")

        if order == "lat_lon" and origin.x < 25 and origin.y > 25:
            logger.warning(f"is ({origin.x}, {origin.y}) really latitude, longitude?")
        elif order == "lon_lat" and origin.x > 25 and origin.y < 25:
            logger.warning(f"is ({origin.x}, {origin.y}) really longitude, latitude?")

        if order == "lon_lat":
            origin = switch_xy(origin)

        self._origin = origin
        self.__proj_str = _build_local_mercator_proj_str(lat_lon=self._origin)
        self._transformers_to[(SRID_WGS84, True)] = _build_transformer(
            from_=self._origin,
            to=SRID_WGS84,
            always_xy=True,
        )
        self._transformers_from[(SRID_WGS84, True)] = _build_transformer(
            from_=SRID_WGS84,
            to=self._origin,
            always_xy=True,
        )
        self._transformers_to[(SRID_WGS84, False)] = _build_transformer(
            from_=self._origin,
            to=SRID_WGS84,
            always_xy=False,
        )
        self._transformers_from[(SRID_WGS84, False)] = _build_transformer(
            from_=SRID_WGS84,
            to=self._origin,
            always_xy=False,
        )

    @property
    def proj_str(self) -> str:
        """
        The projection string of the local CRS. It can also be used e.g. in GIS
        software.
        """
        return self.__proj_str

    def to_crs(
        self,
        shape: BaseGeometry,
        to_srid: int,
        order: Literal["lat_lon", "lon_lat"] = "lat_lon",
    ) -> BaseGeometry:
        """
        Transform a shape from the local CRS to another CRS.

        Parameters
        ----------
        order : Literal["lat_lon", "lon_lat"]
            - "lat_lon": when transforming to a geographic CRS, output coordinate
              order will be like this (latitude/longitude)
            - "lon_lat": when transforming to a geographic CRS, output coordinate
              order will be like this (longitude/latitude)
        """
        if order == "lat_lon":
            always_xy = False
        elif order == "lon_lat":
            always_xy = True
        else:
            raise ValueError("order must be either 'lat_lon' or 'lon_lat'")

        typeerror_if_not_isinstance(shape, BaseGeometry)
        typeerror_if_not_isinstance(to_srid, int)

        transformer = self._transformers_to.get((to_srid, always_xy), None)
        if transformer is None:
            transformer = _build_transformer(from_=self._origin, to=to_srid, always_xy=always_xy)
            self._transformers_to[(to_srid, always_xy)] = transformer
        return transform(transformer, shape)

    def from_crs(
        self,
        shape: BaseGeometry,
        from_srid: int,
        order: Literal["lat_lon", "lon_lat"] = "lat_lon",
    ) -> BaseGeometry:
        """
        Transform a shape from another CRS to the local CRS.

        Parameters
        ----------
        order : Literal["lat_lon", "lon_lat"]
            - "lat_lon": when transforming from a geographic CRS, input
              coordinate order will be expected to be like this
              (latitude/longitude)
            - "lon_lat": when transforming from a geographic CRS, input
              coordinate order will be expected to be like this
              (longitude/latitude)
        """
        if order == "lat_lon":
            always_xy = False
        elif order == "lon_lat":
            always_xy = True
        else:
            raise ValueError("order must be either 'lat_lon' or 'lon_lat'")

        typeerror_if_not_isinstance(shape, BaseGeometry)
        typeerror_if_not_isinstance(from_srid, int)

        transformer = self._transformers_from.get((from_srid, always_xy), None)
        if transformer is None:
            transformer = _build_transformer(from_=from_srid, to=self._origin, always_xy=always_xy)
            self._transformers_from[(from_srid, always_xy)] = transformer
        return transform(transformer, shape)

    def to_wgs84(
        self,
        shape: BaseGeometry,
        order: Literal["lat_lon", "lon_lat"] = "lat_lon",
    ) -> BaseGeometry:
        """
        Parameters
        ----------
        order : Literal["lat_lon", "lon_lat"]
            - "lat_lon": output coordinate order will be like this
              (latitude/longitude)
            - "lon_lat": output coordinate order will be like this
              (longitude/latitude)
        """
        if order not in ["lat_lon", "lon_lat"]:
            raise ValueError("order must be either 'lat_lon' or 'lon_lat'")
        typeerror_if_not_isinstance(shape, BaseGeometry)
        return self.to_crs(shape, SRID_WGS84, order=order)

    def from_wgs84(
        self,
        shape: BaseGeometry,
        order: Literal["lat_lon", "lon_lat"] = "lat_lon",
    ) -> BaseGeometry:
        """
        Parameters
        ----------
        order : Literal["lat_lon", "lon_lat"]
            - "lat_lon": input coordinate order expected to be like this
              (latitude/longitude)
            - "lon_lat": input coordinate order expected to be like this
              (longitude/latitude)
        """
        if order not in ["lat_lon", "lon_lat"]:
            raise ValueError("order must be either 'lat_lon' or 'lon_lat'")
        typeerror_if_not_isinstance(shape, BaseGeometry)
        return self.from_crs(shape, SRID_WGS84, order=order)

    def lat_lon(self, shape: BaseGeometry) -> tuple[float, float]:
        """
        Transform a shape from local CRS to WGS84 in order latitude, longitude.
        """
        typeerror_if_not_isinstance(shape, BaseGeometry)
        centroid_wgs84 = self.to_wgs84(shape.centroid, order="lat_lon")
        return centroid_wgs84.coords.xy[0][0], centroid_wgs84.coords.xy[1][0]

    def lon_lat(self, shape: BaseGeometry) -> tuple[float, float]:
        """
        Transform a shape from local CRS to WGS84 in order longitude, latitude.
        """
        typeerror_if_not_isinstance(shape, BaseGeometry)
        centroid_wgs84 = self.to_wgs84(shape.centroid, order="lon_lat")
        return centroid_wgs84.coords.xy[0][0], centroid_wgs84.coords.xy[1][0]

    @property
    def origin_lat_lon(self) -> tuple[float, float]:
        return self._origin.coords.xy[0][0], self._origin.coords.xy[1][0]

    @property
    def origin_lon_lat(self) -> tuple[float, float]:
        return self._origin.coords.xy[1][0], self._origin.coords.xy[0][0]


def _build_local_mercator_proj_str(lat_lon: tuple[float, float] | Point):
    if isinstance(lat_lon, Point):
        lat_lon = (lat_lon.x, lat_lon.y)
    if not (
        isinstance(lat_lon, (tuple, list)) and len(lat_lon) == 2 and all(isinstance(x, (int, float)) for x in lat_lon)
    ):
        raise TypeError("lat_lon must be a tuple of (latitude, longitude) or a Point")

    proj_str = f"+proj=omerc +lat_0={lat_lon[0]} +lonc={lat_lon[1]} +alpha=0 "
    proj_str += "+k=1 +x_0=0 +y_0=0 +gamma=0 +ellps=WGS84 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs"
    return proj_str


def _build_local_mercator(lat_lon: tuple[float, float] | Point):
    """
    build a local Transverse Mercator projection located at `origin` given in
    EPSG:4326 (WGS84)
    """
    proj_str = _build_local_mercator_proj_str(lat_lon=lat_lon)  # will typecheck
    return pyproj.Proj(proj_str)


def _build_transformer(
    from_: int | tuple[float, float] | Point,
    to: int | tuple[float, float] | Point,
    always_xy: bool = True,
) -> Callable[[float, float], tuple[float, float]]:
    """
    Build a transformer function that transforms coordinates from one CRS to
    another. The CRS can be identified by an EPSG code (int) or by a local
    transverse mercator projection defined by its origin (tuple of lat, lon or
    Point). The function will return a function that can be used to transform
    coordinates, e.g. in shapely's transform function.

    Parameters
    ----------
    from_ : int | tuple[float, float] | Point
        CRS of the input coordinates. Can be either an EPSG code (int) or a
        local transverse mercator projection defined by its origin (tuple of
        lat, lon or Point)
    to : int | tuple[float, float] | Point
        CRS of the output coordinates. Can be either an EPSG code (int) or a
        local transverse mercator projection defined by its origin (tuple of
        lat, lon or Point)
    always_xy : bool, optional
        If true, the transform method will accept as input and return as output
        coordinates using the traditional GIS order, that is longitude,
        latitude for geographic CRS and easting, northing for most projected
        CRS., by default True

    Returns
    -------
    _type_
        _description_
    """
    typeerror_if_not_isinstance(always_xy, bool)
    if isinstance(from_, int):
        proj1 = pyproj.Proj(f"EPSG:{from_}")
    else:
        if isinstance(from_, Point):
            from_ = (from_.x, from_.y)
        proj1 = _build_local_mercator(lat_lon=from_)  # Will typecheck
    if isinstance(to, int):
        proj2 = pyproj.Proj(f"EPSG:{to}")
    else:
        if isinstance(to, Point):
            to = (to.x, to.y)
        proj2 = _build_local_mercator(lat_lon=to)  # Will typecheck

    return pyproj.Transformer.from_proj(proj1, proj2, always_xy=always_xy).transform


# dict of transformers with key (from, to) on module level to improve performance. from and to can be either ints
# to identify a CRS id, or points to indetify a local transverse mercator projection origin
transformers = {}

# same for geods
geod_wgs84 = pyproj.Geod(ellps="WGS84")


def project(
    geom: BaseGeometry,
    from_: int | tuple[float, float] | Point,
    to: int | tuple[float, float] | Point,
) -> BaseGeometry:
    """
    Project a geometry from one CRS to another. The CRS can be identified by an
    EPSG code (int) or by a local transverse mercator projection defined by its
    origin (tuple of lat, lon or Point). The function will automatically store
    transformers for previously used CRS pairs to speed up future projections.

    Parameters
    ----------
    geom : BaseGeometry
        Geometry to project
    from_ : int | tuple[float, float] | Point
        CRS of the input geometry. Can be either an EPSG code (int) or a local
        transverse mercator projection defined by its origin (tuple of lat, lon
        or Point)
    to : int | tuple[float, float] | Point
        CRS of the output geometry. Can be either an EPSG code (int) or a local
        transverse mercator projection defined by its origin (tuple of lat, lon
        or Point)

    Returns
    -------
    BaseGeometry
        The projected geometry
    """
    typeerror_if_not_isinstance(geom, BaseGeometry)
    if isinstance(from_, (tuple, list)):
        from_ = Point(from_)
    if isinstance(to, (tuple, list)):
        to = Point(to)
    assert isinstance(from_, int) or isinstance(to, int)
    if from_ != to:
        transformer = transformers.get((from_, to), None)
        if transformer is None:
            transformer = _build_transformer(from_=from_, to=to)  # will typecheck
            transformers[(from_, to)] = transformer
        return transform(transformer, geom)
    else:
        return geom


def switch_xy(geom: BaseGeometry) -> BaseGeometry:
    """Switch the order of coordinates in a geometry from x, y to y, x."""
    typeerror_if_not_isinstance(geom, BaseGeometry)
    return transform(lambda x, y, z=None: (y, x, z) if z is not None else (y, x), geom)


def lat_lon_to_lon_lat(geom: BaseGeometry) -> BaseGeometry:
    """
    Switch the order of coordinates in a geometry from latitude, longitude to
    longitude, latitude. This is useful for example when working with OSM data,
    which is usually in longitude, latitude order, but pyproj expects latitude,
    longitude order.
    """
    return switch_xy(geom)  # Will typecheck


def lon_lat_to_lat_lon(geom: BaseGeometry) -> BaseGeometry:
    """
    Switch the order of coordinates in a geometry from longitude, latitude to
    latitude, longitude. This is useful for example when working with OSM data,
    which is usually in longitude, latitude order, but pyproj expects latitude,
    longitude order.
    """
    return switch_xy(geom)  # Will typecheck
