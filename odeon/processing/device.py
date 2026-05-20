from typing import Literal
import numpy as np
import pandas as pd

from ..model.base import Object
from ..model.building_element import Roof, Wall, BuildingElement
from ..model.building import Building, Site, Structure, StructureGroup
from ..model.building_unit import BuildingUnit
from ..model.asset import Asset
from ..model.energy_system import EnergySystem
from ..model.decision import DecisionState
from ..model.energy import Medium
from ..model.device import (
    AirWaterHeatpump,
    Battery,
    BoreholeHeatExchanger,
    BrineWaterHeatpump,
    BuildingDhnConnection,
    Chiller,
    ElectrodeBooster,
    ElectrodeHeater,
    FuelOilBoiler,
    MethaneBoiler,
    PhotovoltaicDevice,
    SolarThermalDevice,
    ThermalDemand,
    ThermalStorage,
    WallBox,
    ElectricityGridConnection,
    DhwDemand,
    CoolingDemand,
    HeatingDemand,
    ElectricityDemand,
    Device,
    Demand,
)
from ..model.network import Network, Node
from ..model.component import Component
from ..model.temporal import Temporal




def get_hosts(
    obj: Site | Structure | BuildingUnit | BuildingElement,
    max_descends: int = None,
) -> list[EnergySystem]:
    """
    - will descend into `Building`s, `BuildingUnit`s and `BuildingElement`s
    that are "contained" in obj (if any). Will descend recursively.
    `max_decsends` sets the limit (`0` = don't descend at all, `None` =
    infinite)
    """
    ret = []
    if hasattr(obj, "energy_system") and obj.energy_system is not None:
        ret.append(obj.energy_system)
    if max_descends is None or max_descends > 0:
        new_max_descends = None if max_descends is None else max_descends - 1
        if isinstance(obj, Building):
            for bu in obj.building_units:
                ret += get_hosts(obj=bu, max_descends=new_max_descends)
            for be in obj.building_elements:
                ret += get_hosts(obj=be, max_descends=new_max_descends)
        if isinstance(obj, StructureGroup):
            for b in obj.get_all_buildings():
                ret += get_hosts(obj=b, max_descends=new_max_descends)
    return ret


def get_devices(
    obj: Site | Structure | BuildingUnit | BuildingElement,
    type_: type = None,
    existence: DecisionState = None,
    get_inherited: bool = True,
    max_descends: int = None,
) -> list[Asset]:
    """
    - will descend into `Building`s, `BuildingUnit`s and `BuildingElement`s
    that are "contained" in obj (if any). Will descend recursively.
    `max_decsends` sets the limit (`0` = don't descend at all, `None` =
    infinite)
    - `get_inherited`: if True, `isinstance` will be used, else type must match
    exactly
    """
    ret = []
    if hasattr(obj, "energy_system") and obj.energy_system is not None:
        for d in obj.energy_system.components:
            if (existence is None or existence == d.existence) and (
                type_ is None or (get_inherited and isinstance(d, type_)) or (not get_inherited and type(d) is type_)
            ):
                ret.append(d)
    if max_descends is None or max_descends > 0:
        new_max_descends = None if max_descends is None else max_descends - 1
        if isinstance(obj, Building):
            for bu in obj.building_units:
                ret += get_devices(
                    obj=bu, type_=type_, existence=existence, max_descends=new_max_descends, get_inherited=get_inherited
                )
            for be in obj.building_elements:
                ret += get_devices(
                    obj=be, type_=type_, existence=existence, max_descends=new_max_descends, get_inherited=get_inherited
                )
        if isinstance(obj, StructureGroup):
            for b in obj.get_all_buildings():
                ret += get_devices(
                    obj=b, type_=type_, existence=existence, max_descends=new_max_descends, get_inherited=get_inherited
                )
    return ret


def get_device(
    obj: Site | Structure | BuildingUnit | BuildingElement,
    type_: type = None,
    existence: DecisionState = None,
    get_inherited: bool = True,
    max_descends: int = None,
) -> Asset | None:
    """
    return first matching device in `obj`, or `None`.
    """
    devices = get_devices(
        obj=obj,
        type_=type_,
        existence=existence,
        get_inherited=get_inherited,
        max_descends=max_descends,
    )
    if len(devices) > 0:
        return devices[0]


def has_device(
    obj: Site | Structure | BuildingUnit | BuildingElement,
    type_: type = None,
    existence: DecisionState = None,
    get_inherited: bool = True,
) -> bool:
    return len(get_devices(obj=obj, type_=type_, existence=existence, get_inherited=get_inherited)) > 0


def add_device(building: Building, device: Asset):
    if building is not None:
        building.energy_system.add_devices(device)


def create_dhn_connection_from_demands(building: Building):
    # TODO this method is a quick hack to create dhn connections from demands. Should rather guess the whole system
    bdc = BuildingDhnConnection()
    demands = building.energy_system.get_children_by_type(types=ThermalDemand)
    orig_ts = [d.get_input_flow() for d in demands]
    orig_ts = [x for x in orig_ts if x is not None]
    if orig_ts:
        bdc.set_input_flow(pd.concat(orig_ts, axis=1).sum(axis=1))
    building.energy_system.add_components(bdc)


def create_deg_connection_from_demands(building: Building):
    # TODO this method is a quick hack to create deg connections from demands. Should rather guess the whole system
    bdc = ElectricityGridConnection()
    demands = building.energy_system.get_children_by_type(types=ElectricityDemand)
    orig_ts = [d.get_input_flow() for d in demands]
    orig_ts = [x for x in orig_ts if x is not None]
    if orig_ts:
        bdc.set_input_flow(pd.concat(orig_ts, axis=1).sum(axis=1))
    building.energy_system.add_components(bdc)


def total_demands_by_attributes(obj: Building | BuildingUnit, include_subunits: bool = True):
    """
    return total (summed) values for electricity, heating, dhw, cooling, by
    looking at `Building` and `BuildingUnit` attributes
    """
    el = obj.electricity_demand.total if obj.electricity_demand is not None else 0
    heating = obj.heating_demand.total if obj.heating_demand is not None else 0
    dhw = obj.dhw_demand.total if obj.dhw_demand is not None else 0
    cooling = obj.cooling_demand.total if obj.cooling_demand is not None else 0
    if type(obj) is Building and include_subunits:
        for bu in obj.building_units:
            el_bu, heating_bu, dhw_bu, cooling_bu = total_demands_by_attributes(bu)
            el += el_bu
            heating += heating_bu
            dhw += dhw_bu
            cooling += cooling_bu
    return el, heating, dhw, cooling


def total_demands(obj: Building | BuildingUnit, demand_types: list[type], include_subunits: bool = True):
    """
    return total (summed) values for demands of the given `demand_types`
    (must be subclasses of `Demand`). If `demand_types` is None, electricity,
    heating, dhw, and cooling will be returned
    """
    res = []
    demand_types = (
        demand_types if demand_types is not None else [ElectricityDemand, HeatingDemand, DhwDemand, CoolingDemand]
    )
    all_demands = get_devices(obj, type_=Demand, get_inherited=True, max_descends=1 if include_subunits else 0)
    for demand_type in demand_types:
        res.append(sum(d.input_flow.total for d in all_demands if isinstance(d, demand_type)))
    return res


def get_device_props(
    objects: Object | list[Object],
    type: (
        list[
            Literal[
                "pv_roof",
                "pv_facade",
                "pv_site",
                "pv_unknown",
                "st_roof",
                "st_site",
                "st_unknown",
                "bhe",
                "hp",
                "hp_air_water",
                "hp_brine_water",
                "bes",
                "tes",
                "chiller",
                "ev",
                "boiler",
                "boiler_gas",
                "boiler_oil",
                "boiler_el",
            ]
        ]
        | None
    ),
    property: list[
        Literal[
            "count",
            "count_individual",
            "area_sum",
            "power_sum",
            "capacity_sum",
            "input_sum",
            "input_el_sum",
            "input_heat_sum",
            "output_sum",
            "scop_mean",
            "efficiency_mean",
        ]
    ],
) -> int | float | Temporal | None:
    if isinstance(objects, Object):
        objects = [objects]

    all_offsprings = list(set([x for x in objects for x in x.offspring]))

    def offsprings(objects: list[Object], type) -> list[Object]:
        return [o for o in all_offsprings if isinstance(o, type)]

    devices = {
        "pv_roof": [
            pv
            for pv in offsprings(objects, PhotovoltaicDevice)
            if pv.solar_surface is not None and isinstance(pv.solar_surface.parent, Roof)
        ],
        "pv_facade": [
            pv
            for pv in offsprings(objects, PhotovoltaicDevice)
            if pv.solar_surface is not None and isinstance(pv.solar_surface.parent, Wall)
        ],
        "pv_site": [
            pv
            for pv in offsprings(objects, PhotovoltaicDevice)
            if pv.solar_surface is not None and isinstance(pv.solar_surface.parent, Site)
        ],
        "pv_unknown": [pv for pv in offsprings(objects, PhotovoltaicDevice) if pv.solar_surface is None],
        "st_roof": [
            st
            for st in offsprings(objects, SolarThermalDevice)
            if st.solar_surface is not None and isinstance(st.solar_surface.parent, Roof)
        ],
        "st_site": [
            st
            for st in offsprings(objects, SolarThermalDevice)
            if st.solar_surface is not None and isinstance(st.solar_surface.parent, Site)
        ],
        "st_unknown": [st for st in offsprings(objects, SolarThermalDevice) if st.solar_surface is None],
        "bhe": offsprings(objects, BoreholeHeatExchanger),
        "hp_air_water": offsprings(objects, AirWaterHeatpump),
        "hp_brine_water": offsprings(objects, BrineWaterHeatpump),
        "bes": offsprings(objects, Battery),
        "tes": offsprings(objects, ThermalStorage),
        "chiller": offsprings(objects, Chiller),
        "ev": offsprings(objects, WallBox),
        "boiler_gas": offsprings(objects, MethaneBoiler),
        "boiler_oil": offsprings(objects, FuelOilBoiler),
        "boiler_el": offsprings(objects, (ElectrodeHeater, ElectrodeBooster)),
        "dhn": offsprings(objects, BuildingDhnConnection),
    }

    assert type is None or all(t in devices for t in type)
    devices = {k: v for k, v in devices.items() if k in type or type is None}
    devices_flat = [x for x in devices.values() for x in x]

    if property == "count":
        return len(devices_flat)

    elif property == "count_individual":
        ret = 0
        ds = (
            devices.get("pv_roof", [])
            + devices.get("pv_facade", [])
            + devices.get("pv_site", [])
            + devices.get("st_roof", [])
            + devices.get("st_site", [])
        )
        if ds:
            ret += sum([d.number_modules for d in ds])
        return ret

    elif property == "area_sum":
        ret = 0
        ds = (
            devices.get("pv_roof", [])
            + devices.get("pv_facade", [])
            + devices.get("pv_site", [])
            + devices.get("st_roof", [])
            + devices.get("st_site", [])
        )
        if ds:
            ret += sum([d.module_area for d in ds if d.module_area is not None])
        ds = devices.get("bhe", [])
        if ds:
            ret += sum([d.covered_area for d in ds])
        return ret

    elif property == "power_sum":
        values = [d.power_nominal for d in devices_flat]
        values = [v for v in values if v is not None]
        return sum(values) if values else None

    elif property == "capacity_sum":
        ds = devices.get("bes", []) + devices.get("tes", [])
        values = [d.capacity for d in ds]
        values = [v for v in values if v is not None]
        return sum(values) if values else None

    elif property == "input_sum":
        values = [d.get_input_flow(s) for d in devices_flat for s in d.input_sockets]
        return sum(v.total for v in values if not v.is_empty)

    elif property == "input_el_sum":
        values = [d.get_input_flow(Medium.ELECTRIC_ENERGY) for d in devices_flat]
        return sum(v.total for v in values if not v.is_empty)

    elif property == "input_heat_sum":
        values = [d.get_input_flow(Medium.THERMAL_ENERGY) for d in devices_flat]
        return sum(v.total for v in values if not v.is_empty)

    elif property == "output_sum":
        values = [d.get_output_flow(s) for d in devices_flat for s in d.output_sockets]
        return sum(v.total for v in values if not v.is_empty)

    elif property == "spf_mean":
        ds = devices.get("hp_air_water", []) + devices.get("hp_brine_water", [])
        if ds:
            return np.mean([d.spf for d in ds])

    elif property == "efficiency_mean":
        ds = devices.get("boiler_gas", []) + devices.get("boiler_oil", []) + devices.get("boiler_el", [])
        if ds:
            return np.mean([d.efficiency_nominal for d in ds])


def replace_devices(
    building: Building,
    devices_new: list[Device],
    devices_replaced: list[Device],
) -> None:
    """
    Removes all devices in devices_replaced from building.energy_system and
    adds the devices in devices_new. All inputs and outputs from devices in
    devices_replaced are set for all devices in devices_new.
    """
    inputs: list[Component] = []
    outputs: list[Component] = []
    input_mediums: dict[Component, Medium] = {}
    output_mediums: dict[Component, Medium] = {}
    output_flows = []

    # remove the old devices and store their surroundings for later:
    for d in devices_replaced:
        d: Device
        for i in d.input_components:
            inputs.append(i)
            input_mediums[i] = d.get_input_socket(at=i).medium
            d.remove_input(i)
            # remove busses that are not connected to anything anymore
            # if isinstance(i, Bus):
            #     if i.input_components == [] or i.output_components == []:
            #         if i in building.energy_system.components:
            #             building.energy_system.remove(i)
            #         inputs.remove(i)

        for o in d.output_components:
            output_flow = d.get_output_flow(o)
            if output_flow is not None:
                output_flows.append(output_flow.series)
            outputs.append(o)
            output_mediums[o] = d.get_output_socket(at=o).medium
            d.remove_output(o)
            # if isinstance(o, Bus):
            #     if o.input_components == [] or o.output_components == []:
            #         if o in building.energy_system.components:
            #             building.energy_system.remove(o)
            #         outputs.remove(o)
        building.energy_system.remove_children(d)

    inputs = [i for i in inputs if i not in devices_replaced]
    outputs = [i for i in outputs if i not in devices_replaced]
    betweens = [i for i in inputs if i in outputs]

    for d in devices_new:
        building.energy_system.add_children(d)

        for i in inputs:
            # sockets = i.get_closest_socket_pair(output=d, if_multiple="first")
            # socket at new device with same medium as input:
            medium = input_mediums[i]
            new_socket = d.get_input_socket(at=medium, medium_relation="linear")
            # socket of the input that was removed:
            to_connect_socket = i.get_output_socket(at=medium, medium_relation="linear")
            if new_socket is not None:
                d.set_input(new=to_connect_socket, at=new_socket)

        for o in outputs:
            # sockets = o.get_closest_socket_pair(input=d, if_multiple="first")
            medium = output_mediums[o]
            new_socket = d.get_output_socket(at=medium, medium_relation="linear")
            to_connect_socket = o.get_input_socket(at=medium, medium_relation="linear")
            if new_socket is not None:
                d.set_output(new=to_connect_socket, at=new_socket)

    # remove components (probably busses) that acted as inputs and outputs
    # as the same time if they aren't linked:
    for b in betweens:
        if len(b.components) == 0:
            building.energy_system.remove_children(b)
