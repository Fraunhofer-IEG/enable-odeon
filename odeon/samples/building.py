import pandas as pd
import numpy as np
import random
from typing import List, Literal
from odeon.model import (
    Branch,
    Building,
    Commercial,
    Household,
    RefurbishmentStatus,
    BuildingType,
    Use,
    Commercial,
    CommercialType,
    ScalingReference,
    Resident,
)
from odeon.model.building_element import Roof
from .building_geometry import sample_building_geometry
from .building_physics import (
    sample_building_element_geometries,
    sample_building_physics,
    sample_building_element_physics,
)
from .device import sample_device_host


def sample_series(random_sample: bool = True, year: int = 2022, min_val: int = 0, max_val: int = 40) -> pd.Series:
    idx = pd.date_range(start=f"{year}-01-01", end=f"{year+1}-01-01", freq="h", inclusive="left")
    if random_sample:
        ts = pd.Series(
            random.choices(range(min_val, max_val + 1), k=len(idx)),
            index=idx,
            dtype="float64",
        )
    else:
        values = min_val + (max_val - min_val) / 2 * (1 + np.sin(0.002 * np.array(range(len(idx)))))
        ts = pd.Series(values, index=idx)
    return ts


def sample_building(
    branch: Branch,
    random_sample: bool = True,
    type: Literal["residential", "commercial", "mixed"] = "mixed",
    size: Literal["small", "medium", "large"] = "medium",
    create_geometry: bool = True,
    create_physics: bool = True,
    add_devices: List[Literal["heatpump", "boiler", "pv", "solar_thermal", "chp", "heating_storage"]] = None,
    add_demands: List[Literal["heating_demand", "dhw_demand", "electricity_demand", "cooling_demand"]] = None,
    year: int = 2022,
) -> Building:
    if add_devices is None or add_devices == True:
        add_devices = ["pv", "heatpump", "boiler"]
    elif add_devices == False:
        add_devices = []
    if add_demands is None or add_demands == True:
        add_demands = ["heating_demand", "dhw_demand", "electricity_demand"]
    elif add_demands == False:
        add_demands = []
    if random_sample:
        type = random.choice(["residential", "commercial", "mixed"])
        size = random.choice(["small", "medium", "large"])
        f = random.choice(
            [
                sample_residential_building,
                sample_commercial_building,
                sample_mixed_use_building,
            ]
        )
        b: Building = f(branch, random_sample, size)

    elif type == "residential":
        b = sample_residential_building(branch, random_sample, size)
    elif type == "commercial":
        b = sample_commercial_building(branch, random_sample, size)
    elif type == "mixed":
        b = sample_mixed_use_building(branch, random_sample, size)

    if create_geometry:
        sample_building_geometry(
            building=b,
            random_sample=random_sample,
            footprint_area=b.building_geometry_nominal.footprint_area,
            number_of_floors=b.number_of_floors,
        )
        rcbg = b._building_geometry_cuboid
        bes = sample_building_element_geometries(rcbg)
        b.add_building_elements(bes)

    if create_physics:
        b.building_thermal_zone = sample_building_physics(b.usable_area)
        sample_building_element_physics(b.building_elements)

    b.energy_system, surface = sample_device_host(random_sample, add_devices)
    if surface is not None:
        roofs = b._get_offspring_by_type(Roof)
        roofs[0].solar_surface = surface

    set_sample_demands(building=b, year=year, random_sample=random_sample, add_demands=add_demands)

    return b


def sample_residential_building(
    branch: Branch,
    random_sample: bool = True,
    size: Literal["small", "medium", "large"] = "medium",
) -> Building:
    b = _sample_building(random_sample, size)
    branch.add_objects(b)
    if random_sample:
        while b.usable_area_unassigned > 35:
            hh = sample_household(random_sample)
            if hh.net_floor_area > b.usable_area_unassigned:
                hh = sample_household(False, net_floor_area=b.usable_area_unassigned)
            b.add_building_units(hh)
    else:
        if size == "small":
            n_units = 1
        elif size == "medium":
            n_units = 6
        elif size == "large":
            n_units = 14

        for i in range(n_units):
            hh = sample_household(random_sample, net_floor_area=b.usable_area / n_units)
            b.add_building_units(hh)
    return b


def sample_mixed_use_building(
    branch: Branch,
    random_sample: bool = True,
    size: Literal["small", "medium", "large"] = "medium",
) -> Building:
    b = _sample_building(random_sample, size)
    branch.add_objects(b)

    if random_sample:
        while b.usable_area_unassigned > 35:
            f = random.choice([sample_household, sample_commercial])
            bu = f(random_sample)
            if bu.net_floor_area > b.usable_area_unassigned:
                bu = f(False, net_floor_area=b.usable_area_unassigned)
            b.add_building_units(bu)

    else:
        if size == "small":
            n_units = 1
        elif size == "medium":
            n_units = 6
        elif size == "large":
            n_units = 14

        for _ in range(int(n_units / 2)):
            hh = (sample_household(random_sample, net_floor_area=b.usable_area / n_units),)
            b.add_building_units(hh)
        for _ in range(int(n_units / 2), n_units):
            c = sample_commercial(random_sample, net_floor_area=b.usable_area / n_units)
            b.add_building_units(c)
    return b


def sample_commercial_building(
    branch: Branch,
    random_sample: bool = True,
    size: Literal["small", "medium", "large"] = "medium",
) -> Building:
    b = _sample_building(random_sample, size)
    branch.add_objects(b)
    b.use = Use.COMMERCIAL
    if random_sample:
        while b.usable_area_unassigned > 35:
            bu = sample_commercial(random_sample)
            if bu.net_floor_area > b.usable_area_unassigned:
                bu = sample_commercial(False, net_floor_area=b.usable_area_unassigned)
            b.add_building_units(bu)
    else:
        if size == "small":
            n_units = 1
        elif size == "medium":
            n_units = 4
        elif size == "large":
            n_units = 10
        for _ in range(n_units):
            c = sample_commercial(random_sample, net_floor_area=b.usable_area / n_units)
            b.add_building_units(c)

    return b


def _sample_building(random_sample: bool = True, size: Literal["small", "medium", "large"] = "medium") -> Building:
    if random_sample:
        if size == "small":
            number_of_floors = random.choice([1, 2])
            footprint_area = random.choice([50, 120])
            building_type = random.choice(
                [
                    BuildingType.DETACHED,
                    BuildingType.TERRACED,
                ]
            )
        elif size == "medium":
            number_of_floors = random.choice([2, 4, 6])
            footprint_area = random.choice([120, 200, 300])
            building_type = random.choice([BuildingType.DETACHED, BuildingType.TERRACED, BuildingType.HIGHRISE])
        elif size == "large":
            number_of_floors = random.choice([5, 9])
            footprint_area = random.choice([300, 500])
            building_type = random.choice([BuildingType.DETACHED, BuildingType.HIGHRISE])

        year_of_construction = random.randrange(1900, 2010)
        refurbishment_status = random.choice(
            [
                RefurbishmentStatus.EXISTING_STATE,
                RefurbishmentStatus.STANDARD_REFURBISHMENT,
                RefurbishmentStatus.AMBITIOUS_REFURBISHMENT,
            ]
        )

    else:
        if size == "small":
            number_of_floors = 2
            footprint_area = 70
            building_type = BuildingType.TERRACED
        elif size == "medium":
            number_of_floors = 3
            footprint_area = 150
            building_type = BuildingType.DETACHED
        elif size == "large":
            number_of_floors = 6
            footprint_area = 300
            building_type = BuildingType.HIGHRISE

        year_of_construction = 1958
        refurbishment_status = RefurbishmentStatus.STANDARD_REFURBISHMENT

    b = Building()
    b.building_type = building_type
    b.year_of_construction = year_of_construction
    b.refurbishment_status = refurbishment_status
    b.number_of_floors = number_of_floors
    b.usable_area = footprint_area * number_of_floors
    b.building_geometry_nominal.footprint_area = footprint_area
    b.usable_area = b.building_geometry_nominal.footprint_area * b.number_of_floors
    return b


def sample_household(random_sample: bool = True, net_floor_area=80) -> Household:
    hh = Household()
    if random_sample:
        n_residents = random.randrange(1, 5)
        hh.net_floor_area = random.randrange(50, 100)
    else:
        n_residents = 3
        hh.net_floor_area = net_floor_area
    for _ in range(n_residents):
        hh.add_residents(Resident())
    return hh


def sample_commercial(random_sample: bool = True, net_floor_area=100) -> Commercial:
    c = Commercial()
    if random_sample:
        c.net_floor_area = random.choice(range(0, 200))
        c.commercial_type = random.choice(list(CommercialType))
        c.scaling_reference = ScalingReference(name="Erwerbstaetige", amount=random.choice(range(0, 20)))
    else:
        c.net_floor_area = net_floor_area
        c.commercial_type = CommercialType.GROCERIES
        c.scaling_reference = ScalingReference(name="Erwerbstaetige", amount=20)
    return c


def set_sample_demands(
    building: Building,
    year: int,
    random_sample: bool = True,
    add_demands: List[Literal["heating_demand", "dhw_demand", "electricity_demand", "cooling_demand"]] = None,
) -> None:
    if add_demands is None:
        add_demands = ["heating_demand", "dhw_demand", "electricity_demand", "cooling_demand"]
    for bu in building.building_units:
        if "heating_demand" in add_demands:
            bu.heating_demand = sample_series(random_sample, year)
        if "dhw_demand" in add_demands:
            bu.dhw_demand = sample_series(random_sample, year)
        if "electricity_demand" in add_demands:
            bu.electricity_demand = sample_series(random_sample, year)
        if "cooling_demand" in add_demands:
            bu.cooling_demand = sample_series(random_sample, year)
