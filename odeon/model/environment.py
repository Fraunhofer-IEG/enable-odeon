from numbers import Number
from typing import Literal

import pandas as pd

from .base import Object, Branch
from .temporal import Temporal

from ..processing.temporal import check_temporal_validity


class Weather(Object):
    """
    Remarks
    -------
    - Parent of `Weather` is a `Branch` where the weather is set as
    `<Branch>.weather` (not: part of `<Branch>`.objects)
    """

    # temporal attributes:
    _TEMPORAL_ATTRIBUTES = [
        "_ambient_temperature",
        "_global_horizontal_irradiance",
        "_diffuse_horizontal_irradiance",
        "_direct_normal_irradiance",
        "_soil_temperature",
        "_underground_temperature",
        "_wind_speed",
        "_wind_direction",
        "_pressure",
        "_cloud_coverage",
        "_cloud_coverage",
    ]
    _ambient_temperature: Temporal = None  # [°C] 2 m above
    _global_horizontal_irradiance: Temporal = None  # [kWh/m²]
    _diffuse_horizontal_irradiance: Temporal = None  # [kWh/m²]
    _direct_normal_irradiance: Temporal = None  # [kWh/m²]
    _soil_temperature: Temporal = None  # [°C] depth ca. 1 m? # TODO rename to ground_temperature?
    _underground_temperature: Temporal = None  # [°C] depth ca. 100 m
    _wind_speed: Temporal = None  # [m/s]
    _wind_direction: Temporal = None  # [°] TODO check
    _pressure: Temporal = None  # [Pa]
    _cloud_coverage: Temporal = None  # [eighths]
    _cloud_coverage: Temporal = None  # [eighths]

    # temporal dict attributes:
    _TEMPORAL_DICT_ATTRIBUTES = ["_solar_position"]
    _solar_position: dict[
        Literal[
            "apparent_zenith",
            "zenith",
            "apparent_elevation",
            "elevation",
            "azimuth",
            "equation_of_time",
        ],
        Temporal,
    ] = None

    def __init__(self, branch: Branch = None, **kwargs):
        super().__init__(**kwargs)
        if branch is not None:
            branch.weather = self  # letting branch pass to parent's constructor would add self to branch.objects

    # properties for temporals:

    @property
    def ambient_temperature(self) -> Temporal:
        return self._ambient_temperature

    @ambient_temperature.setter
    def ambient_temperature(self, ambient_temperature: Temporal | Number | pd.Series | None):
        self.set_temporal("_ambient_temperature", ambient_temperature)
        check_temporal_validity(
            temporal=self._ambient_temperature,
            no_total_allowed=True,
            no_series_or_fix_allowed=False,
            min_value=-100,
            max_value=100,
            action="raise",
        )

    @property
    def global_horizontal_irradiance(self) -> Temporal:
        return self._global_horizontal_irradiance

    @global_horizontal_irradiance.setter
    def global_horizontal_irradiance(self, global_horizontal_irradiance: Temporal | Number | pd.Series | None):
        self.set_temporal("_global_horizontal_irradiance", global_horizontal_irradiance)

    @property
    def diffuse_horizontal_irradiance(self) -> Temporal:
        return self._diffuse_horizontal_irradiance

    @diffuse_horizontal_irradiance.setter
    def diffuse_horizontal_irradiance(self, diffuse_horizontal_irradiance: Temporal | Number | pd.Series | None):
        self.set_temporal("_diffuse_horizontal_irradiance", diffuse_horizontal_irradiance)

    @property
    def direct_normal_irradiance(self) -> Temporal:
        return self._direct_normal_irradiance

    @direct_normal_irradiance.setter
    def direct_normal_irradiance(self, direct_normal_irradiance: Temporal | Number | pd.Series | None):
        self.set_temporal("_direct_normal_irradiance", direct_normal_irradiance)

    @property
    def soil_temperature(self) -> Temporal:
        return self._soil_temperature

    @soil_temperature.setter
    def soil_temperature(self, soil_temperature: Temporal | Number | pd.Series | None):
        self.set_temporal("_soil_temperature", soil_temperature)
        check_temporal_validity(
            temporal=self._soil_temperature,
            no_total_allowed=True,
            no_series_or_fix_allowed=True,
            min_value=-100,
            max_value=100,
            action="raise",
        )

    @property
    def underground_temperature(self) -> Temporal:
        return self._underground_temperature

    @underground_temperature.setter
    def underground_temperature(self, underground_temperature: Temporal | Number | pd.Series | None):
        self.set_temporal("_underground_temperature", underground_temperature)
        check_temporal_validity(
            temporal=self._soil_temperature,
            no_total_allowed=True,
            no_series_or_fix_allowed=True,
            min_value=-100,
            max_value=100,
            action="raise",
        )

    @property
    def wind_speed(self) -> Temporal:
        return self._wind_speed

    @wind_speed.setter
    def wind_speed(self, wind_speed: Temporal | Number | pd.Series | None):
        self.set_temporal("_wind_speed", wind_speed)

    @property
    def wind_direction(self) -> Temporal:
        return self._wind_direction

    @wind_direction.setter
    def wind_direction(self, wind_direction: Temporal | Number | pd.Series | None):
        self.set_temporal("_wind_direction", wind_direction)

    @property
    def pressure(self) -> Temporal:
        return self._pressure

    @pressure.setter
    def pressure(self, pressure: Temporal | Number | pd.Series | None):
        self.set_temporal("_pressure", pressure)

    @property
    def cloud_coverage(self) -> Temporal:
        return self._cloud_coverage

    @cloud_coverage.setter
    def cloud_coverage(self, cloud_coverage: Temporal | Number | pd.Series | None):
        self.set_temporal("_cloud_coverage", cloud_coverage)

    def get_solar_position_property(
        self,
        attr: Literal[
            "apparent_zenith",
            "zenith",
            "apparent_elevation",
            "elevation",
            "azimuth",
            "equation_of_time",
        ],
    ) -> Temporal:
        assert attr in ["apparent_zenith", "zenith", "apparent_elevation", "elevation", "azimuth", "equation_of_time"]
        return self.get_dict_temporal(attr="_solar_position", key=attr)

    def set_solar_position_property(
        self,
        attr: Literal[
            "apparent_zenith",
            "zenith",
            "apparent_elevation",
            "elevation",
            "azimuth",
            "equation_of_time",
        ],
        value: Temporal | Number | pd.Series | None,
    ):
        self.set_temporal(attr="_solar_position", key=attr, x=value)

    def set_solar_position(self, df: pd.DataFrame):
        for c in df.columns:
            self.set_solar_position_property(attr=str(c), value=df[c])

    def get_solar_position_as_df(self) -> pd.DataFrame:
        """
        Return a DataFrame with DatetimeIndex.
        """
        srs_list = {}
        for attr in [
            "apparent_zenith",
            "zenith",
            "apparent_elevation",
            "elevation",
            "azimuth",
            "equation_of_time",
        ]:
            srs_list[attr] = self.get_solar_position_property(attr).series

        return pd.DataFrame(srs_list)

    # additional methods:

    def copy(self) -> "Weather":
        """
        Return a new weather object with the same data fields as `self`.
        Fresh id, no parent.
        """
        w = Weather()
        w.ambient_temperature = self.ambient_temperature.copy()
        w.global_horizontal_irradiance = self.global_horizontal_irradiance.copy()
        w.diffuse_horizontal_irradiance = self.diffuse_horizontal_irradiance.copy()
        w.direct_normal_irradiance = self.direct_normal_irradiance.copy()
        w.soil_temperature = self.soil_temperature.copy()
        w.underground_temperature = self.underground_temperature.copy()
        w.wind_speed = self.wind_speed.copy()
        w.wind_direction = self.wind_direction.copy()
        w.pressure = self.pressure.copy()
        w.cloud_coverage = self.cloud_coverage.copy()
        w._solar_position = {k: v.copy() for k, v in self._solar_position.items()}
        return w
