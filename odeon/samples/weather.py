import pandas as pd
import numpy as np
import random
from odeon.model import Weather

# from pvlib.solarposition import get_solarposition # FIXME removed because import not in setup.py /RM


def sample_series(
    random_sample: bool = False,
    year: int = 2022,
    min_val: int = 0,
    max_val: int = 40,
) -> pd.Series:
    idx = pd.date_range(start=f"{year}-01-01", end=f"{year+1}-01-01", freq="h", inclusive="left")
    if random_sample:
        ts = pd.Series(
            random.choices(range(min_val, max_val + 1), k=len(idx)),
            index=idx,
            dtype="float64",
        )
    else:
        values = min_val + (max_val - min_val) / 2 * (1 + np.sin(0.02 * np.array(range(len(idx)))))
        ts = pd.Series(values, index=idx)
    return ts


def sample_weather(year) -> Weather:
    # TODO Add more logic?
    w = Weather()
    w.ambient_temperature = sample_series(random_sample=False, year=year, min_val=-10, max_val=30)
    w.direct_normal_irradiance = sample_series(random_sample=False, year=year, min_val=0, max_val=300)
    w.diffuse_horizontal_irradiance = sample_series(random_sample=False, year=year, min_val=0, max_val=300)
    w.global_horizontal_irradiance = sample_series(random_sample=False, year=year, min_val=0, max_val=600)
    w.soil_temperature = sample_series(random_sample=False, year=year, min_val=5, max_val=12)
    w.wind_speed = sample_series(random_sample=False, year=year, min_val=0, max_val=25)
    w.wind_direction = sample_series(random_sample=False, year=year, min_val=0, max_val=360)
    # w.solar_position = get_solarposition(w.ambient_temperature.index, 10, 51)
    return w
