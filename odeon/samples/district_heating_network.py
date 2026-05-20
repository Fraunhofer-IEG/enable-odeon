from typing import List, Tuple
from shapely import Point

from ..model import (
    DistrictHeatingNetwork,
    DhnNode,
    DhnEdge,
    Building,
    BuildingDhnConnection,
    HeatingDemand,
    DhwDemand,
    NominalGeometry,
    FootprintNominalBuildingGeometry,
    TransferStation,
    Site,
)


def sample_dhn(
    demands: bool = True,
) -> Tuple[
    DistrictHeatingNetwork,
    TransferStation,
    List[Building],
    DhnNode,
    List[DhnNode],
    List[DhnNode],
    List[BuildingDhnConnection],
]:
    """ "
     create a dummy DHN with three buildings, two intermediate nodes and one
     producer node
                                    Building2
           Building1                  /
              |                      /
      IntermediateNode1 --- IntermediateNode2
              |                     |
              |                 Building3
         ProducerNode

    Building1: One heating demand of 5 kK, one DHW demand of 2 kW
    Building2: Two heating demands of 10 kW and 15 kW
    Building3: One heating demand of 8 kW

    - buildings will have BuildingDhnConnections attached to nodes but without
    flows or component links
    - transfer station will be attached to node but be blank in other regards.
    """
    locations = [
        (0, 0),  # Producer Node
        (100, 0),  # IntermediateNode1
        (100, 100),  # IntermediateNode2
        (150, 0),  # Buidling1
        (200, 150),  # Building2
        (50, 100),  # Building3
    ]
    # grow buildings to rectangles:
    producer_point = Point(locations[0])
    inter_point1 = Point(locations[1])
    inter_point2 = Point(locations[2])
    building1_rectangle = Point(locations[3]).buffer(10)  # 20x20 rectangle
    building2_rectangle = Point(locations[4]).buffer(10)  # 20x20 rectangle
    building3_rectangle = Point(locations[5]).buffer(10)  # 20x20 rectangle

    # create nodes:
    producer_node = DhnNode(geometry=NominalGeometry(producer_point))
    inter_node1 = DhnNode(geometry=NominalGeometry(inter_point1))
    inter_node2 = DhnNode(geometry=NominalGeometry(inter_point2))

    building1 = Building(name="Building1")
    building1.building_geometry_nominal = FootprintNominalBuildingGeometry(footprint=building1_rectangle)
    building1_node = DhnNode(geometry=NominalGeometry(building1_rectangle.centroid))
    building1_connection = BuildingDhnConnection()
    building1.energy_system.add_components(building1_connection)
    building1_node.attachment = building1_connection

    building2 = Building(name="Building2")
    building2.building_geometry_nominal = FootprintNominalBuildingGeometry(footprint=building2_rectangle)
    building2_node = DhnNode(geometry=NominalGeometry(building2_rectangle.centroid))
    building2_connection = BuildingDhnConnection()
    building2.energy_system.add_components(building2_connection)
    building2_node.attachment = building2_connection

    building3 = Building(name="Building4")
    building3.building_geometry_nominal = FootprintNominalBuildingGeometry(footprint=building3_rectangle)
    building3_node = DhnNode(geometry=NominalGeometry(building3_rectangle.centroid))
    building3_connection = BuildingDhnConnection()
    building3.energy_system.add_components(building3_connection)
    building3_node.attachment = building3_connection

    # create DHN:
    dhn = DistrictHeatingNetwork()
    dhn.add_nodes([producer_node, inter_node1, inter_node2, building1_node, building2_node, building3_node])
    edges = [
        DhnEdge(node_from=producer_node, node_to=inter_node1),
        DhnEdge(node_from=inter_node1, node_to=inter_node2),
        DhnEdge(node_from=inter_node1, node_to=building1_node),
        DhnEdge(node_from=inter_node2, node_to=building2_node),
        DhnEdge(node_from=inter_node2, node_to=building3_node),
    ]
    dhn.add_edges(edges)

    transfer_station = TransferStation(
        name="Transfer Station",
        geometry=NominalGeometry(shape=producer_point),
    )
    producer_node.attachment = transfer_station

    producer_site = Site(
        name="Producer Site",
        geometry=NominalGeometry(shape=producer_point),
    )
    producer_site.energy_system.add_components([transfer_station])

    # add heat demands:
    if demands:

        building1_heating_demand = HeatingDemand()
        building1_heating_demand.input_flow = 5  # kW, constant heating demand
        building1_dhw_demand = DhwDemand()
        building1_dhw_demand.input_flow = 2  # kW, constant DHW demand
        building1.energy_system.add_components([building1_heating_demand, building1_dhw_demand])

        building2_heating_demand1 = HeatingDemand()
        building2_heating_demand1.input_flow = 10  # kW, constant heating demand
        building2_heating_demand2 = HeatingDemand()
        building2_heating_demand2.input_flow = 15  # kW, constant heating demand
        building2.energy_system.add_components([building2_heating_demand1, building2_heating_demand2])

        building3_heating_demand = HeatingDemand()
        building3_heating_demand.input_flow = 8  # kW, constant heating demand
        building3.energy_system.add_components([building3_heating_demand])

    return [
        dhn,
        producer_site,
        [building1, building2, building3],
        producer_node,
        [inter_node1, inter_node2],
        [building1_node, building2_node, building3_node],
        [building1_connection, building2_connection, building3_connection],
    ]
