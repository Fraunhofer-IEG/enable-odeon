from __future__ import annotations
from abc import ABC

from .base import Object
from .building_physics import ElementPhysics, AdjacentEnvironment
from .device import SolarSurfaceHost
from .geometry import Geometry

from ..processing.utils.utils import typeerror_if_not_isinstance, typeerror_if_not_isinstance_or_none


class BuildingElement(Object, ABC):
    """
    Abstract class for building elements such as Wall, Roof, Floor, Window and
    Door.
    """

    # children attributes:
    _CHILDREN_ATTRIBUTES = {"_element_physics": "ElementPhysics"}
    _element_physics: ElementPhysics = None

    # additional attributes:
    _element_geometry: Geometry = None
    adjacent_environment: AdjacentEnvironment = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def element_geometry(self) -> Geometry:
        return self._element_geometry

    @element_geometry.setter
    def element_geometry(self, element_geometry: Geometry):
        typeerror_if_not_isinstance_or_none(element_geometry, Geometry)
        self._element_geometry = element_geometry

    @property
    def element_physics(self) -> ElementPhysics:
        return self._element_physics

    @element_physics.setter
    def element_physics(self, element_physics: ElementPhysics):
        typeerror_if_not_isinstance_or_none(element_physics, ElementPhysics)
        self._element_physics = element_physics
        if element_physics is not None:
            element_physics._set_parent(self)


class SubelementHost(BuildingElement):
    """
    Abstract class for building elements (only Wall and Roofs) that can host
    subelements (Doors and Windows).
    """

    # children attributes:
    _CHILDREN_ATTRIBUTES = {"_sub_elements": "BuildingElement[]"}
    _sub_elements: list[Door | Window] = None

    def __init__(self, **kwargs):
        self._sub_elements = []
        super().__init__(**kwargs)

    @property
    def sub_elements(self) -> list[Door | Window]:
        return self._sub_elements

    def add_sub_elements(self, sub_elements: Door | Window | list[Door | Window]):
        if isinstance(sub_elements, (Door, Window)):
            sub_elements = [sub_elements]
        for element in sub_elements:
            typeerror_if_not_isinstance(element, (Door, Window))
            if self.parent:
                assert element not in self.parent.building_elements
            self._sub_elements.append(element)
            element._set_parent(self)


class Wall(SolarSurfaceHost, SubelementHost):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class Roof(SolarSurfaceHost, SubelementHost):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class Floor(BuildingElement):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class Window(BuildingElement): ...


class Door(BuildingElement): ...
