import math

import geopandas as geo
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import minimize
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, split

from ..model.base_geometry import CardinalOrientation, TOLERANCE


def shape2d_to_shape3d(geom: BaseGeometry, z: float = 0) -> BaseGeometry:
    def f(x: tuple[float], y: tuple[float], old_z=0):
        return x, y, [z for _ in x]

    return transform(f, geom)


def shape3d_to_shape2d(geom: BaseGeometry) -> BaseGeometry:
    def f(x: tuple[float], y: tuple[float], z: tuple[float] = None):
        return x, y

    return transform(f, geom)


def scale_shape(geom: BaseGeometry, fac: float) -> BaseGeometry:
    """
    `geom` and result: in cartesian coordinate system
    """
    geo_df = geo.GeoDataFrame(geometry=[geom])
    geo_df = geo_df.geometry.scale(xfact=fac, yfact=fac, zfact=1.0)
    return geo_df.iloc[0]


def distance3d(p1: Point, p2: Point):
    dist2d = p1.distance(p2)
    dist3d = np.real(math.sqrt(dist2d**2 + (p1.coords[0][2] - p2.coords[0][2]) ** 2))
    return dist3d


def polygon_to_vectors(polygon: Polygon) -> list[np.array]:
    xs = [*polygon.exterior.xy[0]]
    ys = [*polygon.exterior.xy[1]]
    vs = []
    for x0, x1, y0, y1 in zip(xs[:-1], xs[1:], ys[:-1], ys[1:]):
        dx = x1 - x0
        dy = y1 - y0
        vs.append(np.array([dx, dy]))
    return vs


def edge_lengths(geometry: LineString | Polygon | list[Point]) -> list[float]:
    if isinstance(geometry, Polygon):
        xs, ys = geometry.exterior.coords.xy
        points = [Point(x, y) for x, y in zip(xs, ys)]
    elif isinstance(geometry, LineString):
        points = [Point(c) for c in geometry.coords]
    elif isinstance(geometry, list):
        points = geometry
    lengths = []
    for p1, p2 in zip(points[:-1], points[1:]):
        lengths.append(p1.distance(p2))
    return lengths


def edge_azimuths(geometry: LineString | Polygon | list[Point]) -> list[float]:
    """Returns azimuths for all egdes in geometry exterior
    The azimuth of an edge is the angle between positive y axis and line between
    a coordinate pair. E.g. when y axis is North and x axis is East, an azimuth
    of 60 would be ENE.

    Parameters
    ----------
    geometry : Union[LineString, Polygon, list[Point]]
        Geometry that can either be a LineString, Polygon or a list of Points

    Returns
    -------
    azimuths : list[float]
        List of azimuths in degrees for each edge of the geometry.
        Azimuths are defined from 0 to 360 degrees (e.g. North = 0, South = 180 East = 90, West = 270)
    """
    if isinstance(geometry, Polygon):
        xs, ys = geometry.exterior.coords.xy
        xytuples = [(x, y) for x, y in zip(xs, ys)]
    elif isinstance(geometry, LineString):
        xytuples = [tuple(c) for c in geometry.coords]
    elif isinstance(geometry, list):
        xytuples = [p.xy for p in geometry]
    azimuths = []
    for xy1, xy2 in zip(xytuples[:-1], xytuples[1:]):
        dx = xy2[0] - xy1[0]
        dy = xy2[1] - xy1[1]
        azimuth = math.degrees(math.atan2(dx, dy)) % 360
        azimuths.append(azimuth)
    return azimuths


def angle_of_vectors(xyz: list[np.array] = None, abc: list[np.array] = None) -> float:
    if abc:
        a, b, c = [np.array(x) for x in abc]
    else:
        x, y, z = xyz
        a = np.array(x[0], y[0], z[0])
        b = np.array(x[1], y[1], z[1])
        c = np.array(x[2], y[2], z[2])

    ba = a - b
    bc = c - b
    cosine_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc))
    return np.rad2deg(np.arccos(cosine_angle))


def principal_vectors(xy: list[np.array]) -> tuple[np.array, np.array]:
    """
    `xy`: list of n vectors with x and y component as np.array each
    """

    def f(px):
        py = np.sqrt(1 - px**2)
        qx, qy = py, -px
        return sum([abs((px * xy[i][1] - py * xy[i][0]) * (qx * xy[i][1] - qy * xy[i][0])) for i in range(len(xy))])

    def plot_f(min_=None):
        angle = [i / 10 for i in range(-900, 900)]
        x = [np.sin(np.deg2rad(a)) for a in angle]
        value = [f(x) for x in x]
        min_ = np.rad2deg(math.asin(min_))
        plt.plot(angle, value)
        plt.axvline(min_)
        plt.show()

    px0 = 0
    px = minimize(f, x0=px0, bounds=[[-1.0, 1.0]]).x[0]
    # plot_f(px)
    py = math.sqrt(1 - px**2)
    qx, qy = py, -px
    return np.array([px, py]), np.array([qx, qy])


def principal_orientations(xy: list[np.array]) -> tuple[float, float]:
    p1, p2 = principal_vectors(xy)
    angle1 = np.rad2deg(math.atan(p1[1] / p1[0])) if p1[0] != 0 else 90
    angle2 = perpendicular(angle1)
    return angle1, angle2


def principal_direction_rectangle(polygon: Polygon, equal_area: bool = True) -> Polygon:
    angle1, angle2 = principal_orientations(polygon_to_vectors(polygon))
    polygon = affinity.rotate(polygon, -angle1)
    envelope = polygon.envelope
    if equal_area:
        fac = math.sqrt(polygon.area / envelope.area)
        envelope = affinity.scale(geom=envelope, xfact=fac, yfact=fac)
    envelope = affinity.rotate(envelope, angle1)
    return envelope


def closest_direction_index(
    target: float | CardinalOrientation,
    candidates: list[float | CardinalOrientation],
    allow_antiparallel: bool = False,
):
    """
    return index of the candidate direction (in degrees) that has the smallest
    declination towards a reference direction `target`
    """
    deviations = []
    for c in candidates:
        deviations.append(direction_deviation(target, c, allow_antiparallel))
    closest_index = deviations.index(min(deviations))
    return closest_index


def direction_deviation(
    a: float | CardinalOrientation,
    b: float | CardinalOrientation,
    allow_antiparallel: bool = False,
) -> float:
    """
    calculate declination between reference direction `a` (degrees) and
    direction `b` (degrees)
    """
    if isinstance(a, CardinalOrientation):
        a = a.degrees
    if isinstance(b, CardinalOrientation):
        b = b.degrees
    a = a % 360
    b = b % 360
    if allow_antiparallel:
        a = a % 180
        b = b % 180
    return abs(a - b)


def perpendicular(x: float | CardinalOrientation):
    """
    for `x` in degrees (<0 and >360 allowed), return the perpendicular
    direction `y` with `0 <= y <= 180`
    """
    if isinstance(x, CardinalOrientation):
        x = x.degrees
    x = x % 180
    if x >= 90:
        return 90 - x
    else:
        return 90 + x


def reverse_line(line: LineString) -> LineString:
    def _reverse(x, y, z=None):
        if z:
            return x[::-1], y[::-1], z[::-1]
        return x[::-1], y[::-1]

    return transform(_reverse, line)


def is_rectangle(polygon: Polygon, consider_z: bool = False, abs_tol=0.001) -> bool:
    """
    if `consider_z`, z values must be present for all coords in polygon.
    `abs_tol` will be applied to area comparison and right angle check
    """
    xyz = polygon.exterior.coords
    res = len(xyz) == 5
    if not consider_z:
        res &= math.isclose(polygon.minimum_rotated_rectangle.area, polygon.area, abs_tol=abs_tol)
    else:
        xyz = [*xyz, xyz[1]]
        for i in range(4):
            res &= math.isclose(angle_of_vectors(abc=xyz[i : i + 3]), 90, abs_tol=abs_tol)
    return res


def is_tilted_rectangle(polygon: Polygon, abs_tol=0.001) -> bool:
    """
    tilted rectangle = rectangle with two pairs of adjacent coords that have
    the same z value
    """
    res = True
    if any(len(xyz) > 2 for xyz in polygon.exterior.coords[:-1]):
        zs = [xyz[2] for xyz in polygon.exterior.coords[:-1]]
        res &= (zs[0] == zs[1] and zs[2] == zs[3]) or (zs[0] == zs[3] and zs[1] == zs[2])
    res &= is_rectangle(polygon, consider_z=True, abs_tol=abs_tol)
    return res


def create_prism(
    horizontal_polygon: Polygon,
    height: float,
    z_offset: float = None,
) -> tuple[Polygon, list[Polygon], Polygon]:
    """
    - Extrude `horizontal_rectangle` by `height`.
    - Return: Bottom polygon (same as `horizontal_polygon` but with z set, if not before), vertical rectangles,
    top polygon
    - The result will be in same SRID as `horizontal_polygon`
    - if `z_offset`, lower z will be `z_offset`, upper z will be `z_offset + height`. Else, original lower z will be
    kept, if present, or lower z will be 0
    """

    def ensure_z(tpls: tuple | list[tuple], z=None, dz=None):
        if isinstance(tpls[0], (float, int)):
            tpls = [tpls]
        res = []
        for tpl in tpls:
            if len(tpl) == 2 or z is not None:
                z = z or 0
                tpl = (tpl[0], tpl[1], z)
            if dz is not None:
                tpl = (tpl[0], tpl[1], tpl[2] + dz)
            res.append(tpl)
        return res

    pointtuples = tuple(horizontal_polygon.exterior.coords)
    bottom = Polygon(ensure_z(pointtuples, z=z_offset))
    top = Polygon(ensure_z(pointtuples, z=z_offset, dz=height))
    sides = []
    for p1, p2 in zip(pointtuples[:-1], pointtuples[1:]):
        p1, p2 = ensure_z([p1, p2], z=z_offset)
        p3 = (p2[0], p2[1], p2[2] + height)
        p4 = (p1[0], p1[1], p1[2] + height)
        sides.append(Polygon((p1, p2, p3, p4, p1)))
    return bottom, sides, top


def create_rectangle(
    location: Point = None,
    dimensions: tuple[float, float] = None,
    dimensions_projected: tuple[float, float] = None,
    azimuth: float = 0,
    tilt: float = None,
    height: float = None,
    z_offset: float = None,
    z_centroid: float = None,
    force3d: bool = False,
) -> Polygon:
    if location is None:
        location = Point(0, 0)
    if dimensions is not None:
        dimension_azimuthal, dimension_crossazimuthal = dimensions
        if tilt is None and height is None and dimensions_projected is None:
            tilt = 0
        if tilt is not None:
            dimension_azimuthal_projected = dimension_azimuthal * math.cos(np.deg2rad(tilt)) if tilt != 90 else 0
        elif height is not None:
            dimension_azimuthal_projected = math.sqrt(dimension_azimuthal**2 + height**2)
    elif dimensions_projected is not None:
        dimension_azimuthal_projected, dimension_crossazimuthal = dimensions_projected
        dimension_azimuthal = None
        assert (
            tilt is not None or height is not None
        ), "If dimensions_projected are declared, tilt or height must be given, too."
    if tilt == 90 or dimension_azimuthal_projected == 0:
        height = dimension_azimuthal if dimension_azimuthal is not None else height
        polygon = __create_vertical_rectangle(
            location=location,
            dimension_crossazimuthal=dimension_crossazimuthal,
            azimuth=azimuth,
            height=height,
            z_offset=z_offset,
            z_centroid=z_centroid,
        )
    else:
        polygon = __create_horizontal_rectangle(
            location=location,
            dimensions=(dimension_azimuthal_projected, dimension_crossazimuthal),
            azimuth=azimuth,
            z_offset=z_offset if z_offset is not None else z_centroid,
            force3d=force3d,
        )
        if tilt or height:
            polygon = transform_rectangle_z_keep_xy(
                rectangle=polygon,
                tilt=tilt,
                height=height,
                azimuth=azimuth,
                z_offset=z_offset,
                z_centroid=z_centroid,
            )
    return polygon


def __create_horizontal_rectangle(
    location: Point,
    dimensions: tuple[float, float],
    azimuth: float = 0,
    z_offset: float = None,
    force3d: bool = False,
) -> Polygon:
    dim_az, dim_crossaz = dimensions
    o_xy = location.xy[0][0], location.xy[1][0]  # origin
    xyz_pointtuples = (
        (o_xy[0] - 0.5 * dim_az, o_xy[1] - 0.5 * dim_crossaz),
        (o_xy[0] + 0.5 * dim_az, o_xy[1] - 0.5 * dim_crossaz),
        (o_xy[0] + 0.5 * dim_az, o_xy[1] + 0.5 * dim_crossaz),
        (o_xy[0] - 0.5 * dim_az, o_xy[1] + 0.5 * dim_crossaz),
        (o_xy[0] - 0.5 * dim_az, o_xy[1] - 0.5 * dim_crossaz),
    )
    polygon = Polygon(xyz_pointtuples)
    polygon = affinity.rotate(polygon, 90 - azimuth)
    if force3d or z_offset is not None:
        polygon = shape2d_to_shape3d(polygon, z_offset or 0)
    return polygon


def __create_vertical_rectangle(
    location: Point,
    dimension_crossazimuthal: float,
    azimuth: float = 0,
    height: float = None,
    z_offset: float = None,
    z_centroid: float = None,
) -> Polygon:
    if z_offset is None:
        if z_centroid is not None:
            z_offset = z_centroid - height / 2
        else:
            z_offset = 0
    dim_crossaz = dimension_crossazimuthal
    o_xy = location.xy[0][0], location.xy[1][0]
    xyz_pointtuples = (
        (o_xy[0], o_xy[1] - 0.5 * dim_crossaz, z_offset),
        (o_xy[0], o_xy[1] - 0.5 * dim_crossaz, z_offset + height),
        (o_xy[0], o_xy[1] + 0.5 * dim_crossaz, z_offset + height),
        (o_xy[0], o_xy[1] + 0.5 * dim_crossaz, z_offset),
        (o_xy[0], o_xy[1] - 0.5 * dim_crossaz, z_offset),
    )
    polygon = Polygon(xyz_pointtuples)
    polygon = affinity.rotate(polygon, -azimuth - 90)
    return polygon


def transform_rectangle_z_keep_xy(
    rectangle: Polygon,
    tilt: float = None,
    height: float = None,
    z_offset: float = None,
    z_centroid: float = None,
    azimuth: float = None,
    azimuth_cardinal: CardinalOrientation = None,
):
    """
    - if `tilt`: tilt will be applied in azimuth direction.
    - if `height`: `height` will be applied to the "upper" vertices in azimuth
    direction.

    Lower vertices will have `z = z_offset`, upper vertices according to `tilt`.
    Original z values of rectangle will be overwritten (if any)
    """
    azs = edge_azimuths(rectangle)
    lengths = edge_lengths(rectangle)
    # lengths = lengths(rectangle)
    azimuth = azimuth if azimuth is not None else azimuth_cardinal.degrees
    i_downward_edge = closest_direction_index(azimuth, azs, False)
    i_upper_vertices = i_downward_edge, (i_downward_edge - 1) % 4
    i_lower_vertices = (i_downward_edge + 1) % 4, (i_downward_edge + 2) % 4
    dimension_azimuthal = lengths[i_downward_edge]
    if azimuth is not None:
        if (tilt is not None) and (0 <= tilt <= 90):
            dz = abs(math.tan(np.deg2rad(tilt)) * dimension_azimuthal)
        else:
            dz = abs(height)
    if z_offset is None:
        if z_centroid is not None:
            z_offset = z_centroid - dz / 2
        else:
            z_offset = 0
    xy_pointtuples = list(rectangle.exterior.coords)[:-1]
    xy_pointtuples = [
        (x, y, dz + z_offset) if i in i_upper_vertices else (x, y, z_offset)
        for i, (x, y, *_) in enumerate(xy_pointtuples)
    ]
    xy_pointtuples.append(xy_pointtuples[0])
    return Polygon(xy_pointtuples)


def create_line(location: Point, length, azimuth) -> LineString:
    origin_xy = location.xy[0][0], location.xy[1][0]
    dx = length
    x = origin_xy[0] + dx / 2
    y = origin_xy[1]
    linestring = LineString(((x + dx, y), (x - dx, y)))
    return affinity.rotate(linestring, azimuth)


def cut_shape_into_pieces(n: int, shape: Polygon):
    """
    Divide a polygon into `n` approximately equal pieces using parallel lines
    along the longest side of the polygon's minimum rotated rectangle.

    Parameters
    ----------
    n : int
        Number of pieces to divide the polygon into. Must be a positive integer.
    shape : Polygon
        The polygon to be divided. Must be an instance of `shapely.geometry.Polygon`.

    Returns
    -------
    List[Polygon]
        A list of `shapely.geometry.Polygon` objects representing the divided pieces.

    Raises
    ------
    ValueError
        If `n` is not a positive integer.
    TypeError
        If `shape` is not an instance of `Polygon`.

    Notes
    -----
    - The function calculates the minimum rotated rectangle of the polygon to determine
      its longest side and uses it as a reference for dividing the shape.
    """

    if n <= 0:
        raise ValueError("n must be a positive integer.")
    if not isinstance(shape, Polygon):
        raise TypeError("shape must be a Polygon instance.")

    def _cut_polygon_by_lines(polygon, lines):
        polygons = []
        for i, line in enumerate(lines):
            new_poligons = split(polygon, line)
            if i + 1 == len(lines):
                for poly in new_poligons.geoms:
                    polygons.append(poly)
            else:
                polygons.append(min((poly for poly in new_poligons.geoms), key=lambda poly: poly.area))
                polygon = max((poly for poly in new_poligons.geoms), key=lambda poly: poly.area)
        return polygons

    # Calculate the minimum rotated rectangle (bounding box)
    rotated_box = shape.minimum_rotated_rectangle
    # Removed unused variables box_coords and box_bounds
    corners = list(rotated_box.exterior.coords)[:-1]

    # get linstrings and coords of the sides
    sides = []
    for i in range(len(corners) - 1):
        sides.append((LineString([corners[i], corners[i + 1]]), corners[i], corners[i + 1]))
    sides.append((LineString([corners[-1], corners[0]]), corners[-1], corners[0]))

    # find shortest line with minimum y and x coords
    shortest_sides = [s for s in sides if s[0].length == min(s[0].length for s in sides)]
    shortest_side = min(shortest_sides, key=lambda s: (min(s[1][0], s[2][0]), min(s[1][1], s[2][1])))
    shortest_line = shortest_side[0]

    # create translation vector from longest side
    for ls, _, _ in sides:
        if ls != shortest_line and (ls.coords[0] == shortest_side[1] or ls.coords[0] == shortest_side[2]):
            longest_line = ls
            break

    dx = (longest_line.xy[0][1] - longest_line.xy[0][0]) / n
    dy = (longest_line.xy[1][1] - longest_line.xy[1][0]) / n

    translation_vector = (dx, dy)

    # create vector to make line long enought to correctly cut the shapes
    point_one_dx = shortest_line.xy[0][0] - shortest_line.xy[0][1]
    point_one_dy = shortest_line.xy[1][0] - shortest_line.xy[1][1]

    point_two_dx = -point_one_dx
    point_two_dy = -point_one_dy

    extended_start_point = (shortest_line.xy[0][0] + point_one_dx, shortest_line.xy[1][0] + point_one_dy)
    extended_end_point = (shortest_line.xy[0][1] + point_two_dx, shortest_line.xy[1][1] + point_two_dy)
    extended_line = LineString([extended_start_point, extended_end_point])

    moved_lines = []
    for i in range(1, n):
        moved_line = LineString(
            [
                (point[0] + translation_vector[0] * i, point[1] + translation_vector[1] * i)
                for point in extended_line.coords
            ]
        )
        moved_lines.append(moved_line)

    pieces = _cut_polygon_by_lines(shape, moved_lines)
    return pieces
