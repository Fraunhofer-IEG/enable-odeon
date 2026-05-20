from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree
import numpy as np


def _strtree_and_geometries(geometries_or_tree) -> tuple[STRtree, list[BaseGeometry]]:
    # copy exists in crescendo
    if isinstance(geometries_or_tree, STRtree):
        return geometries_or_tree, geometries_or_tree.geometries
    else:
        assert isinstance(geometries_or_tree, list) and all(isinstance(got, BaseGeometry) for got in geometries_or_tree)
        return STRtree(geometries_or_tree), geometries_or_tree


def _query_dwithin(tree: STRtree, geometries: list[BaseGeometry], distance: float) -> dict[int, list[int]]:
    """
    Query `tree` for `geometries` within `distance`.

    Returns
    -------
    Mapping dictionary with an index from `geometries` as key and indices from
    `tree.geometries` that are within `distance` as value
    # TODO will empty geometries be returned in dict?
    """
    # copy exists in crescendo
    igeoms, itrees = tree.query(geometry=geometries, predicate="dwithin", distance=distance).tolist()
    mapping = {}
    for igeom, itree in zip(igeoms, itrees):
        mapping[igeom] = mapping.get(igeom, []) + [itree]
    return mapping


def closest_geometry_pair(shapes1: list[BaseGeometry], shapes2: list[BaseGeometry]) -> tuple[int, int]:
    # copy exists in crescendo
    tree = STRtree(geoms=shapes1)
    indices, distance = tree.query_nearest(
        geometry=shapes2,
        all_matches=False,
        exclusive=True,
        return_distance=True,
    )
    ishapes2, ishapes1 = indices.tolist()
    imin = np.argmin(distance)
    i1 = ishapes1[imin]
    i2 = ishapes2[imin]
    return i1, i2
