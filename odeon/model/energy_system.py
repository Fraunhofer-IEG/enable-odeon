from __future__ import annotations
from typing import Literal

import pandas as pd
from numbers import Number

from .temporal import Temporal
from .base import Object
from .component import Component
from .device import (
    BiomassSupply, BuildingDhnConnection, Demand, ElectricityGridConnection, 
    ElectricityGridSource, FuelOilSupply, GasGridConnection, HeatingDemand, 
    DhwDemand, ElectricityDemand, HeatDemand, CoolingDemand,)

from ..processing.utils.utils import (
    none_object_or_list_to_list,
    type_typetuple_or_typelist_to_typetuple,
    typeerror_if_not_isinstance,
    typeerror_if_not_list_isinstance,
)


class DemandAccessor(Object):
    """
    A mixin class to describe an Object that can manage subordinate demands.

    This class provides methods and properties to access and manipulate demand
    objects that are offspring of the object. It allows for easy retrieval and
    modification of these demands.

    Inheriting classes must implement the `energy_system` property to provide
    access to the associated energy system.
    """

    @property
    def energy_system(self):
        raise Exception("Abstract property")

    def get_demands(
        self,
        type: type | tuple[type] | None = None,
        only_reachable_through: type | tuple[type] | None = None,
        omit_reachable_through: type | tuple[type] | None = None,
    ) -> list["Demand"]:
        """
        Get all demand objects of type `type` that are offspring of this
        object. Filer depending on what objects are located in between a demand
        and this object.

        Parameters
        ----------
        type : type | tuple[type] | None, optional
            The type or types of demand objects to retrieve. If None, all
            demand types will be returned.
        only_reachable_through : type | tuple[type] | None, optional
            If specified, only demands that are offspring of objects of this
            type will be returned. If None, all demands will be returned.
        omit_reachable_through : type | tuple[type] | None, optional
            If specified, demands that are offspring of objects of this type
            will be omitted from the result. If None, no demands will be omitted.
        """
        if type is None:
            type = Demand
        type = type_typetuple_or_typelist_to_typetuple(type)
        assert all(issubclass(t, Demand) for t in type)
        return self.find_objects_filtered(
            type=type,
            only_reachable_through=only_reachable_through,
            omit_reachable_through=omit_reachable_through,
        )

    def set_demand_flow(
        self,
        type: type,
        flow: Temporal | Number | pd.Series | None,
    ):
        """
        Set the flow for demand of type `demand_type`. If no offspring of this
        type exists, a new object will be created and added to the energy
        system. If exactly one offspring of this type exists, the flow of that
        object will be adjusted. Otherwise an exception will be raised.

        If `flow` is None, no demand will be created, and all existing offspring
        demands of this type will be removed from the energy system.

        Note that e.g. for a building, offspring demands are the direct demands
        of the building as well as all demands in all building units.
        """
        assert issubclass(type, Demand)
        demands: list[Demand] = self._get_offspring_by_type(type)

        if flow is None:
            for demand in demands:
                demand.remove_from_parent()
            return

        if len(demands) == 0:
            demand = type()
            demand.set_input_flow(flow)
            self.energy_system.add_components(demand)
        elif len(demands) == 1:
            demands[0].set_input_flow(flow)
        else:
            msg = [
                f"Found {len(demands)} existing demand objects.",
                "This method works only with 0 or 1 existing demand objects.",
                "You need to find and adjust the demand objects manually.",
            ]
            raise Exception(" ".join(msg))

    def get_summed_demand_input_flow(
        self,
        type: type | tuple[type] | None = None,
        include_subdemands: bool = True,
        if_empty: Literal["zero", "raise"] = "zero",
    ) -> Temporal:
        """
        Get the summed input flow of all offspring demand objects of type in
        `type`. If no demands of this type exist, an empty Temporal object
        will be returned.

        Parameters
        ----------
        type: type | tuple[type] | None, optional
            The type or types of demand objects to retrieve. If None, all
            demand types will be considered.
        include_subdemands: bool, optional
            If True, subdemands will be included in the sum. If False, only
            the direct demands will be considered. For example, for a building,
            direct demands are those attached to the building, while subdemands
            are those attached to its building units.
        if_empty: Literal["zero", "raise"], optional
            Determines the behavior when a demand has no input flow. If set to
            "raise", an exception will be raised. If set to "zero", the demand
            will be treated as zero as long as the total is also zero, else an
            exception will be raised.

        Returns
        -------
        Temporal
            A read-only Temporal object representing the summed input flow of all
            demands of the specified types. If no demands are found, an empty
            Temporal object will be returned.
        """
        omit_reachable_through = None if include_subdemands else DemandAccessor
        demands = self.get_demands(
            type=type,
            only_reachable_through=None,
            omit_reachable_through=omit_reachable_through,
        )
        timeseries = []
        for demand in demands:
            input_flow = demand.input_flow
            if input_flow is None:
                if if_empty == "raise":
                    raise ValueError(
                        f"Demand {demand} has no input flow. "
                        "This is not allowed when calculating the total of all demands."
                    )
                elif if_empty == "zero":
                    if demand.total is not None and demand.total != 0:
                        raise ValueError(f"Demand {demand} has no input flow, but a total value of {demand.total}.")
                    else:
                        ...  # do nothing, will be added as zero later
            else:
                timeseries.append(input_flow)

        if len(timeseries) == 0:
            temporal = Temporal(total=0, read_only=True)
            return temporal  # won't have a timeindex

        else:
            # sum all timeseries. If at least one input temporal had a timeindex,
            # this will be set as explicit timeindex. Parent will be None:
            temporal = Temporal.sum(timeseries)
            if temporal.has_master:
                temporal.remove_from_master()  # will keep the timeindex
            temporal.read_only = True
            return temporal

    def get_summed_demand_input_flow_total(
        self,
        type: type | tuple[type] | None = None,
        include_subdemands: bool = True,
        if_empty: Literal["zero", "raise"] = "zero",
        if_none: Literal["zero", "raise"] = "zero",
    ) -> float:
        """
        Get the total of the summed input flow of all offspring demand objects
        of type in `type`. This will be more performant than
        `get_summed_demand_input_flow` if only the total is needed.

        Parameters
        ----------
        type: type | tuple[type] | None, optional
            The type or types of demand objects to retrieve. If None, all
            demand types will be considered.
        include_subdemands: bool, optional
            If True, subdemands will be included in the sum. If False, only
            the direct demands will be considered. For example, for a building,
            direct demands are those attached to the building, while subdemands
            are those attached to its building units.
        if_empty: Literal["zero", "raise"], optional
            Determines the behavior when a demand has no input flow. If set to
            "raise", an exception will be raised. If set to "zero", the demand
            will be treated as zero as long as the total is also zero, else an
            exception will be raised.
        if_none: Literal["zero", "raise"], optional
            Determines the behavior when no demands of the specified type are
            found. If set to "raise", an exception will be raised. If set to
            "zero", the total will be returned as zero.
        """
        omit_reachable_through = None if include_subdemands else DemandAccessor
        demands = self.get_demands(
            type=type,
            only_reachable_through=None,
            omit_reachable_through=omit_reachable_through,
        )
        if len(demands) == 0:
            if if_none == "raise":
                raise ValueError("No demands found.")
            elif if_none == "zero":
                return 0.0
        total = 0.0
        for demand in demands:
            total_ = demand.input_flow.total
            if total_ is None:
                if if_empty == "raise":
                    raise ValueError(
                        f"Demand {demand} has no total value. "
                        "This is not allowed when calculating the total of all demands."
                    )
                elif if_empty == "zero":
                    total_ = 0
                total += total_
        return total

    @property
    def electricity_demand(self) -> Temporal:
        """
        The final electricity demand calculated as the summed input flow of all
        offspring objects of type `ElectricityDemand`.
        """
        return self.get_summed_demand_input_flow(type=ElectricityDemand)

    @electricity_demand.setter
    def electricity_demand(self, flow: Temporal | Number | pd.Series | None):
        """
        Set the input flow of the only existing offspring of type
        `ElectricityDemand`, or create a new demand in the energy system.
        If `flow` is None, all existing offspring of type `ElectricityDemand`
        will be removed.
        """
        self.set_demand_flow(type=ElectricityDemand, flow=flow)

    @property
    def dhw_demand(self) -> Temporal:
        """
        The final DHW demand calculated as the summed input flow of all
        offspring objects of type `DhwDemand`.
        """
        return self.get_summed_demand_input_flow(DhwDemand)

    @dhw_demand.setter
    def dhw_demand(self, flow: Temporal | Number | pd.Series | None):
        """
        Set the input flow of the only existing offspring of type
        `DhwDemand`, or create a new demand in the energy system. If `flow` is
        None, all existing offspring of type `DhwDemand` will be removed.
        """
        self.set_demand_flow(type=DhwDemand, flow=flow)

    @property
    def heating_demand(self) -> Temporal:
        """
        The final heating demand calculated as the summed input flow of all
        offspring objects of type `HeatingDemand`.
        """
        return self.get_summed_demand_input_flow(HeatingDemand)

    @heating_demand.setter
    def heating_demand(self, flow: Temporal | Number | pd.Series | None):
        """
        Set the input flow of the only existing offspring of type
        `HeatingDemand`, or create a new demand in the energy system. If `flow` is
        None, all existing offspring of type `HeatingDemand` will be removed.
        """
        self.set_demand_flow(type=HeatingDemand, flow=flow)

    @property
    def heat_demand(self) -> Temporal:
        """
        The final heat demand (heating + DHW) calculated as the summed input
        flow of all offspring objects of type `HeatDemand`.
        """
        return self.get_summed_demand_input_flow(HeatDemand)

    @heat_demand.setter
    def heat_demand(self, flow: Temporal | Number | pd.Series | None):
        """
        Set the input flow of the only existing offspring of type
        `HeatDemand`, or create a new demand in the energy system. If `flow` is
        None, all existing offspring of type `HeatDemand` will be removed.
        """
        self.set_demand_flow(type=HeatDemand, flow=flow)

    @property
    def cooling_demand(self) -> Temporal:
        """
        The final cooling demand calculated as the summed input flow of all
        offspring objects of type `CoolingDemand`.
        """
        return self.get_summed_demand_input_flow(CoolingDemand)

    @cooling_demand.setter
    def cooling_demand(self, flow: Temporal | Number | pd.Series | None):
        """
        Set the input flow of the only existing offspring of type
        `CoolingDemand`, or create a new demand in the energy system. If `flow` is
        None, all existing offspring of type `CoolingDemand` will be removed.
        """
        self.set_demand_flow(type=CoolingDemand, flow=flow)


class EnergySystem(DemandAccessor):
    """
    A collection of components that form a union or a system (possibly linked
    with other energy systems)
    """

    # children attributes:
    _CHILDREN_ATTRIBUTES = {"_components": "Component[]"}
    _components: list[Component] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._components = []

    @property
    def energy_system(self):
        return self  # required for the DemandAccessor mixin

    @property
    def components(self) -> list[Component]:
        return [*self._components]

    def add_components(self, components: Component | list[Component]):
        """
        Add components to the energy system. This will create a parent-child
        relation between the energy system and the components. If the
        components are already part of the energy system, a ValueError will be
        raised.
        """
        components = none_object_or_list_to_list(components)
        typeerror_if_not_list_isinstance(components, Component)

        for object in components:
            if object in self._components:
                raise ValueError(f"{object} already in components")
            self._components.append(object)
            object._set_parent(self)

    def remove_components(self, components: Component | list[Component]):
        """
        Remove components from the energy system. This will remove the
        parent-child relation between the energy system and the components. If
        the components are not part of the energy system, a ValueError will be
        raised.
        """

        components = none_object_or_list_to_list(components)
        typeerror_if_not_list_isinstance(components, Component)

        components_copy = self._components.copy()
        for object in components:
            if object not in components_copy:
                raise ValueError(f"{object} not in components")
            components_copy.remove(object)
            object.remove_from_parent()
        self._components = components_copy


class EnergySystemHost(DemandAccessor):
    """
    A mixin class that provides a child attribute `energy_system` that can
    store components.
    """

    _CHILDREN_ATTRIBUTES = {"_energy_system": "EnergySystem"}
    _energy_system: EnergySystem = None

    def __init__(self, energy_system: EnergySystem = None, **kwargs):
        super().__init__(**kwargs)
        if energy_system is not None:
            self.energy_system = energy_system
        else:
            self.energy_system = EnergySystem()

    @property
    def energy_system(self) -> EnergySystem:
        return self._energy_system

    @energy_system.setter
    def energy_system(self, energy_system: EnergySystem):
        typeerror_if_not_isinstance(energy_system, EnergySystem)
        assert energy_system.parent is None
        self._energy_system = energy_system
        energy_system._set_parent(self)


    def get_total_emissions(self) -> Temporal:
        """
        This function collects all Emissions for the object, and sums them up.
        The Emissions are gathered from the supply connections: FuelOilSupply,
        BiomassSupply, GasGridConnection, ElectricityGridConnection,
        BuildingDhnConnection

        Returns
        -------
        series
            Temporal of the buildings total Emissions
        """
        emission_dic = self.get_emissions_by_energy_carrier()
        series = None
        for value in emission_dic.values():
            if series is None:
                series = value
            else:
                series = Temporal.sum([series, value])
        return series

    def get_emissions_by_energy_carrier(self):
        """
        This function collects all Emissions for the object, sorted by energy
        carrier used. The Emissions are gathered from the supply connections:
        FuelOilSupply, BiomassSupply, GasGridConnection,
        ElectricityGridConnection, BuildingDhnConnection

        Returns
        -------
        emission_dic
            Dictinary with energy carriers as keys and the matching Emissions
            for that carrier as Dynamic Temporal
        """
        emission_dict = {}
        supply_list = [
            FuelOilSupply,
            BiomassSupply,
            GasGridConnection,
            ElectricityGridConnection,
            ElectricityGridSource,
            BuildingDhnConnection,
        ]
        supply_devices = self.collect_devices(supply_list)
        for device in supply_devices:
            co2_emissions = device.calc_co2_emissions()
            input_mediums = device.get_input_mediums()

            # CO2 emissions always refer to the first medium:
            medium = input_mediums[0]
            if medium not in emission_dict.keys():
                emission_dict[medium] = Temporal(co2_emissions)
            else:
                emission_dict[medium] = emission_dict[medium] + co2_emissions

        return emission_dict

    def get_primary_energy_demand_by_energy_carrier(self):
        """
        This function collects all Primary Energy dmeands for the object,
        sorted by energy carrier used. The PE Demands are gathered from the
        supply connections: FuelOilSupply, BiomassSupply, GasGridConnection,
        ElectricityGridConnection, BuildingDhnConnection

        Returns
        -------
        primary_energy_dic
            Dictinary with energy carriers as keys and the matching primary
            energy demand for that carrier as Dynamic Temporal
        """
        primary_energy_dict = {}
        supply_list = [
            FuelOilSupply,
            BiomassSupply,
            GasGridConnection,
            ElectricityGridConnection,
            ElectricityGridSource,
            BuildingDhnConnection,
        ]
        supply_devices = self.collect_devices(supply_list)
        for device in supply_devices:
            primary_energy_consumption = device.calc_primary_energy_consumption()
            input_mediums = device.get_input_mediums()

            # primary energy consumption always refers to the first medium:
            medium = input_mediums[0]
            if medium not in primary_energy_dict.keys():
                primary_energy_dict[medium] = Temporal(primary_energy_consumption)
            else:
                primary_energy_dict[medium] = primary_energy_dict[medium] + primary_energy_consumption

        return primary_energy_dict

    def get_total_primary_energy_demand(self) -> Temporal:
        """
        This function collects all Primary Energy dmeands for the object, and
        sums them up. The PE Demands are gathered from the supply connections:
        FuelOilSupply, BiomassSupply, GasGridConnection,
        ElectricityGridConnection, BuildingDhnConnection

        Returns
        -------
        series
            Temporal of the buildings total primary energy demand
        """
        primary_energy_dict = self.get_primary_energy_demand_by_energy_carrier()
        series = None
        for value in primary_energy_dict.values():
            if series is None:
                series = value
            else:
                series = series + value
        return series