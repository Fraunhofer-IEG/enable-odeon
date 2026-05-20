from typing import Literal
from abc import ABC

from .base import Object, StrEnum
from .base_geometry import CardinalOrientation
from .geometry import Geometry

from ..processing.geometry_cartesian import closest_direction_index


class RoofType(StrEnum):
    GABLE = "gable"
    FLAT = "flat"
    SHED = "shed"
    OTHER = "other"


class BuildingGeometry(Object, ABC):
    """
    Abstract class to describe the full geometry of a building including its
    footprint, floor, walls, roofs and windows.

    - to access the building footprint, use e.g.:
        - `footprint.geometry.geometry` (None, Point or Polygon)
        - `footprint.geometry.polygon` (None or Polygon)
        - `footprint.geometry.area` (None or float)
    - how to use `footprint`: Some `GeometryObject`s (`NominalGeometry` e.g.) can store attributes like
    `height`, `azimuth`, etc. These are not intended to actually describe the building geometry and should be
    left empty, at best.
    """

    floor_geometries: list[Geometry] = None
    wall_geometries: list[Geometry] = None
    roof_geometries: list[Geometry] = None
    window_wall_geometries: list[Geometry] = None
    window_roof_geometries: list[Geometry] = None
    door_geometries: list[Geometry] = None

    footprint: Geometry = None
    altitude: float = None  # [m]
    _footprint_area: float = None
    dimensions: tuple[float, float] = None  # [m] (ridge orientation, roof orientation)
    roof_type: RoofType = None
    building_height: float = None  # [m]
    eaves_height: float = None  # [m]
    roof_height: float = None  # [m]
    roof_height_net: float = None  # [m]
    roof_tilt: float = None  # [°]
    roof_length: float = None  # = ridge length
    overhang_height: float = None  # [m]
    overhang_length: float = None  # [m] ridge orientation
    overhang_width: float = None  # [m] roof orientation
    roof_orientation: float = None  # [°]
    ridge_orientation: float = None  # [°]
    roof_orientation_cardinal: CardinalOrientation = None
    ridge_orientation_cardinal: CardinalOrientation = None
    long_ridged_roof: bool = None  # whether ridge direction is in direction of longer building dimension
    single_roof_width: float = None  # [m]
    single_roof_width_net: float = None  # [m]
    # window factor for walls & door factor:
    # either for all walls, or for ridge and roof oriented walls (i.e. wall with azimuth in roof direction / ridge
    # direction), or per (best fitting) wall azimuth
    window_wall_factor: float | tuple[float, float] | dict[CardinalOrientation, float] = None  # [m²/m²]
    door_factor: float | tuple[float, float] | dict[CardinalOrientation, float] = None  # [m²/m²]
    # window factor for roof: either uniform for all roofs, or per (best fitting) roof azimuth
    window_roof_factor: float | tuple[CardinalOrientation, float] = None  # [m²/m²]
    window_roof_vertical: bool = False  # if not vertical, it's the same tilt as the roof

    def __init__(self, footprint: Geometry = None, **kwargs):
        self.floor_geometries = []
        self.wall_geometries = []
        self.roof_geometries = []
        self.window_wall_geometries = []
        self.window_roof_geometries = []
        self.door_geometries = []
        self.footprint = footprint
        super().__init__(**kwargs)

    @property
    def geometries(self):
        return (
            self.floor_geometries
            + self.wall_geometries
            + self.roof_geometries
            + self.window_wall_geometries
            + self.window_roof_geometries
            + self.door_geometries
        )

    @property
    def window_geometries(self):
        return self.window_wall_geometries + self.window_roof_geometries

    @property
    def footprint_area(self):
        if self.footprint is not None and self.footprint.is_polygon:
            return self.footprint.shape.area
        else:
            return self._footprint_area

    @footprint_area.setter
    def footprint_area(self, area: float):
        if self.footprint is not None and self.footprint.is_polygon:
            raise Exception("can't set footprint area when a shape is present")
        else:
            self._footprint_area = area

    @property
    def roof_area(self):
        """
        the (possibly inclined) area of all parts of the roof. Might return
        `None`.
        """
        ra = 0
        if self.roof_geometries:
            for rg in self.roof_geometries:
                if hasattr(rg, "area") and rg.area:
                    ra += rg.area
        if self.window_roof_geometries:
            for wrg in self.window_geometries:
                if hasattr(wrg, "area") and wrg.area:
                    ra -= wrg.area
        if ra > 0:
            return ra


class FootprintNominalBuildingGeometry(BuildingGeometry):
    def __init__(self, footprint: Geometry = None, **kwargs):
        super().__init__(footprint=footprint, **kwargs)


class RoofedCuboidBuildingGeometry(BuildingGeometry):
    def __init__(self, **kwargs):
        footprint = kwargs.pop("footprint", None)
        assert footprint is None
        super().__init__(**kwargs)

    @property
    def footprint(self):
        return self.floor_geometries[0]

    @footprint.setter
    def footprint(self, footprint):
        # this is ugly. RoofedCuboidBuildingGeometry constructor tries to set footprint=None (from BuildingGeometry)
        # and would raise an AttributeError if this setter didn't exist
        Warning("can't set footprint for RoofedCuboidBuildingGeometry")

    def element_with_orientation(
        self,
        element_type: Literal["wall", "roof", "window", "window_wall", "window_roof", "door"],
        direction: float | CardinalOrientation,
        allow_antiparallel: bool = False,
    ):
        """
        Get wall, roof, door or window with azimuth (i.e. outward normal) closest to direction.
        If `element_type == "roof"`, for a flat roof, the roof will always be returned.
        """
        if isinstance(direction, CardinalOrientation):
            direction = direction.degrees
        if element_type == "wall":
            elements = self.wall_geometries
        elif element_type == "roof":
            if self.roof_type is RoofType.FLAT:
                return self.roof_geometries[0]
            else:
                elements = self.roof_geometries
        elif element_type == "window":
            elements = self.window_geometries
        elif element_type == "window_wall":
            elements = self.window_wall_geometries
        elif element_type == "window_roof":
            elements = self.window_roof_geometries
        elif element_type == "door":
            elements = self.door_geometries
        else:
            raise KeyError()
        azimuths = [e.geometry.azimuth for e in elements]
        idx = closest_direction_index(direction, azimuths, allow_antiparallel=allow_antiparallel)
        return self.elements[idx]
