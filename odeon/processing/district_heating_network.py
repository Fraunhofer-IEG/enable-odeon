import math
import random
from typing import Literal
from copy import deepcopy

import geopandas as gpd
import networkx as nx
import pandas as pd
from shapely.geometry.base import BaseGeometry
from shapely import Point, LineString

from ..model.temporal import Temporal
from ..model.base import Object
from ..model import BuildingDhnConnection, LargeScaleHeatpump, DhnConnectable
from ..model.building import Structure
from ..model.district_heating_network import DhnEdge, DhnJunction, DhnNode, DhnPipe, DistrictHeatingNetwork
from ..model.network import Network
from ..model.geometry import Geometry
from .utils.utils import (
    typeerror_if_not_isinstance,
    typeerror_if_not_list_isinstance,
    typeerror_if_not_isinstance_or_none,
)
from .network import categorize_by_attachment


def calc_pipe_roughness(pipe: DhnPipe):  # TODO remove?
    raise DeprecationWarning("Looks unused, will be removed if no complaints in the next months")
    if pipe.material in ["Copper", "Brass", "Bronze", "Light metal", "Glass"]:
        pipe.roughness = 0.0000014
    if pipe.material == "Rubber":
        pipe.roughness = 0.0000016
    if pipe.material == "Steel":
        pipe.roughness = 0.00001
    else:
        pipe.roughness = 0.00001


def lambda_calc(dia: float) -> float:
    """
    fricition factor http://www.verenum.ch/Dokumente/PLH-FW_V1.2.pdf S. 131
    """
    raise DeprecationWarning("Looks unused, will be removed if no complaints in the next months")
    return -0.002 * math.log(dia) + 0.013


def velocity_calc(dia: float, delta_p_L: float, rho: float) -> float:
    # TODO replace symbols with english words (esp. uppercase letters)
    """
    velocity darcy weißbach equation
    """
    raise DeprecationWarning("Looks unused, will be removed if no complaints in the next months")
    return (delta_p_L * 2 * dia / (lambda_calc(dia) * rho)) ** (1 / 2)


def pipe_design(Q_max: float, delta_p_L: float, rho: float, c_p: float) -> float:
    # TODO replace symbols with english words (esp. uppercase letters)
    """
    Pipe design - matching the Q_max
    """
    raise DeprecationWarning("Looks unused, will be removed if no complaints in the next months")
    list_possible_dias = [x / 1000 for x in list(range(5, 2500, 5))]
    dict_Q = {}
    for i in range(0, len(list_possible_dias)):
        dia = list_possible_dias[i]
        Q_test = Q_calc(dia, velocity_calc(dia, delta_p_L, rho), c_p, rho)
        dict_Q[(Q_test, dia)] = abs(Q_test - Q_max)
    return min(dict_Q, key=dict_Q.get)[1]


def Q_calc(dia: float, v: float, c_p: float, rho: float) -> float:
    # TODO replace symbols with english words (esp. uppercase letters)
    """
    calculation of heat flow
    """
    raise DeprecationWarning("Looks unused, will be removed if no complaints in the next months")
    delta_T = 30
    return c_p * rho * math.pi / 4 * dia**2 * v * delta_T


def calculate_diameter(dhn: DistrictHeatingNetwork, density: float, c_p: float, consumers: list):
    # TODO replace symbols with english words (esp. uppercase letters)
    # TODO docstring
    raise DeprecationWarning("Looks unused, will be removed if no complaints in the next months")
    graph = dhn.graph
    for edge in graph.edges:
        pipe = list(graph.edges[edge[0], edge[1]].values())[0]
        pipe: DhnPipe
        Q_transport = sum(
            list(graph.nodes[con].values())[0].heat_quantity.max()
            for con in consumers
            if con in list(nx.nodes(nx.dfs_tree(graph, edge[1])))
        )
        # TODO please comment on why this is disabled and why it is still in here
        # list_duplicates = list(nx.nodes(nx.dfs_tree(graph, edge[1])))+list(nx.dfs_successors(graph, edge[1]))
        # end_nodes = [unique for unique in list_duplicates if list_duplicates.count(unique) == 1]
        # list_edges_paths = []
        # for end_node in end_nodes:
        #     list_edges_paths = list_edges_paths + list(nx.all_simple_edge_paths(graph, edge[0], end_node))[0]
        # necessary_paths = list(set(list_edges_paths))
        # distance = 0
        # for edge_path in necessary_paths:
        #     distance = distance + list(graph.edges[edge_path[0], edge_path[1]].values())[0].length
        # Q_transport = Q_transport + distance * math.pi * 0.05 * 0.0008 * 85

        pipe.diameter = pipe_design(Q_transport, 150, density, c_p)
        if 0.015 > pipe.diameter:
            pipe.diameter = 0.015



def to_geopandas(
    dhn: DistrictHeatingNetwork,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
    # TODO is there a way to call .network.to_geopandas()?
    """
    return four GeoDataFrames: First for nodes, second for edges, third for
    junctions, fourth for pipes
    """
    node_ids, device_ids, device_types, node_geometries = [], [], [], []
    for n in dhn.nodes:
        node_ids.append(n.id)
        device_ids.append(n.attachment.id if n.attachment else None)
        device_types.append(n.attachment.__class__.__name__ if n.attachment else None)
        node_geometries.append(n.geometry.shape)
    node_df = pd.DataFrame(dict(id=node_ids, device_id=device_ids, device_types=device_types))
    node_gdf = gpd.GeoDataFrame(data=node_df, geometry=node_geometries)

    edge_ids, node_from_ids, node_to_ids, edge_geometries, pipe_supply_id, pipe_return_id = [], [], [], [], [], []
    for e in dhn.edges:
        edge_ids.append(e.id)
        node_from_ids.append(e._node_from.id if e.node_from else None)
        node_to_ids.append(e.node_to.id if e.node_to else None)
        edge_geometries.append(e.geometry.shape)
        pipe_supply_id.append(e.pipe_supply.id)
        pipe_return_id.append(e.pipe_return.id)
    edge_df = pd.DataFrame(
        dict(
            id=edge_ids,
            node_from_id=node_from_ids,
            node_to_id=node_to_ids,
            pipe_supply_id=pipe_supply_id,
            pipe_return_id=pipe_return_id,
        )
    )
    edge_gdf = gpd.GeoDataFrame(data=edge_df, geometry=edge_geometries)

    junction_ids, junction_device_ids, junction_device_types, junction_geometries = [], [], [], []
    for j in dhn.junctions:
        assert isinstance(j, DhnJunction)
        junction_ids.append(j.id)
        junction_device_ids.append(j.attachment.id if j.attachment else None)
        junction_device_types.append(j.attachment.__class__.__name__ if j.attachment else None)
        junction_geometries.append(j.geometry.shape)
    junction_df = pd.DataFrame(
        dict(id=junction_ids, junction_device_ids=junction_device_ids, junction_device_types=junction_device_types)
    )
    junction_gdf = gpd.GeoDataFrame(data=junction_df, geometry=junction_geometries)

    pipe_ids, junction_from_ids, junction_to_ids, pipe_geometries = [], [], [], []
    for p in dhn.pipes:
        assert isinstance(p, DhnPipe)
        pipe_ids.append(p.id)
        junction_from_ids.append(p.junction_from.id if p.junction_from else None)
        junction_to_ids.append(p.junction_to.id if p.junction_to else None)
        pipe_geometries.append(p.geometry.shape)
    pipe_df = pd.DataFrame(dict(id=pipe_ids, junction_from_id=junction_from_ids, junction_to_id=junction_to_ids))
    pipe_gdf = gpd.GeoDataFrame(data=pipe_df, geometry=pipe_geometries)

    return node_gdf, edge_gdf, junction_gdf, pipe_gdf


# IMPLEMENT
def from_geopandas(
    node_gdf: gpd.GeoDataFrame, pipe_gdf: gpd.GeoDataFrame, dhn: DistrictHeatingNetwork = None
) -> DistrictHeatingNetwork:
    raise NotImplementedError()
    ...


def to_geopackage(dhn: DistrictHeatingNetwork, filename: str):
    node_gdf, edges_gdf, junctions_gdf, pipe_gdf = to_geopandas(dhn)
    node_gdf.to_file(filename, driver="GPKG", layer="nodes")
    edges_gdf.to_file(filename, driver="GPKG", layer="edges")
    junctions_gdf.to_file(filename, driver="GPKG", layer="junctions")
    pipe_gdf.to_file(filename, driver="GPKG", layer="pipes")


# IMPLEMENT
def from_geopackage(filename: str, dhn: DistrictHeatingNetwork = None) -> DistrictHeatingNetwork:
    raise NotImplementedError()
    gpd.GeoDataFrame.from_file(filename)
