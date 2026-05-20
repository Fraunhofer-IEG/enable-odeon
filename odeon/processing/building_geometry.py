import math
import numbers

from shapely.affinity import rotate
from shapely.geometry.polygon import Polygon

from ..model.building import Building
from ..model.building_geometry import (
    BuildingGeometry,
    FootprintNominalBuildingGeometry,
    RoofedCuboidBuildingGeometry,
    RoofType,
)
from ..model.geometry import TiltedRectangleGeometry, Geometry
from ..model.building_element import Door, Floor, Roof, Wall, Window
from ..model.base_geometry import CardinalOrientation

from .geometry_cartesian import (
    closest_direction_index,
    create_prism,
    create_rectangle,
    perpendicular,
)


def geometry_creatable(bg: BuildingGeometry):
    """returns whether geometry elements can be created from the data set in `bg`"""

    res = True
    res &= bg.building_height is not None or bg.eaves_height is not None
    res &= bg.overhang_length is not None or bg.roof_length is not None
    if bg.roof_type is RoofType.FLAT:
        res &= bg.overhang_width is not None
    else:
        res &= (
            bg.roof_height_net is not None
            or (bg.building_height is not None and bg.eaves_height is not None)
            or bg.roof_tilt is not None
            or (bg.roof_height is not None and (bg.overhang_height is not None or bg.overhang_width is not None))
        )
        res &= (
            bg.single_roof_width is not None
            or bg.overhang_width is not None
            or (bg.overhang_height is not None and bg.roof_tilt is not None)
        )
    res &= (bg.roof_type is RoofType.FLAT and bg.overhang_length == bg.overhang_width) or (
        bg.roof_orientation is not None
        or bg.ridge_orientation is not None
        or bg.roof_orientation_cardinal is not None
        or bg.ridge_orientation_cardinal is not None
        or bg.long_ridged_roof is not None
    )
    res &= (
        (bg.door_factor is not None)
        & (bg.window_roof_factor is not None)
        & (bg.window_wall_factor is not None)
        & (bg.window_roof_vertical is not None)
    )
    res &= bg.altitude is not None
    return res


def footprint_nominal_to_roofed_cuboid(building: Building):
    """
    create a `RoofedCuboidBuildingGeometry` by analysing `building`'s
    `FootprintNominalBuildingGeometry` and add it to `building afterwards.
    """
    rcbg = _roofed_cuboid_from_footprint_nominal(building.building_geometry_nominal)
    geometries_subgeometries = _create_roofed_cuboid_geometries(rcbg, building.building_geometry_nominal.footprint)
    building.building_geometry_cuboid = rcbg
    building_elements = []
    building_elements += [Floor(element_geometry=g) for g in rcbg.floor_geometries]
    building_elements += [Wall(element_geometry=g) for g in rcbg.wall_geometries]
    building_elements += [Roof(element_geometry=g) for g in rcbg.roof_geometries]
    building_elements += [Window(element_geometry=g) for g in rcbg.window_geometries]
    building_elements += [Door(element_geometry=g) for g in rcbg.door_geometries]

    # find and set subelements:
    subelements = []
    for be in building_elements:
        subgeometry = next((gs[1] for gs in geometries_subgeometries if gs[0] is be.element_geometry), None)
        if subgeometry is not None:
            subelement = next(be for be in building_elements if be.element_geometry is subgeometry)
            be.add_sub_elements(subelement)
            subelements.append(subelement)

    building_elements = [be for be in building_elements if be not in subelements]
    building.add_building_elements(building_elements)


def _roofed_cuboid_from_footprint_nominal(fnbg: FootprintNominalBuildingGeometry) -> RoofedCuboidBuildingGeometry:
    assert isinstance(fnbg, FootprintNominalBuildingGeometry)
    rcbg = RoofedCuboidBuildingGeometry()
    rcbg.roof_type = fnbg.roof_type
    rcbg.building_height = fnbg.building_height
    rcbg.eaves_height = fnbg.eaves_height
    rcbg.roof_height = fnbg.roof_height
    rcbg.roof_height_net = fnbg.roof_height_net
    rcbg.roof_tilt = fnbg.roof_tilt
    rcbg.roof_length = fnbg.roof_length
    rcbg.overhang_length = fnbg.overhang_length
    rcbg.overhang_width = fnbg.overhang_width
    rcbg.overhang_height = fnbg.overhang_height
    rcbg.roof_orientation = fnbg.roof_orientation
    rcbg.ridge_orientation = fnbg.ridge_orientation
    rcbg.roof_orientation_cardinal = fnbg.roof_orientation_cardinal
    rcbg.ridge_orientation_cardinal = fnbg.ridge_orientation_cardinal
    rcbg.long_ridged_roof = fnbg.long_ridged_roof
    rcbg.single_roof_width = fnbg.single_roof_width
    rcbg.single_roof_width_net = fnbg.single_roof_width_net
    rcbg.altitude = fnbg.altitude
    rcbg.window_wall_factor = fnbg.window_wall_factor
    rcbg.door_factor = fnbg.door_factor
    rcbg.window_roof_factor = fnbg.window_roof_factor
    rcbg.window_roof_vertical = fnbg.window_roof_vertical
    return rcbg


def _create_roofed_cuboid_geometries(
    bg: RoofedCuboidBuildingGeometry,
    footprint: Geometry,
) -> list[tuple[TiltedRectangleGeometry, TiltedRectangleGeometry]]:
    """
    required input:
    - for any `roof_type`:
        - `overhang_width`
        - `overhang_length` or `roof_length`
    - for `roof_type == FLAT` all of:
        - `building_height` or `eaves_height`
    - for `roof_type == GABLE` and `roof_type == SHED` all of:
        - `building_height` or `eaves_height`
        - `roof_height_net` or (`building_height` and `eaves_height`) or
        `roof_tilt` or (`roof_height` and
        (`overhang_height` or `overhang_width`))
        - `single_roof_width` or `overhang_width` or (`overhang_height` and
        `roof_tilt`)
        - `overhang_length`
        - `roof_orientation` or `ridge_orientation` or `roof_orientation_cardinal`
        or `ridge_orientation_cardinal` or `long_ridged_roof`
    - `door_factor`, `window_roof_factor`, `window_wall_factor`, `window_roof_vertical`

    Returns pairs of elements and their sub-elements (i.e walls and
    windows/doors in that walls, roofs and windows in that roof). Geometries will
    already be added to `bg`, though.

    what else:
    - created walls will be in order: 2x along ridge direction, 2x along roof
    direction
    """
    assert footprint.is_polygon
    assert geometry_creatable(bg), "insufficient data"
    footprint = TiltedRectangleGeometry.from_generic(footprint)
    dimensions = footprint.dimensions
    orientations = footprint.orientations

    # create walls and floor (we had floor before, but without altitude):
    floor_polygon, wall_polygons, _ = create_prism(footprint.polygon, bg.eaves_height, bg.altitude)
    wall_geometries = [TiltedRectangleGeometry(shape=wall) for wall in wall_polygons]
    floor_geometries = [TiltedRectangleGeometry(shape=floor_polygon)]

    # decide on ridge orientation:
    if bg.ridge_orientation is None:
        if bg.ridge_orientation_cardinal is not None:
            bg.ridge_orientation = bg.ridge_orientation_cardinal.degrees
        elif bg.roof_orientation is not None:
            bg.ridge_orientation = perpendicular(bg.roof_orientation)
        elif bg.roof_orientation_cardinal is not None:
            bg.ridge_orientation = perpendicular(bg.roof_orientation_cardinal.degrees)
        elif bg.long_ridged_roof is not None:
            if bg.long_ridged_roof:
                assert dimensions[0] != dimensions[1]
                if (dimensions[0] > dimensions[1] and bg.long_ridged_roof) or (
                    dimensions[0] < dimensions[1] and not bg.long_ridged_roof
                ):
                    bg.ridge_orientation = orientations[0]
                else:
                    bg.ridge_orientation = orientations[1]
    assert bg.ridge_orientation is not None

    # sort dimensions:
    idx_ridge = closest_direction_index(bg.ridge_orientation, orientations) % 2
    bg.dimensions = [dimensions[idx_ridge], dimensions[1 - idx_ridge]]
    bg.ridge_orientation = orientations[idx_ridge]
    bg.roof_orientation = orientations[1 - idx_ridge]
    bg.ridge_orientation_cardinal = CardinalOrientation.by_closest_degrees(bg.ridge_orientation)
    bg.roof_orientation_cardinal = CardinalOrientation.by_closest_degrees(bg.roof_orientation)

    # set roof type constraints:
    if bg.roof_type is RoofType.FLAT:
        bg.roof_tilt = 0
        bg.roof_height = 0
        bg.roof_height_net = 0
        bg.overhang_height = 0
    if bg.roof_type is RoofType.SHED:
        bg.overhang_height = bg.overhang_height if bg.overhang_width > 0 else 0
    if bg.roof_type in [RoofType.FLAT, RoofType.SHED]:
        bg.single_roof_width_net = bg.dimensions[1]
        bg.single_roof_width = bg.single_roof_width_net + 2 * bg.overhang_width
    elif bg.roof_type is RoofType.GABLE:
        bg.single_roof_width_net = bg.dimensions[1] / 2
        bg.single_roof_width = bg.single_roof_width_net + bg.overhang_width
        bg.overhang_width = bg.overhang_width if bg.overhang_width > 0 else 0

    # fill data gaps:
    __harmonize(bg)

    # set & create remaining:
    bg.floor_geometries = floor_geometries  # TODO create new function for floor
    bg.wall_geometries = wall_geometries  # TODO create new function for walls
    __create_roof_geometries(bg)
    walls_windows = __create_window_wall_geometries(bg)
    roofs_windows = __create_window_roof_geometries(bg)
    walls_doors = __create_door_geometries(bg)

    return walls_windows + roofs_windows + walls_doors


def __harmonize(bg: BuildingGeometry):
    def make_abc(ab_to_c, ac_to_b, bc_to_a):
        def abc(a, b, c):
            n_vars = len([x for x in [a, b, c] if x is not None])
            if n_vars == 2:
                a = a if a is not None else bc_to_a(b, c)
                b = b if b is not None else ac_to_b(a, c)
                c = c if c is not None else ab_to_c(a, b)
            # elif n_vars == 3:
            #     assert a == bc_to_a(b, c), "overdefined with contradictions"
            #     assert b == ac_to_b(a, c), "overdefined with contradictions"
            #     assert c == ab_to_c(a, b), "overdefined with contradictions"
            return a, b, c

        return abc

    def make_a_plus_b_equals_c():
        return make_abc(lambda a, b: a + b, lambda a, c: c - a, lambda b, c: c - b)

    def make_opposite_over_adjacent_equals_tangens():
        return make_abc(
            lambda a, b: math.degrees(math.atan2(a, b)),
            lambda a, c: a / math.tan(math.radians(c)),
            lambda b, c: b * math.tan(math.radians(c)),
        )

    n_missing = __n_missing(bg)
    while not __complete(bg):
        bg.roof_height_net, bg.overhang_height, bg.roof_height = make_a_plus_b_equals_c()(
            bg.roof_height_net, bg.overhang_height, bg.roof_height
        )  # roof_height_net + overhang_height = roof_height
        bg.eaves_height, bg.roof_height_net, bg.building_height = make_a_plus_b_equals_c()(
            bg.eaves_height, bg.roof_height_net, bg.building_height
        )  # eaves_height + roof_height_net = building_height
        bg.roof_height, bg.single_roof_width, bg.roof_tilt = make_opposite_over_adjacent_equals_tangens()(
            bg.roof_height, bg.single_roof_width, bg.roof_tilt
        )  # roof_height/single_roof_width = tan(roof_tilt)
        bg.overhang_height, bg.overhang_width, bg.roof_tilt = make_opposite_over_adjacent_equals_tangens()(
            bg.overhang_height, bg.overhang_width, bg.roof_tilt
        )  # overhang_height/overhang_width = tan(roof_tilt)
        n_missing_1 = __n_missing(bg)
        assert n_missing_1 < n_missing, "can't solve system - underdefined?"
        n_missing = n_missing_1


def __n_missing(bg: BuildingGeometry):
    xs = [
        bg.dimensions,
        bg.roof_type,
        bg.building_height,
        bg.eaves_height,
        bg.roof_height,
        bg.roof_height_net,
        bg.roof_tilt,
        bg.overhang_length,
        bg.overhang_width,
        bg.overhang_height,
        bg.roof_orientation,
        bg.ridge_orientation,
        bg.single_roof_width,
        bg.altitude,
    ]
    return len([x for x in xs if x is None])


def __complete(bg: BuildingGeometry):
    return __n_missing(bg) == 0


def __closest_rectangle_azimuths(polygon: Polygon, target: float):
    xs = [*polygon.exterior.xy[0]]
    ys = [*polygon.exterior.xy[1]]
    dx10 = xs[1] - xs[0]
    dy10 = ys[1] - ys[0]
    dx21 = xs[2] - xs[1]
    dy21 = ys[2] - ys[1]

    azimuths = []
    if abs(dy10) == 0:
        azimuths.append(math.degrees(math.copysign(math.pi / 2, dx10)))
    else:
        azimuths.append(math.degrees(math.atan(dx10 / dy10)))

    if abs(dy21) == 0:
        azimuths.append(math.degrees(math.copysign(math.pi / 2, dx21)))
    else:
        azimuths.append(math.degrees(math.atan(dx21 / dy21)))

    idx = closest_direction_index(target=target, candidates=azimuths, allow_antiparallel=True)
    azimuth = azimuths[idx]
    azimuth_perpendicular = azimuths[1 - idx]
    return azimuth, azimuth_perpendicular


def __create_roof_geometries(bg: RoofedCuboidBuildingGeometry) -> list[TiltedRectangleGeometry]:
    dimensions = bg.dimensions
    xc, yc = bg.footprint.centroid.x, bg.footprint.centroid.y

    zlo = bg.altitude + bg.eaves_height - bg.overhang_height  # roof lower edges altitude
    zhi = bg.altitude + bg.building_height  # roof top altitude
    # x values differ in cross-ridge direction:
    xlo = xc - dimensions[1] / 2 - bg.overhang_width  # first edge in cross-ridge direction
    xhi = xc + dimensions[1] / 2 + bg.overhang_width  # roof second edge
    # y values differ in ridge direction:
    ylo = yc - dimensions[0] / 2 - bg.overhang_length  # first edge in ridge direction
    yhi = yc + dimensions[0] / 2 + bg.overhang_length  # roof second edge

    if bg.roof_type is RoofType.FLAT:
        xyz_pointtuples = [[[xlo, ylo, zhi], [xlo, yhi, zhi], [xhi, yhi, zhi], [xhi, ylo, zhi]]]
    elif bg.roof_type is RoofType.SHED:
        xyz_pointtuples = [[[xlo, ylo, zlo], [xlo, yhi, zlo], [xhi, yhi, zhi], [xhi, ylo, zhi]]]
    elif bg.roof_type is RoofType.GABLE:
        xyz_pointtuples = [
            [[xlo, ylo, zlo], [xlo, yhi, zlo], [xc, yhi, zhi], [xc, ylo, zhi]],
            [[xhi, ylo, zlo], [xhi, yhi, zlo], [xc, yhi, zhi], [xc, ylo, zhi]],
        ]
    xyz_pointtuples = [[*xyzp, xyzp[0]] for xyzp in xyz_pointtuples]  # repeat first vertex
    roof_polygons = [Polygon(xyzp) for xyzp in xyz_pointtuples]

    # calculate azimuths in 3035. (bg.ridge_orientation is expressed in degrees towards geographic North, azimuth_ridge
    # is expressed as degrees towards positive y)
    azimuth_ridge, azimuth_roof = __closest_rectangle_azimuths(bg.footprint.polygon, bg.ridge_orientation)
    roof_polygons = [rotate(p, -azimuth_ridge, origin=bg.footprint.centroid) for p in roof_polygons]

    bg.roof_geometries = [TiltedRectangleGeometry(shape=p, altitude=bg.altitude) for p in roof_polygons]


def __create_window_wall_geometries(
    bg: RoofedCuboidBuildingGeometry,
) -> list[tuple[TiltedRectangleGeometry, TiltedRectangleGeometry]]:
    """
    Create geometries for windows in walls.
    """
    # TODO doubled code with __create_door_geometries
    assert bg.window_wall_factor is not None
    assert len(bg.wall_geometries) == 4
    if isinstance(bg.window_wall_factor, numbers.Number):
        bg.window_wall_factor = [bg.window_wall_factor for _ in range(4)]
    else:
        azimuths = [w.azimuth for w in bg.wall_geometries]
        if isinstance(bg.window_wall_factor, (list, tuple)) and len(bg.window_wall_factor) == 2:
            # = along ridge oriented walls, along roof oriented walls (=in roof orientation, in ridge orientation)
            bg.window_wall_factor = {
                bg.roof_orientation: bg.window_wall_factor[0],
                bg.roof_orientation + 180: bg.window_wall_factor[0],
                bg.ridge_orientation: bg.window_wall_factor[1],
                bg.ridge_orientation + 180: bg.window_wall_factor[1],
            }
        if isinstance(bg.window_wall_factor, dict):
            indices = {closest_direction_index(k, azimuths): v for k, v in bg.window_wall_factor.items()}
            indices = {k: indices[k] if k in indices else 0 for k in range(4)}
        bg.window_wall_factor = [*dict(sorted(indices.items())).values()]

    window_polygons = []
    ret = []
    for wall, wfw in zip(bg.wall_geometries, bg.window_wall_factor):
        if wfw > 0:
            window_polygons.append(
                create_rectangle(
                    location=wall.centroid,
                    dimensions=(wall.dimensions[0] * math.sqrt(wfw), wall.dimensions[1] * math.sqrt(wfw)),
                    azimuth=wall.azimuth,
                    tilt=wall.tilt,
                    z_centroid=wall.z_centroid,
                    force3d=True,
                )
            )
            window_geometry = TiltedRectangleGeometry(shape=window_polygons[-1])
            ret.append((wall, window_geometry))
            bg.window_wall_geometries.append(window_geometry)

    return ret


def __create_window_roof_geometries(
    bg: RoofedCuboidBuildingGeometry,
) -> list[tuple[TiltedRectangleGeometry, TiltedRectangleGeometry]]:
    """
    Create geometries for windows in roofs.
    """
    assert bg.window_roof_factor is not None
    assert 1 <= len(bg.roof_geometries) <= 2
    if bg.roof_type not in [RoofType.SHED, RoofType.GABLE]:
        bg.window_roof_factor = 0
        return []
    if isinstance(bg.window_roof_factor, numbers.Number):
        bg.window_roof_factor = [bg.window_roof_factor for _ in range(len(bg.roof_geometries))]
    elif isinstance(bg.window_roof_factor, dict):
        azimuths = [w.azimuth for w in bg.roof_geometries]
        indices = {closest_direction_index(k, azimuths): v for k, v in bg.window_roof_factor.items()}
        indices = {k: indices[k] if k in indices else 0 for k in range(4)}
        bg.window_roof_factor = [*dict(sorted(indices.items())).values()]
    else:
        raise TypeError()

    window_polygons = []
    ret = []
    for roof, wfr in zip(bg.roof_geometries, bg.window_roof_factor):
        if wfr > 0:
            window_polygons.append(
                create_rectangle(
                    location=roof.centroid,
                    dimensions=(roof.dimensions[0] * math.sqrt(wfr), roof.dimensions[1] * math.sqrt(wfr)),
                    azimuth=roof.azimuth,
                    tilt=90 if bg.window_roof_vertical else roof.tilt,
                    z_centroid=roof.z_centroid,
                    force3d=True,
                )
            )
            window_geometry = TiltedRectangleGeometry(shape=window_polygons[-1])
            ret.append((roof, window_geometry))
            bg.window_roof_geometries.append(window_geometry)

    return ret


def __create_door_geometries(
    bg: RoofedCuboidBuildingGeometry,
) -> list[tuple[TiltedRectangleGeometry, TiltedRectangleGeometry]]:
    """
    Create geometries for doors (in walls).
    """
    assert bg.door_factor is not None
    assert len(bg.wall_geometries) == 4
    if isinstance(bg.door_factor, numbers.Number):
        bg.door_factor = [bg.door_factor for _ in range(4)]
    else:
        azimuths = [w.azimuth for w in bg.wall_geometries]
        if isinstance(bg.door_factor, (list, tuple)) and len(bg.door_factor) == 2:
            # = along ridge oriented walls, along roof oriented walls (=in roof orientation, in ridge orientation)
            bg.door_factor = {
                bg.roof_orientation: bg.door_factor[0],
                bg.roof_orientation + 180: bg.door_factor[0],
                bg.ridge_orientation: bg.door_factor[1],
                bg.ridge_orientation + 180: bg.door_factor[1],
            }
        if isinstance(bg.door_factor, dict):
            indices = {closest_direction_index(k, azimuths): v for k, v in bg.door_factor.items()}
            indices = {k: indices[k] if k in indices else 0 for k in range(4)}
        bg.door_factor = [*dict(sorted(indices.items())).values()]

    door_polygons = []
    ret = []
    for wall, df in zip(bg.wall_geometries, bg.door_factor):
        if df > 0:
            door_polygons.append(
                create_rectangle(
                    location=wall.centroid,
                    dimensions=(wall.dimensions[0] * math.sqrt(df), wall.dimensions[1] * math.sqrt(df)),
                    azimuth=wall.azimuth,
                    tilt=90,
                    z_offset=wall.z_min,
                    force3d=True,
                )
            )
            door_geometry = TiltedRectangleGeometry(shape=door_polygons[-1])
            ret.append((wall, door_geometry))
            bg.door_geometries.append(door_geometry)

    return ret
