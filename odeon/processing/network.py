import itertools
import math
from collections import Counter
import sys
from time import sleep
from typing import Any, Callable, Literal
import logging

import fiona
import geopandas as gpd
import networkx as nx
import pandas as pd
import plotly.graph_objects as go
import contextily as cx
from scipy.spatial import distance
from shapely import GeometryCollection, ops, convex_hull, buffer
from shapely.geometry.base import BaseGeometry
from shapely.geometry import LineString, MultiLineString, Point, Polygon, MultiPoint
from tqdm import tqdm
import matplotlib.pyplot as plt

from ..model.device import *  # for from_geopackage
from ..model.geometry import LinestringGeometry, Geometry
from ..model.network import Edge, Network, Node
from ..model.building import Building, Structure
from ..model.base import id_authority
from .geometry_cartesian import TOLERANCE

# still in use:
# - endpoints()
# - get_close_point_sets()
from . import geometry_network as gnp

logger = logging.getLogger(f"enable.{__name__}")


# -----------------------------------------------------------------------------
# helpers
# -----------------------------------------------------------------------------


def _str_to_class(classname):
    return getattr(sys.modules[__name__], classname)


def _set_to_str(set_of_strs: set[str], separator: str = ";") -> str:
    assert not any(separator in p for p in set_of_strs)
    lst = sorted(list(set_of_strs), key=str.lower)
    return separator.join(lst)


def _str_to_set(str_: str, separator: str = ";") -> set[str]:
    return set(str_.split(separator)) if str_ is not None else set()



# -----------------------------------------------------------------------------
# conversions & I/O
# -----------------------------------------------------------------------------


# KEEP
def to_geopackage(
    network: Network,
    filename: str,
    node_attributes: list[str | tuple[str, str] | tuple[str, str, Callable]] = None,
    edge_attributes: list[str | tuple[str, str] | tuple[str, str, Callable]] = None,
    node_layername: str = "nodes",
    edge_layername: str = "edges",
    crs: Any = "EPSG:4326",
):
    node_attributes = node_attributes or []
    edge_attributes = edge_attributes or []
    node_attributes += [
        ("attachment_type", lambda n: n.attachment.__class__.__name__ if n.attachment else None),
        ("attachment_id", lambda n: n.attachment.id if n.attachment and hasattr(n.attachment, "id") else None),
        ("partitions", lambda n: ", ".join(sorted(n.partitions_list))),
    ]
    edge_attributes += [("partitions", lambda e: ", ".join(sorted(e.partitions_list)))]
    node_gdf = network.to_node_gdf(attributes=node_attributes)
    edge_gdf = network.to_edge_gdf(attributes=edge_attributes)
    if node_gdf.crs is None or edge_gdf.crs is None:
        raise Exception("Can't determine CRS. Is the network part of a project thathas a valid Projector?")
    if node_gdf.crs is not None:
        node_gdf = node_gdf.to_crs(crs)
    if edge_gdf.crs is not None:
        edge_gdf = edge_gdf.to_crs(crs)
    node_gdf.to_crs(crs).to_file(filename, driver="GPKG", layer=node_layername)
    edge_gdf.to_crs(crs).to_file(filename, driver="GPKG", layer=edge_layername)


# KEEP
def from_geopackage(
    filename: str,
    node_attributes: dict[str, str | tuple[Callable, tuple[str]]] = None,
    edge_attributes: dict[str, str | tuple[Callable, tuple[str]]] = None,
    node_layername: str = "nodes",
    edge_layername: str = "edges",
) -> Network:
    """
    Parameters
    ----------
    node_attributes : dict[str, str | tuple[Callable, tuple[str]]], optional
        Dict with target Node attribute name as key and description of how to
        get it as value. If value is str, this will read target value from
        `node_gdf[value]`. If value is a tuple of callable and strings, the
        callable will be executed with the corresponding column values from
        `node_gdf` as arguments indicated by the string tuple.
    edge_attributes : dict[str, str | tuple[Callable, tuple[str]]], optional
        Just the same
    """
    node_attributes = {
        "partitions": (_str_to_set, ("partitions",)),
        "attachment": (lambda at: _str_to_class(at)() if type(at) is str else None, ("attachment_type",)),
    } | (node_attributes or {})
    edge_attributes = {"partitions": (_str_to_set, ("partitions",))} | (edge_attributes or {})
    layers = fiona.listlayers(filename)
    node_gdf = gpd.GeoDataFrame.from_file(filename, layer=node_layername) if node_layername in layers else None
    edge_gdf = gpd.GeoDataFrame.from_file(filename, layer=edge_layername) if edge_layername in layers else None
    return from_node_edge_gdfs(node_gdf, edge_gdf, node_attributes, edge_attributes)


# KEEP
# TODO be more cautious with loading ids
# UPDATE won't work anymore with setting ids
def from_node_edge_gdfs(
    node_gdf: gpd.GeoDataFrame,
    edge_gdf: gpd.GeoDataFrame,
    node_attributes: dict[str, str | tuple[Callable, tuple[str]]] = None,  # yes
    edge_attributes: dict[str, str | tuple[Callable, tuple[str]]] = None,
):
    """
    Create Network from two GeoDataFrames.

    Parameters
    ----------
    node_gdf : gpd.GeoDataFrame
        Columns "id", "geometry", all optional
    edge_gdf : gpd.GeoDataFrame
        Columns "id", "geometry", "node_to_id", "node_from_id", all optional
    node_attributes : dict[str, str | tuple[Callable, tuple[str]]], optional
        Dict with target Node attribute name as key and description of how to
        get it as value. If value is str, this will read
        target  value from `node_gdf[value]`. If value is a tuple of callable
        and strings, the callable will be executed with the corresponding column
        values from `node_gdf` as arguments indicated by the string tuple
    edge_attributes : dict[str, str | tuple[Callable, tuple[str]]], optional
        Just the same
    """

    node_attributes = node_attributes or {}
    edge_attributes = edge_attributes or {}
    nodes, edges = {}, {}

    def attributes_to_object(item, valuedict, obj):
        to_, from_ = item  # to_ = str, from_ = str or Tuple[Callable, Tuple[str]]
        if isinstance(from_, str):
            obj.__setattr__(to_, valuedict[from_])
        else:
            params = [valuedict.get(a, None) for a in from_[1]]
            obj.__setattr__(to_, from_[0](*params))
        return obj

    if node_gdf is not None:
        for i in range(node_gdf.shape[0]):
            ndict = node_gdf.iloc[i].to_dict()
            node = Node(id=ndict.pop("id", None), geometry=Geometry(shape=ndict.pop("geometry", None)))
            for nattr in node_attributes.items():
                node = attributes_to_object(nattr, ndict, node)
            nodes[node.id] = node

    if edge_gdf is not None:
        for j in range(edge_gdf.shape[0]):
            edict = edge_gdf.iloc[j].to_dict()
            edge = Edge(
                id=edict.pop("id", None),
                geometry=LinestringGeometry(shape=edict.pop("geometry", None)),
                _node_to=nodes.get(edict.pop("node_to_id", None), None),  # must be present, no default needed
                _node_from=nodes.get(edict.pop("node_from_id", None), None),  # must be present, no default needed
            )
            for eattr in edge_attributes.items():
                attributes_to_object(eattr, edict, edge)
            edges[edge.id] = edge

    id_authority.last_value_from_objects(*nodes.values(), *edges.values())
    net = Network(edges=list(edges.values()), nodes=list(nodes.values()))
    return net


# KEEP
def component_index_as_gdf(network: Network) -> gpd.GeoDataFrame:
    """
    Create a Geodataframe containing edges with the index of the component per
    edge as determined by the networkx analysis of the network graph. The result
    may be used in manual inspection in QGIS etc.
    """

    if not network.is_valid():
        raise ValueError("Network must be valid to create component index.")

    g = network.graph
    components = list(nx.connected_components(g))
    component_index = {node: i for i, component in enumerate(components) for node in component}

    records = []
    for edge in network.edges:
        records.append(
            {
                "edge_id": edge.id,
                "component_index": component_index[edge.node_from.id],  # node_to would also work
                "geometry": edge.geometry.shape,
            }
        )

    df = pd.DataFrame.from_records(records)
    gdf = gpd.GeoDataFrame(data=df, geometry="geometry")
    if network.project is not None:
        gdf.crs = network.project.projector.proj_str
    return gdf


# KEEP
def categorize_by_attachment(network: Network, types: list[type], separate_none: bool = True) -> list[list[Node]]:
    """
    - if `separate_none`: will return n(`types`) + 2 lists with second to last
    list containing nodes with attachments that are neither `None` nor of any
    type from `types`, last list containing nodes that have `None` as
    attachment
    - if not `separate_none`: will return n(`types`) + 1 lists with last list
    containing nodes with attachments that are not of any type from `types`,
    including those that are `None`
    """
    res = [[] for _ in types] + [[]]
    if separate_none:
        res.append([])
    for n in network.nodes:
        if isinstance(n.attachment, tuple(types)):
            for i, t in enumerate(types):
                if isinstance(n.attachment, t):
                    res[i].append(n)
        elif n.attachment is None:
            res[-1].append(n)
        else:
            res[len(types)].append(n)  # same res list as res[-1] if not separate_none
    return res



# KEEP
def set_as_partitions(network: Network, edge_attributes: list[str] = None, node_attributes: list[str] = None) -> None:
    """
    Add to the `partitions` set of all Edges and Nodes in `network` strings
    of the form "key=value" for each attribute in `edge_attributes` and `node_attributes`

    Parameters
    ----------
    - `edge_attributes`: A list of attributes from `network.edges` that should be
    added to the `partitions` set of each Edge.
    - `node_attributes`: A list of attributes from `network.nodes` that should be
    added to the `partitions` set of each Node.
    """
    edge_attributes = edge_attributes or []
    node_attributes = node_attributes or []
    for e in network.edges:
        e.partitions = e.partitions | set([f"{k}={e.get_attribute(k)}" for k in edge_attributes])
    for n in network.nodes:
        n.partitions = n.partitions | set([f"{k}={n.get_attribute(k)}" for k in node_attributes])
