import pandas as pd
from typing import List, Literal
from ..model import Project, Branch, Projector
from .weather import sample_weather
from .building import sample_building
from .geometry import LATLON_BERLIN_EUREF, LATLON_BOCHUM_IEG


def sample_project(
    n_branches: int = 0,
    n_buildings: int = 20,
    random_sample: bool = True,
    type: Literal["residential", "commercial", "mixed"] = "mixed",
    size: Literal["small", "medium", "large"] = "medium",
    create_geometry: bool = True,
    create_physics: bool = True,
    add_devices: List[Literal["heatpump", "boiler", "pv", "solar_thermal", "chp", "heating_storage"]] = None,
    add_demands: List[Literal["heating_demand", "dhw_demand", "electricity_demand", "cooling_demand"]] = None,
    root_year: int = 2022,
) -> Project:
    if add_demands is None or add_demands == True:
        add_demands = ["heating_demand", "dhw_demand", "electricity_demand"]
    elif add_demands == False:
        add_demands = []
    if add_devices is None:
        add_devices = ["pv", "heatpump", "boiler"]
    elif add_devices == False:
        add_devices = []
    project = Project(projector=Projector(origin=LATLON_BOCHUM_IEG))
    project.main_branch = sample_branch(
        n_buildings=n_buildings,
        random_sample=random_sample,
        type=type,
        size=size,
        create_geometry=create_geometry,
        create_physics=create_physics,
        add_devices=add_devices,
        add_demands=add_demands,
        year=root_year,
    )
    for _ in range(n_branches):
        branch = sample_branch(
            n_buildings=n_buildings,
            random_sample=random_sample,
            type=type,
            size=size,
            create_geometry=create_geometry,
            create_physics=create_physics,
            add_devices=add_devices,
            add_demands=add_demands,
            year=root_year,
        )
        project.add_branches(branch)
    return project


def sample_branch(
    n_buildings: int = 20,
    random_sample: bool = True,
    type: Literal["residential", "commercial", "mixed"] = "mixed",
    size: Literal["small", "medium", "large"] = "medium",
    create_geometry: bool = True,
    create_physics: bool = True,
    add_devices: List[Literal["heatpump", "boiler", "pv", "solar_thermal", "chp", "heating_storage"]] = None,
    add_demands: List[Literal["heating_demand", "dhw_demand", "electricity_demand", "cooling_demand"]] = None,
    year: int = 2022,
) -> Branch:
    if add_demands is None or add_demands == True:
        add_demands = ["heating_demand", "dhw_demand", "electricity_demand"]
    elif add_demands == False:
        add_demands = []
    if add_devices is None:
        add_devices = ["pv", "heatpump", "boiler"]
    elif add_devices == False:
        add_devices = []
    branch = Branch(year=year)
    for _ in range(n_buildings):
        building = sample_building(
            branch=branch,
            random_sample=random_sample,
            type=type,
            size=size,
            create_geometry=create_geometry,
            create_physics=create_physics,
            add_devices=add_devices,
            add_demands=add_demands,
            year=year,
        )
        branch.add_objects(building)
    branch.weather = sample_weather(year)
    return branch
