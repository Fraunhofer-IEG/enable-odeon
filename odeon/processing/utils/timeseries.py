import calendar
import pandas as pd


def part_of_year(timeseries: pd.Series) -> float:
    idx_min = timeseries.index.min()
    idx_max = timeseries.index.max()
    assert timeseries.index.is_monotonic_increasing, "can handle only monotonic timeindices"
    assert idx_min.year == idx_max.year, "can handle only timeindices within one calendar year"
    td_idx = idx_max - idx_min + timeseries.index.freq.delta
    td_full = pd.Timestamp(year=idx_min.year + 1, month=1, day=1) - pd.Timestamp(year=idx_min.year, month=1, day=1)
    return td_idx / td_full


def is_regular(series: pd.Series) -> bool:
    """
    Return whether the series' index intervals are equally spaced.
    """
    return pd.infer_freq(series) is not None


def is_intrayear(series: pd.Series) -> bool:
    """
    Returns whether the series starts and ends in the same calendar
    year.
    """
    return series.index.min().year == series.index.max().year


def is_hourly(series: pd.Series) -> bool:
    """
    Returns whether the series is regular spaced with distance of one
    hour.
    """
    return series.index.freq is not None and pd.Timedelta(series.index.freq) == pd.Timedelta(hours=1)


def is_regular_year(series: pd.Series) -> bool:
    """
    Returns whether the series covers a full calendar year (with any
    temporal frequency).
    """
    # Creates a new sorted DatetimeIndex and compares this with index
    freq = pd.infer_freq(series.index)
    year = series.index.min().year
    dtidx = pd.date_range(start=f"{year}-01-01", end=f"{year+1}-01-01", freq=freq, inclusive="left")
    return dtidx.equals(series.index)


def is_hourly_regular_year(series: pd.Series) -> bool:
    """
    Returns whether the series covers a full calandar year in hourly
    distance (i.e. 8760 timesteps for non-leap years, 8784 timesteps for
    leap years).
    """
    return is_regular_year(series=series) and is_hourly(series=series)


def df_year_adjustment(
    df_original: pd.DataFrame,
    target_dti: pd.DatetimeIndex | int,
) -> pd.DataFrame:
    """
    Transform a Dataframe with DatetimeIndex to another year by changing the
    index values and adding or removing values if original year or target year
    is a leap year.

    If the original year is a leap year and the target year isn't, the values of
    Feburary 29th will be removed.
    If the original year isn't a leap year but the target year is, the values of
    Februray 28th will be duplicated to Februray 29th.

    Parameters
    ----------
    - `df_original`: Dataframe with sorted DatetimeIndex with all timestamps
    from the same calendar year
    """
    from_leap_year = df_original.index[0].is_leap_year

    if isinstance(target_dti, pd.DatetimeIndex):
        target_year = target_dti[0].year
        to_leap_year = target_dti[0].is_leap_year
    elif isinstance(target_dti, int):
        target_year = target_dti
        to_leap_year = calendar.isleap(target_dti)
    else:
        raise TypeError()

    if from_leap_year and not to_leap_year:
        df_to = df_original.copy()
        df_to = df_to[~((df_to.index.month == 2) & (df_to.index.day == 29))]
        index_to = pd.to_datetime(
            {
                "year": target_year,
                "month": df_to.index.month,
                "day": df_to.index.day,
                "hour": df_to.index.hour,
                "second": df_to.index.second,
                "nanosecond": df_to.index.nanosecond,
            }
        )
        df_to.index = index_to
    else:
        df_to = df_original.copy()
        index_to = pd.to_datetime(
            {
                "year": target_year,
                "month": df_to.index.month,
                "day": df_to.index.day,
                "hour": df_to.index.hour,
                "second": df_to.index.second,
                "nanosecond": df_to.index.nanosecond,
            }
        )
        df_to.index = index_to
        if (from_leap_year and to_leap_year) or (not from_leap_year and not to_leap_year):
            ...  # nothing to do
        elif not from_leap_year and to_leap_year:
            df_to_feb29 = df_to[((df_to.index.month == 2) & (df_to.index.day == 28))]
            df_to_feb29.index = df_to_feb29.index + pd.DateOffset(days=1)
            df_to = pd.concat(
                [
                    df_to[(df_to.index.month < 3)],
                    df_to_feb29,
                    df_to[(df_to.index.month >= 3)],
                ],
                axis=0,
            )
    return df_to


def dti_from_year(year: int) -> pd.DatetimeIndex:
    """Create an hourly full-year ascending datetime index from a year"""
    dti = pd.date_range(start=f"1/1/{year}", end=f"1/1/{year+1}", inclusive="left", freq="h")
    return dti


def year_from_dti(dti: pd.DatetimeIndex | pd.DataFrame | int) -> int:
    if isinstance(dti, pd.DatetimeIndex):
        return dti[0].year
    elif isinstance(dti, pd.DataFrame):
        return dti.index[0].year
    elif isinstance(dti, int):
        return dti
    else:
        raise TypeError()
