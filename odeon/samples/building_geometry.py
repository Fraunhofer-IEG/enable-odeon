from math import sqrt
import random
from odeon.model import (
    Building,
    FootprintNominalBuildingGeometry,
    Geometry,
    CardinalOrientation,
    RoofType,
)
from odeon.processing.geometry_cartesian import create_rectangle
from odeon.processing.building_geometry import footprint_nominal_to_roofed_cuboid

WINDOW_WALL_FACTOR = 0.17  # assumption
WINDOW_ROOF_FACTOR_PER_ROOF_TYPE = {
    RoofType.FLAT: 0,
    RoofType.SHED: 0.15,
    RoofType.GABLE: 0.2,
}  # assumption
DOOR_FACTOR_PER_FLOOR = 0.02  # assumption
OVERHANG_LENGTH_RANGE = [0, 0.7]  # assumption
OVERHANG_WIDTH_RANGE = [0, 0.7]  # assumption
ROOF_TILT_RANGE_GABLE = [30, 50]  # assumption
ROOF_TILT_RANGE_SHED = [15, 35]  # assumption


def sample_building_geometry(
    building: Building,
    random_sample: bool = True,
    footprint_area: float = 100,
    number_of_floors: int = 3,
) -> None:
    bgn = sample_building_geometry_nominal(
        random_sample=random_sample,
        footprint_area=footprint_area,
        number_of_floors=number_of_floors,
    )
    building.building_geometry_nominal = bgn
    footprint_nominal_to_roofed_cuboid(building)


def sample_building_geometry_nominal(
    random_sample: bool = True,
    footprint_area: float = 100,
    number_of_floors: int = 3,
) -> FootprintNominalBuildingGeometry:
    bgn = FootprintNominalBuildingGeometry()
    geometry = Geometry()
    geometry.shape = create_rectangle(dimensions=(0.5 * sqrt(footprint_area), 2 * sqrt(footprint_area)))

    if random_sample:
        bgn.door_factor = {random.choice(list(CardinalOrientation)): DOOR_FACTOR_PER_FLOOR}
        bgn.window_roof_factor = WINDOW_ROOF_FACTOR_PER_ROOF_TYPE.get(bgn.roof_type, 0)
        bgn.window_wall_factor = WINDOW_WALL_FACTOR
        bgn.roof_type = random.choice(list(WINDOW_ROOF_FACTOR_PER_ROOF_TYPE.keys()))
        bgn.overhang_length = random.uniform(*OVERHANG_LENGTH_RANGE)
        bgn.overhang_width = random.uniform(*OVERHANG_WIDTH_RANGE)
        if bgn.roof_type is RoofType.FLAT:
            bgn.roof_tilt = 0
        elif bgn.roof_type is RoofType.SHED:
            bgn.roof_tilt = random.uniform(*ROOF_TILT_RANGE_SHED)
        elif bgn.roof_type is RoofType.GABLE:
            bgn.roof_tilt = random.uniform(*ROOF_TILT_RANGE_GABLE)

    else:
        bgn.door_factor = {CardinalOrientation.NORTHWEST: DOOR_FACTOR_PER_FLOOR}
        bgn.window_roof_factor = WINDOW_ROOF_FACTOR_PER_ROOF_TYPE.get(bgn.roof_type, 0)
        bgn.window_wall_factor = WINDOW_WALL_FACTOR
        bgn.roof_type = RoofType.GABLE
        bgn.overhang_length = 0.2
        bgn.overhang_width = 0.2
        bgn.roof_tilt = 35

    if (
        bgn.roof_orientation is None
        and bgn.ridge_orientation is None
        and bgn.roof_orientation_cardinal is None
        and bgn.ridge_orientation_cardinal is None
        and bgn.long_ridged_roof is None
    ):
        bgn.long_ridged_roof = True

    bgn.footprint = geometry
    bgn.building_height = number_of_floors * 3
    bgn.altitude = 10
    bgn.eaves_height = (number_of_floors - 0.9) * 3
    bgn.roof_height = 3

    return bgn
