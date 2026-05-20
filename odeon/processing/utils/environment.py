import numpy as np
from odeon.model import Weather, Temporal
import pandas as pd
from scipy.optimize import fmin


# EXTRACT to mosaic
def heating_degree_days(
    weather: Weather,
    heating_temperature_limit: float = 15.0,
    heating_target_temperature: float = 20.0,
) -> int:
    """
    For all days with daily temperature mean below `heating_temperature_limit`,
    sum up the difference between daily mean and `heating_target_temperature`.

    In VDI 2067, `heating_temperature_limit` is 15 and
    `heating_target_temperature` is 20.
    """
    return _heating_degree_days(
        weather.ambient_temperature,
        heating_temperature_limit=heating_temperature_limit,
        heating_target_temperature=heating_target_temperature,
    )


# EXTRACT to mosaic
def cooling_degree_days(
    weather: Weather,
    cooling_temperature_limit: float = 18.3,
    cooling_target_temperature: float = 22.0,
) -> int:
    """
    For all days with daily temperature mean above `cooling_temperature_limit`,
    sum up the difference between daily mean and limit.
    """
    return _cooling_degree_days(
        weather.ambient_temperature,
        cooling_temperature_limit=cooling_temperature_limit,
        cooling_target_temperature=cooling_target_temperature,
    )


# EXTRACT to mosaic
def _heating_degree_days(
    ambient_temperature: Temporal,
    heating_temperature_limit: float = 15.0,
    heating_target_temperature: float = 20.0,
) -> int:
    """
    For all days with daily temperature mean below `heating_temperature_limit`,
    sum up the difference between daily mean and `heating_target_temperature`.

    In VDI 2067, `heating_temperature_limit` is 15 and
    `heating_target_temperature` is 20.
    """
    if not isinstance(ambient_temperature, Temporal) or not isinstance(ambient_temperature.timeindex, pd.DatetimeIndex):
        raise Exception()
    ambient_temperature_df = ambient_temperature.timeseries.to_frame()
    means: pd.DataFrame = ambient_temperature_df.groupby(ambient_temperature_df.index.floor("D")).mean()
    means = means.iloc[:, 0]
    hdd = pd.Series(0.0, index=means.index)
    hdd[means - heating_temperature_limit < 0] = heating_target_temperature - means
    n = hdd.sum()
    return n


# EXTRACT to mosaic
def _cooling_degree_days(
    ambient_temperature: pd.Series,
    cooling_temperature_limit: float = 18.3,
    cooling_target_temperature: float = 22.0,
) -> int:
    """
    For all days with daily temperature mean above `cooling_temperature_limit`,
    sum up the difference between daily mean and `cooling_target_temperature`.
    """
    if not isinstance(ambient_temperature, pd.Series) or not isinstance(ambient_temperature.index, pd.DatetimeIndex):
        raise Exception()
    ambient_temperature = ambient_temperature.to_frame()
    means: pd.DataFrame = ambient_temperature.groupby(ambient_temperature.index.floor("D")).mean()
    means = means.iloc[:, 0]
    hdd = pd.Series(0.0, index=means.index)
    hdd[means - cooling_temperature_limit < 0] = cooling_target_temperature - means
    n = hdd.sum()
    return n


# EXTRACT to mosaic
def fit_ambient_temperature(
    ambient_temperature: pd.Series,
    min_value: float | None = None,
    mean_value: float | None = None,
    max_value: float | None = None,
    heating_degree_days: int | None = None,
    cooling_degree_days: int | None = None,
    heating_temperature_limit: float = 15.0,
    cooling_temperature_limit: float = 18.3,
    heating_target_temperature: float = 20.0,
    cooling_target_temperature: float = 22.0,
) -> pd.Series:
    """
    Fit the temperature series `ambient_temperature` to the parameters by linear
    transformation.

    Parameters
    ----------
    min_value : float | None
        The target minimum temperature in the year
    mean_value : float | None
        The target average temperature in the year
    max_value : float | None
        The target maximum temperature in the year
    heating_degree_days : int | None
        The target number of heating degree days calculated with
        `heating_temperature_limit` and `heating_target_temperature`
    cooling_degree_days : int | None
        The target number of cooling degree days calculated with
        `cooling_temperature_limit` and `cooling_target_temperature`
    heating_temperature_limit : float
        The temperature limit for calculating heating degree days (i.e. the
        temperature below which heating is needed)
    cooling_temperature_limit : float
        The temperature limit for calculating cooling degree days (i.e. the
        temperature above which cooling is needed)
    heating_target_temperature : float
        The target temperature for calculating heating degree days (i.e. the
        desired room temperature for calculating heating degree days)
    cooling_target_temperature : float
        The target temperature for calculating cooling degree days (i.e. the
        desired room temperature for calculating cooling degree days)
    """

    MIN_LINEAR_FACTOR = 0.5
    MAX_LINEAR_FACTOR = 2

    # check parameters:
    params = [min_value, mean_value, max_value, heating_degree_days, cooling_degree_days]
    linear_params = [min_value, mean_value, max_value]
    n_params = len([x for x in params if x is not None])
    n_linear_params = len([x for x in linear_params if x is not None])
    if n_params > 2:
        raise Exception("Cannot fit ambient temperature series if more than two parameters are given")
    if not isinstance(ambient_temperature, Temporal) or not isinstance(ambient_temperature.timeindex, pd.DatetimeIndex):
        raise Exception()

    # calculate indicators for ambient_temperature:
    at_min = ambient_temperature.timeseries.min()
    at_max = ambient_temperature.timeseries.max()
    at_mean = ambient_temperature.timeseries.mean()

    if n_linear_params == 2:
        # = linear fit, T' = aT + b:
        assert heating_degree_days is None
        assert cooling_degree_days is None

        if min_value is not None and max_value is not None:
            a = (max_value - min_value) / (at_max - at_min)
            b = min_value - a * at_min

        elif min_value is not None and mean_value is not None:
            a = (mean_value - min_value) / (at_mean - at_min)
            b = min_value - a * at_min

        elif mean_value is not None and max_value is not None:
            a = (max_value - mean_value) / (at_max - at_mean)
            b = mean_value - a * at_mean

    elif min_value is not None and heating_degree_days is not None:

        def f_apply_scaling_and_calc_deviation(x):
            hdd = _heating_degree_days(
                ambient_temperature=(x * (ambient_temperature.timeseries - at_min)) + min_value,
                heating_temperature_limit=heating_temperature_limit,
                heating_target_temperature=heating_target_temperature,
            )
            return abs(heating_degree_days - hdd)

        a, *_ = fmin(func=f_apply_scaling_and_calc_deviation, x0=1)
        b = -a * at_min + min_value

    else:
        raise Exception("Invalid parameter combination")

    # apply scaling:
    if a < MIN_LINEAR_FACTOR or a > MAX_LINEAR_FACTOR:
        raise Exception("linear factor out of accepted range")
    result_series = a * ambient_temperature.timeseries + b

    return result_series


# EXTRACT to mosaic
def create_sinusoidal_underground_temperature_series(
    weather: Weather,
    ground_temperature_min: float = 3,  # [°C]
    ground_temperature_max: float = 20,  # [°C]
    offset: int = 2800,
) -> pd.Series:
    """
    Create a sinusoidal temperature curve for underground temperature and return
    it.

    Parameters
    ----------
    offset : int
        The number of offset timesteps for the sine curve. 0 would mean
        that the average temperature is reached at January 1, 2135 would mean that
        it is reached on April 1
    """
    amplitude = (ground_temperature_max - ground_temperature_min) / 2
    mean = (ground_temperature_max + ground_temperature_min) / 2
    sine_wave = mean + amplitude * np.sin((2 * np.pi / 8760) * (np.arange(8760) - offset))
    ground_temperature = pd.Series(sine_wave + 273.15, index=weather.validity.index)

    return ground_temperature
