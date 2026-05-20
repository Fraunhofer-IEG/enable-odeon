from __future__ import annotations
from copy import copy, deepcopy
from numbers import Number
from typing import Callable, Literal

import networkx as nx
from shapely import Point
import geopandas as gpd

from .base import GeometryObject, Object
from .geometry import Geometry


from ..processing.utils.geometry import closest_geometry_pair
from ..processing.utils.graph import get_nodes_with_degree
from ..processing.utils.utils import type_typetuple_or_typelist_to_typetuple
from ..processing.geometry_cartesian import TOLERANCE


class NetworkObject(GeometryObject):  # TODO set type to Organizer so that it can have (nodes') attachments as members

    # other attributes:
    _partitions: set[str] = None

    def __init__(self, partitions: set[str] | str | None = None, geometry: Geometry | None = None, **kwargs):
        if isinstance(partitions, str):
            self._partitions = {partitions}
        else:
            self._partitions = partitions or set()
        kwargs |= dict(geometry=geometry)
        super().__init__(**kwargs)

    @property
    def network(self) -> Network:
        return self.parent

    @property
    def partitions(self) -> set[str]:
        return copy(self._partitions)

    @partitions.setter
    def partitions(self, partitions: set[str]):
        assert isinstance(partitions, set) or partitions is None
        if partitions is None:
            self._partitions = set()
        else:
            assert all(isinstance(p, str) for p in partitions)
            self._partitions = partitions

    @property
    def partitions_list(self) -> list[str]:
        return list(self._partitions)

    def add_partition(self, partition: str | list[str] | set[str]):
        if isinstance(partition, str):
            self._partitions.add(partition)
        else:  # list or set
            for p in partition:
                self._partitions.add(p)

    def remove_partitions(self, partition: str | list[str] | set[str]):
        if isinstance(partition, str):
            self._partitions.remove(partition)
        else:  # list or set
            for p in partition:
                self._partitions.remove(p)

    def _set_network(self, net: Network):
        """Set network parent (internal helper).

        Notes
        -----
        This is an internal helper. External code should call
        `Network.remove_nodes()` / `Network.add_nodes()` instead so that
        bookkeeping (graphs, parent links) is handled consistently.
        """
        if net is not None:
            self._set_parent(parent=net)
        else:
            self.remove_from_parent()


class Node(NetworkObject):

    # associated attributes:
    _ASSOCIATED_ATTRIBUTES = ["_attachment"]
    _attachment: Object | None = None

    # other attributes:
    _elevation: float | None = (
        None  # [m] # TODO remove? also in <GeometryObject>.geometry.altitude # TODO above ground? above sea level?
    )

    def __init__(
        self,
        elevation: float | None = None,
        attachment: Object | None = None,
        geometry: Geometry | None = None,
        partitions: set[str] | None = None,
        **kwargs,
    ):
        self._elevation = elevation
        self._attachment = attachment
        super().__init__(partitions=partitions, geometry=geometry, **kwargs)

    @property
    def elevation(self) -> float | None:
        if self._elevation is not None:
            return self._elevation
        elif self.geometry is not None:
            return self.geometry.altitude

    @property
    def attachment(self) -> Object | None:
        # remark: this is not the parent. The Node's parent is the Network, this could be an associated building etc.
        return self._attachment

    @attachment.setter
    def attachment(self, obj: Object):
        if obj is None:
            self._attachment = obj
        else:
            if obj.branch is not self.branch and self.branch is not None:
                raise Exception(f"Can't set an attachment with a differing branch: {obj.branch} vs {self.branch}")
            self._attachment = obj

    def copy(self, deep_custom_data: bool = True) -> "Node":
        """Create a shallow or deep copy of the node.

        Parameters
        ----------
        deep_custom_data : bool, default True
            If True, ``custom_data`` is deep-copied; otherwise a shallow copy
            is used.

        Returns
        -------
        Node
            New node with copied geometry, partitions, attachment reference
            (same object) and optionally deep-copied ``custom_data``. The
            returned node has no network assigned.
        """

        node = Node(
            name=self.name,
            custom_data=deepcopy(self.custom_data) if deep_custom_data else copy(self.custom_data),
            elevation=self.elevation,
            attachment=self.attachment,
            geometry=copy(self.geometry),
            partitions=copy(self.partitions),
        )
        return node


class Edge(NetworkObject):

    # associated attributes:
    _ASSOCIATED_ATTRIBUTES = ["_node_to", "_node_from"]
    _node_to: Node = None
    _node_from: Node = None

    # other attributes:
    _length: float = None  # [m]

    def __init__(
        self,
        node_from: Node | None = None,
        node_to: Node | None = None,
        length: float | None = None,
        partitions: set[str] | None = None,
        geometry: Geometry | None = None,
        **kwargs,
    ):
        self._node_to = node_to
        self._node_from = node_from
        self.length = length
        super().__init__(partitions=partitions, geometry=geometry, **kwargs)

    @property
    def node_to(self) -> Node | None:
        return self._node_to

    @node_to.setter
    def node_to(self, node: Node | None):
        """Set the target (downstream) node.

        Parameters
        ----------
        node : Node or None
            Node to assign. Passing ``None`` does not remove the previous
            node from the network; use ``Network.remove_nodes`` for that.

        Notes
        -----
        This does not implicitly add the node to the network. Call
        ``Network.add_nodes`` if needed.
        """
        if isinstance(node, Node) or node is None:
            self._node_to = node
        else:
            raise TypeError(f"{node} is not an instance of {Node}")

    @property
    def node_from(self) -> Node | None:
        return self._node_from

    @node_from.setter
    def node_from(self, node: Node | None):
        """Set the origin (upstream) node.

        Parameters
        ----------
        node : Node or None
            Node to assign. Passing ``None`` does not remove the previous
            node from the network; use ``Network.remove_nodes`` for that.

        Notes
        -----
        This does not implicitly add the node to the network. Call
        ``Network.add_nodes`` if needed.
        """
        if isinstance(node, Node) or node is None:
            self._node_from = node
        else:
            raise TypeError(f"{node} is not an instance of {Node}")

    @property
    def nodes(self) -> list[Node | None]:
        return [self._node_from, self.node_to]

    @property
    def length(self) -> float | None:
        if self._length is not None:
            return self._length
        elif self.geometry is not None:
            return self.geometry.shape.length

    @length.setter
    def length(self, length: Number | None):
        if isinstance(length, Number):
            self._length = float(length)
        elif length is None:
            self._length = None
        else:
            raise TypeError(f"{length} is not a number")

    def connected(self, other: "Edge") -> bool:
        return self.common_node(other) is not None

    def common_node(self, other: "Edge") -> Node | None:
        if self._node_from in other.nodes:
            return self._node_from
        elif self._node_to in other.nodes:
            return self._node_to

    def opposite_node(self, this: Node | None) -> Node | None:
        """
        return opposite node of `this` in the edge. Will return `None` if
        `this` is not connected to edge
        """
        if this is self._node_from:
            return self._node_to
        elif this is self._node_to:
            return self._node_from


class Network(Object):
    """
    Notes
    -----

    A Network is *valid* if the following applies:

    - all nodes referenced in edges (`node_from`, `node_to`) are also
      stored in the network's nodes list
    - all ids are unique integers
    - all nodes and edges in the network have the network set as parent
      (i.e. as network)

    A Network is *edgecomplete* if the following applies:

    - Each edge has `node_from` and `node_to` set to a Node object

    A Network is *linked* if the following applies:

    - The Network is valid and edgecomplete
    - Each node is connected to at least one edge

    A Network is *geometric* if the following applies:

    - All nodes have a (point) geometry
    - All edges have a (linestring) geometry

    A Network is *continuous* if the following applies:

    - The Network is valid and edgecomplete
    - The (linestring) geometry of each edge touches the (point) geometries of
      `node_from`/`node_to` at the first/last vertex of the linestring

    A Network is *planar* if the following applies:

    - The Network is continuous
    - No node geometries are identical (touch/congruent)
    - No edge geometries intersect (cross)
    """

    # children attributes:
    _CHILDREN_ATTRIBUTES = {
        "_nodes": "Node[]",
        "_edges": "Edge[]",
    }
    _nodes: list[Node] = None
    _edges: list[Edge] = None

    # other attributes:
    KW_OBJECT = "object"
    KW_LENGTH = "length"
    KW_WEIGHT = "weight"
    KW_PARTITIONS = "partitions"
    _graph: nx.Graph = None
    _digraph: nx.DiGraph = None

    def __init__(self, nodes: list[Node] = None, edges: list[Edge] = None, **kwargs):
        self._nodes = []
        self._edges = []
        self._graph = None
        self._digraph = None
        self.set_nodes(nodes)
        self.set_edges(edges)
        self._reset_graphs()
        super().__init__(**kwargs)

    @property
    def graph(self) -> nx.Graph:
        """
        Return an undirected nx.Graph with `Edge.id` and `Node.id` as graph
        identifiers. This requires the network to be *valid*, *edgecomplete*
        and *doublet-free* (ignoring direction).

        Graph edge dicts will have the form `{KW_OBJECT: <Edge>, KW_LENGTH:
        <Edge>.length, KW_WEIGHT: 1}`.
        Graph node dicts will have the from `{KW_OBJECT: <Node>}`.
        `KW_OBJECT`, `KW_LENGTH` and `KW_WEIGHT` are class attributes.

        Raises an exception if a pair of nodes is connected by multiple edges
        (regardless of direction indicated by `node_from`, `node_to`)
        """
        if self._graph is None:
            self._graph = self._to_networkx(directed=False)
        return self._graph

    # IMPLEMENT
    @graph.setter
    def graph(self, graph: nx.Graph):
        """
        Setter
        """
        raise NotImplementedError("update me!")
        nodes, edges = [], []
        for u, v, d in graph.edges(data=True):
            if self.KW_OBJECT in d and type(d[self.KW_OBJECT]) is Edge:
                edges.append(d[self.KW_OBJECT])
            else:
                NotImplementedError()
        self.remove_edges(self.edges)
        self.remove_nodes(self.nodes)
        self.add_edges(edges)
        self._set_nodes_from_edges()

    @property
    def digraph(self) -> nx.DiGraph:
        """
        Return a directed nx.DiGraph with `Edge.id` and `Node.id` as graph
        identifiers. The graph edges will be created from `Network.edges`,
        where `node_from` and `node_to` of each `Network.edge` indicate the
        direction of the resulting `nx.DiGraph` edge.
        This requires the network to be *valid*, *edgecomplete* and
        *doublet-free* (respecting direction).

        Graph edge dicts will have the form `{KW_OBJECT: <Edge>, KW_LENGTH:
        <Edge>.length, KW_WEIGHT: 1}`.
        Graph node dicts will have the from `{KW_OBJECT: <Node>}`.
        `KW_OBJECT`, `KW_LENGTH` and `KW_WEIGHT` are class attributes.

        Raises an exception if a pair of nodes is connected by multiple edges
        with same direction (indicated by `node_from`, `node_to`)
        """
        if self._digraph is None:
            self._digraph = self._to_networkx(directed=True)
        return self._digraph

    def _reset_graphs(self):
        """
        Reset the internal graph representations. This will force a rebuild
        upon next access. Required after any change to nodes or edges.
        """
        self._graph = None
        self._digraph = None

    def _to_networkx(self, directed: bool = True) -> nx.DiGraph | nx.Graph:
        if not self.is_valid():
            raise Exception("Can't convert network to graph/digraph: Network is not valid")
        if not self.is_edgecomplete():
            raise Exception("Can't convert network to graph/digraph: Some edges lack nodes or differ parent")
        if not self.is_doublet_free(respect_direction=directed):
            raise Exception("Can't convert network to graph/digraph: Network contains doublets")
        nodes, edges = [], []
        for n in self.nodes:
            nodes.append((n.id, n))
        for e in self.edges:
            edges.append((e.node_from.id, e.node_to.id, e))
        graph = nx.DiGraph() if directed else nx.Graph()
        graph.add_nodes_from([[id, {self.KW_OBJECT: data}] for id, data in nodes])
        graph.add_edges_from(
            [
                [
                    id1,
                    id2,
                    {
                        self.KW_OBJECT: data,
                        self.KW_LENGTH: data.length,
                        self.KW_WEIGHT: 1,
                        self.KW_PARTITIONS: data.partitions,
                    },
                ]
                for id1, id2, data in edges
            ]
        )
        return graph

    # IMPLEMENT
    @classmethod
    def _from_networkx(cls, graph: nx.DiGraph):
        raise NotImplementedError("update me!")
        nodes, edges = [], []
        for u, v, d in graph.edges(data=True):
            if cls.KW_OBJECT in d and type(d[cls.KW_OBJECT]) is Edge:
                edges.append(d[cls.KW_OBJECT])
            else:
                NotImplementedError()
        obj = Network(__edges=edges)
        obj.set_nodes_from_edges()
        obj.id = project_manager.get_id()
        return obj

    # KEEP
    def to_edge_gdf(
        self,
        attributes: list[str | tuple[str, str] | tuple[str, Callable]] | None = None,
    ) -> gpd.GeoDataFrame:
        """
        Convert the network's edges to a GeoDataFrame. Columns are:

        - "id"
        - "node_from_id"
        - "node_to_id"
        - "geometry"
        - "partitions" (list of partition names), one column for each partition
          (boolean), and any additional columns specified in `attributes`.

        Parameters
        ----------
        attributes : list[str | tuple[str, str] | tuple[str, Callable]] | None
            List of attributes to include in the GeoDataFrame. Each attribute
            can be:
            - A string representing the attribute name.
            - A tuple of the form (target_name, attribute_name) to rename the
              attribute in the GeoDataFrame.
            - A tuple of the form (target_name, callable) to compute the
              attribute using a function.
        """
        attributes = attributes or []
        records = []
        partitions = self.partitions()
        for e in self.edges:
            record = {
                "id": e.id,
                "node_from_id": e.node_from.id if e.node_from else None,
                "node_to_id": e.node_to.id if e.node_to else None,
                "geometry": e.geometry.shape,
                "partitions": e.partitions_list,
            }
            for partition in partitions:
                record |= {partition: partition in e.partitions}
            for attribute in attributes:
                if isinstance(attribute, str):
                    record[attribute] = e.get_attribute(attribute)
                else:
                    target, arg = attribute
                    if isinstance(arg, str):
                        record[target] = e.get_attribute(arg)
                    else:
                        record[target] = arg(e)
            records.append(record)
        if records:
            gdf = gpd.GeoDataFrame(data=records, geometry="geometry")
            if self.project is not None and self.project.projector is not None:
                gdf = gdf.set_crs(self.project.projector.proj_str)
        else:
            gdf = gpd.GeoDataFrame()
        return gdf

    # KEEP
    def to_node_gdf(
        self,
        attributes: list[str | tuple[str, str] | tuple[str, Callable]] | None = None,
    ) -> gpd.GeoDataFrame:
        """
        Convert the network's nodes to a GeoDataFrame. Columns are:

        - "id"
        - "geometry"
        - "partitions" (list of partition names), one column for each partition
          (boolean), and any additional columns specified in `attributes`.

        Parameters
        ----------
        attributes : list[str | tuple[str, str] | tuple[str, Callable]] | None
            List of attributes to include in the GeoDataFrame. Each attribute
            can be:
            - A string representing the attribute name.
            - A tuple of the form (target_name, attribute_name) to rename the
              attribute in the GeoDataFrame.
            - A tuple of the form (target_name, callable) to compute the
              attribute using a function.
        """
        attributes = attributes or []
        records = []
        partitions = self.partitions()
        for n in self.nodes:
            record = {
                "id": n.id,
                "geometry": n.geometry.shape,
                "partitions": n.partitions_list,
            }
            for partition in partitions:
                record |= {partition: partition in n.partitions}
            for attribute in attributes:
                if isinstance(attribute, str):
                    record[attribute] = n.get_attribute(attribute)
                else:
                    target, arg = attribute
                    if isinstance(arg, str):
                        record[target] = n.get_attribute(arg)
                    else:
                        record[target] = arg(n)
            records.append(record)
        if records:
            gdf = gpd.GeoDataFrame(data=records, geometry="geometry")
            if self.project is not None and self.project.projector is not None:
                gdf = gdf.set_crs(self.project.projector.proj_str)
        else:
            gdf = gpd.GeoDataFrame()
        return gdf

    @property
    def nodes(self):
        return self._nodes

    @property
    def edges(self):
        return self._edges

    # KEEP
    def set_nodes(self, nodes: list[Node]):
        """
        Set the network's nodes to `nodes`. This will remove existing nodes.
        Any edges connecting to formerly present nodes will also be removed.
        """
        self._reset_graphs()
        if (isinstance(nodes, list) and all(isinstance(e, Node) for e in nodes)) or nodes is None:
            self.remove_nodes(self._nodes, edge_mode="remove")
            if nodes is not None:
                self.add_nodes(nodes)
        else:
            raise TypeError()

    # KEEP
    def set_edges(self, edges: list[Edge]):
        """
        Set the network's edges to `edges`. This will remove existing edges.
        The nodes referenced in `edges` will alse be added to the network, if
        not already present. Nodes formerly present in the network won't be
        removed.
        """
        self._reset_graphs()
        if (isinstance(edges, list) and all(isinstance(e, Edge) for e in edges)) or edges is None:
            self.remove_edges(self.edges)
            if edges is not None:
                self.add_edges(edges)
        else:
            raise TypeError()

    # KEEP
    def add_nodes(
        self,
        nodes: list[Node] | Node,
        existing_mode: Literal["skip", "exception"] = "exception",
    ):
        if nodes:
            if isinstance(nodes, Node):
                nodes = [nodes]
            self._reset_graphs()
            nodes_new = set(nodes) - set(self.nodes)
            if existing_mode == "exception" and len(nodes_new) < len(nodes):
                raise ValueError(f"some nodes already in network")
            for node in nodes_new:
                if isinstance(node, Node):
                    assert node.network is None
                    self._nodes.append(node)
                    node._set_network(self)
                else:
                    raise Exception(f"{node} is not an instance of {Node}")

    # KEEP
    def add_edges(
        self,
        edges: list[Edge] | Edge,
        existing_mode: Literal["skip", "exception"] = "exception",
    ):
        """
        Add `edges` to the network.
        This will also add any node in any of `edges` not yet in the network.
        """
        if edges:
            if isinstance(edges, Edge):
                edges = [edges]
            self._reset_graphs()
            nodes_add = set()
            edges_new = set(edges) - set(self.edges)
            if existing_mode == "exception" and len(edges_new) < len(edges):
                raise ValueError(f"some edges already in network")
            for edge in edges_new:
                if isinstance(edge, Edge):
                    assert edge.network is None
                    self._edges.append(edge)
                    edge._set_network(self)
                    nodes_add |= set([n for n in edge.nodes if n is not None])
                else:
                    raise TypeError(f"{edge} is not an instance of {Edge}")
            nodes_new = nodes_add - set(self.nodes)
            self.add_nodes(list(nodes_new), existing_mode=existing_mode)

    # KEEP
    def remove_nodes(
        self,
        nodes: list[Node, int],
        edge_mode: Literal["remove", "set_none"] = "remove",
    ):
        """
        Parameters
        ----------
        nodes : list
            List of Nodes and/or Node ids that are currently in the network and
            shall be removed.
        edge_mode : str
            - 'remove': any edge in the network that is connected to at least
                one node from `nodes` will be removed from the network
            - 'set_none': In the connected edges, references to removed nodes
                will be set to None
        """
        if nodes:
            self._reset_graphs()
            for i, node in enumerate(nodes):
                if isinstance(node, int):
                    nodes[i] = self.get_node_by_id(node)
                else:
                    if not isinstance(node, Node):
                        raise TypeError()
                    if node not in self.nodes:
                        raise ValueError(f"{node} not in network")
            self._nodes = [n for n in self._nodes if n not in nodes]
            for node in nodes:
                node._set_parent(None, error_if_not_found=False)  # we already removed it manually at parent side
            if edge_mode == "remove":
                for e in [*self._edges]:
                    if e._node_from in nodes or e._node_to in nodes:
                        self._edges.remove(e)
                        e._set_parent(None, error_if_not_found=False)  # we already removed it manually at parent side
            else:
                for e in self._edges:
                    if e._node_from in nodes:
                        e._node_from = None
                    if e._node_to in nodes:
                        e._node_to = None

    # KEEP
    def remove_edges(
        self,
        edges: list[Edge, int],
        node_mode: Literal["keep_all", "keep_connected", "remove"] = "keep_all",
        use_graph: bool = True,
    ):
        """
        Remove edges from the network. For those edges, the attributes
        `network`, `node_from` and `node_to` will be set to None.

        Parameters
        ----------
        edges : list
            List of Edges and/or Edge ids that are currently in the network and
            shall be removed.
        node_mode : str
            - 'keep_all': Don't affect network's nodes
            - 'remove': any node in the network that is connected to at least
              one edge from `edges` will be removed from the network
            - 'keep_connected': remove only those nodes that are unconnected
              after removing all edges
        use_graph : bool
            Whether to use the graph representation for edge lookups. This is
            faster for large networks and many edges to remove. However, it
            requires that the network is valid, edgecomplete and doublet-free.
        """
        if edges:

            # determine edges to remove and check validity:
            for i, edge in enumerate(edges):
                if isinstance(edge, int):
                    edges[i] = self.get_edge_by_id(edge)
                else:
                    if not isinstance(edge, Edge):
                        raise TypeError()
                    if edge not in self._edges:
                        raise ValueError(f"{edge} not in network")

            # determine nodes to remove and remove them:
            if node_mode in ["remove", "keep_connected"]:
                nodes_to_remove = []
                if node_mode == "remove":
                    for edge in edges:
                        for n in edge.nodes:
                            if n not in nodes_to_remove:
                                nodes_to_remove.append(n)
                if node_mode == "keep_connected":
                    for node in self._nodes:
                        if all(e in edges for e in self.get_edges_by_nodes(node, use_graph=use_graph)):
                            nodes_to_remove.append(node)

                # reset graph before removing anything:
                self._reset_graphs()

                # remove nodes:
                for n in nodes_to_remove:
                    self._nodes.remove(n)
                    n._set_parent(None, error_if_not_found=False)  # we already removed it manually at parent side

            else:
                # reset graph before removing anything:
                self._reset_graphs()

            # clear edges:
            for edge in edges:
                edge._node_from = None
                edge._node_to = None

            # remove edges:
            self._edges = [e for e in self._edges if e not in edges]
            for edge in edges:
                edge._set_parent(None, error_if_not_found=False)  # we dissolved it manually -> don't raise an error

    # KEEP
    def pop(
        self,
        objects: list[NetworkObject],
        edge_mode: Literal["remove", "remove_and_return", "set_none"] = "remove",
        node_mode: Literal["set_none", "copy"] = "set_none",
    ) -> tuple[list[Node], list[Edge]]:
        """
        Remove `objects` from the Network and return them. This will also set
        their `parent` and `network` attribute to None. If some of these objects
        are connected (via `<Edge>.node_from`, `<Edge>.node_to`), these
        connections will be kept.

        If the connected Node of an Edge in `objects` is not contained in
        `objects`, this Node won't be removed from the Network.

        Parameters
        ----------
        objects : list
            List of NetworkObjects to be removed from the Network.
        edge_mode : str
            For Edges that are not in `objects` but are connected to at least
            one Node that is in `objects`, this strategy will be applied:
            - "remove": The Edge will be removed from the Network. It won't
                be returned.
            - "remove_and_return": The Edge will be removed from the
                Network. It will be returned.
            - "set_none": The Edge will remain in the Network. The
                respective Node (`node_from` or `node_to`) will be set to
                None.
        node_mode : str
            Nodes of Edges in `objects` that are not in `objects` won't be
            deleted. This parameter decides whether they will be returned:
            - "set_none": The respective Node (`node_from` or `node_to`) in
                the returned Edge will be set to None
            - "copy": The respective Node in the returned Edge will be a
                copy of the original one (still contained in the Network)
        """
        assert all(isinstance(o, NetworkObject) for o in objects)
        assert all(o.network is self for o in objects)
        assert edge_mode in ["remove", "remove_and_return", "set_none"]
        assert node_mode in ["set_none", "copy"]

        self._reset_graphs()
        res_edges = []
        res_nodes = []
        copied_nodes = {}
        for edge in [o for o in objects if isinstance(o, Edge)]:

            if edge in self.edges:
                if edge.node_from not in objects:
                    if node_mode == "set_none":
                        edge.node_from = None
                    elif node_mode == "copy":
                        if edge.node_from in copied_nodes:
                            edge.node_from = copied_nodes[edge.node_from]
                        else:
                            copied_node = edge.node_from.copy(deep_custom_data=True)
                            copied_nodes[edge.node_from] = copied_node
                            edge.node_from = copied_node

                if edge.node_to not in objects:
                    if node_mode == "set_none":
                        edge.node_to = None
                    elif node_mode == "copy":
                        if edge.node_to in copied_nodes:
                            edge.node_to = copied_nodes[edge.node_to]
                        else:
                            copied_node = edge.node_to.copy(deep_custom_data=True)
                            copied_nodes[edge.node_to] = copied_node
                            edge.node_to = copied_node
                edge.remove_from_parent()
                if edge in self._edges:
                    self._edges.remove(edge)
                res_edges.append(edge)

        for node in self.nodes:
            if node in objects:
                node.remove_from_parent()
                if node in self._nodes:
                    self._nodes.remove(node)
                res_nodes.append(node)

                edges = self.get_edges_by_nodes(nodes=node)
                for edge in edges:
                    if edge not in objects:
                        if edge_mode in ["remove", "remove_and_return"]:
                            edge.remove_from_parent()
                            self._edges.remove(edge)
                            if edge_mode == "remove_and_return":
                                res_edges.append(edge)
                        elif edge_mode == "set_none":
                            if edge.node_from is node:
                                edge.node_from = None
                            else:
                                assert edge.node_to is node
                                edge.node_to = None

        self._reset_graphs()
        return res_nodes, res_edges

    # KEEP
    def detach(
        self,
        objects: list[NetworkObject],
        edge_mode: Literal["remove", "remove_and_return", "set_none"] = "remove",
        node_mode: Literal["set_none", "copy"] = "set_none",
    ) -> Network:
        """
        Detach the specified `objects` from the Network and return them as a new
        Network.

        This will also set the `parent` and `network` attribute of the detached
        objects to None. If some of these objects are connected (via
        `<Edge>.node_from`, `<Edge>.node_to`), these connections will be kept.

        If the connected Node of an Edge in `objects` is not contained in
        `objects`, this Node won't be removed from the Network.

        Parameters
        ----------
        objects : list
            List of NetworkObjects to be removed from the Network.
        edge_mode : str
            For Edges that are not in `objects` but are connected to at least
            one Node that is in `objects`, this strategy will be applied:
            - "remove": The Edge will be removed from the Network. It won't
                be returned.
            - "remove_and_return": The Edge will be removed from the
                Network. It will be returned.
            - "set_none": The Edge will remain in the Network. The
                respective Node (`node_from` or `node_to`) will be set to
                None.
        node_mode : str
            Nodes of Edges in `objects` that are not in `objects` won't be
            deleted. This parameter decides whether they will be returned:
            - "set_none": The respective Node (`node_from` or `node_to`) in
                the returned Edge will be set to None
            - "copy": The respective Node in the returned Edge will be a
                copy of the original one (still contained in the Network)
        """
        nodes, edges = self.pop(
            objects=objects,
            edge_mode=edge_mode,
            node_mode=node_mode,
        )
        return Network(nodes=nodes, edges=edges)

    # IMPLEMENT
    def add_network(self, other: Network):
        """
        Add all Nodes and Edges from `other` to the Network. `other` won't
        contain any Nodes or Edges afterwards.
        """
        raise NotImplementedError("update me!")

    def _remove(self, network_objects: list[NetworkObject]):
        """
        Don't call this function from outside this module. Use
        `<Network>.remove_nodes()` and `<Network>.remove_edges()
        """
        nodes = [no for no in network_objects if isinstance(no, Node)]
        edges = [no for no in network_objects if isinstance(no, Edge)]
        self._nodes = [n for n in self._nodes if n not in nodes]
        self._edges = [e for e in self._edges if e not in edges]

    def attachments(self) -> list:
        return [n.attachment for n in self._nodes if n.attachment is not None]

    def partitions(self) -> set[str]:
        return self.node_partitions() | self.edge_partitions()

    def node_partitions(self) -> set[str]:
        partitions = [n.partitions for n in self.nodes]
        if partitions:
            return set.union(*partitions)
        else:
            return set()

    def edge_partitions(self) -> set[str]:
        partitions = [e.partitions for e in self.edges]
        if partitions:
            return set.union(*partitions)
        else:
            return set()

    # KEEP
    def clear_partitions(self):
        """
        Remove all partitions from all nodes and edges.
        """
        for e in self.edges:
            e.partitions = set()
        for n in self.nodes:
            n.partitions = set()

    # KEEP
    def get_nodes_by_attachments(self, attachments: list[Object]) -> list[Node]:
        return [n for n in self._nodes if n.attachment in attachments]

    # KEEP
    def get_node_by_attachment(self, attachment: Object) -> Node | None:
        """
        Get the Node that has `attachment` as attachment. Return None if not
        present.
        """
        nodes = self.get_nodes_by_attachments([attachment])
        return nodes[0] if nodes else None

    # KEEP
    def get_nodes_by_attachment_types(self, attachment_types: type | list[type]) -> list[Node]:
        """
        Get all Nodes that have an attachment of any of `attachment_types`.
        """
        attachment_types = type_typetuple_or_typelist_to_typetuple(attachment_types)
        return [n for n in self._nodes if isinstance(n.attachment, attachment_types)]

    # KEEP
    def get_attachments_of_type(self, attachment_types: type | list[type]) -> list[Object]:
        attachment_types = type_typetuple_or_typelist_to_typetuple(attachment_types)
        return [a for a in self.attachments() if isinstance(a, attachment_types)]

    # KEEP
    def get_by_partition(
        self,
        partition: str | list[str | None] | None,
        what: Literal["nodes", "edges", "both"] = "both",
    ) -> list[Edge | Node]:
        """
        Parameters
        ----------
        partition : str, list of str or None
            Partition or list of partitions to filter for. If None, all
            network objects without a partition will be returned
        """
        if not isinstance(partition, list):
            partition = [partition]
        res = []
        if what in ["nodes", "both"]:
            res += [
                n
                for n in self.nodes
                if any(p in n.partitions for p in partition) or (None in partition and not n.partitions)
            ]
        if what in ["edges", "both"]:
            res += [
                e
                for e in self.edges
                if any(p in e.partitions for p in partition) or (None in partition and not e.partitions)
            ]
        return res

    # KEEP
    def get_nodes_from_all_edges(self) -> list[Node]:
        """
        Returns a unique list of all nodes referenced in the network's edges.
        All these nodes should also be present in the network's nodes (while
        the network can contain additional nodes that are not part of any edge)
        """
        nodes = []
        for e in self.edges:
            if e.node_from is not None and e.node_from not in nodes:
                nodes.append(e.node_from)
            if e.node_to is not None and e.node_to not in nodes:
                nodes.append(e.node_to)
        return nodes

    # KEEP
    @staticmethod
    def get_nodes_from_edges(edges: list[Edge]) -> list[Node]:
        """
        Get all nodes connected to any of `edges`.
        """
        ret = []
        for e in edges:
            ret += [n for n in [e.node_to, e.node_from] if n not in ret]
        return ret

    # KEEP
    @staticmethod
    def get_common_nodes_from_edges(edges: list[Edge]) -> list[Node]:
        """
        Get nodes that at least two of `edges` have in common
        """
        nodes = []
        for i, e in enumerate(edges):
            this_nodes = [e.common_node(e2) for e2 in edges[i + 1 :]]
            nodes += [tn for tn in this_nodes if tn not in nodes and tn is not None]
        return nodes

    # KEEP
    def get_edges_by_node_pair(
        self,
        nodes: list[Node],
        respect_direction: bool = False,
        use_graph: bool = False,
    ) -> list[Edge]:
        """
        From the network's edges, get all that connect a pair of nodes,
        ignoring whether these nodes are included in the network's nodes.

        Parameters
        ----------
        nodes : list
            A list containing two Nodes
        respect_direction : bool
            If True, two edges are only regarded identical if they start at the
            same node and end at the same node. If False, they will be regarded
            identical also if start and end node are reversed
        use_graph : bool
            If True, use the networkx graph/digraph to retrieve the edges. This
            will be faster if the graph is already created, but requires the
            network to be valid, edgecomplete and doublet-free.
        """
        ret = []
        if use_graph:
            if respect_direction:
                for _, v, d in self.digraph.out_edges(nodes[0].id, data=True):
                    if v == nodes[1].id:
                        e = d[self.KW_OBJECT]
                        if e not in ret:
                            ret.append(e)
            else:
                for _, v, d in self.graph.edges(nodes[0].id, data=True):
                    if v == nodes[1].id:
                        e = d[self.KW_OBJECT]
                        if e not in ret:
                            ret.append(e)
            return ret
        else:
            for e in self._edges:
                if e.node_from == nodes[0] and e.node_to == nodes[1] and e not in ret:
                    ret.append(e)
                elif not respect_direction and e.node_from == nodes[1] and e.node_to == nodes[0] and e not in ret:
                    ret.append(e)
            return ret

    # KEEP
    def get_edges_by_nodes(
        self,
        nodes: Node | list[Node],
        direction: Literal["incoming", "outgoing", "both"] = "both",
        use_graph: bool = False,
    ) -> list[Edge]:
        """
        From the network's edges, get all that are connected to any of `nodes`
        ignoring whether the nodes are included in the network's nodes.

        Parameters
        ----------
        nodes : Node or list of Node
            A Node or list of Nodes
        direction : str
            The direction of the edges to retrieve. Can be "incoming",
            "outgoing", or "both".
        use_graph : bool
            If True, use the networkx graph/digraph to retrieve the edges. This
            will be faster if the graph is already created, but requires the
            network to be valid, edgecomplete and doublet-free.
        """
        if isinstance(nodes, Node):
            nodes = [nodes]
        ret = []
        if use_graph:
            if direction in ["outgoing", "both"]:
                for n in nodes:
                    if n.id in self.digraph.nodes:
                        for _, v, d in self.digraph.out_edges(n.id, data=True):
                            e = d[self.KW_OBJECT]
                            if e not in ret:
                                ret.append(e)
            if direction in ["incoming", "both"]:
                for n in nodes:
                    if n.id in self.digraph.nodes:
                        for u, _, d in self.digraph.in_edges(n.id, data=True):
                            e = d[self.KW_OBJECT]
                            if e not in ret:
                                ret.append(e)
            return ret
        else:
            for e in self._edges:
                if direction in ["outgoing", "both"] and e.node_from in nodes and e not in ret:
                    ret.append(e)
                if direction in ["incoming", "both"] and e.node_to in nodes and e not in ret:
                    ret.append(e)
            return ret

    # KEEP
    def get_node_by_id(
        self,
        id: int,
        use_graph: bool = False,
    ) -> Node | None:
        """
        Parameters
        ----------
        id : int
            The id of the Node to retrieve
        use_graph : bool
            If True, use the networkx graph/digraph to retrieve the node. This
            will be faster if the graph is already created, but requires the
            network to be valid, edgecomplete and doublet-free.
        """
        if use_graph:
            if id in self.graph.nodes:
                return self.graph.nodes[id][self.KW_OBJECT]
            else:
                return None
        else:
            return next((n for n in self._nodes if n.id == id), None)

    # KEEP
    def get_edge_by_id(self, id: int) -> Edge | None:
        return next((e for e in self._edges if e.id == id), None)

    # KEEP
    def get_node_ids_by_edge_ids(self, edge_ids: list[int]) -> list[int]:
        ret = []
        for e in self._edges:
            if e.id in edge_ids:
                ret += [node.id for node in [e._node_from, e._node_to] if node is not None]
        return list(set(ret))

    # KEEP
    def get_nodes_of_component(self, anchor: Node) -> list[Node]:
        component_nodes = self.get_nodes_of_components()
        return next(c for c in component_nodes if anchor in c)

    # KEEP
    def get_edges_of_components(self) -> list[list[Edge]]:
        """
        Get the edges of all components in individual lists.
        """
        components = [*nx.components.connected_components(self.graph)]
        ret = [[] for _ in components]
        for edge in self.edges:
            ic = next(i for i, c in enumerate(components) if edge.node_from.id in c)  # no need to check other node too
            ret[ic].append(edge)
        ret = sorted(ret, key=len, reverse=True)
        return ret

    # KEEP
    def get_nodes_of_components(self) -> list[list[Node]]:
        """
        Get the nodes of all components in individual lists.
        """
        components = [*nx.components.connected_components(self.graph)]
        ret = [[] for _ in components]
        for node in self.nodes:
            ic = next(i for i, c in enumerate(components) if node.id in c)
            ret[ic].append(node)
        ret = sorted(ret, key=len, reverse=True)
        return ret

    # KEEP
    def get_nodes_with_degree(self, degree: int, directed: bool = False):
        graph = self.graph if not directed else self.digraph
        node_ids = get_nodes_with_degree(graph, degree)
        return [n for n in self.nodes if n.id in node_ids]

    # KEEP
    def get_end_nodes(self) -> list[Node]:
        """
        Get Nodes that 0 or 1 Edges  connect to (ignorant of direction by
        `node_from`/`node_to`).

        This is similar to `get_nodes_with_degree(degree=0)` except that it can
        be used even if the Network is not valid and edgecomplete.
        """
        nodes_to = [e.node_to for e in self.edges]
        nodes_from = [e.node_from for e in self.edges]
        nodes = nodes_to + nodes_from
        counter = Counter(nodes)
        end_nodes = [item for item, count in counter.items() if count <= 1]
        return end_nodes

    # KEEP
    def get_empty_end_nodes(self) -> list[Node]:
        """
        Get end nodes (degree <= 1) that don't have an attachment.
        """
        en = self.get_end_nodes()
        empty_end_nodes = [n for n in en if n.attachment is None]
        return empty_end_nodes

    # KEEP
    def get_closest_node_to_point(self, point: Point, nodes: list[Node] | None = None,) -> Node:
        if nodes is None:
            nodes = self.nodes
        node_geoms = [(node.geometry.shape.x, node.geometry.shape.y) for node in nodes]
        index_closest_node = distance.cdist([point.coords[0]], node_geoms).argmin()
        return nodes[index_closest_node]

    # KEEP
    def get_closest_node_to_shape(self,  shape: BaseGeometry, nodes: list[Node] | None = None,) -> Node:
        if nodes is None:
            nodes = self.nodes
        inode, ishape = closest_geometry_pair(shapes1=[n.geometry.shape for n in nodes], shapes2=shape)
        return nodes[inode]

    # REMOVE ?
    def categorize_edges_by_nodecount(self) -> tuple[list[Edge], list[Edge], list[Edge]]:
        edges_0 = []
        edges_1 = []
        edges_2 = []
        for e in self.edges:
            if e.node_to is None or e.node_from is None:
                if e.node_to is None and e.node_from is None:
                    edges_0.append(e)
                else:
                    edges_1.append(e)
            else:
                edges_2.append(e)
        return edges_0, edges_1, edges_2

    # KEEP
    def connectivity_matrix(self) -> dict[Node, dict[Node, Edge]]:
        """
        Create a "matrix" with source nodes as first index, target nodes as second
        index and connecting edge as value.
        """
        ret = {n: {} for n in self.nodes}
        for edge in self.edges:
            ret[edge.node_from][edge.node_to] = edge
        return ret

    # KEEP
    def length(self, missing: Literal["skip", "raise"] = "raise") -> float:
        """
        Return the total length of all Edges in the Network. If an Edge has no
        length set, this will either skip it (if `missing` is "skip") or raise
        an exception (if `missing` is "raise").
        """
        length = 0
        for edge in self.edges:
            if edge.length is not None:
                length += edge.length
            elif missing == "raise":
                raise ValueError(f"Edge {edge} has no length set")
        return length

    # KEEP
    def doublets(self, respect_direction: bool = True) -> list[list[Edge]]:
        """
        Return edges that connect the same pair of nodes in the network. Edges
        that have one or both nodes set to None will be ignored.

        Returns
        -------
        A list of lists of edges that connect the same pair of nodes
        """
        nids_edges = {}
        for edge in self._edges:
            if edge.node_from is not None and edge.node_to is not None:
                nids = (edge.node_from.id, edge.node_to.id)
                if not respect_direction:
                    nids = (min(nids), max(nids))
                if nids in nids_edges:
                    nids_edges[nids].append(edge)
                else:
                    nids_edges[nids] = [edge]
        return [e for e in nids_edges.values() if len(e) > 1]

    # KEEP
    def loops(self) -> list[Edge]:
        """
        Return edges in the network that start and end at the same node. Edges
        that have both nodes set to None will be ignored.
        """
        ret = []
        for edge in self._edges:
            if edge.node_from is not None and edge.node_from is edge.node_to:
                ret.append(edge)
        return ret

    # KEEP
    def n_cycles(self, directed: bool = False) -> int:
        """The network needs to be valid, edgecomplete and doublet-free."""
        if directed:
            cycles = nx.simple_cycles(self.digraph)
            len(cycles)
        else:
            cycles = nx.cycle_basis(self.graph)
            return len(cycles)

    # KEEP
    def n_components(self) -> int:
        """The network needs to be valid, edgecomplete and doublet-free."""
        c = nx.components.connected_components(self.graph)
        return len(list(c))

    # KEEP
    def is_valid(self) -> bool:
        """
        Return whether
        - all nodes referenced in edges (`node_from`, `node_to`) are also
          stored in the network's nodes list
        - all ids are unique floats
        - all nodes and edges in the network have the network set as parent
          (i.e. as network)
        """
        ids = set([x.id for x in self._edges]) | set([x.id for x in self._nodes])

        if len(ids) != len(self._edges) + len(self._nodes) or None in ids:
            return False

        if len(self._nodes) > 0:
            node_networks = set([n.network for n in self._nodes])
            if node_networks != {self}:
                return False

        if len(self._edges) > 0:
            edge_network = set([e.network for e in self._edges])
            if edge_network != {self}:
                return False

        edge_nodes = set([n for e in self._edges for n in e.nodes])
        nodes = set(self._nodes)
        if edge_nodes | {None} > nodes | {None}:
            return False

        return True

    # KEEP
    def is_edgecomplete(self) -> bool:
        """
        Return whether each edge has `node_from` and `node_to` set to a (node)
        object
        """
        for e in self._edges:
            if (
                e._node_from is None
                or e._node_to is None
                or e._node_from.network is not self
                or e._node_to.network is not self
            ):
                return False
        return True

    # KEEP
    def is_linked(self) -> bool:
        """
        Return whether
        - the network is valid and edgecomplete, and
        - each node is connected to at least one edge
        """
        ret = self.is_valid()
        ret &= self.is_edgecomplete()
        ret &= set(self._nodes) == set([n for e in self._edges for n in e.nodes if n is not None])
        return ret

    # KEEP
    # TEST
    def is_geometric(self) -> bool:
        """
        Return whether
        - all nodes have a (point) geometry, and
        - all edges have a (linestring) geometry
        """
        for n in self._nodes:
            if n.geometry is None or n.geometry.shape is None or n.geometry.shape.geom_type != "Point":
                return False
        for e in self._edges:
            if e.geometry is None or e.geometry.shape is None or e.geometry.shape.geom_type != "LineString":
                return False
        return True

    # KEEP
    def is_continuous(self, allowed_distance: float = TOLERANCE) -> bool:
        """
        Return whether
        - the network is valid, edgecomplete and geometric, and
        - the (linestring) geometry of each edge touches the (point) geometries
        of `node_from`/`node_to` at the first/last vertex of the linestring,
        considering LineString direction.
        """
        if not self.is_geometric():
            return False
        for e in self._edges:
            if (
                e.node_from.geometry.shape.distance(Point(e.geometry.shape.coords[0])) > allowed_distance
                or e.node_to.geometry.shape.distance(Point(e.geometry.shape.coords[-1])) > allowed_distance
            ):
                return False
        return True

    # KEEP
    # IMPLEMENT
    def is_planar(self) -> bool:
        """
        Return whether
        - the Network is continuous, and
        - no node geometries are identical (touch/congruent), and
        - no edge geometries intersect (cross)
        """
        ret = self.is_continuous()
        raise NotImplementedError()
        return ret

    # KEEP
    def is_doublet_free(self, respect_direction: bool = True) -> bool:
        return len(self.doublets(respect_direction=respect_direction)) == 0

    # KEEP
    def is_loop_free(self) -> bool:
        return len(self.loops()) == 0
