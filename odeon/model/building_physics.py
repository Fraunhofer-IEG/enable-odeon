from __future__ import annotations
from numbers import Number
from enum import Enum

import pandas as pd

from .base import Object
from .temporal import Temporal


class MassDistribution(str, Enum):
    MASS_CONCENTRATED_INSIDE = "mass_concentrated_inside"
    MASS_CONCENTRATED_OUTSIDE = "mass_concentrated_outside"
    MASS_CONCENTRATED_INSIDE_OUTSIDE = "mass_splited_inside_outside"
    MASS_CONCENTRATED_CONSISTENT = "mass_distributed_consistent"
    MASS_CONCENTRATED_CENTRAL = "mass_concentrated_central"


class Transparency(str, Enum):
    TRANSPARENT = "transparent"
    OPAQUE = "opaque"


class AdjacentEnvironment(str, Enum):
    GROUND = "ground"
    AIR = "air"
    UNHEATED = "unheated"


class WindowType(str, Enum):
    TRIPLE_THERMAL_INSULATION_GLAZING_FOR_PASSIVE_HOUSE = "triple_thermal_insulation_glazing_for_passive_house"
    TRIPLE_THERMAL_INSULATION_GLAZING = "triple_thermal_insulation_glazing"
    DOUBLE_THERMAL_INSULATION_GLAZING = "double_thermal_insulation_glazing"


class BuildingThermalZone(Object):

    # temporal attributes:
    _TEMPORAL_ATTRIBUTES = [
        "_heattranscoef_ventilation_w_per_sqm_k",
        "_indoor_temperature_setpoint",
        "_indoor_temperature",
        "_operative_temperature",
        "_internal_solar_gains",
    ]
    _heattranscoef_ventilation_w_per_sqm_k: Temporal = None  # [W/(m²K)] floor area related
    _indoor_temperature_setpoint: Temporal = None  # [°C]
    _indoor_temperature: Temporal = None  #  [°C]
    _operative_temperature: Temporal = None  # [°C]
    _internal_solar_gains: Temporal = None  # [kW]

    # additional attributes:
    heated_area: float = None  # [m²]
    envelope_surface_area: float = None  # [m²]
    heated_volume: float = None  # [m³]
    internal_heat_capacity_j_per_k: float = None  # [J/K] # TODO check that unit is right!! TODO unit
    heattranscoef_thermal_bridges_w_per_sqm_k: float = None  # [W/(m²K)] envelope specific
    heatloss_ventilation: float = None  # [kW]
    heatloss_thermal_bridges: float = None  # [kW]
    internal_heat_gains: float = None  # [kW]
    air_exchange_rate_use: float = None  # [1/h] expressed as share of the building volume # TODO check!

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    # properties for temporals:

    @property
    def heattranscoef_ventilation_w_per_sqm_k(self) -> Temporal:
        return self._heattranscoef_ventilation_w_per_sqm_k

    @heattranscoef_ventilation_w_per_sqm_k.setter
    def heattranscoef_ventilation_w_per_sqm_k(
        self,
        heattranscoef_ventilation_w_per_sqm_k: Temporal | Number | pd.Series | None,
    ) -> Temporal:
        self.set_temporal("_heattranscoef_ventilation_w_per_sqm_k", heattranscoef_ventilation_w_per_sqm_k)

    @property
    def indoor_temperature_setpoint(self) -> Temporal:
        return self._indoor_temperature_setpoint

    @indoor_temperature_setpoint.setter
    def indoor_temperature_setpoint(
        self,
        indoor_temperature_setpoint: Temporal | Number | pd.Series | None,
    ) -> Temporal:
        self.set_temporal("_indoor_temperature_setpoint", indoor_temperature_setpoint)

    @property
    def indoor_temperature(self) -> Temporal:
        return self._indoor_temperature

    @indoor_temperature.setter
    def indoor_temperature(self, indoor_temperature: Temporal | Number | pd.Series | None) -> Temporal:
        self.set_temporal("_indoor_temperature", indoor_temperature)

    @property
    def operative_temperature(self) -> Temporal:
        return self._operative_temperature

    @operative_temperature.setter
    def operative_temperature(self, operative_temperature: Temporal | Number | pd.Series | None) -> Temporal:
        self.set_temporal("_operative_temperature", operative_temperature)

    @property
    def internal_solar_gains(self) -> Temporal:
        return self._internal_solar_gains

    @internal_solar_gains.setter
    def internal_solar_gains(self, internal_solar_gains: Temporal | Number | pd.Series | None) -> Temporal:
        self.set_temporal("_internal_solar_gains", internal_solar_gains)


class ElementPhysics(Object):

    # temporal attributes:
    _TEMPORAL_ATTRIBUTES = [
        "_ambient_temperature",
        "_direct_solar_irradiance",
        "_diffuse_solar_irradiance",
    ]
    # In IsoSim, this can be different from weather depending on adjacent environment:
    _ambient_temperature: Temporal = None  # [°C]
    # In IsoSim, these can be different from weather depending on tilt and azimuth:
    _direct_solar_irradiance: Temporal = None  # [kW/m²]
    _diffuse_solar_irradiance: Temporal = None  # [kW/m²]

    # additional attributes:
    material: str = None
    u_value_w_per_sqm_k: float = None  # [W/m²K]
    structure: dict = None
    construction_type: str = None
    transparency: Transparency = None
    shading_factor: float = None  # [1], 0..1
    view_factor: float = None  # [1], 0..1
    _total_solar_irradiance: pd.DataFrame = None  # [kW/m²] # TODO Dict of Temporals? -> "deactivated" for now

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    # properties for temporals:

    @property
    def ambient_temperature(self) -> Temporal:
        return self._ambient_temperature

    @ambient_temperature.setter
    def ambient_temperature(self, ambient_temperature: Temporal | Number | pd.Series | None) -> Temporal:
        self.set_temporal("_ambient_temperature", ambient_temperature)

    @property
    def direct_solar_irradiance(self) -> Temporal:
        return self._direct_solar_irradiance

    @direct_solar_irradiance.setter
    def direct_solar_irradiance(self, direct_solar_irradiance: Temporal | Number | pd.Series | None) -> Temporal:
        self.set_temporal("_direct_solar_irradiance", direct_solar_irradiance)

    @property
    def diffuse_solar_irradiance(self) -> Temporal:
        return self._diffuse_solar_irradiance

    @diffuse_solar_irradiance.setter
    def diffuse_solar_irradiance(self, diffuse_solar_irradiance: Temporal | Number | pd.Series | None) -> Temporal:
        self.set_temporal("_diffuse_solar_irradiance", diffuse_solar_irradiance)

    @property
    def total_solar_irradiance(self):
        # the attribute was typehinted as pd.DataFrame. If it's a dataframe with
        # timeindex, it might be necessary to transform it into a dict of
        # Temporals. As no further specification is given here in Odeon, this has
        # to be judged by analysing the BuildingSimulator.
        raise NotImplementedError()


class OpaqueElementPhysics(ElementPhysics):
    specific_heat_capacity_j_per_sqm_k: float = None  # [J/(m2 K)] (wall area specific)
    mass_distribution: MassDistribution = None
    insulation_thickness: float = None  # [m]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class WallPhysics(OpaqueElementPhysics):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class RoofPhysics(OpaqueElementPhysics):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class FloorPhysics(OpaqueElementPhysics):

    # temporal attributes:
    _TEMPORAL_ATTRIBUTES = ["_ground_temperature"]
    _ground_temperature: Temporal = None  # [°C] # TODO: move to environment?

    # additional attributes:
    heat_capacity_soil: float = None  # TODO unit?

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    # properties for temporals:

    @property
    def ground_temperature(self) -> Temporal:
        return self._ground_temperature

    @ground_temperature.setter
    def ground_temperature(self, ground_temperature: Temporal | Number | pd.Series | None) -> Temporal:
        self.set_temporal("_ground_temperature", ground_temperature)


class WindowPhysics(ElementPhysics):
    total_solar_energy_transmittance: float = None  # [1], 0..1, 1=100% transmittance
    frame_portion: float = None  # [1], 0..1
    window_type: WindowType = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class DoorPhysics(ElementPhysics):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
