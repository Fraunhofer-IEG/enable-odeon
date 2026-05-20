from __future__ import annotations
from dataclasses import dataclass
from numbers import Number
from typing import TYPE_CHECKING, Literal

import pandas as pd
import numpy as np

from .asset import Asset, CombiAsset
from .base import Object, StrEnum
from .component import FixedComponent, Component, Socket, ThermalComponent
from .energy import Medium, MediumManager
from .temporal import Temporal
from ..processing.utils.utils import (
    convert_unit,
    typeerror_if_not_isinstance,
    typeerror_if_not_isinstance_or_none,
    typeerror_if_not_list_isinstance,
)

import odeon.model as om  # required to access EnergySystemHost in code

if TYPE_CHECKING:
    from .expense import ExpenseType
    from .energy_system import EnergySystemHost
    from .district_heating_network import DistrictHeatingNetwork, DhnNode


class HeatingDistributionType(StrEnum):
    RADIATORS = "radiators"
    CONVECTORS = "convectors"
    PANEL_RADIATORS = "panel_radiators"
    TOWEL_RADIATORS = "towel_radiators"
    FLOOR_HEATING = "floor_heating"


class BuildingDistributionType(StrEnum):  # TODO move to mosaic
    DISTRICT = "Fernheizung (Fernwaerme)"
    FLOOR = "Etagenheizung"
    BLOCK = "Blockheizung"
    CENTRAL = "Zentralheizung"
    SINGLE = "Einzel-/Mehrraumoefen (auch Nachtspeicherheizung)"
    NO = "Keine Heizung im Gebaeude oder in den Wohnungen"


class HeatTransformer(StrEnum):  # TODO move to mosaic
    BIOMASS = "biomasse"
    DISTRICT = "fernwärme"
    FUEL_OIL = "heizöl"
    NATURAL_GAS = "erdgas"
    HEATPUMP = "wärmepumpe"
    ELSE = "sonstige"
    NO_TRANSFORMER = "Kein_system"


@dataclass
class TemperatureSet:
    supply_temp: float = None
    return_temp: float = None
    room_temp: float = None


@dataclass
class HeatingCurveParameterSet:
    heating_curve_slope: float = None
    heating_curve_offset: float = None
    radiators_exponent: float = None


class _ComponentAsset(Asset, FixedComponent): ...


class Device(_ComponentAsset):
    """
    A component of an energy system (with input and output flows, conversion
    factors etc.) that has economic attributes (lifetime, expenses, decisions
    etc.).
    """

    ...


class Bus(Asset, Component):
    """
    Distribution and transport of energy between any number of Components that
    is not subject to loss etc.

    The assumption for a `Bus` is that the sum of input flows equals the sum
    of output flows for any timestep. This assumption isn't implemented or
    used anywhere, though.

    A Bus can't have factors different than 0.

    A Bus is also an `Asset` meaning that it can have economic properties.
    """

    # the designated medium, can be overwritten by inheriting classes:
    _MEDIUM: Medium = None

    # the actual medium, specifies _MEDIUM if given, else set by user:
    _medium: Medium = None

    def __init__(
        self,
        medium: Medium = None,
        inputs: list[Socket | Medium | Component] = None,
        outputs: list[Socket | Medium | Component] = None,
        input_sockets: list[Socket] = None,
        output_sockets: list[Socket] = None,
        **kwargs,
    ):
        kwargs |= dict(
            inputs=inputs,
            outputs=outputs,
            input_sockets=input_sockets,
            output_sockets=output_sockets,
        )
        super().__init__(**kwargs)

        # assert that the provided medium specifies the design medium, if both are given:
        if self._MEDIUM is not None:
            typeerror_if_not_isinstance(self._MEDIUM, Medium)
            mm = MediumManager()
            if medium is None:
                medium = self._MEDIUM
            elif not mm.specifies(medium, self._MEDIUM):
                raise Exception("Can't set a medium that doesn't specify the design medium")

        self.medium = medium  # call setter

    # overrides super method
    def add_input_socket(self, socket: Socket, **kwargs):
        """
        Add a (parent-less) Socket to the Bus. The socket might already
        have `other`, `flow` or `medium` set. If no Medium is set, `self.medium`
        will be set as the Socket's Medium.
        """
        super().add_input_socket(socket=socket, factor=1.0)
        if socket.medium is None:
            socket.medium = self._medium

    # overrides super method
    def add_output_socket(self, socket: Socket, **kwargs):
        """
        Add a (parent-less) Socket to the Component. The socket might already
        have `other`, `flow` or `medium` set. If no Medium is set, `self.medium`
        will be set as the Socket's Medium.
        """
        super().add_output_socket(socket=socket, factor=1.0)
        if socket.medium is None:
            socket.medium = self._medium

    # overrides super method
    def add_input(
        self,
        new: Socket | Medium | Component | None,
        medium: Medium = None,
        flow: Temporal | Number | pd.Series | None = None,
        factor: pd.Series | Number | None = 1.0,
        **kwargs,
    ) -> Socket:
        if isinstance(new, FixedComponent):
            for s in new.output_sockets:
                if s.is_abstract:  # = has no component set
                    if s.medium is self.medium:  # TODO include medium relation
                        new = s
                        break
        return super().add_input(new=new, medium=medium, flow=flow, factor=factor)

    # overrides super method
    def add_output(
        self,
        new: Socket | Medium | Component | None,
        medium: Medium = None,
        flow: Temporal | Number | pd.Series | None = None,
        factor: pd.Series | Number | None = 1.0,
    ) -> Socket:
        if isinstance(new, FixedComponent):
            for s in new.input_sockets:
                if s.is_abstract:  # = has no component set
                    if s.medium is self.medium:  # TODO include medium relation
                        new = s
                        break
        return super().add_output(new=new, medium=medium, flow=flow, factor=factor)

    # overrides super method
    def _set_factor(self, socket: Socket, factor: Number | Temporal | None):
        if factor != 1.0:
            raise Exception("Can't set factors for a SingleMediumComponent")

    @classmethod
    def from_inputs_outputs(
        cls,
        medium: Medium,
        inputs: list[Component] = None,
        outputs: list[Component] = None,
        always_add_on_busses: bool = True,
        medium_relation: Literal["exact", "socket_specifies", "socket_generalizes", "linear"] = "exact",
        medium_considered: Literal["socket", "link"] = "socket",
    ) -> "Bus":
        """
        Create a new Bus that connects `inputs` and `outputs`. For each such
        component, the relevant Socket will be identified by `medium`. The
        result must be unambiguous per component. Otherwise, an exception will
        be raised.

        If a component is a `Bus` and either doesn't have a matching Socket, or
        `always_add_on_busses`, a new Socket will be created.
        """
        inputs = inputs or []
        outputs = outputs or []
        typeerror_if_not_isinstance(medium, Medium)
        typeerror_if_not_list_isinstance(inputs, Component)
        typeerror_if_not_list_isinstance(outputs, Component)

        bus = cls()
        bus.medium = medium

        for input in inputs:
            if isinstance(input, Bus) and always_add_on_busses:
                socket = input.add_output(new=medium)
            else:
                socket = input.get_output_socket(
                    at=medium,
                    medium_relation=medium_relation,
                    medium_considered=medium_considered,
                )
                if isinstance(input, Bus) and socket is None:
                    socket = input.add_output(new=medium)
                assert socket is not None
            bus.add_input(new=socket)

        for output in outputs:
            if isinstance(output, Bus) and always_add_on_busses:
                socket = output.add_input(new=medium)
            else:
                socket = output.get_input_socket(
                    at=medium,
                    medium_relation=medium_relation,
                    medium_considered=medium_considered,
                )
                if isinstance(output, Bus) and socket is None:
                    socket = output.add_input(new=medium)
                assert socket is not None
            bus.add_output(new=socket)

        return bus

    @property
    def medium(self):
        """
        The Medium of the Bus. It can be used by the user to store nominal
        information on this Bus and won't be analyzed for the underlying wiring
        functions.

        E.g. it's not a violation of the data model if  Bus has
        `Medium.ELECTRIC_ENERGY` as `medium` but receives input from a Component
        with `Medium.THERMAL_ENERGY`.
        """
        return self._medium

    @medium.setter
    def medium(self, medium: Medium | None):
        typeerror_if_not_isinstance_or_none(medium, Medium)
        self._medium = medium

    def __repr__(self):
        id_str = f"id={self.id}"
        name_str = f", name={self.name}" if self.name is not None else ""
        medium_str = f", med='{self.medium.label}'" if self.medium is not None else ""
        input_str = f", in={len(self.input_components)}/{len(self.input_sockets)}" if len(self.input_sockets) else ""
        output_str = (
            f", out={len(self.output_components)}/{len(self.output_sockets)}" if len(self.output_sockets) else ""
        )
        return f"{self.__class__.__name__}({id_str}{name_str}{medium_str}{input_str}{output_str})"


class ThermalBus(Bus, ThermalComponent): ...


class ComponentGroup(Device):

    # children attributes:
    # TODO make this an association and rewrite class
    _CHILDREN_ATTRIBUTES = {
        "_devices": "Device[]"
    }  # TODO this might cause problems as children colud have a different device host
    _devices: list[Device] = None

    # additional attributes:
    _DEVICE_TYPES: list[type] = None

    def __init__(self, devices: list[Device] = None, **kwargs):
        self._devices = []
        if devices is not None:
            assert len(devices) == len(self._DEVICE_TYPES)
            for d, dt in zip(devices, self._DEVICE_TYPES):
                assert isinstance(d, dt)
                self._devices.append(d)
        else:
            for dt in self._DEVICE_TYPES:
                d = dt()
                self._devices.append(d)
        super().__init__(**kwargs)
        for device in self._devices:
            assert device.parent is None
            device._set_parent(self)

    def get_device(self, device_type: type) -> Device | list[Device]:
        devices = [d for d in self._devices if isinstance(d, device_type)]
        return devices[0] if len(devices) == 1 else devices

    @property
    def devices(self) -> list[Device]:
        return self._devices.copy()

    def calc_expenses(self, expense_types: list["ExpenseType"] = None):
        ret = super().calc_expenses(expense_types)
        for d in self._devices:
            ret += d.calc_expenses(expense_types)
        return ret


# ----------------------------------------------------------------------------------------------------------------------
# abstract classes – Transformer, Storage
# ----------------------------------------------------------------------------------------------------------------------


class Transformer(Device):
    """
    An energy transforming device with a nominal power value acting as
    dimension.

    Remarks
    -------
    For a transformer, the following interpretations are common:

    - The input flow divided by its input factor equals the output flow divided
    by the output factor, for all combinations of input and output.
    - There is no retardation in the device, i.e. the above relation holds
    individually for all timesteps.

    These interpretations aren't used or implemented anywhere, though.
    """

    # temporal attributes:
    _TEMPORAL_DICT_ATTRIBUTES = ["_relative_power_max"]
    _relative_power_max: dict[Socket, Temporal] = None  # [kW]

    # additional attributes:
    specific_co2_emissions: float = None  # per primary output [gCO2eq/kWh]
    specific_primary_energy_consumption: float = None  # per primary output [1]
    flh_min: float = None  # full load hours [h/a]
    flh_max: float = None  # full load hours [h/a]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    # functions for temporals:

    def get_relative_power_max(self, at: Socket | Medium | Component | None = None) -> Temporal:
        """
        The theoretical maximal power (per input or output) that can be reached
        with a dimension of 1 under given circumstances. Independent of the set
        dimension.

        Parameters
        ----------
        - `socket`: If the Device has more than one socket (input + output), the
        socket must be specified, otherwise None can be used
        """
        socket = self.get_socket(at=at)
        if socket is None:
            raise Exception("No appropriate Socket found")
        power_max = self._relative_power_max.get(socket, None)
        if power_max is None:
            self.set_relative_power_max(power_max=power_max, at=socket)
        return self._relative_power_max[socket]

    def set_relative_power_max(
        self,
        power_max: Temporal | Number | pd.Series | None,
        at: Socket | Medium | Component | None = None,
    ):
        """
        The theoretical maximal power (per input or output) that can be reached
        with a dimension of 1 under given circumstances. Independent of the set
        dimension.

        Parameters
        ----------
        - `socket`: If the Device has more than one socket (input + output), the
        socket must be specified, otherwise None can be used
        """
        socket = self.get_socket(at=at)
        if socket is None:
            raise Exception("No appropriate Socket found")
        self.set_temporal(attr="_relative_power_max", x=power_max, key=socket)

    # additional methods:

    @property
    def power_nominal(self):  # [kW]
        """
        The scalar nominal power of the device, which is the same as the
        Transformer's dimension. The nominal power can be in any relation to
        the actual power (of the only/main output or input), or to the maximal
        power.
        """
        return self.dimension

    @power_nominal.setter
    def power_nominal(self, value: float):  # [kW]
        self.dimension = value

    def get_power_max(self, at: Socket | Medium | Component | None = None) -> Temporal | None:
        """
        The theoretical maximal power (per input or output) that can be reached
        with the given dimension under given circumstances.

        Parameters
        ----------
        - `socket`: If the Device has more than one socket (input + output), the
        socket must be specified, otherwise None can be used
        """
        if self.dimension is None:
            raise Exception()
        relative_power_max = self.get_relative_power_max(at=at)
        if relative_power_max is None:
            raise Exception()
        return relative_power_max * self.dimension

    @property
    def usage_count(self):
        raise NotImplementedError()  # TODO look at number of times any _input or _output changes from 0 to non-0

    @property
    def usage_time(self):  # [h]
        """
        Total duration during validity in which the (main) output flow is > 0.
        """
        if len(self.outlinks) > 0:
            flow = self.get_output_flow()
            return len(flow.series[flow.series > 0])
        elif len(self.inlinks) > 0:
            flow = self.get_input_flow()
            return len(flow.series[flow.series > 0])
        else:
            raise Exception()

    def calc_flh(self) -> float:  # TODO could also apply to Component
        """
        The full load hours of the Transformer, i.e. the summed (main) output
        flow divided by the nominal power. If the transformer has multiple
        outputs, the first output socket is used.
        """
        if len(self._output_sockets) == 0:
            raise Exception("No output sockets defined – can't calculate full load hours")
        output_flow = self.get_output_flow(self._output_sockets[0])
        if output_flow is not None and output_flow.total is not None and self.power_nominal is not None:
            return output_flow.total / self.power_nominal

    def calc_co2_emissions(self) -> Temporal:
        """
        The CO2 emissions of the Transformer, calculated by multiplying the
        specific CO2 emissions with the (main) output or input flow. If the
        transformer has multiple outputs, the first output socket is used.

        Returns
        -------
        The CO2 emissions in grams of CO2 equivalent per kWh as a Temporal. If
        the specific CO2 emissions or the relevant flow is not defined, an empty
        Temporal is returned.
        """
        if self.specific_co2_emissions is not None:
            if self.outlinks and self.get_output_flow() is not None:
                ret = self.get_output_flow() * self.specific_co2_emissions
            elif self.inlinks and self.get_input_flow() is not None:
                ret = self.get_input_flow() * self.specific_co2_emissions
            return Temporal(ret)
        return Temporal()

    def calc_primary_energy_consumption(self) -> Temporal:
        """
        The primary energy consumption of the Transformer, calculated by
        multiplying the specific primary energy consumption with the (main)
        output or input flow. If the transformer has multiple outputs, the first
        output socket is used.

        Returns
        -------
        The primary energy consumption in kWh as a Temporal. If the specific
        primary energy consumption or the relevant flow is not defined, an empty
        Temporal is returned.
        """

        if self.specific_primary_energy_consumption is not None:
            if self.outlinks and self.get_output_flow() is not None:
                ret = self.get_output_flow() * self.specific_primary_energy_consumption
            elif self.inlinks and self.get_input_flow() is not None:
                ret = self.get_input_flow() * self.specific_primary_energy_consumption
            return Temporal(ret)
        return Temporal()


class Storage(Device):
    """
    An energy storing device with a capacity (in kWh) acting as dimension.
    """

    # temporal attributes:
    _TEMPORAL_ATTRIBUTES = ["_content"]
    _content: Temporal = None  # [kWh]

    # additional attributes:
    capacity_min: float = None  # [kWh]
    _power_input_relative: float = None  # [1/h] or [kW/kWh]
    _power_output_relative: float = None  # [1/h] or [kW/kWh]
    _power_input_nominal: float = None  # [kW] was: input_max # TODO could be moved to Component
    _power_output_nominal: float = None  # [kW] was: output_max # TODO could be moved to Component
    loss_rate: float = None  # [1/h]
    unload_time: float = None  # [h] # TODO property = capacity_nominal/power_output_nominal?

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    # properties for temporals:

    @property
    def content(self) -> Temporal:
        return self._content

    @content.setter
    def content(self, content: Temporal | Number | pd.Series | None):
        self.set_temporal("_content", content)

    # additional methods:

    @property
    def soc(self) -> Temporal:  # [1]
        """
        The state of charge (SOC) of the storage, i.e. the content divided by
        the capacity. Independent of the set dimension. Range should be 0...1,
        but this isn't enforced. If no capacity is set, an empty Temporal is
        returned.
        """
        if self.capacity is not None:
            return self.content / self.capacity
        else:
            return Temporal()

    @soc.setter
    def soc(self, series):
        if self.capacity is not None:
            self.content = series * self.capacity
        else:
            raise Exception("Can't set SOC if capacity is not set")

    @property
    def capacity(self):  # [kWh]
        return self.dimension

    @capacity.setter
    def capacity(self, value: float):  # [kWh]
        self.dimension = value

    @property
    def power_input_relative(self):
        return (
            self._power_input_relative
            if self._power_input_relative is not None
            else self._power_input_nominal / self.capacity
        )

    @power_input_relative.setter
    def power_input_relative(self, value: float):
        self._power_input_relative = value
        self._power_input_nominal = None

    @property
    def power_output_relative(self):
        return (
            self._power_output_relative
            if self._power_output_relative is not None
            else self._power_output_nominal / self.capacity
        )

    @power_output_relative.setter
    def power_output_relative(self, value: float):
        self._power_output_relative = value
        self._power_output_nominal = None

    @property
    def power_input_nominal(self):
        return (
            self._power_input_nominal
            if self._power_input_nominal is not None
            else (
                self._power_input_relative * self.capacity
                if self._power_input_relative is not None and self.capacity is not None
                else None
            )
        )

    @power_input_nominal.setter
    def power_input_nominal(self, value: float):
        self._power_input_nominal = value
        self._power_input_relative = None

    @property
    def power_output_nominal(self):
        return (
            self._power_output_nominal
            if self._power_output_nominal is not None
            else (
                self._power_output_relative * self.capacity
                if self._power_output_relative is not None and self.capacity is not None
                else None
            )
        )

    @power_output_nominal.setter
    def power_output_nominal(self, value: float):
        self._power_output_nominal = value
        self._power_output_relative = None

    @property
    def power_nominal(self):  # [kW]
        return self.power_output_nominal or self.get_max_output_flow()

    @power_nominal.setter
    def power_nominal(self, value: float):  # [kW]
        self.power_output_nominal = value

    @property
    def power(self):  # [kW]
        return self.power_nominal or self.get_max_output_flow()

    @power.setter
    def power(self, value: float):  # [kW]
        self.power_nominal = value


# ----------------------------------------------------------------------------------------------------------------------
# Generic sources
# ----------------------------------------------------------------------------------------------------------------------


class HeatSource(Transformer, ThermalComponent):
    _OUTPUT_MEDIUMS = [Medium.THERMAL_ENERGY]


class AirHeatSource(HeatSource):
    _OUTPUT_MEDIUMS = [Medium.AIR_THERMAL_ENERGY]


class ElectricitySource(Transformer):
    # TODO remove
    _OUTPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY]


# ----------------------------------------------------------------------------------------------------------------------
# DistrictHeatingNetwork and associated classes
# ----------------------------------------------------------------------------------------------------------------------


class DhnConnectable(Transformer, ThermalComponent):

    # class constants:
    _INPUT_MEDIUMS = [Medium.WATER_THERMAL_ENERGY]
    _OUTPUT_MEDIUMS = [Medium.WATER_THERMAL_ENERGY]

    # temporal attributes:
    _TEMPORAL_ATTRIBUTES = [
        "_pressure_output_flow",
        "_pressure_input_flow",
        "_mass_flow",
    ]
    _pressure_output_flow: Temporal = None
    _pressure_input_flow: Temporal = None
    _mass_flow: Temporal = None

    # associated attributes:
    _ASSOCIATED_ATTRIBUTES = ["dhn"]
    dhn: "DistrictHeatingNetwork" = None  # TODO remove

    # properties for temporal attributes:

    @property
    def pressure_output_flow(self) -> Temporal:
        return self._pressure_output_flow

    @pressure_output_flow.setter
    def pressure_output_flow(self, pressure_output_flow: Temporal | Number | pd.Series | None):
        self.set_temporal("_pressure_output_flow", pressure_output_flow)

    @property
    def pressure_input_flow(self) -> Temporal:
        return self._pressure_input_flow

    @pressure_input_flow.setter
    def pressure_input_flow(self, pressure_input_flow: Temporal | Number | pd.Series | None):
        self.set_temporal("_pressure_input_flow", pressure_input_flow)

    @property
    def mass_flow(self) -> Temporal:
        return self._mass_flow

    @mass_flow.setter
    def mass_flow(self, mass_flow: Temporal | Number | pd.Series | None):
        self.set_temporal("_mass_flow", mass_flow)

    # additional methods:

    @property
    def district_heating_network(self) -> DistrictHeatingNetwork | None:
        """
        The `DistrictHeatingNetwork` this object is connected to.
        """
        thermal_grid = self.thermal_grid
        if thermal_grid is not None:
            return thermal_grid.district_heating_network


class TransferStation(DhnConnectable):  # TODO rename to ThermalGridSource

    # temporal attributes:
    _TEMPORAL_ATTRIBUTES = [
        "_pressure_setpoint_output_flow",
        "_output_forward_setpoint_temperature",
        "_volume_flow",
    ]
    _pressure_setpoint_output_flow: Temporal = None
    _output_forward_setpoint_temperature: Temporal = None
    _volume_flow: Temporal = None

    # additional attributes:
    transfer_efficiency: float = None
    producer_massflow_max: float = None  # TODO unit?

    # properties for temporal attributes:

    @property
    def pressure_setpoint_output_flow(self) -> Temporal:
        return self._pressure_setpoint_output_flow

    @pressure_setpoint_output_flow.setter
    def pressure_setpoint_output_flow(self, pressure_setpoint_output_flow: Temporal | Number | pd.Series | None):
        self.set_temporal("_pressure_setpoint_output_flow", pressure_setpoint_output_flow)

    @property
    def output_forward_setpoint_temperature(self) -> Temporal:
        return self._output_forward_setpoint_temperature

    @output_forward_setpoint_temperature.setter
    def output_forward_setpoint_temperature(
        self, output_forward_setpoint_temperature: Temporal | Number | pd.Series | None
    ):
        self.set_temporal("_output_forward_setpoint_temperature", output_forward_setpoint_temperature)

    @property
    def volume_flow(self) -> Temporal:
        return self._volume_flow

    @volume_flow.setter
    def volume_flow(self, volume_flow: Temporal | Number | pd.Series | None):
        self.set_temporal("_volume_flow", volume_flow)


class BuildingDhnConnection(DhnConnectable):  # TODO rename to ThermalGridConnection or ThermalGridSink?

    # temporal attributes:
    _TEMPORAL_ATTRIBUTES = [
        "_input_forward_setpoint_temperature",
        "_input_return_setpoint_temperature",
    ]
    _input_forward_setpoint_temperature: Temporal = None  # [°C]
    _input_return_setpoint_temperature: Temporal = None  # [°C]

    # additional attributes:
    temperature_flex: float = 20  # [K] # TODO extract constant
    efficiency_nominal: float = None  # [1] 0...1

    # properties for temporal attributes:

    @property
    def input_forward_setpoint_temperature(self) -> Temporal:
        return self._input_forward_setpoint_temperature

    @input_forward_setpoint_temperature.setter
    def input_forward_setpoint_temperature(
        self,
        input_forward_setpoint_temperature: Temporal | Number | pd.Series | None,
    ):
        self.set_temporal("_input_forward_setpoint_temperature", input_forward_setpoint_temperature)

    @property
    def input_return_setpoint_temperature(self) -> Temporal:
        return self._input_return_setpoint_temperature

    @input_return_setpoint_temperature.setter
    def input_return_setpoint_temperature(
        self,
        input_return_setpoint_temperature: Temporal | Number | pd.Series | None,
    ):
        self.set_temporal("_input_return_setpoint_temperature", input_return_setpoint_temperature)


class DhnLink(Transformer, ThermalComponent):  # TODO rename to ThermalGridLink # TODO remove?
    """
    A device that exchanges heat between two hydraulically separated
    `ThermalGrid`s. The ThermalGridLink should be set as attachment to one node
    of both upper and lower network.
    """

    # class constants:
    _INPUT_MEDIUMS = [Medium.WATER_THERMAL_ENERGY]
    _OUTPUT_MEDIUMS = [Medium.WATER_THERMAL_ENERGY]

    # associated attributes
    _ASSOCIATED_ATTRIBUTES = [
        "upper",
        "lower",
    ]
    upper: "DistrictHeatingNetwork" = None
    lower: "DistrictHeatingNetwork" = None

    def get_connecting_node_of_upper(self) -> DhnNode | None:
        if self.upper is not None:
            res = self.upper.get_nodes_by_attachments([self])
            if len(res) == 1:
                return res[0]
            elif len(res) > 1:
                raise Exception()

    def get_connecting_node_of_lower(self) -> DhnNode | None:
        if self.lower is not None:
            res = self.lower.get_nodes_by_attachments([self])
            if len(res) == 1:
                return res[0]
            elif len(res) > 1:
                raise Exception()


class Pump(Asset):  # TODO: Other superclass for Pump # TODO move to different section
    transfer_efficiency: float = None  # TODO express by existing <Transformer>.input_efficiency and ._output_efficiency
    producer_massflow_max: float = None


# ----------------------------------------------------------------------------------------------------------------------
# Electricity grid
# ----------------------------------------------------------------------------------------------------------------------


class ElectricityGrid(Transformer):  # TODO might already exist in deg?
    # class constants:
    _INPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY]
    _OUTPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY]


class ElectricityGridSource(Transformer):
    """
    A source for electricity from another grid, a generator etc. We don't care
    where the electricity comes from (hence no input).
    """

    _OUTPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY]


class ElectricityGridSink(Transformer):
    """
    A sink for electricity e.g. export to an outer grid. We don't care where the
    electricity goes (hence no output).
    """

    _INPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY]


class ElectricityGridConnection(Transformer):
    """
    This component can be used in two ways:

    - as a two-way connection from one grid to something (e.g. another grid)
      that allows both input (=export) and output (=import). That something is
      not modelled.
    - as a one-way connection between two electricity grids, e.g. a
      medium-voltage grid and a district grid , or a district grid and a "grid"
      inside a building. The user needs to define which direction is meant (and
      hence what is understood as `input` and `output`).
    """

    # class constants:
    _INPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY]
    _OUTPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY]


class FourPoleElectricityGridConnection(Transformer):
    """
    This component can be used as a two-way connection between two electricity
    grids, e.g. a medium-voltage grid and a district grid , or a district grid
    and a building grid.

    It's the user's responsibility to assure that inputs and outputs are wired
    correctly to only two components.
    """

    # class constants:
    _INPUT_MEDIUMS = [
        Medium.ELECTRIC_ENERGY,  # input from primary to secondary
        Medium.ELECTRIC_ENERGY,  # input from secondary to primary
    ]
    _OUTPUT_MEDIUMS = [
        Medium.ELECTRIC_ENERGY,  # output from primary to secondary
        Medium.ELECTRIC_ENERGY,  # output from secondary to primary
    ]

    def get_socket(
        self,
        from_: Literal["primary", "secondary"] | None,
        to_: Literal["primary", "secondary"] | None,
    ) -> Socket:
        if from_ is not None and to_ is not None:
            raise Exception("Can't specify both from_ and to_")
        if from_ is None and to_ is None:
            raise Exception("Must specify either from_ or to_")

        if from_ == "primary":
            return self._input_sockets[0]
        elif from_ == "secondary":
            return self._input_sockets[1]
        elif to_ == "primary":
            return self._output_sockets[0]
        elif to_ == "secondary":
            return self._output_sockets[1]


class TransformerStation(Transformer):
    # class constants:
    _mv_node: om.DegNode = None
    _INPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY]
    _OUTPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY]

    @property
    def mv_node(self) -> om.DegNode:
        return self._mv_node

    @mv_node.setter
    def mv_node(self, mv_node: om.DegNode):
        self._mv_node = mv_node


# ----------------------------------------------------------------------------------------------------------------------
# Other grids and supplies
# ----------------------------------------------------------------------------------------------------------------------


class GasGrid(Asset):
    gas: Medium = Medium.NATURAL_GAS


class GasGridConnection(Transformer):
    # class constants:
    _INPUT_MEDIUMS = [Medium.GASEOUS_CHEMICAL_ENERGY]
    _OUTPUT_MEDIUMS = [Medium.GASEOUS_CHEMICAL_ENERGY]

    # associated attributes:
    _ASSOCIATED_ATTRIBUTES = ["grid"]
    grid: GasGrid = None


class BiomassSupply(Transformer):
    # class constants:
    _OUTPUT_MEDIUMS = [Medium.BIOMASS]

    # additional attributes:
    fuel: Medium = None


class FuelOilSupply(Transformer):
    # class constants:
    _OUTPUT_MEDIUMS = [Medium.FUEL_OIL]


# ----------------------------------------------------------------------------------------------------------------------
# demands
# ----------------------------------------------------------------------------------------------------------------------
# Note that Demands inherit from FixedComponent instead of Device.


class Demand(FixedComponent):
    @property
    def input_flow(self):
        return self.get_input_flow()

    @input_flow.setter
    def input_flow(self, flow: Temporal | Number | pd.Series | None):
        self.set_input_flow(flow)


class ElectricityDemand(Demand):
    _INPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY]


class WallBox(ElectricityDemand): ...


class ChargingStation(Transformer):
    # class constants:
    _INPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY]
    _OUTPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY]

    # additional attributes:
    year_of_construction = None
    charging_points: int = None
    charger_type: str = None
    capacity: float = None  # kW
    # TODO number of four according to BNetzA register. Make more abstract?
    cap_point1: float = None  # kW
    type_point1: str = None
    cap_point2: float = None  # kW
    type_point2: str = None
    cap_point3: float = None  # kW
    type_point3: str = None
    cap_point4: float = None  # kW
    type_point4: str = None


class ChemicalDemand(Demand):
    # class constants:
    _INPUT_MEDIUMS = [Medium.CHEMICAL_ENERGY]


class GasDemand(ChemicalDemand):
    # class constants:
    _INPUT_MEDIUMS = [Medium.NATURAL_GAS]


class ThermalDemand(Demand, ThermalComponent):
    # class constants:
    _INPUT_MEDIUMS = [Medium.THERMAL_ENERGY]


class HeatDemand(ThermalDemand): ...


class DhwDemand(HeatDemand): ...


class HeatingDemand(HeatDemand):
    heating_distribution_type: HeatingDistributionType = None


class CoolingDemand(ThermalDemand): ...


class HeatingDistribution(Transformer, ThermalComponent):  # Alternativer Name: HeatEmitter?
    # TODO shouldn't this inherit from HeatingDemand?
    # class constants:
    _INPUT_MEDIUMS = [Medium.THERMAL_ENERGY]

    # additional attributes
    norm_heat_output: float = None
    norm_temperature_set: "TemperatureSet" = None
    heating_curve: HeatingCurveParameterSet = None
    heating_distribution_type: HeatingDistributionType = None


class HeatingTransformationSystem(Asset):  # TODO make it a combi asset

    # associated attributes:
    _ASSOCIATED_ATTRIBUTES = ["heating_system", "dhw_system"]
    heating_system: Asset = None
    dhw_system: Asset = None

    # additional attributes:
    # zensus_building_distribution_type: HeatingDistributionType = None # TODO Remove?
    # main_transformation_system: HeatTransformer = None


# ----------------------------------------------------------------------------------------------------------------------
# Solar
# ----------------------------------------------------------------------------------------------------------------------


class SolarSurface(Object):
    """
    A (possible) solar active surface/area as part of a Roof, Wall or Site.

    The SolarSurface doesn't store devices. Rather, the associated devices can
    be dynamically retrieved by collecting the SolarTransformers in the
    SolarSurface's parent's EnergySystem.
    """

    # additional attributes:
    tilt: float = None  # normally, copied from self.attachment.geometry.tilt
    azimuth: float = None  # [°]
    usable_length: float = None  # [m]
    usable_width: float = None  # [m]
    usable_area: float = None  # [m²]
    factor_existing_pv: float = None  # [1] 0...1
    factor_occupied_nonsolar: float = None  # [1] 0...1
    possible_number_modules: float = None  # [1]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def _get_energy_system_host(self) -> EnergySystemHost | None:
        ancestors = self.get_ancestors_of_type(om.EnergySystemHost)
        if len(ancestors):
            return ancestors[0]  # closest one

    @property
    def devices(self) -> list[SolarTransformer]:
        esho = self._get_energy_system_host()
        if esho is not None:
            return [
                d for d in esho.energy_system.components if isinstance(d, SolarTransformer) and d.solar_surface is self
            ]
        else:
            return []

    def add_solar_transformers(self, solar_transformers: SolarTransformer | list[SolarTransformer]):
        """
        Add `transformers` to the SolarSurface. If `transformer` is not yet
        in the list of devices of the SolarSurface's parent's EnergySystem, they
        will be added.
        """
        if not isinstance(solar_transformers, (list, tuple)):
            solar_transformers = [solar_transformers]
        for object in solar_transformers:
            typeerror_if_not_isinstance_or_none(object, SolarTransformer)
        esho = self._get_energy_system_host()
        for st in solar_transformers:
            if st not in esho.energy_system.components:
                esho.energy_system.add_components(st)
            st._solar_surface = self

    def remove_solar_transformers(self, solar_transformers: SolarTransformer | list[SolarTransformer]):
        """
        Remove `devices` from the SolarSurface. The Transformer's
        EnergySystem will remain unchanged.
        """
        if not isinstance(solar_transformers, (list, tuple)):
            solar_transformers = [solar_transformers]
        esho = self._get_energy_system_host()
        for transformer in solar_transformers:
            transformer._solar_surface = None


class SolarSurfaceHost(Object):
    """
    A mixin class for classes that can have a SolarSurface (e.g. Roof, Wall,
    Site)
    """

    # children attributes:
    _CHILDREN_ATTRIBUTES = {"_solar_surface": "SolarSurface"}
    _solar_surface: SolarSurface = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def solar_surface(self) -> SolarSurface:
        return self._solar_surface

    @solar_surface.setter
    def solar_surface(self, surface: SolarSurface):
        if not isinstance(surface, SolarSurface) and surface is not None:
            raise Exception(f"{surface} is not an instance of {SolarSurface} or {None}")
        self._solar_surface = surface
        assert surface.parent is None
        if surface is not None:
            surface._set_parent(self)


class SolarMountingConfiguration(Object):

    # additional attributes:
    tilt_modules: float = None  # [°]
    azimuth_modules: float = None  # [°]
    azimuth_modules_east: float = None  # [°]
    azimuth_modules_west: float = None  # [°]
    distance_between_modules: float = 0  # [m]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def is_east_west(self):
        # TODO please somebody check whether this is correct
        return self.azimuth_modules_east is not None and self.azimuth_modules_west is not None


class SolarTransformer(Transformer):

    # temporal attributes:
    _TEMPORAL_ATTRIBUTES = ["_total_irradiance_j_per_sqm"]
    _total_irradiance_j_per_sqm: Temporal = None  # [J/m²]

    # children attributes:
    _CHILDREN_ATTRIBUTES = {"_solar_mounting_configuration": "SolarMountingConfiguration"}
    _solar_mounting_configuration: SolarMountingConfiguration = None

    # associated attributes:
    _ASSOCIATED_ATTRIBUTES = ["_solar_surface"]
    _solar_surface: SolarSurface = None

    # additional attributes:
    module_area: float = None  # [m²]
    number_modules: int = None  # [1]
    efficiency_nominal: float = None  # [1] 0...1

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    # properties for temporal attributes:

    @property
    def total_irradiance_j_per_sqm(self) -> Temporal:
        return self._total_irradiance_j_per_sqm

    @total_irradiance_j_per_sqm.setter
    def total_irradiance_j_per_sqm(self, total_irradiance_j_per_sqm: Temporal | Number | pd.Series | None):
        self.set_temporal("_total_irradiance_j_per_sqm", total_irradiance_j_per_sqm)

    # additional methods:

    @property
    def solar_mounting_configuration(self) -> SolarMountingConfiguration:
        return self._solar_mounting_configuration

    @solar_mounting_configuration.setter
    def solar_mounting_configuration(self, configuration: SolarMountingConfiguration):
        typeerror_if_not_isinstance_or_none(configuration, SolarMountingConfiguration)
        if self._solar_mounting_configuration is not None:
            self._solar_mounting_configuration.remove_from_parent()
        self._solar_mounting_configuration = configuration
        configuration._set_parent(self)

    @property
    def solar_surface(self) -> SolarSurface:
        return self._solar_surface

    @solar_surface.setter
    def solar_surface(self, surface: SolarSurface):
        typeerror_if_not_isinstance_or_none(surface, SolarSurface, none_ok=True)
        if surface is None:
            if self.solar_surface is not None:
                self.solar_surface.remove_solar_transformers(self)
        else:
            assert surface.parent is self.parent
            surface.add_solar_transformers(self)

    @property
    def is_mounted(self):
        return (
            self._solar_mounting_configuration.tilt_modules is None
            or self.energy_system.tilt == self._solar_mounting_configuration.tilt_modules
        ) and (
            self._solar_mounting_configuration.azimuth_modules is None
            or self.energy_system.azimuth == self._solar_mounting_configuration.azimuth_modules
        )

    @property
    def power_nominal_per_area(self):
        return self.power_nominal / self.module_area


class PhotovoltaicDevice(SolarTransformer):
    # class constants:
    _OUTPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY]

    # additional attributes:
    temperature_nominal_stc: float = 25  #  TODO magic constant # TODO unit?
    temperature_coefficient_voltage: float = None  # [°C]
    number_inverters: int = None
    modules_per_string: int = None
    strings_per_inverter: int = None


class SolarThermalDevice(SolarTransformer, ThermalComponent):
    """
    `_dimension` = `module_area` [m²]
    """

    # class constants:
    _OUTPUT_MEDIUMS = [Medium.WATER_THERMAL_ENERGY]

    # additional attributes:
    power_nominal_per_module_area: float = 0.7

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def power_nominal(self) -> float | None:
        if self.dimension is not None:
            return self.dimension * self.power_nominal_per_module_area

    @power_nominal.setter
    def power_nominal(self, value: float):
        self.module_area = value / self.power_nominal_per_module_area

    @property
    def module_area(self):
        return self.dimension

    @module_area.setter
    def module_area(self, value):
        self.dimension = value


# ----------------------------------------------------------------------------------------------------------------------
# additional RE sources
# ----------------------------------------------------------------------------------------------------------------------


class WindpowerDevice(Transformer):
    # class constants:
    _OUTPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY]

    # additional attributes:
    turbine_type: str = None
    number_turbines: int = None  # [1]
    total_capacity: float = None  # [kW]


class BoreholeHeatExchanger(Transformer, ThermalComponent):
    # TODO add units
    # TODO lot of constants...
    # TODO very similar to BTES...

    # class constants:
    _OUTPUT_MEDIUMS = [Medium.BRINE_THERMAL_ENERGY]

    # additional attributes:
    inner_diameter_pipe: float = 0.0216  # 0.026 from EED example
    outer_diameter_pipe: float = 0.02667  # 0.032 from EED example
    shank_spacing_pipe: float = 0.0323  # 0.0604 from EED example
    roughness_pipe: float = 1.0e-6  #
    conductivity_pipe: float = 0.4  # 0.42 from EED example
    rho_cp_pipe: float = 1542000.0  #
    conductivity_soil: float = 2.0
    rho_cp_soil: float = 2343493.0
    conductivity_grout: float = (
        1.0  # kg: idea: Would it be clearer if parameters were named with their object in the first place and the specification second? -> grout_conductivity, grout_rho
    )
    rho_cp_grout: float = 3901000.0
    undisturbed_ground_temp: float = None
    drilling_depth: float = None
    buried_depth: float = 2.0
    diameter: float = 0.150
    simulation_length: int = (
        None  # kg: Aren't these parameters very specific for the geothermal installer and would be better placed there?
    )
    eft_min: float = None  # minimal fluid temperature
    eft_max: float = None
    drilling_depth_min: float = None
    drilling_depth_max: float = None
    spacing_min: float = None
    spacing_max: float = None
    n_boreholes: int = None
    covered_area: float = None

    @property
    def geothermal_coverage(self) -> float | None:
        return self.custom_data.get("geothermal_coverage", None)

    @geothermal_coverage.setter
    def geothermal_coverage(self, value: float):
        if not isinstance(value, (float, int)) and value is not None:
            raise Exception(f"{value} is not a number or None")
        self.custom_data["geothermal_coverage"] = value


class GroundHeatCollector(Transformer, ThermalComponent):
    _OUTPUT_MEDIUMS = [Medium.BRINE_THERMAL_ENERGY]


class GeoStar(BoreholeHeatExchanger):
    _OUTPUT_MEDIUMS = [Medium.BRINE_THERMAL_ENERGY]


class ShallowGeoStar(GeoStar):
    _OUTPUT_MEDIUMS = [Medium.BRINE_THERMAL_ENERGY]


class GroundWaterConnection(Transformer, ThermalComponent):  # TODO rename
    # class constants:
    _OUTPUT_MEDIUMS = [Medium.WATER_THERMAL_ENERGY]

    # additional attributes:
    efficiency_nominal: float = None


class GeothermalWell(Transformer, ThermalComponent):
    # class constants:
    _INPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY]
    _OUTPUT_MEDIUMS = [Medium.WATER_THERMAL_ENERGY]

    # additional attributes:
    has_turbine: bool = False  # whether device has a turbine that recuperates electricity from downstream flow
    efficiency_nominal: float = None


class MineWaterReservoir(Transformer, ThermalComponent):
    # class constants:
    _INPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY]
    _OUTPUT_MEDIUMS = [Medium.WATER_THERMAL_ENERGY]

    # additional attributes:
    has_turbine: bool = False  # whether device has a turbine that recuperates electricity from downstream flow
    efficiency_nominal: float = None


class WasteWaterTreatment(Transformer, ThermalComponent):
    # class constants:
    _INPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY]
    _OUTPUT_MEDIUMS = [Medium.WATER_THERMAL_ENERGY]

    # additional attributes:
    has_turbine: bool = False  # whether device has a turbine that recuperates electricity from downstream flow
    efficiency_nominal: float = None


# ----------------------------------------------------------------------------------------------------------------------
# Heatpumps
# ----------------------------------------------------------------------------------------------------------------------


class Heatpump(Transformer, ThermalComponent):
    """
    Attributes
    ----------
    - `cop`: The nominal COP
    - `spf`: The nominal SPF
    """

    # class constants:
    _INPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY, Medium.THERMAL_ENERGY]
    _OUTPUT_MEDIUMS = [Medium.THERMAL_ENERGY]

    # temporal attributes:
    _TEMPORAL_ATTRIBUTES = ["_cop"]
    _cop: Temporal = None  # [1]

    # additional attributes:
    efficiency_carnot: float = None
    efficiency_lorenz: float = None
    n_stages: int = None  # [1] >=1
    spf: float = None  # [1]
    heat_source: str = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    # properties for temporal attributes:

    @property
    def cop(self) -> Temporal:
        """
        The nominal COP
        """
        return self._cop

    @cop.setter
    def cop(self, cop: Temporal | Number | pd.Series | None):
        self.set_temporal("_cop", cop)

    # additional attributes

    def calc_cop(self) -> Temporal:  # [1]
        """
        Calculate the COP based on input and output flows.
        """
        output_flow = self.get_output_flow(Medium.THERMAL_ENERGY, medium_relation="socket_specifies")
        input_flow = self.get_input_flow(Medium.ELECTRIC_ENERGY)
        return output_flow / input_flow

    def calc_scop(self) -> float | None:  # [1]
        """
        Calculate the SCOP based on input and output flows.
        """
        output_flow = self.get_output_flow(Medium.THERMAL_ENERGY, medium_relation="socket_specifies").total
        input_flow = self.get_input_flow(Medium.ELECTRIC_ENERGY).total
        if output_flow is not None and input_flow is not None:
            return output_flow / input_flow

    def calc_carnot_cop(self) -> Temporal:
        """
        The (theoretical) Carnot COP calculated from `output_forward_temperature` and
        `input_forward_temperature` of the Heatpump.

        .. math:: \text{COP} = \frac{T_{\text{out,f}}}{T_{\text{out,f}} - T_{\text{in,f}}}
        """
        if self.output_forward_temperature.is_empty or self.input_forward_temperature.is_empty:
            return Temporal()
        cop = convert_unit(self.output_forward_temperature.series, "°C", "K") / (
            self.output_forward_temperature.series - self.input_forward_temperature.series
        )
        return Temporal(series=cop, timeindex=self.timeindex)

    def calc_reduced_carnot_cop(self) -> Temporal:
        """
        The theoretical COP calculated from `output_forward_temperature`,
        `input_forward_temperature` and `efficiency_carnot` of the Heatpump.

        .. math:: \text{COP} = \frac{T_{\text{out,f}}}{T_{\text{out,f}} - T_{\text{in,f}}} \cdot \eta_{\text{carnot}}
        """
        return self.calc_carnot_cop() * self.efficiency_carnot

    def calc_lorenz_cop(self) -> Temporal:
        """
        The (theoretical) Lorenz COP calculated from the medium output temperature
        and the medium input temperature of the Heatpump.

        .. math::

            \text{COP} = \frac{T_{\text{out,m}}}{T_{\text{out,m}} - T_{\text{in,m}}}
            T_{\text{out,m}} = \frac{T_{\text{out,f}} - T_{\text{out,r}}}{\ln\left(\frac{T_{\text{out,f}}}{T_{\text{out,r}}}\right)}
            T_{\text{in,m}} = \frac{T_{\text{in,f}} - T_{\text{in,r}}}{\ln\left(\frac{T_{\text{in,f}}}{T_{\text{in,r}}}\right)}

        """
        if any(
            [
                self.output_forward_temperature.is_empty,
                self.output_return_temperature.is_empty,
                self.input_forward_temperature.is_empty,
                self.input_return_temperature.is_empty,
            ]
        ):
            return Temporal()

        t_out_f = convert_unit(self.output_forward_temperature.series, "°C", "K")
        t_out_r = convert_unit(self.output_return_temperature.series, "°C", "K")
        t_in_f = convert_unit(self.input_forward_temperature.series, "°C", "K")
        t_in_r = convert_unit(self.input_return_temperature.series, "°C", "K")

        t_out_medium = (t_out_f - t_out_r) / np.log(t_out_f / t_out_r)
        t_in_medium = (t_in_f - t_in_r) / np.log(t_in_f / t_in_r)

        cop = t_out_medium / (t_out_medium - t_in_medium)

        return Temporal(series=cop, timeindex=self.timeindex)

    def calc_reduced_lorenz_cop(self) -> Temporal:
        """
        The Lorenz COP calculated from the medium output temperature,
        the medium input temperature and `efficiency_lorenz` of the Heatpump.

        .. math::

            \text{COP} = \frac{T_{\text{out,m}}}{T_{\text{out,m}} - T_{\text{in,m}}} \cdot \eta_{\text{lorenz}}
            T_{\text{out,m}} = \frac{T_{\text{out,f}} - T_{\text{out,r}}}{\ln\left(\frac{T_{\text{out,f}}}{T_{\text{out,r}}}\right)}
            T_{\text{in,m}} = \frac{T_{\text{in,f}} - T_{\text{in,r}}}{\ln\left(\frac{T_{\text{in,f}}}{T_{\text{in,r}}}\right)}
        """
        return self.calc_lorenz_cop() * self.efficiency_lorenz


class BrineWaterHeatpump(Heatpump):
    _INPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY, Medium.BRINE_THERMAL_ENERGY]
    _OUTPUT_MEDIUMS = [Medium.WATER_THERMAL_ENERGY]


class WaterWaterHeatpump(Heatpump):
    _INPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY, Medium.WATER_THERMAL_ENERGY]
    _OUTPUT_MEDIUMS = [Medium.WATER_THERMAL_ENERGY]


class LakeWaterHeatpump(WaterWaterHeatpump): ...  # TODO rename to AmbientWaterWaterHeatpump?


class AirWaterHeatpump(Heatpump):
    _INPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY, Medium.AIR_THERMAL_ENERGY]
    _OUTPUT_MEDIUMS = [Medium.WATER_THERMAL_ENERGY]


class AirAirHeatpump(Heatpump):
    _INPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY]
    _OUTPUT_MEDIUMS = [Medium.AIR_THERMAL_ENERGY]


class BoosterHeatpump(Heatpump):
    """
    Device that raises the temperature of a mass flow by extracting heat from
    another reservoir
    """

    _INPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY, Medium.THERMAL_ENERGY]  # 1: cold reservoir
    _OUTPUT_MEDIUMS = [Medium.WATER_THERMAL_ENERGY]  # massflow to be boosted (for net balance it's just an output)


class LargeScaleHeatpump(Heatpump):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def calc_empirical_cop(self):
        # TODO concrete device model - remove / move to BRIX
        # TODO adapt to Temporal
        list_cop = []
        for i in range(self.temperature_source.shape[0]):  # TODO use boolean indexing
            if self.temperature_source.iloc[i] < self.temperature_supply.iloc[i]:
                list_cop.append(
                    1.4480
                    * 10**12
                    * (self.temperature_supply.iloc[i] - self.temperature_source.iloc[i] + 2 * 88.730) ** (-4.9460)
                )
            else:
                list_cop.append(10**6)
        self.thermal_efficiency = pd.Series(list_cop, index=self.temperature_source.index)


class Chiller(Transformer, ThermalComponent):
    # TODO INPUT_MEDIUMS, OUTPUT_MEDIUMS?
    eer_nominal: float = None


class CompressionChiller(Chiller):
    _INPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY]
    _OUTPUT_MEDIUMS = [Medium.WATER_THERMAL_ENERGY, Medium.WATER_THERMAL_ENERGY]  # 1.  supply, 2. waste heat


class HybridBrineWaterHeatpump(CombiAsset):
    DEVICE_TYPES = [BrineWaterHeatpump, CompressionChiller]


class HybridAirWaterHeatpump(CombiAsset):
    DEVICE_TYPES = [AirWaterHeatpump, CompressionChiller]


# ----------------------------------------------------------------------------------------------------------------------
# other Transformers
# ----------------------------------------------------------------------------------------------------------------------


class ElectricTransformer(Transformer):
    # TODO too many constants
    # TODO many attributes
    # TODO documentation missing

    # class constants:
    _OUTPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY]  # TODO no input medium?

    # temporal attributes:
    _TEMPORAL_ATTRIBUTES = ["_transformer_load"]
    _transformer_load: Temporal = None

    # additional attributes:
    sn_mva: float = 0.4
    vn_hv_kv: float = 20
    vn_lv_kv: float = 0.4
    vk_percent: float = 6
    vkr_percent: float = 1.425
    pfe_kw: float = 1.35
    i0_percent: float = 0.3375
    shift_degree: float = 150
    vector_group: str = "Dyn5"
    tap_side: str = "hv"
    tap_neutral: float = 0
    tap_min: float = -2
    tap_max: float = 2
    tap_step_degree: float = 2.5
    tap_step_percent: float = 0
    tap_phase_shifter: bool = False

    # properties for temporal attributes:

    @property
    def transformer_load(self) -> Temporal:
        return self._transformer_load

    @transformer_load.setter
    def transformer_load(self, transformer_load: Temporal | Number | pd.Series | None):
        self.set_temporal("_transformer_load", transformer_load)


class ElectrodeHeater(Transformer, ThermalComponent):
    """
    Device that prepares DHW or space heating by consuming electricity.
    """

    # class constants:
    _INPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY]
    _OUTPUT_MEDIUMS = [Medium.THERMAL_ENERGY]

    # additional attributes:
    efficiency_nominal: float = None


class ElectrodeBooster(Transformer, ThermalComponent):
    """
    Device that feeds from a low-exergy source and supplies a high-exergy
    target by consuming electricity.

    This could be used to prepare DHW from a space heating reservoir, or to
    raise the space heating temperature supplied original by RE sources.
    """

    _INPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY, Medium.THERMAL_ENERGY]  # TODO THERMAL_ENERGY needed?
    _OUTPUT_MEDIUMS = [Medium.THERMAL_ENERGY]


class HeatExchanger(Transformer, ThermalComponent):
    """
    Device that transfers heat from a source mass with (slightly or
    much) higher temperature down to a target mass with lower temperature.
    """

    _INPUT_MEDIUMS = [Medium.THERMAL_ENERGY]
    _OUTPUT_MEDIUMS = [Medium.THERMAL_ENERGY]


class FreshWaterStation(HeatExchanger): ...


# ----------------------------------------------------------------------------------------------------------------------
# Boilers and CHPs
# ----------------------------------------------------------------------------------------------------------------------


class Boiler(Transformer, ThermalComponent):
    # class constants:
    _INPUT_MEDIUMS = [Medium.CHEMICAL_ENERGY]
    _OUTPUT_MEDIUMS = [Medium.THERMAL_ENERGY]

    # additional attributes:
    efficiency_nominal: float = None


class MethaneBoiler(Boiler):
    _INPUT_MEDIUMS = [Medium.NATURAL_GAS]
    _OUTPUT_MEDIUMS = [Medium.WATER_THERMAL_ENERGY]


class FuelOilBoiler(Boiler):
    _INPUT_MEDIUMS = [Medium.FUEL_OIL]
    _OUTPUT_MEDIUMS = [Medium.WATER_THERMAL_ENERGY]


class BiomassBoiler(Boiler):
    _INPUT_MEDIUMS = [Medium.BIOMASS]
    _OUTPUT_MEDIUMS = [Medium.WATER_THERMAL_ENERGY]


class HydrogenBoiler(Boiler):
    _INPUT_MEDIUMS = [Medium.HYDROGEN]
    _OUTPUT_MEDIUMS = [Medium.WATER_THERMAL_ENERGY]


class Chp(Transformer, ThermalComponent):
    # class constants:
    _INPUT_MEDIUMS = [Medium.CHEMICAL_ENERGY]
    _OUTPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY, Medium.WATER_THERMAL_ENERGY]

    # additional attributes:
    nominal_electricity_ratio: float = None  # [1] use _input, _output to calc actual ratio
    nominal_heat_ratio: float = None  # [1] use _input, _output to calc actual ratio


class MethaneChp(Chp):
    _INPUT_MEDIUMS = [Medium.NATURAL_GAS]


class BiomassChp(Chp):
    _INPUT_MEDIUMS = [Medium.BIOMASS]


class Electrolyzer(Transformer, ThermalComponent):
    _INPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY]
    _OUTPUT_MEDIUMS = [Medium.HYDROGEN, Medium.WATER_THERMAL_ENERGY]


class FuelCell(Transformer, ThermalComponent):
    _INPUT_MEDIUMS = [Medium.HYDROGEN]
    _OUTPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY, Medium.WATER_THERMAL_ENERGY]


# ----------------------------------------------------------------------------------------------------------------------
# Thermal Storages
# ----------------------------------------------------------------------------------------------------------------------


class ThermalStorage(Storage, ThermalComponent):  # TODO not all ThermalStorages have volume and area
    # class constants:
    _INPUT_MEDIUMS = [Medium.THERMAL_ENERGY]
    _OUTPUT_MEDIUMS = [Medium.THERMAL_ENERGY]

    # additional attributes: # TODO move these to WaterThermalEnergyStorage or SensibleThermalEnergyStorage soon
    volume: float = None  # [m³]
    ratio_area_volume: float = None  # [1/m]
    usable_temperature_delta: float = None  # [K] used to convert energy capacity to volume (E = V * ρ * c_p * ΔT)


class SensibleThermalEnergyStorage(ThermalStorage): ...


class WaterThermalEnergyStorage(SensibleThermalEnergyStorage):
    """
    A sensible thermal energy storage that uses water as storage medium
    """


class TankThermalEnergyStorage(WaterThermalEnergyStorage): ...


class DhwStorage(TankThermalEnergyStorage): ...


class HeatingStorage(TankThermalEnergyStorage): ...


class PitThermalEnergyStorage(WaterThermalEnergyStorage):

    # temporal attributes:
    _TEMPORAL_ATTRIBUTES = [
        "_temperature_top",
        "_temperature_bottom",
    ]
    _temperature_top: Temporal = None  # [°C]
    _temperature_bottom: Temporal = None  # [°C]

    # additional attributes:
    lambda_top: float = None  # [kW/mK]
    thickness_insulation_top: float = None  # [m]
    lambda_side_bottom: float = None  # [kW/mK]
    thickness_insulation_side_bottom: float = None  # [m]
    temperature_soil: float = None  # [°C] # TODO get from environment?
    area_top: float = None  # [m²]
    area_bottom: float = None  # [m²]
    area_sides: float = None  # [m²]
    height: float = None

    # properties for temporal attributes:

    @property
    def temperature_top(self) -> Temporal:
        return self._temperature_top

    @temperature_top.setter
    def temperature_top(self, temperature_top: Temporal | Number | pd.Series | None):
        self.set_temporal("_temperature_top", temperature_top)

    @property
    def temperature_bottom(self) -> Temporal:
        return self._temperature_bottom

    @temperature_bottom.setter
    def temperature_bottom(self, temperature_bottom: Temporal | Number | pd.Series | None):
        self.set_temporal("_temperature_bottom", temperature_bottom)


class IceStorage(ThermalStorage):
    height: float = None  # [m]
    radius: float = None  # [m]


class BoreholeThermalEnergyStorage(ThermalStorage):
    # TODO add units
    # TODO lot of constants...
    # TODO very similar to BHE...

    # class constants:
    _INPUT_MEDIUMS = [Medium.THERMAL_ENERGY]
    _OUTPUT_MEDIUMS = [Medium.THERMAL_ENERGY]

    # additional attributes:
    inner_diameter_pipe: float = 0.0216  # 0.026 from EED example
    outer_diameter_pipe: float = 0.02667  # 0.032 from EED example
    shank_spacing_pipe: float = 0.0323  # 0.0604 from EED example
    roughness_pipe: float = 1.0e-6  #
    conductivity_pipe: float = 0.4  # 0.42 from EED example
    rho_cp_pipe: float = 1542000.0  #
    conductivity_soil: float = 2.0
    rho_cp_soil: float = 2343493.0
    conductivity_grout: float = (
        1.0  # kg: idea: Would it be clearer if parameters were named with their object in the first place and the specification second? -> grout_conductivity, grout_rho
    )
    rho_cp_grout: float = 3901000.0
    undisturbed_ground_temp: float = None
    drilling_depth: float = None
    buried_depth: float = 2.0
    diameter: float = 0.150
    simulation_length: int = (
        None  # kg: Aren't these parameters very specific for the geothermal installer and would be better placed there?
    )
    eft_min: float = None  # minimal fluid temperature
    eft_max: float = None
    drilling_depth_min: float = None
    drilling_depth_max: float = None
    spacing_min: float = None
    spacing_max: float = None
    n_boreholes: int = None
    covered_area: float = None

    def calc_length_per_borehole(self) -> float | None:
        # TODO review this relations
        if self.drilling_depth is not None:
            if self.buried_depth is None:
                return self.drilling_depth
            else:
                return self.drilling_depth - self.buried_depth

    def calc_total_length(self) -> float | None:
        length_per_borehole = self.calc_length_per_borehole()
        if length_per_borehole is not None:
            return self.n_boreholes * length_per_borehole


class MineThermalEnergyStorage(ThermalStorage): ...


# ----------------------------------------------------------------------------------------------------------------------
# Other Storages
# ----------------------------------------------------------------------------------------------------------------------


class ElectricityStorage(Storage):
    _INPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY]
    _OUTPUT_MEDIUMS = [Medium.ELECTRIC_ENERGY]


class Battery(ElectricityStorage): ...


class HydrogenStorage(Storage):
    _INPUT_MEDIUMS = [Medium.HYDROGEN]
    _OUTPUT_MEDIUMS = [Medium.HYDROGEN]


# ----------------------------------------------------------------------------------------------------------------------
# CombiAssets
# ----------------------------------------------------------------------------------------------------------------------


class PtesHeatpumpCombination(CombiAsset):
    """

    Example
    -------

    ```
        >>> phc = PtesHeatpumpCombination()
        >>> dh = EnergySystem()
        >>> dh.add_components(phc)
        >>> phc.hp.exists = False
        >>> phc.ptes.capacity = 100
        >>> phc.hp.host
        dh
    ```

    The `CombiDevice` is a `Device` on its own, so you can set the usual
    attributes:
    ```
        >>> phc = PtesHeatpumpCombination()
        >>> dh = EnergySystem()
        >>> dh.add_components(phc)
        >>> phc.exists = False
        >>> phc.host
        dh
    ```
    """

    # class constants:
    _ASSET_TYPES = [PitThermalEnergyStorage, WaterWaterHeatpump]

    @property
    def ptes(self) -> PitThermalEnergyStorage:
        return self.get_device(PitThermalEnergyStorage)

    @property
    def hp(self) -> WaterWaterHeatpump:
        return self.get_device(WaterWaterHeatpump)
