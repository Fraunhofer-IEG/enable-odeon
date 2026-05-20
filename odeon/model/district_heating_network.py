from __future__ import annotations
from enum import Enum
from numbers import Number
from typing import Literal
import numpy as np
import pandas as pd

from .base import Object
from .geometry import Geometry
from .temporal import Temporal
from .energy_network import EnergyNetwork, EnergyNetworkObject, EnergyNode, EnergyEdge
from .network import Edge, Node
from .device import BuildingDhnConnection, TransferStation
from .building import Building, Site

from ..processing.utils.utils import typeerror_if_not_isinstance, typeerror_if_not_isinstance_or_none

class DhnFluid(str, Enum):
    WATER = "Water"
    BRINE_E_GLYCOL_25 = "INCOMP::MEG-25%"  # TODO please add explaining comment


class DhnObject(EnergyNetworkObject):  # TODO necessary?
    ...


class DistrictHeatingNetwork(EnergyNetwork):
    fluid: DhnFluid = None

    def __init__(self, nodes: list[Node] = None, edges: list[Edge] = None, **kwargs):
        self.fluid = DhnFluid.WATER
        super().__init__(nodes=nodes, edges=edges, **kwargs)

    @property
    def pipes(self) -> list["DhnPipe"]:
        pipes = []
        for edge in self.edges:
            pipes += edge.pipes
        return pipes

    @property
    def junctions(self) -> list["DhnJunction"]:
        junctions = []
        for node in self.nodes:
            junctions += node.junctions
        return junctions

    @property
    def building_dhn_connections(self):
        raise Exception("deprecated. Use get_attachments_of_type(BuildingDhnConnection)")

    @property
    def transformers(self):
        raise Exception("deprecated. Use get_attachments_of_type(Transformer)")

    @property
    def pipes_supply(self) -> "DhnPipe":
        pipes_supply = [edge.pipe_supply for edge in self.edges if isinstance(edge, DhnEdge)]
        return pipes_supply

    @property
    def pipes_return(self) -> "DhnPipe":
        pipes_return = [edge.pipe_return for edge in self.edges if isinstance(edge, DhnEdge)]
        return pipes_return

    @property
    def junctions_supply(self) -> "DhnJunction":
        return [node.junction_supply for node in self.nodes]

    @property
    def junctions_return(self) -> "DhnJunction":
        return [node.junction_return for node in self.nodes]

    @property
    def partly_piped(self):
        """
        Check if the network has any pipes or junctions.
        """
        return bool(self.pipes or self.junctions)

    @property
    def fully_piped(self):
        """
        Check if all nodes have a supply and return junction, and all edges have
        a supply and return pipe.
        """
        ret = all(node.junction_supply is not None and node.junction_return is not None for node in self.nodes)
        ret &= all(edge.pipe_supply is not None and edge.pipe_return is not None for edge in self.edges)
        return ret

    def is_applied(
        self,
        check_producers: bool = True,
        check_consumers: bool = True,
        check_dhn_component_links: bool = False,
    ) -> bool:
        """
        Checks that the district heating network is properly applied meaning
        that there must only be `BuildingDhnConnections` and `TransferStations`
        attached as consumers and producers and no `Sites` or `Buildings`.
        The method also checks that all `TransferStations` are part of a `Site`
        or `Building` energy system and all `BuildingDhnConnections` are part
        of a `Building` energy system.
        If `check_dhn_component_links` is set to True, it is also checks that
        all `TransferStations` and `BuildingDhnConnections` attached to the
        network are also linked as `input_components` and `output_components`
        and that there outputs and inputs are not None.
        """

        # Check validity of input arguments
        if check_dhn_component_links and not (check_producers and check_consumers):
            raise ValueError(
                "check_dhn_component_links can only be True if both check_producers and check_consumers are True."
            )

        if check_producers:
            # no Site as attachment
            if not len(self.get_nodes_by_attachment_types(Site)) == 0:
                return False
            # at least one TransferStation
            if not len(self.get_nodes_by_attachment_types(TransferStation)) > 0:
                return False
            # All TransferStations are part of a Site or Building energy system
            if not all(
                isinstance(node.attachment.energy_system.parent, (Building, Site))
                for node in self.get_nodes_by_attachment_types(TransferStation)
            ):
                return False

        if check_consumers:
            # no Building as attachment
            if not len(self.get_nodes_by_attachment_types(Building)) == 0:
                return False
            # at least one BuildingDhnConnection
            if not len(self.get_nodes_by_attachment_types(BuildingDhnConnection)) > 0:
                return False
            # All BuildingDhnConnections are part of a Building energy system
            if not all(
                isinstance(node.attachment.energy_system.parent, Building)
                for node in self.get_nodes_by_attachment_types(BuildingDhnConnection)
            ):
                return False

        if check_dhn_component_links:
            # check that all components are present
            if not set(self.get_attachments_of_type(TransferStation)) == set(self.input_components):
                return False
            if not set(self.get_attachments_of_type(BuildingDhnConnection)) == set(self.output_components):
                return False
            # Check that outputs and inputs are set
            if any(c.output is None for c in self.input_components):
                return False
            if any(c.input is None for c in self.output_components):
                return False

        return True

    def get_pipe_between_junctions(self, junction_from: DhnJunction, junction_to: DhnJunction) -> DhnPipe:
        for pipe in self.pipes:
            if pipe.junction_from is junction_from and pipe.junction_to is junction_to:
                return pipe

    def get_pipes_by_junctions(
        self,
        junctions: DhnJunction | list[DhnJunction],
        direction: Literal["incoming", "outgoing", "both"] = "both",
        level: Literal["supply", "return", "both"] = "both",
    ):
        if isinstance(junctions, DhnJunction):
            junctions = [junctions]
        ret = []
        if level in ["supply", "both"]:
            for p in self.pipes_supply:
                if direction in ["outgoing", "both"] and p.junction_from in junctions and p not in ret:
                    ret.append(p)
                if direction in ["incoming", "both"] and p.junction_to in junctions and p not in ret:
                    ret.append(p)
        if level in ["return", "both"]:
            for p in self.pipes_return:
                if direction in ["outgoing", "both"] and p.junction_from in junctions and p not in ret:
                    ret.append(p)
                if direction in ["incoming", "both"] and p.junction_to in junctions and p not in ret:
                    ret.append(p)
        return ret


class DhnNode(EnergyNode, DhnObject):

    # children attributes:
    _CHILDREN_ATTRIBUTES = {
        "_junction_supply": "DhnJunction",
        "_junction_return": "DhnJunction",
    }
    _junction_supply: "DhnJunction" = None
    _junction_return: "DhnJunction" = None

    def __init__(
        self,
        elevation: float | None = None,
        attachment: Object | None = None,
        geometry: Geometry | None = None,
        partitions: set[str] | None = None,
        **kwargs,
    ):
        kwargs |= dict(
            elevation=elevation,
            attachment=attachment,
            partitions=partitions,
            geometry=geometry,
        )
        super().__init__(**kwargs)

    @property
    def junctions(self) -> list["DhnJunction"]:
        return [self._junction_supply, self._junction_return]

    @property
    def junction_supply(self) -> "DhnJunction":
        return self._junction_supply

    @junction_supply.setter
    def junction_supply(self, junction_supply: "DhnJunction"):
        self.set_junction_supply(junction=junction_supply)

    @property
    def junction_return(self) -> "DhnJunction":
        return self._junction_return

    @junction_return.setter
    def junction_return(self, junction_return: "DhnJunction"):
        self.set_junction_return(junction=junction_return)

    @property
    def junctions(self) -> list["DhnJunction"]:
        """
        Return the junctions of this node, i.e. supply and return junctions (0, 1 or 2)
        """
        junctions = []
        if self._junction_supply is not None:
            junctions.append(self._junction_supply)
        if self._junction_return is not None:
            junctions.append(self._junction_return)
        return junctions

    def set_junction_supply(self, junction: "DhnJunction"):
        typeerror_if_not_isinstance(junction, DhnJunction)
        if self.junction_supply is not None:
            self.remove_junction_supply()
        self._junction_supply = junction
        junction._set_parent(self)

    def remove_junction_supply(self):
        if self.junction_supply is None:
            return
        pipes = self.network.get_pipes_by_junctions(junctions=self.junction_supply, level="supply")
        self._junction_supply.remove_from_parent()
        self._junction_supply = None
        for pipe in pipes:
            assert isinstance(pipe, DhnPipe)
            pipe.edge.remove_pipe_supply()

    def set_junction_return(self, junction: "DhnJunction"):
        typeerror_if_not_isinstance(junction, DhnJunction)
        if self.junction_return is not None:
            self.remove_junction_return()
        self._junction_return = junction
        junction._set_parent(self)

    def remove_junction_return(self):
        if self.junction_return is None:
            return
        pipes = self.network.get_pipes_by_junctions(junctions=self.junction_return, level="return")
        self._junction_return.remove_from_parent()
        self._junction_return = None
        for pipe in pipes:
            assert isinstance(pipe, DhnPipe)
            pipe.edge.remove_pipe_supply()

    def remove_junctions(self):
        self.remove_junction_supply()
        self.remove_junction_return()


class DhnJunction(DhnObject):

    # temporal attributes:
    _TEMPORAL_ATTRIBUTES = [
        "_temperature",
        "_pressure",
    ]
    _temperature: Temporal = None  # [°C]
    _pressure: Temporal = None  # [Pa = kg/(ms²)]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    # properties for temporals:

    @property
    def temperature(self) -> Temporal:
        return self._temperature

    @temperature.setter
    def temperature(self, temperature: Temporal | Number | pd.Series | None):
        self.set_temporal("_temperature", temperature)

    @property
    def pressure(self) -> Temporal:
        return self._pressure

    @pressure.setter
    def pressure(self, pressure: Temporal | Number | pd.Series | None):
        self.set_temporal("_pressure", pressure)

    # additional methods:

    @property
    def network(self) -> DistrictHeatingNetwork | None:
        return self.parent.network if self.parent is not None else None

    @property
    def node(self) -> DhnNode:
        return self.parent

    @property  # TODO Verschaltung von attachments relevant: Wie werden Vor- und Rücklauf an den Attachments der Junctions verknüpft? /kg
    def attachment(self) -> Object:
        return self.node.attachment

    @attachment.setter
    def attachment(self, obj: Object):
        self.node.attachment = obj


class DhnEdge(EnergyEdge, DhnObject):

    # children attributes:
    _CHILDREN_ATTRIBUTES = {
        "_pipe_supply": "DhnPipe",
        "_pipe_return": "DhnPipe",
    }
    _pipe_supply: "DhnPipe" = None  # TODO Find supply pipe by a function/property
    _pipe_return: "DhnPipe" = None  # TODO Find return pipe by a function/property

    # temporal attributes:
    _TEMPORAL_ATTRIBUTES = ["_net_exergy_flow"]
    _net_exergy_flow: Temporal = None  # the net exergy flow through this edge per timestep or in total

    # other attributes:
    type: str = None
    distance_between_pipe_edges: float = None  # [m]
    distance_between_pipe_centers: float = None  # [m]
    _node_to: DhnNode = None
    _node_from: DhnNode = None
    _diameter: float = None  # [m]
    _material: str = (None,)
    _diameter_nominal_mm: float = None  # [mm]
    _u_value_w_per_sqm_k: float = None  # [W/(m2*K)]

    def __init__(
        self,
        node_from: Node | None = None,
        node_to: Node | None = None,
        diameter: float = None,
        material: str = None,
        length: float | None = None,
        partitions: set[str] | str | None = None,
        geometry: Geometry | None = None,
        **kwargs,
    ):
        self._diameter = diameter
        self._material = material
        super().__init__(
            node_from=node_from,
            node_to=node_to,
            length=length,
            partitions=partitions,
            geometry=geometry,
            **kwargs,
        )

    # properties for temporal attributes:

    @property
    def net_exergy_flow(self) -> Temporal:
        return self._net_exergy_flow

    @net_exergy_flow.setter
    def net_exergy_flow(self, net_exergy_flow: Temporal | Number | pd.Series | None):
        self.set_temporal("_net_exergy_flow", net_exergy_flow)

    # additional methods:

    @property
    def node_to(self) -> DhnNode:
        return self._node_to

    @node_to.setter
    def node_to(self, node: DhnNode):
        typeerror_if_not_isinstance_or_none(node, DhnNode)
        # workaround to call parent setter:
        super(__class__, self.__class__).node_to.__set__(self, node)

    @property
    def node_from(self) -> DhnNode:
        return self._node_from

    @node_from.setter
    def node_from(self, node: DhnNode):
        typeerror_if_not_isinstance_or_none(node, DhnNode)
        # workaround to call parent setter:
        super(__class__, self.__class__).node_from.__set__(self, node)

    @property
    def pipe_supply(self) -> DhnPipe | None:
        return self._pipe_supply

    @pipe_supply.setter
    def pipe_supply(self, pipe_supply: DhnPipe):
        self.set_pipe_supply(pipe=pipe_supply)

    @property
    def pipe_return(self) -> DhnPipe | None:
        return self._pipe_return

    @pipe_return.setter
    def pipe_return(self, pipe_return: "DhnPipe"):
        self.set_pipe_return(pipe=pipe_return)

    @property
    def pipes(self) -> list["DhnPipe"]:
        """
        Return contained pipes (0, 1 or 2)
        """
        pipes = []
        if self._pipe_supply is not None:
            pipes.append(self._pipe_supply)
        if self._pipe_return is not None:
            pipes.append(self._pipe_return)
        return pipes

    @property
    def material(self) -> str | None:
        pipe_values = []
        if self._material is not None:
            return self._material
        else:
            if self._pipe_supply is not None and self._pipe_supply.material is not None:
                pipe_values.append(self._pipe_supply.material)
            if self._pipe_return is not None and self._pipe_return.material is not None:
                pipe_values.append(self._pipe_return.material)
            if len(pipe_values) > 1:
                raise Exception("Pipes have different materials. Can't provide unifying value")
            if pipe_values:
                return pipe_values[0]

    @material.setter
    def material(self, material: str):
        self._material = material
        if self._pipe_supply is not None and self._pipe_supply.material is not None:
            self._pipe_supply.material = material
        if self._pipe_return is not None and self._pipe_return.material is not None:
            self._pipe_return.material = material

    @property
    def diameter(self) -> float | None:
        pipe_values = []
        if self._diameter is not None:
            return self._diameter
        else:
            if self._pipe_supply is not None and self._pipe_supply.diameter is not None:
                pipe_values.append(self._pipe_supply.diameter)
            if self._pipe_return is not None and self._pipe_return.diameter is not None:
                pipe_values.append(self._pipe_return.diameter)
            if pipe_values:
                return np.mean(pipe_values)

    @diameter.setter
    def diameter(self, diameter: float):
        self._diameter = diameter
        if self._pipe_supply is not None and self._pipe_supply.diameter is not None:
            self._pipe_supply.diameter = diameter
        if self._pipe_return is not None and self._pipe_return.diameter is not None:
            self._pipe_return.diameter = diameter

    @property
    def diameter_nominal_mm(self) -> float | None:
        pipe_values = []
        if self._diameter_nominal_mm is not None:
            return self._diameter_nominal_mm
        else:
            if self._pipe_supply is not None and self._pipe_supply.diameter_nominal_mm is not None:
                pipe_values.append(self._pipe_supply.diameter_nominal_mm)
            if self._pipe_return is not None and self._pipe_return.diameter_nominal_mm is not None:
                pipe_values.append(self._pipe_return.diameter_nominal_mm)
            if pipe_values:
                return np.mean(pipe_values)

    @diameter_nominal_mm.setter
    def diameter_nominal_mm(self, diameter_nominal_mm: float):
        self._diameter_nominal_mm = diameter_nominal_mm
        if self._pipe_supply is not None and self._pipe_supply.diameter_nominal_mm is not None:
            self._pipe_supply.diameter_nominal_mm = diameter_nominal_mm
        if self._pipe_return is not None and self._pipe_return.diameter_nominal_mm is not None:
            self._pipe_return.diameter_nominal_mm = diameter_nominal_mm

    @property
    def u_value_w_per_sqm_k(self) -> float | None:
        pipe_values = []
        if self._u_value_w_per_sqm_k is not None:
            return self._u_value_w_per_sqm_k
        else:
            if self._pipe_supply is not None and self._pipe_supply.u_value_w_per_sqm_k is not None:
                pipe_values.append(self._pipe_supply.u_value_w_per_sqm_k)
            if self._pipe_return is not None and self._pipe_return.u_value_w_per_sqm_k is not None:
                pipe_values.append(self._pipe_return.u_value_w_per_sqm_k)
            if pipe_values:
                return np.mean(pipe_values)

    @u_value_w_per_sqm_k.setter
    def u_value_w_per_sqm_k(self, u_value_w_per_sqm_k: float):
        self._u_value_w_per_sqm_k = u_value_w_per_sqm_k
        if self._pipe_supply is not None and self._pipe_supply.u_value_w_per_sqm_k is not None:
            self._pipe_supply.u_value_w_per_sqm_k = u_value_w_per_sqm_k
        if self._pipe_return is not None and self._pipe_return.u_value_w_per_sqm_k is not None:
            self._pipe_return.u_value_w_per_sqm_k = u_value_w_per_sqm_k

    @property
    def heat_flow(self) -> Temporal:  # [kW]
        if (
            self._pipe_supply is not None
            and self._pipe_return is not None
            and not self._pipe_supply.mass_flow_kg_per_s.is_empty
            and not self._pipe_supply.temperature_in.is_empty
            and not self._pipe_return.temperature_in.is_empty
            and self._pipe_supply.network.fluid == DhnFluid.WATER
        ):
            # TODO cp is hardcode here. Value should be placed somewhere self.network.fluid I guess...
            series = (
                self._pipe_supply.mass_flow_kg_per_s
                * 4.18
                * (self._pipe_supply.temperature_in - self._pipe_return.temperature_in)
            )
            return series
        else:
            return Temporal()

    def set_pipe_supply(self, pipe: "DhnPipe"):

        typeerror_if_not_isinstance(pipe, DhnPipe)

        # set junction from self to pipe or vice versa, and assert that they don't contradict:
        if self.node_from.junction_supply is None and pipe.junction_from is not None:
            self.node_from.set_junction_supply(pipe.junction_from)
        elif self.node_from.junction_supply is not None and pipe.junction_from is None:
            if pipe.parent is None:
                pipe._set_parent(self)
            else:
                assert pipe.parent is self  # probably already set at other node
                pipe._set_parent(self, error_if_not_found=False)
            pipe.set_junction_from(self.node_from.junction_supply)
        elif self.node_from.junction_supply is not pipe.junction_from:
            raise Exception()

        # set junction from self to pipe or vice versa, and assert that they don't contradict:
        if self.node_to.junction_supply is None and pipe.junction_to is not None:
            self.node_to.set_junction_supply(pipe.junction_to)
        elif self.node_to.junction_supply is not None and pipe.junction_to is None:
            if pipe.parent is None:
                pipe._set_parent(self)
            else:
                assert pipe.parent is self  # probably already set at other node
                pipe._set_parent(self, error_if_not_found=False)
            pipe.set_junction_to(self.node_to.junction_supply)
        elif self.node_to.junction_supply is not pipe.junction_to:
            raise Exception()

        # assert pipe.junction_from is None or pipe.junction_from is self.node_from.junction_supply
        # assert pipe.junction_to is None or pipe.junction_to is self.node_to.junction_supply
        self._pipe_supply = pipe
        if pipe.parent is None:
            pipe._set_parent(self)
        else:
            assert pipe.parent is self  # probably already set at a node

    def remove_pipe_supply(self):
        self._pipe_return.remove_from_parent()  # or remove_net / parent as method in DhnObject?
        self._pipe_return = None
        self._pipe_supply = None

    def set_pipe_return(self, pipe: "DhnPipe"):

        typeerror_if_not_isinstance(pipe, DhnPipe)

        # set junction from self to pipe or vice versa, and assert that they don't contradict:
        if self.node_from.junction_return is None and pipe.junction_to is not None:
            self.node_from.set_junction_return(pipe.junction_to)
        elif self.node_from.junction_return is not None and pipe.junction_to is None:
            if pipe.parent is None:
                pipe._set_parent(self)
            else:
                assert pipe.parent is self  # probably already set at other node
                pipe._set_parent(self, error_if_not_found=False)
            pipe.set_junction_to(self.node_from.junction_return)
        elif self.node_from.junction_return is not pipe.junction_to:
            raise Exception()

        # set junction from self to pipe or vice versa, and assert that they don't contradict:
        if self.node_to.junction_return is None and pipe.junction_from is not None:
            self.node_to.set_junction_return(pipe.junction_from)
        elif self.node_to.junction_return is not None and pipe.junction_from is None:
            if pipe.parent is None:
                pipe._set_parent(self)
            else:
                assert pipe.parent is self  # probably already set at other node
                pipe._set_parent(self, error_if_not_found=False)
            pipe.set_junction_from(self.node_to.junction_return)
        elif self.node_to.junction_return is not pipe.junction_from:
            raise Exception()

        # assert pipe.junction_from is None or pipe.junction_from is self.node_from.junction_return
        # assert pipe.junction_to is None or pipe.junction_to is self.node_to.junction_return
        self._pipe_return = pipe
        if pipe.parent is None:
            pipe._set_parent(self)
        else:
            assert pipe.parent is self  # probably already set at other node

    def remove_pipe_return(self):
        self._pipe_return.remove_from_parent()  # or remove_net / parent as method in DhnObject?
        self._pipe_return = None


class DhnPipe(DhnObject):
    """
    Parent: DhnEdge
    """

    # associated attributes:
    _ASSOCIATED_ATTRIBUTES = ["_junction_from", "_junction_to"]
    _junction_from: DhnJunction = None
    _junction_to: DhnJunction = None

    # temporal attributes:
    _TEMPORAL_ATTRIBUTES = [
        "_mass_flow_kg_per_s",
        "_mean_fluid_velocity",
        "_temperature_in",
        "_temperature_out",
        "_temperature_external",
        "_pressure_in",
        "_pressure_out",
        "_reynolds",
        "_friction_coef_lambda",
    ]
    _mass_flow_kg_per_s: Temporal = None  # [kg/s]
    _mean_fluid_velocity: Temporal = None  # [m/s]
    _temperature_in: Temporal = None  # [°C]
    _temperature_out: Temporal = None  # [°C]
    _temperature_external: Temporal = None  # [°C] ambient temperature
    _pressure_in: Temporal = None  # [Pa = kg/(ms²) = 1e-5 bar]
    _pressure_out: Temporal = None  # [Pa = kg/(ms²) = 1e-5 bar]
    _reynolds: Temporal = None  # [1]
    _friction_coef_lambda: Temporal = None

    # other attributes:
    type: str = None
    material: str = None
    diameter: float = None  # [m]
    diameter_nominal_mm: float = None  # [mm] (e.g. 80 = DN80)
    u_value_w_per_sqm_k: float = None  # [W/(m²K)]
    friction: float = None  # [1]
    roughness: float = None  # [m]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    # properties for temporal attributes:

    @property
    def mass_flow_kg_per_s(self) -> Temporal:
        return self._mass_flow_kg_per_s

    @mass_flow_kg_per_s.setter
    def mass_flow_kg_per_s(self, mass_flow_kg_per_s: Temporal | Number | pd.Series | None):
        self.set_temporal("_mass_flow_kg_per_s", mass_flow_kg_per_s)

    @property
    def mean_fluid_velocity(self) -> Temporal:
        return self._mean_fluid_velocity

    @mean_fluid_velocity.setter
    def mean_fluid_velocity(self, mean_fluid_velocity: Temporal | Number | pd.Series | None):
        self.set_temporal("_mean_fluid_velocity", mean_fluid_velocity)

    @property
    def temperature_in(self) -> Temporal:
        return self._temperature_in

    @temperature_in.setter
    def temperature_in(self, temperature_in: Temporal | Number | pd.Series | None):
        self.set_temporal("_temperature_in", temperature_in)

    @property
    def temperature_out(self) -> Temporal:
        return self._temperature_out

    @temperature_out.setter
    def temperature_out(self, temperature_out: Temporal | Number | pd.Series | None):
        self.set_temporal("_temperature_out", temperature_out)

    @property
    def temperature_external(self) -> Temporal:
        return self._temperature_external

    @temperature_external.setter
    def temperature_external(self, temperature_external: Temporal | Number | pd.Series | None):
        self.set_temporal("_temperature_external", temperature_external)

    @property
    def pressure_in(self) -> Temporal:
        return self._pressure_in

    @pressure_in.setter
    def pressure_in(self, pressure_in: Temporal | Number | pd.Series | None):
        self.set_temporal("_pressure_in", pressure_in)

    @property
    def pressure_out(self) -> Temporal:
        return self._pressure_out

    @pressure_out.setter
    def pressure_out(self, pressure_out: Temporal | Number | pd.Series | None):
        self.set_temporal("_pressure_out", pressure_out)

    @property
    def reynolds(self) -> Temporal:
        return self._reynolds

    @reynolds.setter
    def reynolds(self, reynolds: Temporal | Number | pd.Series | None):
        self.set_temporal("_reynolds", reynolds)

    @property
    def friction_coef_lambda(self) -> Temporal:
        return self._friction_coef_lambda

    @friction_coef_lambda.setter
    def friction_coef_lambda(self, friction_coef_lambda: Temporal | Number | pd.Series | None):
        self.set_temporal("_friction_coef_lambda", friction_coef_lambda)

    # additional methods:

    @property
    def length(self) -> float | None:
        """
        The length of the pipe in meters.
        """
        return self.parent.length if self.parent is not None else None

    @property
    def network(self) -> DistrictHeatingNetwork | None:
        return self.parent.network if self.parent is not None else None

    @property
    def edge(self) -> DhnEdge | None:
        return self.parent

    def set_junction_to(self, junction: DhnJunction):
        typeerror_if_not_isinstance(junction, DhnJunction)
        if junction.network is None and self.network is not None:
            assert junction.parent is None
            junction._set_parent(self.parent.node_to)
        else:
            assert junction.network is self.network
        # assert junction.network is self.network
        self._junction_to = junction

    def set_junction_from(self, junction: DhnJunction):
        typeerror_if_not_isinstance(junction, DhnJunction)
        if junction.network is None and self.network is not None:
            assert junction.parent is None
            junction._set_parent(self.parent.node_from)
        else:
            assert junction.network is self.network
        # assert junction.network is self.network
        self._junction_from = junction

    def remove_junction_to(self):
        self._junction_to = None

    def remove_junction_from(self):
        self._junction_from = None

    @property
    def junction_from(self) -> DhnJunction:
        return self._junction_from

    @junction_from.setter
    def junction_from(self, junction_from: "DhnJunction"):
        self.set_junction_from(junction_from)

    @property
    def junction_to(self) -> DhnJunction:
        return self._junction_to

    @junction_to.setter
    def junction_to(self, junction_to: "DhnJunction"):
        self.set_junction_to(junction_to)

    @property
    def fluid(self) -> DhnFluid:
        return self.network.fluid

    @property
    def temperature_loss(self) -> Temporal:  # [K]
        if (
            isinstance(self.temperature_in, Temporal)
            and isinstance(self.temperature_out, Temporal)
            and not self.temperature_in.is_empty
            and not self.temperature_out.is_empty
        ):  # FIXME update criteria -> Done?
            return self.temperature_in - self.temperature_out
        else:
            return Temporal()

    @property
    def max_temperature_loss(self) -> float | None:  # [K]
        temperature_loss = self.temperature_loss
        if temperature_loss is not None:
            return temperature_loss.max()

    @property
    def pressure_loss(self) -> Temporal:  # [Pa]
        if (
            isinstance(self.pressure_in, Temporal)
            and isinstance(self.pressure_out, Temporal)
            and not self.pressure_in.is_empty
            and not self.pressure_out.is_empty
        ):  # FIXME update criteria -> Done?
            return self.pressure_in - self.pressure_out
        else:
            return Temporal()

    @property
    def max_pressure_loss(self) -> float | None:  # [Pa]
        pressure_loss = self.pressure_loss
        if pressure_loss is not None:
            return pressure_loss.max()

    @property
    def max_mean_fluid_velocity(self) -> float | None:  # [m/s]
        mean_fluid_velocity = self.mean_fluid_velocity
        if mean_fluid_velocity is not None:
            return mean_fluid_velocity.max()

    @property
    def pressure_loss_per_length(self) -> Temporal:  # [Pa/m]
        """
        The pressure loss in Pascal per meter.
        """
        if (
            isinstance(self.pressure_in, Temporal)
            and isinstance(self.pressure_out, Temporal)
            and not self.pressure_in.is_empty
            and not self.pressure_out.is_empty
        ):  # FIXME update criteria -> Done?
            return (self.pressure_in - self.pressure_out) / self.parent.length
        else:
            return Temporal()

    @property
    def heat_loss(self) -> Temporal:  # [kW]
        """
        Heatloss over pipe in kW.
        Values >0 correspond to a heat loss, while <0 would mean a heat gain
        over the pipe.
        """
        if (
            isinstance(self.mass_flow_kg_per_s, Temporal)
            and isinstance(self.temperature_in, Temporal)
            and isinstance(self.temperature_out, Temporal)
            and self.network.fluid == DhnFluid.WATER
            and not self.mass_flow_kg_per_s.is_empty
            and not self.temperature_in.is_empty
            and not self.temperature_out.is_empty
        ):  # FIXME update criteria -> Done?
            # TODO cp is hardcode here. Value should be placed somewhere self.network.fluid I guess...
            return self.mass_flow_kg_per_s * 4.18 * (self.temperature_in - self.temperature_out)
        else:
            return Temporal()

    @property
    def max_heat_loss(self) -> float | None:  # [kW]
        if self.heat_loss is not None:
            return self.heat_loss.max()

    # TODO further possible properties:
    # - heat flow (forward, return, net)
    # - heat loss
