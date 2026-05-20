from .geometry import Geometry
from .base import Object


class Waters(Object):
    """
    Base class for all type of waters (stagnant and running)
    """

    geometry: Geometry = None
    volume: float = None  # [m³]
    max_depth: float = None  # [m]
    specific_heat_capacity_kj_per_kg_k: float = 4.2  # [kJ/kgK]
    density: float = 999.975  # [kg/m³]

    def __init__(self, geometry: Geometry = None, volume: float = None, max_depth: float = None) -> None:
        self.geometry = geometry
        self.volume = volume
        self.max_depth = max_depth
        self.specific_heat_capacity_kj_per_kg_k = self.specific_heat_capacity_kj_per_kg_k
        self.density = self.density


class River(Waters):
    """
    Class to describe running waters (rivers, cannels, ...)
    """

    def __init__(self, geometry: Geometry = None, volume: float = None, max_depth: float = None) -> None:
        super().__init__(geometry, volume, max_depth)


class Lake(Waters):
    """
    Class to describe stagnant waters (lakes, ponds, ...)
    """

    def __init__(self, geometry: Geometry = None, volume: float = None, max_depth: float = None) -> None:
        super().__init__(geometry, volume, max_depth)

    @property
    def energy_potential_kj(self) -> float:
        """
        The function returns the theoretical maximum energy that can be
        extracted under the constraint, that the water temperature may only
        change by 1 K. The unit of the returned value is [kJ]!
        """
        return self.specific_heat_capacity_kj_per_kg_k * self.density * self.volume * 1
