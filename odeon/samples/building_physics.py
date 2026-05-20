from typing import List
from odeon.model import (
    RoofedCuboidBuildingGeometry,
    Building,
    BuildingThermalZone,
    BuildingElement,
    Floor,
    Door,
    Wall,
    Roof,
    Window,
    FloorPhysics,
    WindowPhysics,
    RoofPhysics,
    WindowType,
    DoorPhysics,
    WallPhysics,
    AdjacentEnvironment,
    MassDistribution,
    Transparency,
)


def sample_building_physics(heated_area: float) -> BuildingThermalZone:
    bp = BuildingThermalZone()
    bp.heated_area = heated_area
    bp.air_exchange_rate_use = 0.4
    bp.internal_heat_capacity_j_per_k = heated_area * 10000
    bp.heattranscoef_thermal_bridges_w_per_sqm_k = 0.2
    bp.heated_volume = heated_area * 3
    return bp


def sample_building_element_geometries(rcbg: RoofedCuboidBuildingGeometry) -> List[BuildingElement]:
    building_elements = []
    building_elements += [Floor(element_geometry=g) for g in rcbg.floor_geometries]
    building_elements += [Wall(element_geometry=g) for g in rcbg.wall_geometries]
    building_elements += [Roof(element_geometry=g) for g in rcbg.roof_geometries]
    building_elements += [Window(element_geometry=g) for g in rcbg.window_geometries]
    building_elements += [Door(element_geometry=g) for g in rcbg.door_geometries]
    return building_elements


def sample_building_element_physics(building_elements: List[BuildingElement]):
    for f in [be for be in building_elements if isinstance(be, Floor)]:
        f.element_physics = FloorPhysics()
        f.adjacent_environment = AdjacentEnvironment.GROUND
        f.element_physics.u_value_w_per_sqm_k = 0.5
        f.element_physics.specific_heat_capacity_j_per_sqm_k = 110000
        f.element_physics.mass_distribution = MassDistribution.MASS_CONCENTRATED_INSIDE
        f.element_physics.transparency = Transparency.OPAQUE
        f.element_physics.view_factor = 0
        f.element_physics.shading_factor = 0

    for w in [be for be in building_elements if isinstance(be, Wall)]:
        w.element_physics = WallPhysics()
        w.adjacent_environment = AdjacentEnvironment.AIR
        w.element_physics.u_value_w_per_sqm_k = 0.3
        w.element_physics.specific_heat_capacity_j_per_sqm_k = 50000
        w.element_physics.mass_distribution = MassDistribution.MASS_CONCENTRATED_INSIDE
        w.element_physics.transparency = Transparency.OPAQUE
        w.element_physics.view_factor = 0.5
        w.element_physics.shading_factor = 0.6

    for r in [be for be in building_elements if isinstance(be, Roof)]:
        r.element_physics = RoofPhysics()
        r.adjacent_environment = AdjacentEnvironment.AIR
        r.element_physics.u_value_w_per_sqm_k = 0.3
        r.element_physics.specific_heat_capacity_j_per_sqm_k = 50000
        r.element_physics.mass_distribution = MassDistribution.MASS_CONCENTRATED_INSIDE
        r.element_physics.transparency = Transparency.OPAQUE
        r.element_physics.view_factor = 0.5
        r.element_physics.shading_factor = 0.6

    for w in [be for be in building_elements if isinstance(be, Window)]:
        w.element_physics = WindowPhysics()
        w.adjacent_environment = AdjacentEnvironment.AIR
        w.element_physics.u_value_w_per_sqm_k = 0.5
        w.element_physics.transparency = Transparency.TRANSPARENT
        w.element_physics.view_factor = 0
        w.element_physics.shading_factor = 0.2
        w.element_physics.frame_portion = 0.2
        w.element_physics.window_type = WindowType.DOUBLE_THERMAL_INSULATION_GLAZING
        w.element_physics.total_solar_energy_transmittance = 0.5

    for d in [be for be in building_elements if isinstance(be, Door)]:
        d.element_physics = DoorPhysics()
        d.adjacent_environment = AdjacentEnvironment.AIR
        d.element_physics.u_value_w_per_sqm_k = 0.5
        d.element_physics.transparency = Transparency.TRANSPARENT
        d.element_physics.view_factor = 0.5
        d.element_physics.shading_factor = 0.2
