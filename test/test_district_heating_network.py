from odeon.model import (
    LinestringGeometry,
    Geometry,
    Edge,
    Network,
    DhnEdge,
    DhnJunction,
    DhnPipe,
    DistrictHeatingNetwork,
    DhnNode,
)
from odeon.processing.district_heating_network import to_geopandas
import unittest
from shapely.geometry import Point, LineString


class TestDhnProcessing(unittest.TestCase):

    def test_set_junctions_from_pipes(self):
        """

        System:

        ```txt

        jreturn_1 <--preturn_21--- jreturn_2 <--preturn_32--- jreturn_3
            |            |            |            |            |
         node_1 ------edge_12-----> node_2 ------edge_23-----> node_3
            |            |            |            |            |
        jsupply_1 ---psupply_12--> jsupply_2 ---psupply_23--> jsupply_3

        ```
        """
        node_1 = DhnNode()
        node_2 = DhnNode()
        node_3 = DhnNode()
        edge_12 = DhnEdge(node_from=node_1, node_to=node_2)
        edge_23 = DhnEdge(node_from=node_2, node_to=node_3)

        jsupply_1 = DhnJunction()
        jsupply_2 = DhnJunction()
        jsupply_3 = DhnJunction()

        psupply_12 = DhnPipe()
        psupply_12.junction_from = jsupply_1
        psupply_12.junction_to = jsupply_2

        psupply_23 = DhnPipe()
        psupply_23.junction_to = jsupply_3
        psupply_23.junction_from = jsupply_2

        jreturn_1 = DhnJunction()
        jreturn_2 = DhnJunction()
        jreturn_3 = DhnJunction()

        preturn_21 = DhnPipe()
        preturn_21.junction_from = jreturn_2
        preturn_21.junction_to = jreturn_1

        preturn_32 = DhnPipe()
        preturn_32.junction_from = jreturn_3
        preturn_32.junction_to = jreturn_2

        pdhn = DistrictHeatingNetwork()
        pdhn.add_nodes([node_1, node_2, node_3])
        pdhn.add_edges([edge_12, edge_23])

        edge_12.set_pipe_supply(psupply_12)
        assert edge_12.pipe_supply is psupply_12
        assert edge_12.node_from.junction_supply is psupply_12.junction_from  # = node_1, junction_supply_1
        assert edge_12.node_to.junction_supply is psupply_12.junction_to  # = node_2, junction_supply_2

        edge_12.set_pipe_return(preturn_21)
        assert edge_12.pipe_return is preturn_21
        assert edge_12.node_from.junction_return is preturn_21.junction_to  # = node_1, junction_return_1
        assert edge_12.node_to.junction_return is preturn_21.junction_from  # =node_2, junction_return_2

        edge_23.set_pipe_supply(psupply_23)
        assert edge_23.pipe_supply is psupply_23
        assert edge_23.node_from.junction_supply is psupply_23.junction_from
        assert edge_23.node_to.junction_supply is psupply_23.junction_to

        edge_23.set_pipe_return(preturn_32)
        assert edge_23.pipe_return is preturn_32
        assert edge_23.node_from.junction_return is preturn_32.junction_to
        assert edge_23.node_to.junction_return is preturn_32.junction_from

        for e in pdhn.edges:
            assert e.pipe_supply.junction_from in pdhn.junctions
            assert e.pipe_supply.junction_to in pdhn.junctions
            assert e.pipe_return.junction_from in pdhn.junctions
            assert e.pipe_return.junction_to in pdhn.junctions

    def test_to_networkx(self):
        node_1 = DhnNode(geometry=Geometry(shape=Point([0, 0])))
        node_2 = DhnNode(geometry=Geometry(shape=Point([0, 1])))
        node_3 = DhnNode(geometry=Geometry(shape=Point([1, 1])))
        edge_1 = DhnEdge(
            geometry=LinestringGeometry(shape=LineString([Point([0, 0]), Point([0, 1])])),
            node_from=node_1,
            node_to=node_2,
        )
        edge_2 = DhnEdge(
            geometry=LinestringGeometry(shape=LineString([Point([0, 1]), Point([1, 1])])),
            node_from=node_2,
            node_to=node_3,
        )

        junction_supply_1 = DhnJunction(geometry=Geometry(shape=Point([0, 0])))
        junction_supply_2 = DhnJunction(geometry=Geometry(shape=Point([0, 1])))
        junction_supply_3 = DhnJunction(geometry=Geometry(shape=Point([1, 1])))
        pipe_supply_1 = DhnPipe(
            geometry=LinestringGeometry(shape=LineString([Point([0, 0]), Point([0, 1])])),
            junction_from=junction_supply_1,
            junction_to=junction_supply_2,
        )
        pipe_supply_2 = DhnPipe(
            geometry=LinestringGeometry(shape=LineString([Point([0, 1]), Point([1, 1])])),
            junction_from=junction_supply_2,
            junction_to=junction_supply_3,
        )

        junction_return_1 = DhnJunction(geometry=Geometry(shape=Point([0, 0])))
        junction_return_2 = DhnJunction(geometry=Geometry(shape=Point([0, 1])))
        junction_return_3 = DhnJunction(geometry=Geometry(shape=Point([1, 1])))
        pipe_return_1 = DhnPipe(
            geometry=LinestringGeometry(shape=LineString([Point([0, 0]), Point([0, 1])])),
            junction_from=junction_return_2,
            junction_to=junction_return_1,
        )
        pipe_return_2 = DhnPipe(
            geometry=LinestringGeometry(shape=LineString([Point([0, 1]), Point([1, 1])])),
            junction_from=junction_return_3,
            junction_to=junction_return_2,
        )

        pdhn = DistrictHeatingNetwork()
        pdhn.add_edges([edge_1, edge_2])

        edge_1.set_pipe_supply(pipe_supply_1)
        edge_1.set_pipe_return(pipe_return_1)

        edge_2.set_pipe_supply(pipe_supply_2)
        edge_2.set_pipe_return(pipe_return_2)

        graph = pdhn.graph
        gdf_nodes, gdf_edges, gdf_junction, gdf_pipes = to_geopandas(pdhn)


if __name__ == "__main__":
    TestDhnProcessing().test_set_junctions_from_pipes()
    TestDhnProcessing().test_to_networkx()
