from typing import Literal

from .base import Object
from .energy_system import EnergySystem, EnergySystemHost
from .network import Network, NetworkObject, Node, Edge
from .device import Bus
from .asset import Asset
from .temporal import Temporal

from ..processing.utils.utils import type_typetuple_or_typelist_to_typetuple


class EnergyNetwork(Network, Bus):
    """
    A class representing an energy network, which is a specialized type of
    network. It inherits additionally from `Bus`, which adds an energy topology
    and flow layer to the Network, allowing to connect components as inputs and
    outputs.
    Additionally, it inherits from `Asset`, which allows to store economic
    information that apply to the full network.
    """

    def __init__(self, nodes=None, edges=None, **kwargs):
        kwargs |= dict(nodes=nodes, edges=edges)
        super().__init__(**kwargs)

    def get_connected_energy_systems_via_links(self) -> list[EnergySystem]:
        """
        Returns a list of all energy systems that are directly connected to this
        energy network via links, i.e. component connections. This may include
        the energy system of the network itself.
        """
        components = self.components
        energy_systems = list(set(c.energy_system for c in components))
        return energy_systems

    def get_connected_energy_systems_via_attachments(self) -> list[EnergySystem]:
        """
        Returns a list of all energy systems that are directly connected to this
        energy network via attachments, i.e. nodes and edges that have an
        attachment. An energy systems is considered connected if it is attached
        to a node directly, or if an ancestor is attached, or if an offspring is
        attached.
        """
        attachments: list[Object] = self.attachments()
        energy_systems = []
        for attachment in attachments:
            energy_systems += attachment.find_objects(EnergySystem)
            energy_systems += attachment.get_ancestors_of_type(EnergySystem)
            if isinstance(attachment, EnergySystem):
                energy_systems.append(attachment)
        energy_systems = list(set(energy_systems))
        return energy_systems

    def get_connected_energy_system_hosts_via_links(self) -> list[EnergySystemHost]:
        """
        Returns a list of hosts of all energy system hosts that are directly
        connected to this energy network via links, i.e. component connections.
        This may include the energy system host of the network itself.

        Note that the classes `Building`, `BuildingUnit`, `Site`, and `Vicinity`
        all inherit from `EnergySystemHost`, so this method will return all
        instances of these classes that are connected to the energy network.
        """
        energy_systems = self.get_connected_energy_systems_via_links()
        energy_system_hosts = [
            e.get_closest_ancestor_of_type(EnergySystemHost, not_found="none") for e in energy_systems
        ]
        energy_system_hosts = list(set(energy_system_hosts))
        return energy_system_hosts

    def get_connected_energy_system_hosts_via_attachments(self) -> list[EnergySystemHost]:
        """
        Returns a list of hosts of all energy system hosts that are directly
        connected to this energy network via attachments. An energy systems host
        is considered connected if it is attached to a node directly, or if an
        ancestor is attached, or if an offspring is attached.
        """
        attachments: list[Object] = self.attachments()
        energy_system_hosts = []
        for attachment in attachments:
            energy_system_hosts += attachment.find_objects(EnergySystemHost)
            energy_system_hosts += attachment.get_ancestors_of_type(EnergySystemHost)
            if isinstance(attachment, EnergySystemHost):
                energy_system_hosts.append(attachment)
        energy_system_hosts = list(set(energy_system_hosts))
        return energy_system_hosts

    def get_connected_energy_system_hosts(self, type: type | list[type] = None) -> list[EnergySystemHost]:
        """
        Returns a list of all energy system hosts that are directly connected to
        this energy network. The hosts are considered connected if they are
        attached to a node directly, or if an ancestor is attached, or if an
        offspring is attached. The method checks for consistency between the two
        methods of connection (links and attachments) and raises an error if
        they are not consistent. If `type` is provided, it filters the hosts by
        the specified type(s).

        Note that the classes `Building`, `BuildingUnit`, `Site`, and `Vicinity`
        all inherit from `EnergySystemHost`, so this method will return all
        instances of these classes that are connected to the energy network.
        """
        hosts_links = self.get_connected_energy_system_hosts_via_links()
        hosts_attachments = self.get_connected_energy_system_hosts_via_attachments()
        if set(hosts_links) != set(hosts_attachments):
            raise ValueError(
                "Energy system hosts connected via links and \
                attachments are not consistent."
            )
        if type is not None:
            type = type_typetuple_or_typelist_to_typetuple(type)
            hosts_links = [h for h in hosts_links if isinstance(h, type)]
        return hosts_links

    def check_consistencey_of_connected_energy_system_hosts(self) -> bool:
        """
        Check whether the connections described by nodes' attachments and linked
        components are consistent. The descriptions are considered consistent if
        the accessible energy system hosts are the same for both methods.
        """
        hosts_links = self.get_connected_energy_system_hosts_via_links()
        hosts_attachments = self.get_connected_energy_system_hosts_via_attachments()
        return set(hosts_links) == set(hosts_attachments)

    def check_consistency_of_connected_components(self) -> bool:
        """
        Check whether the connections described by nodes' attachments and linked
        components are consistent. The descriptions are considered consistent if
        the linked components are exactly the same as the attachments.
        """
        components_links = self.input_components + self.output_components
        components_attachments = self.attachments()
        return set(components_links) == set(components_attachments)

    def apply_connections_from_attachments(
        self,
        input_component_types: list[type],
        output_component_types: list[type],
        if_extra_components: Literal["ignore", "warn", "error"] = "error",
        write_lossless_input_flow: bool = False,
    ):
        """
        Ensures that all components attached to nodes are also linked to the
        energy network as input and output components. If
        `write_lossless_input_flow` is set to True, it also writes a lossless
        input flow to the network based on the input flow of the output
        components (i.e. the output flows of the network).

        If any input component already has an output set, or if any output
        component already has an input set, an error will be raised. If there
        are any extra components that don't map to any attachment, this will
        either be ignored, warned about, or raise an error.

        Parameters
        ----------
        input_component_types : list[type], optional
            A list of component types that should be considered as input
            components.
        output_component_types : list[type], optional
            A list of component types that should be considered as output
            components.
        if_extra_components : Literal["ignore", "warn", "error"], optional
            Specifies how to handle extra components already connected to the
            network (as input or output) that do not map to any attachment.
            Options are "ignore", "warn", or "error". Defaults to "error".
        write_lossless_input_flow : bool, optional
            If set to True, writes a lossless input flow to the network based on
            the input flow of the output components (i.e. the output flows of
            the network). Defaults to False.
        """

        # collect currently connected components via attachments:
        input_components = self.get_attachments_of_type(input_component_types)
        output_components = self.get_attachments_of_type(output_component_types)

        # collect currently connected components via inputs and outputs:
        present_input_components = self.input_components
        present_output_components = self.output_components

        # select components that are not already connected:
        new_input_components = [c for c in input_components if c not in present_input_components]
        new_output_components = [c for c in output_components if c not in present_output_components]

        # check for conflicts:
        for component in new_input_components:
            if component.output is not None:
                raise ValueError(f"Input component {component} already has an output set.")
        for component in new_output_components:
            if component.input is not None:
                raise ValueError(f"Output component {component} already has an input set.")

        # check for extra components:
        extra_input_components = [c for c in present_input_components if c not in input_components]
        extra_output_components = [c for c in present_output_components if c not in output_components]
        if extra_input_components or extra_output_components:
            if if_extra_components == "ignore":
                pass
            elif if_extra_components == "warn":
                print(
                    f"Warning: Extra input components {extra_input_components} \
                        and output components {extra_output_components} found."
                )
            elif if_extra_components == "error":
                raise ValueError(
                    f"Extra input components {extra_input_components} and \
                        output components {extra_output_components} found."
                )

        # set inputs and outputs:
        for component in new_input_components:
            if len(component.output_sockets) != 1:
                raise ValueError(f"Input component {component} must have exactly one output socket.")
            self.add_input(component.output_socket)
        for component in new_output_components:
            if len(component.input_sockets) != 1:
                raise ValueError(f"Output component {component} must have exactly one input socket.")
            self.add_output(component.input_socket)

        if write_lossless_input_flow:
            flows = []
            for output_component in self.output_components:
                output_flow = output_component.get_input_flow(at=self)
                if output_flow.is_empty:
                    raise Exception(
                        f"Output component {output_component} has no input flow at the energy network, \
                            so a lossless input flow cannot be written."
                    )
                else:
                    flows.append(output_flow)
            self.input_flow = Temporal.sum(flows)


class EnergyNetworkObject(NetworkObject, Asset):
    """
    A base class for objects within an energy network, which combines
    functionalities of `NetworkObject` and `Asset`. This class is designed to
    represent components within an energy network that also have economic
    attributes.
    """

    ...


class EnergyNode(EnergyNetworkObject, Node):
    """
    A class representing a node in an energy network. It inherits from
    `EnergyNetworkObject`, which allows it to have both network and economic
    attributes.
    """

    ...


class EnergyEdge(EnergyNetworkObject, Edge):
    """
    A class representing an edge in an energy network. It inherits from
    `EnergyNetworkObject`, which allows it to have both network and economic
    attributes.
    """

    ...
