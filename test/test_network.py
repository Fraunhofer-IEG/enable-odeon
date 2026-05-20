import unittest

from odeon.model.device import BuildingDhnConnection, LargeScaleHeatpump
from odeon.model.geometry import LinestringGeometry, Geometry
from odeon.model.network import Edge, Network, Node
from shapely.geometry import LineString, Point


class TestNode(unittest.TestCase):
    def test_node(self):
        node = Node()
        assert node.network is None
        assert node.partitions == set()
        assert node.partitions_list == []

        node.partitions = {"test", "123"}
        assert "test" in node.partitions

        node.add_partition("456")
        assert "456" in node.partitions

        node.remove_partitions("123")
        assert "123" not in node.partitions


class TestEdge(unittest.TestCase):
    def test_edge(self):
        node1 = Node(geometry=Geometry(shape=Point(0, 0)))
        node2 = Node(geometry=Geometry(shape=Point(3, 4)))
        node3 = Node()
        edge12 = Edge(
            node_from=node1,
            node_to=node2,
            geometry=LinestringGeometry(shape=LineString([Point(0, 0), Point(3, 4)])),
            length=10,
        )
        assert node1 in edge12.nodes
        assert node2 in edge12.nodes
        assert edge12.opposite_node(node1) is node2

        assert edge12.length == 10
        edge12.length = None
        assert edge12.length == 5

        edge23 = Edge()
        edge23.node_from = node2
        edge23.node_to = node3
        assert node2 in edge23.nodes
        assert node3 in edge23.nodes
        assert edge23.length is None

        assert edge12.connected(edge23)
        assert edge23.connected(edge12)
        assert edge12.common_node(edge23) is node2


class TestNetwork(unittest.TestCase):
    def test_add_set_get_remove(self):
        def nodes_edges():
            node1 = Node(geometry=Geometry(shape=Point(0, 0)))
            node2 = Node(geometry=Geometry(shape=Point(3, 4)))
            node3 = Node(geometry=Geometry(shape=Point(3, 8)))
            edge12 = Edge(node_from=node1, node_to=node2)
            edge23 = Edge(node_from=node2, node_to=node3)
            nodes = [node1, node2, node3]
            edges = [edge12, edge23]
            return node1, node2, node3, edge12, edge23, nodes, edges

        node1, node2, node3, edge12, edge23, nodes, edges = nodes_edges()
        network = Network(nodes=nodes, edges=edges)
        assert all(n in network.nodes for n in nodes)
        assert all(e in network.edges for e in edges)
        assert all(n.network is network for n in nodes)
        assert all(e.network is network for e in edges)

        node1, node2, node3, edge12, edge23, nodes, edges = nodes_edges()
        network = Network()
        network.add_edges(edges=edges)
        assert all(n in network.nodes for n in nodes)
        assert all(e in network.edges for e in edges)

        node1, node2, node3, edge12, edge23, nodes, edges = nodes_edges()
        network = Network()
        with self.assertRaises(ValueError):
            network.add_nodes(nodes=[*nodes, *nodes])
        assert len(network.nodes) == 0

        node1, node2, node3, edge12, edge23, nodes, edges = nodes_edges()
        network = Network(nodes=nodes, edges=edges)
        network.set_nodes(nodes=nodes)
        assert len(network.nodes) == 3
        assert all(n in network.nodes for n in nodes)
        assert len(network.edges) == 0

        node1, node2, node3, edge12, edge23, nodes, edges = nodes_edges()
        network = Network(nodes=nodes, edges=edges)
        network.set_edges(edges=edges)
        assert all(n in network.nodes for n in nodes)
        assert all(e in network.edges for e in edges)

        node1, node2, node3, edge12, edge23, nodes, edges = nodes_edges()
        network = Network(nodes=nodes, edges=edges)
        network.remove_nodes([node1], edge_mode="remove")
        assert len(network.nodes) == 2
        assert network.edges == [edge23]
        assert edge12.node_from is node1
        assert edge12.node_to is node2
        assert node1.network is None
        assert edge12.network is None

        node1, node2, node3, edge12, edge23, nodes, edges = nodes_edges()
        network = Network(nodes=nodes, edges=edges)
        network.remove_nodes([node1], edge_mode="set_none")
        assert len(network.nodes) == 2
        assert len(network.edges) == 2
        assert edge12.node_from is None
        assert edge12.node_to is node2
        assert node1.network is None
        assert edge12.network is network

        node1, node2, node3, edge12, edge23, nodes, edges = nodes_edges()
        network = Network(nodes=nodes, edges=edges)
        network.remove_edges([edge12], node_mode="keep_all")
        assert len(network.nodes) == 3
        assert len(network.edges) == 1
        assert edge12.node_from is None
        assert edge12.node_to is None
        assert edge12.network is None
        assert node1.network is network

        node1, node2, node3, edge12, edge23, nodes, edges = nodes_edges()
        network = Network(nodes=nodes, edges=edges)
        network.remove_edges([edge12], node_mode="keep_connected")
        assert len(network.nodes) == 2
        assert len(network.edges) == 1
        assert edge12.node_from is None
        assert edge12.node_to is None
        assert edge12.network is None
        assert node1.network is None

        node1, node2, node3, edge12, edge23, nodes, edges = nodes_edges()
        network = Network(nodes=nodes, edges=edges)
        network.remove_edges([edge12], node_mode="remove")
        assert len(network.nodes) == 1
        assert len(network.edges) == 1
        assert edge12.node_from is None
        assert edge12.node_to is None
        assert edge12.network is None
        assert node1.network is None
        assert node2.network is None

        node1, node2, node3, edge12, edge23, nodes, edges = nodes_edges()
        network = Network(edges=edges)
        assert len(network.get_nodes_from_all_edges()) == 3
        assert all(n in network.nodes for n in network.get_nodes_from_all_edges())

        assert network.get_edges_by_node_pair([node2, node1], respect_direction=False) == [edge12]
        assert network.get_edges_by_node_pair([node2, node1], respect_direction=True) == []
        assert network.get_edges_by_node_pair([node1, node3], respect_direction=False) == []

        assert network.get_edges_by_nodes([node1, node3], direction="both") == [edge12, edge23]
        assert network.get_edges_by_nodes([node1, node3], direction="incoming") == [edge23]
        assert network.get_edges_by_nodes([node1, node3], direction="outgoing") == [edge12]

        network.remove_nodes([node1], edge_mode="set_none")
        assert network.categorize_edges_by_nodecount() == ([], [edge12], [edge23])

    def test_partitions(self):
        node1 = Node(partitions=set(["a", "b"]))
        node2 = Node(partitions=set(["b"]))
        node3 = Node()
        edge12 = Edge(partitions=set(["c", "b"]))
        edge23 = Edge()
        nodes = [node1, node2, node3]
        edges = [edge12, edge23]
        network = Network(nodes=nodes, edges=edges)

        assert network.node_partitions() == set(["a", "b"])
        assert network.edge_partitions() == set(["b", "c"])
        assert network.partitions() == set(["a", "b", "c"])
        assert all(x in network.get_by_partition("a", what="nodes") for x in [node1])
        assert all(x in network.get_by_partition("b", what="nodes") for x in [node1, node2])
        assert all(x in network.get_by_partition("b", what="edges") for x in [edge12])
        assert all(x in network.get_by_partition("b", what="both") for x in [node1, node2, edge12])
        assert all(x in network.get_by_partition(None, what="both") for x in [node3])
        assert all(x not in network.get_by_partition(None, what="both") for x in [node1, node2, edge12])
        assert all(x in network.get_by_partition(["a", None], what="both") for x in [node1, node3, edge23])
        assert all(x not in network.get_by_partition(["a", None], what="both") for x in [node2, edge12])

    # IMPLEMENT
    def test_attachments(self): ...

    def test_graph(self):
        node1 = Node()
        node2 = Node()
        node3 = Node(attachment=LargeScaleHeatpump())
        edge12 = Edge(node_from=node1, node_to=node2, length=12)
        edge23 = Edge(node_from=node2, node_to=node3)
        nodes = [node1, node2, node3]
        edges = [edge12, edge23]
        network = Network(nodes=nodes, edges=edges)

        graph = network.graph
        assert all(x.id in graph.nodes for x in nodes)

        digraph = network.digraph
        # TODO test more stuff

        node1 = Node()
        node2 = Node()
        node3 = Node(attachment=LargeScaleHeatpump())
        edge12 = Edge(node_from=node1, node_to=node2, length=12)
        edge23 = Edge(node_from=node2, node_to=node3)
        nodes = [node1, node2, node3]
        edges = [edge12, edge23]
        edge23_2 = Edge(node_from=node1, node_to=node2)
        network = Network(
            nodes=nodes, edges=[*edges, edge23_2]
        )  # Raises an error because nodes cant be in multiple networks

    def test_loops_cycles(self):
        node1 = Node()
        node2 = Node()
        node3 = Node(attachment=LargeScaleHeatpump())
        edge12 = Edge(node_from=node1, node_to=node2)
        edge23 = Edge(node_from=node2, node_to=node3)
        nodes = [node1, node2, node3]
        edges = [edge12, edge23]
        network = Network(nodes=nodes, edges=edges)

        assert network.is_doublet_free(respect_direction=False)
        assert network.is_loop_free()

        node1 = Node()
        node2 = Node()
        node3 = Node(attachment=LargeScaleHeatpump())
        edge12 = Edge(node_from=node1, node_to=node2)
        edge23 = Edge(node_from=node2, node_to=node3)
        nodes = [node1, node2, node3]
        edges = [edge12, edge23]
        edge22 = Edge(node_from=node2, node_to=node2)
        network = Network(nodes=nodes, edges=[*edges, edge22])
        assert network.loops() == [edge22]
        assert network.n_cycles() == 1
        assert not network.is_loop_free()

        node1 = Node()
        node2 = Node()
        node3 = Node(attachment=LargeScaleHeatpump())
        edge12 = Edge(node_from=node1, node_to=node2)
        edge23 = Edge(node_from=node2, node_to=node3)
        nodes = [node1, node2, node3]
        edges = [edge12, edge23]
        edge22 = Edge(node_from=node2, node_to=node2)
        edge13 = Edge(node_from=node1, node_to=node3)
        nodes = [node1, node2, node3]
        edges = [edge12, edge23]
        network = Network(nodes=nodes, edges=[*edges, edge22, edge13])
        assert network.n_cycles() == 2

        network.remove_edges([edge22, edge13])
        assert network.loops() == []
        assert network.n_cycles() == 0

    def test_doublets(self):
        node1 = Node()
        node2 = Node()
        node3 = Node(attachment=LargeScaleHeatpump())
        edge12 = Edge(node_from=node1, node_to=node2)
        edge23 = Edge(node_from=node2, node_to=node3)
        nodes = [node1, node2, node3]
        edges = [edge12, edge23]
        network = Network(nodes=nodes, edges=edges)

        assert network.is_doublet_free(respect_direction=False)

        node1 = Node()
        node2 = Node()
        node3 = Node(attachment=LargeScaleHeatpump())
        edge12 = Edge(node_from=node1, node_to=node2)
        edge23 = Edge(node_from=node2, node_to=node3)
        nodes = [node1, node2, node3]
        edges = [edge12, edge23]
        edge23_2 = Edge(node_from=node2, node_to=node3)
        network = Network(nodes=nodes, edges=[*edges, edge23_2])
        assert not network.is_doublet_free(respect_direction=True)
        assert not network.is_doublet_free(respect_direction=False)

        node1 = Node()
        node2 = Node()
        node3 = Node(attachment=LargeScaleHeatpump())
        edge12 = Edge(node_from=node1, node_to=node2)
        edge23 = Edge(node_from=node2, node_to=node3)
        nodes = [node1, node2, node3]
        edges = [edge12, edge23]
        edge32 = Edge(node_from=node3, node_to=node2)
        network = Network(nodes=nodes, edges=[*edges, edge32])
        assert network.is_doublet_free(respect_direction=True)
        assert not network.is_doublet_free(respect_direction=False)

    def test_valid_edgecomplete_linked(self):
        def nodes_edges():
            node1 = Node(geometry=Geometry(shape=Point(0, 0)))
            node2 = Node(geometry=Geometry(shape=Point(3, 4)))
            node3 = Node(geometry=Geometry(shape=Point(3, 8)))
            edge12 = Edge(node_from=node1, node_to=node2)
            edge23 = Edge(node_from=node2, node_to=node3)
            nodes = [node1, node2, node3]
            edges = [edge12, edge23]
            return node1, node2, node3, edge12, edge23, nodes, edges

        # valid:

        node1, node2, node3, edge12, edge23, nodes, edges = nodes_edges()
        network = Network(nodes=nodes, edges=edges)
        assert network.is_valid()
        network._nodes.remove(node1)
        assert not network.is_valid()

        node1, node2, node3, edge12, edge23, nodes, edges = nodes_edges()
        network = Network(nodes=nodes, edges=edges)
        network.nodes[0]._Identified__id = network.edges[0].id  # don't do this at home
        assert not network.is_valid()

        node1, node2, node3, edge12, edge23, nodes, edges = nodes_edges()
        network = Network(nodes=nodes, edges=edges)
        network.nodes[0]._Object__parent = None  # don't do this at home
        assert not network.is_valid()

        # edgecomplete:

        node1, node2, node3, edge12, edge23, nodes, edges = nodes_edges()
        network = Network(nodes=nodes, edges=edges)
        assert network.is_edgecomplete()
        network.edges[0]._node_to = None
        assert not network.is_edgecomplete()

        # linked:

        node1, node2, node3, edge12, edge23, nodes, edges = nodes_edges()
        network = Network(nodes=nodes, edges=edges)
        assert network.is_linked()
        network.add_nodes([Node()])
        assert not network.is_linked()

    # IMPLEMENT test with more complex network
    def test_complex(self): ...

    # IMPLEMENT
    def test_gdf(self): ...

    # IMPLEMENT
    def test_geopackage(self): ...


if __name__ == "__main__":
    TestNetwork().test_valid_edgecomplete_linked()
    TestNode().test_node()
    TestEdge().test_edge()
    TestNetwork().test_add_set_get_remove()
    TestNetwork().test_partitions()
    TestNetwork().test_attachments()
    TestNetwork().test_graph()
    TestNetwork().test_loops_cycles()
    TestNetwork().test_doublets()
    TestNetwork().test_complex()
    TestNetwork().test_gdf()
    TestNetwork().test_geopackage()
