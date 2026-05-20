from copy import deepcopy

from shapely import Polygon, Point, LineString

from ..model import (
    Network,
    DistrictElectricityGrid,
    DegNode,
    DegCable,
    Geometry,
    Building,
    Site,
    PhotovoltaicDevice,
    ElectricityDemand,
    Medium,
    Heatpump,
    ElectrodeHeater,
    ElectrodeBooster,
    ElectricityGridConnection,
    WindpowerDevice,
    Bus,
    TransformerStation,
)


def edge_set_partitions_from_neighbors(edges, network):

    all_edges = network.edges
    for edge in edges:
        if len(edge.partitions) == 0:
            for node in edge.nodes:
                other_edges = [e for e in all_edges if node in e.nodes and e.id != edge.id]
                p_set = set([])
                for other_edge in other_edges:
                    for p in other_edge.partitions:
                        p_set.add(p)
                    if len(p_set) > 0:
                        break
                if len(p_set) > 0:
                    break

            edge.partitions = p_set


def unify_hover_nodes(network: DistrictElectricityGrid):
    nodes = network.nodes
    edges = network.edges
    removed_nodes = []
    for node in nodes:
        if node in removed_nodes:
            continue
        matching_nodes = [
            node2
            for node2 in nodes
            if node.geometry.shape.distance(node2.geometry.shape) <= 10**-6
            and node2 != node
            and node.vn_kv == node2.vn_kv
        ]

        original_edges = [edge for edge in edges if node.id in edge.nodes]

        for node2 in matching_nodes:

            if isinstance(node2.attachment, TransformerStation):
                continue
            elif isinstance(node2.attachment, ElectricityGridConnection):
                print("warning, hovernodes exist for loads")
                continue

            removed_nodes.append(node2)
            node_2_edges = [edge for edge in edges if node2 in edge.nodes]

            for edge in node_2_edges:
                if edge not in original_edges:
                    edge_nodes = edge.nodes
                    new_node = next(n for n in edge_nodes if n != node2)

                    new_geometry = Geometry(LineString([node.geometry.shape, new_node.geometry.shape]))

                    new_edge = DegCable(
                        geometry=new_geometry, node_from=node, node_to=new_node, partitions=edge.partitions
                    )
                    network.add_edges([new_edge])
                network.remove_edges([edge], node_mode="keep_all")
                print("rewired edge")
            if node2.attachment is not None:
                raise NotImplementedError
                if not isinstance(node2.attachment, list):
                    node2.attachment = [node2.attachment]
                [node.add_attachment(at) for at in node2.attachment]
                print(f"moved node attachment: {node2.attachment}")
            print(f"removed_node {node2}")
            network.remove_nodes([node2])


def cut_lines(deg):
    """
    Cuts lines (cables) from a given degree object based on their geometric proximity and attachment status.
    This function identifies and removes cables that are geometrically close to each other, defined by a specified
    threshold. It checks the distances between the nodes of each cable and removes those that are too close,
    while also keeping track of the removed cables for further processing or logging.
    The function operates in two main phases:
    1. It iterates through all cables and checks for proximity between their nodes. If two cables are found to be
        close enough (within the defined threshold), the second cable is marked for removal.
    2. It then checks for any cables that have nodes with no attachments. If such a cable is found to be connected
        to only one other cable, it is also marked for removal.
    Parameters:
    -----------
    deg : object
         An object representing the degree of the system, which contains a list of cables. Each cable has nodes
         that possess geometry and attachment properties.
    Returns:
    --------
    None
         The function modifies the `deg` object in place by removing the identified cables.
    Notes:
    ------
    - The function prints the attachments of the cables that are being removed for debugging purposes.
    - The removal of cables is done in a way that ensures connected nodes are preserved where possible.
    - The function assumes that the `deg` object has methods `remove_cables` and properties `cables` that are
      compatible with the operations performed within this function.
    """

    threshold = 1e-6
    cables_to_remove = []
    total_removed_cables = []
    for cable in deg.cables:
        if cable in cables_to_remove:
            continue
        l1_node1_geom = cable.nodes[0].geometry.shape
        l1_node2_geom = cable.nodes[1].geometry.shape

        for s_cable in deg.cables:
            if s_cable.id == cable.id:
                continue
            l2_node1_geom = s_cable.nodes[0].geometry.shape
            l2_node2_geom = s_cable.nodes[1].geometry.shape
            if l2_node1_geom.distance(l1_node1_geom) < threshold or l2_node1_geom.distance(l1_node2_geom) < threshold:
                if (
                    l2_node2_geom.distance(l1_node1_geom) < threshold
                    or l2_node2_geom.distance(l1_node2_geom) < threshold
                ):
                    cables_to_remove.append(s_cable)
                    total_removed_cables.append(s_cable)
                    print(f" cable 1 attachment: {cable.nodes[0].attachment}, {cable.nodes[1].attachment}")
                    print(f" cable 2 attachment: {s_cable.nodes[0].attachment}, {s_cable.nodes[1].attachment}")
                    # TODO handle attachments

    deg.remove_cables(cables_to_remove, node_mode="keep_connected")

    while True:
        cables_to_remove = []
        for cable in deg.cables:
            for node in cable.nodes:
                if node.attachment is None:
                    edges = [c for c in deg.cables if node in c.nodes]
                    if len(edges) == 1:
                        cables_to_remove.append(cable)
                        break
        if len(cables_to_remove) > 0:
            deg.remove_cables(cables_to_remove, node_mode="keep_connected")
            total_removed_cables += cables_to_remove
        else:
            break
    print(f"removed cables: {total_removed_cables}")


def convert_network_to_deg(net: Network) -> DistrictElectricityGrid:
    """
    # TODO update docstring
    Converts an `Network` into a `DistrictHeatingNetwork`.
    Returns a new Object and keeps the original `Network` untouched.
    The `Node`s of both networks share the same `BuildingDegConnection`s or `TransferStation`s

    Parameters
    ----------
    net : Network
        Original network

    Returns
    -------
    DistrictHeatingNetwork
        New network including `DegPipe`s, `DegJunction`s and `DegNode`s
    """
    deg = _convert_to_deg(net)
    return deg


def _convert_to_deg(net: Network) -> DistrictElectricityGrid:
    """
    # TODO update docstring
    Creates a `DistrictHeatingNetwork` as a deepcopy of a given Network. All
    Edges will be replaced by DegCables, all Nodes by DegNodes. Per DegNode, a
    DegJunction will be created. Per DegCable, a forward flow DegPipe and a
    backward flow DegPipe will be created, and connected to the DegJunctions.

    The parent of the DistrictHeatingNetwork will be set to None. All
    attachments will be set to the same objects as in the original network
    (i.e. no copying takes place here).

    The input Network must be *valid* and *edgecomplete*. # TODO not yet,
    but might be wiser
    """
    # Empty Network
    deg = DistrictElectricityGrid()

    # Mapping for new Nodes
    node_mapping = dict()

    # Add nodes
    for n in net.nodes:
        deg_n = DegNode()
        attr_to_exlude = [
            "_Object__parent",
            "_attachment",
            "_Identified__id",
            "_affiliations",
            "_children_attributes",
            "_associated_attributes",
            "_temporal_attributes",
            "_temporal_dict_attributes",
        ]
        for attr in n.__dict__:
            if attr in deg_n.__dict__:
                if attr not in attr_to_exlude:
                    # Make a deepcopy of the attribute
                    deg_n.__dict__[attr] = deepcopy(n.__dict__[attr])
        deg.add_nodes([deg_n])
        deg_n.attachment = n.attachment

        node_mapping[n] = deg_n

    # Add cables
    for e in net.edges:
        deg_e = DegCable()
        attr_to_exlude = [
            "_Object__parent",
            "_Identified__id",
            "_node_from",  # already copied; will be set by looking at mapping
            "_node_to",  # already copied; will be set by looking at mapping
            "_affiliations",
            "_children_attributes",
            "_associated_attributes",
            "_temporal_attributes",
            "_temporal_dict_attributes",
        ]
        for attr in e.__dict__:
            if attr in deg_e.__dict__:
                if attr not in attr_to_exlude:
                    # Make a deepcopy of the attribute
                    deg_e.__dict__[attr] = deepcopy(e.__dict__[attr])
        # Node mapping
        if e.node_from is not None:
            deg_e._node_from = node_mapping[e.node_from]
        else:
            node_from = DegNode(geometry=Geometry(shape=Point(e.geometry.shape.coords[0])))
            deg.add_nodes([node_from])
            deg_e._node_from = node_from
        if e.node_to is not None:
            deg_e._node_to = node_mapping[e.node_to]
        else:
            node_to = DegNode(geometry=Geometry(shape=Point(e.geometry.shape.coords[-1])))
            deg.add_nodes([node_to])
            deg_e._node_to = node_to

        deg.add_edges([deg_e])

    assert deg.is_valid()
    assert deg.is_edgecomplete()

    return deg


def collect_all_attachments_in_deg(deg):
    net_attachments = []
    for n in deg.nodes:
        if n.attachment not in net_attachments and n.attachment is not None:
            net_attachments.append(n.attachment)
    return net_attachments


def get_matching_node_in_deg_to_a_geometry(deg, geometry):
    shape = geometry.shape
    if isinstance(shape, Polygon):
        rounded_coords = [(round(x, 3), round(y, 3)) for x, y in shape.exterior.coords]
        shape = Polygon(rounded_coords)

        matching_nodes = [node for node in deg.nodes if shape.distance(node.geometry.shape) <= 0.001]
        if len(matching_nodes) == 0:
            matching_nodes = [node for node in deg.nodes if shape.contains(node.geometry.shape)]

    elif isinstance(shape, Point):
        # shape = Point(round(shape.x, 3), round(shape.y, 3))
        matching_nodes = [node for node in deg.nodes if shape == node.geometry.shape]
    else:
        raise ValueError("Geometry is not of type Point or Polygon")
    if len(matching_nodes) > 0:
        node = matching_nodes[0]
    else:
        node = None
    return node


def connect_pv_devices(branch, gen_type=PhotovoltaicDevice | WindpowerDevice):
    buildings = branch.find_objects([Building])
    sites = branch.find_objects([Site])
    objects = buildings + sites
    for o in objects:
        if o.energy_system is None:
            continue
        for c in o.energy_system.components:
            if isinstance(c, gen_type):
                grid_con = next(
                    (c for c in o.energy_system.components if isinstance(c, ElectricityGridConnection)), None
                )
                el_bus = next(
                    (
                        c
                        for c in o.energy_system.components
                        if isinstance(c, Bus) and c.medium == Medium.ELECTRIC_ENERGY
                    ),
                    None,
                )
                if grid_con is None:
                    grid_con = ElectricityGridConnection()
                    o.energy_system.add_components(grid_con)
                #     print(f"created new e-grid-con for objects of ID {o.id}")
                if el_bus is None:
                    el_bus = Bus(medium=Medium.ELECTRIC_ENERGY)
                    o.energy_system.add_components(el_bus)
                #    print(f"created new el bus for objects of ID {o.id}")

                c.set_output(el_bus, at=Medium.ELECTRIC_ENERGY)
                grid_con.set_input(el_bus, at=Medium.ELECTRIC_ENERGY)


def connect_demand_devices(
    branch,
    # TODO Changed type hint and default? Is this correct? /MJ
    demand_types: (
        Heatpump
        | ElectrodeHeater
        | ElectrodeBooster
        | ElectricityDemand
        | list[Heatpump | ElectrodeHeater | ElectrodeBooster | ElectricityDemand]
    ) = [Heatpump, ElectrodeHeater, ElectrodeBooster, ElectricityDemand],
    objects: list[Building | Site] = None,
):
    if not isinstance(demand_types, list):
        demand_types = [demand_types]
    buildings = branch.find_objects([Building])
    sites = branch.find_objects([Site])
    if objects is None:
        objects = buildings + sites
    for o in objects:
        if o.energy_system is None:
            continue
        if not o.electricity_demand.is_empty and ElectricityDemand in demand_types:
            if o.electricity_demand.total > 0:
                if not any(isinstance(c, ElectricityDemand) for c in o.energy_system.components):
                    el = ElectricityDemand()
                    o.energy_system.add_components(el)
                    el.set_input_flow(o.electricity_demand, at=Medium.ELECTRIC_ENERGY)

        for c in o.energy_system.components:

            if any(isinstance(c, demand_type) for demand_type in demand_types):

                grid_con = next(
                    (c for c in o.energy_system.components if isinstance(c, ElectricityGridConnection)), None
                )
                el_bus = next(
                    (
                        c
                        for c in o.energy_system.components
                        if isinstance(c, Bus) and c.medium == Medium.ELECTRIC_ENERGY
                    ),
                    None,
                )
                if grid_con is None:
                    grid_con = ElectricityGridConnection()
                    o.energy_system.add_components(grid_con)
                if el_bus is None:
                    el_bus = Bus(medium=Medium.ELECTRIC_ENERGY)
                    o.energy_system.add_components(el_bus)
                #   print(f"created new el bus for objects of ID {o.id}")

                c.set_input(el_bus, at=Medium.ELECTRIC_ENERGY)
                grid_con.set_output(el_bus, at=Medium.ELECTRIC_ENERGY)
