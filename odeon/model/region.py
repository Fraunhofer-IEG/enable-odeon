from typing import Any
import geopandas as gpd
import copy
from shapely import Polygon

from .base import Organizer
from .base_geometry import KEY_GEOM


class Region(Organizer):
    """
    Attributes
    ----------
    seed : Any
        Use this to store any constituting object, e.g. a center point or a
        spatial object that was used to define this region
    """

    boundary: Polygon = None
    seed: Any = None

    def __init__(self, boundary: Polygon = None, seed=None, **kwargs):
        super().__init__(**kwargs)
        self.boundary = boundary
        self.seed = seed


class Segregation(Organizer):
    """
    A collection of non-overlapping Regions (typically spanning a larger
    region without any holes). Regions will be stored as `<Organizer>.members`
    """

    _CHILDREN_ATTRIBUTES = {"_regions": "Region[]"}
    _regions: list[Region] = None

    def __init__(self, regions: list[Region] = None, **kwargs):
        super().__init__(**kwargs)
        self._regions = []
        if regions is not None:
            self.add_regions(regions)

    @property
    def regions(self) -> list[Region]:
        return copy.copy(self._regions)

    def add_regions(self, regions: list[Region]):
        assert isinstance(regions, (list, tuple)) and all(isinstance(r, Region) for r in regions)
        assert all(r.branch == self.branch or r.branch is None for r in regions)
        for r in regions:
            r._set_parent(self)
        self._regions += regions

    def to_gdf(self) -> gpd.GeoDataFrame:
        dicts = []
        for i, r in enumerate(self._regions):
            dicts.append({"index": i, "object": r, KEY_GEOM: r.boundary})
        gdf = gpd.GeoDataFrame(data=dicts, geometry=KEY_GEOM)
        gdf.set_index("index")
        return gdf
