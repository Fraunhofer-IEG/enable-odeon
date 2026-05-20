from __future__ import annotations
from typing import Literal
from numbers import Number
import pandas as pd
import numpy as np
import zlib

from .base import Identified, Object, Branch

from ..processing.utils.utils import typeerror_if_not_isinstance, typeerror_if_not_isinstance_or_none


def hourly_year_dti(year: int) -> pd.DatetimeIndex:
    return pd.date_range(start=f"{year}-01-01", end=f"{year+1}-01-01", freq="h", inclusive="left")


def error_if_readonly(temporal: "Temporal"):
    if temporal._READ_ONLY:
        raise Exception("Temporal is in read-only mode")


def hdf_key_from_temporal(temporal: "Temporal") -> str:
    """
    Get a key for the given temporal that can be used to store/retrieve
    temporals for that object in a dictionary. The key is based on the
    object's ID.
    """
    if not isinstance(temporal, Temporal) or temporal.id is None:
        raise ValueError("Temporal must have an ID")

    return f"id{temporal.id}"


SERIES = 0
SHAPE = 1
FIX = 2
TOTAL = 3
TIMEINDEX = 4
PARENT = 5
MASTER = 6
TIMESERIES = 7
TIMESHAPE = 8
LENGTH = 9


class Temporal(Identified):
    """Represent time‑dependent numeric data together with multiple equivalent
    or derived representations (shape, series, total, fix) and rich metadata.

    Core concepts
    -------------
    - **total**: Float representing the annual (full-period) sum of the series.
    Units follow the semantic meaning of the owning attribute (e.g. kWh / a).
    For an hourly year this equals series.sum().
    - **fix**: Constant per‑timestep value (scalar). A fix implies the shape is
    uniform and can yield both a total (once a timeindex is known) and a series.
    Storing a fix instead of an expanded series saves memory & IO.
    - **timeindex**: A pandas.DatetimeIndex (hourly resolution) covering exactly
    one calendar year of the parent branch. Leap years have 8784 entries,
    otherwise 8760. A Temporal without a timeindex is considered non‑temporal
    (it may still hold a total or fix). When attached as an attribute to an
    object that belongs to a branch the timeindex is implicitly provided by that
    branch and must not be overridden.
    - **series**: Absolute hourly values stored with a RangeIndex (0..n-1) to
    decouple value storage from calendar alignment.
    - **timeseries**: View of the same data as ``series`` but with the branch's
    DatetimeIndex. Not stored separately; created on demand.
    - **shape**: Relative hourly profile (values summing to 1.0) stored with
    a RangeIndex. Relation: ``series == shape * total`` when both are defined.
    - **timeshape**: Shape with DatetimeIndex (analogue to timeseries).
    - **master**: Another Temporal whose shape & timeindex this instance may
    reference to avoid duplication. A client carries its own total (and
    optionally fix) but delegates profile and index to its master. Multiple
    clients can share one master.

    Availability & constraint logic
    -------------------------------
    A Temporal may *store* a subset of (series | shape | total | fix |
    timeindex) while still being able to *derive* others. Internally a
    constraint bitmask (``_constraints``) records which sources are authoritative.
    Derivation rules (simplified):

    - **series**: from stored series, or (total & shape), or (fix & timeindex),
    or (master.shape & total)
    - **shape**: from stored shape, or (series & total), or (fix & timeindex),
    or master.shape
    - **total**: from stored total, or (series.sum()), or (fix * len(timeindex))
    - **fix**: only if explicitly stored (never derived to avoid ambiguity)
    - **timeindex**: from stored (detached temporals) or from parent branch or
    from master

    Mutually exclusive / incompatible initialisation patterns are validated.
    For example you cannot supply both ``series`` and ``timeseries`` (the
    latter implies both values & timeindex) or give ``fix`` together with an
    explicit ``series``. The constructor normalises inputs into the internal
    canonical form (RangeIndex based series/shape plus optional timeindex and
    scalars) and sets constraint flags accordingly.

    Storage optimisation
    --------------------
    For storage optimization, the following attributes can be used:

    - **_STORE_SERIES**: If True, derived series (from shape+total) may be cached.
    - **_STORE_SHAPE**: If True, derived shape (from series or fix) may be cached.

    By default both are False favouring lower memory footprint at the expense
    of repeated recalculation for frequent access.

    Swapping & memory management
    ----------------------------
    swap_mode can be one of the following:

    - **loaded**: Keep in memory.
    - **swapped**: Remove immediately from memory and store in file instead;
    load transiently on next access.
    - **lazy**: Load once on demand and keep until next explicit swap.

    Only the *constraining* representation (series or shape) is swapped.
    HDF5 persistence is delegated to the project's ``FileAdapter``; each
    branch maps its temporals to a branch‑scoped HDF file via a key derived
    from the temporal's id (see ``hdf_key_from_temporal``).

    Master–client semantics
    -----------------------
    If ``master`` is set:

    - series = total * master.shape (conceptually; may be derived lazily)
    - shape = master.shape (never copied unless the link is removed)
    - timeindex = master.timeindex

    Updating a master's total does not ripple to clients. Clients keep their
    own totals; changing a client's total scales its effective series.
    Cycles and cross‑branch master/client relationships are disallowed.

    Arithmetic operations
    ---------------------
    Supported: +, -, *, /. Operations accept scalars or other Temporals.
    Operations attempt to use the most compact representation (e.g. two
    fixes => fix; fix with total+shape => new total+shape; otherwise series
    derivation). Timeindex alignment is assumed identical (same branch) when
    both sides are temporal; heterogeneous indices should be normalised by
    caller before combining (behaviour otherwise is implementation defined).

    Read‑only mode
    --------------
    ``read_only`` prevents any mutating operations (attribute setting,
    swapping, master/client changes). Attempted writes raise Exceptions.
    """

    _STORE_SHAPE: bool = False  # whether to store the shape
    # whenever it gets calculated while the series is already stored. This will
    # increase performance, precision, and memory usage. Otherwise, the relative
    # series will be recalculated every time it is accessed. Whenever the
    # shape is explicitly set by the user, this attribute has no effect.

    _STORE_SERIES: bool = False  # whether to store the series whenever it gets
    # calculated while the shape is already stored. This will increase
    # performance, precision, and memory usage. Otherwise, the series will be
    # recalculated every time it is accessed. Whenever the series is explicitly
    # set by the user, this attribute has no effect.

    _READ_ONLY: bool = False  # whether the temporal is in read-only mode. If
    # True, any modification will raise an exception

    _SWAP_MODE: Literal["lazy", "swapped", "loaded"] = "loaded"
    # Swap modes:
    # - 'loaded': Series is loaded and will stay loaded until swapped manually
    # - 'swapped': Series is not loaded. It will be loaded when a getter is
    #    called, and not stored
    # - 'lazy': Series is not loaded. It will be loaded when a getter is
    #    called, and stored until swapped again

    _swapped: bool = False  # whether the series has been swapped out of memory.
    # this can be False even if the swap mode is 'swapped' or 'lazy', if the
    # series was never loaded, or if the series only has a fix or total value so
    # that swapping is not necessary

    _n_accesses: int = 0  # number of accesses to the series. Will be increased
    # whenever the series is accessed

    _series_none: bool = True  # whether the series is None. This attribute
    # is intended to prevent loading the series from HDF just to check whether
    # it's present

    __series: pd.Series | None = None  # with RangeIndex. full
    # series. only stored if explicitly set, otherwise None

    __shape: pd.Series | None = None  # The shape of the seires. If given,
    # sum must be = 1

    _total: Number | None = None
    _fix: Number | None = None
    _timeindex: pd.DatetimeIndex | None = None
    _parent: Object | None = None
    _master: Temporal | None = None
    _clients: list["Temporal"]

    # analytical statistics that will be loaded lazily:
    _min: Number | None = None
    _max: Number | None = None
    _mean: Number | None = None

    _constraints: dict[str, bool] = None

    def __init__(
        self,
        *,
        timeseries: pd.Series | None = None,
        series: pd.Series | None = None,
        timeindex: pd.DatetimeIndex | None = None,
        shape: pd.Series | None = None,
        total: Number | None = None,
        fix: Number | None = None,
        master: Temporal | None = None,
        read_only: bool = False,
    ) -> None:
        """Initialize a Temporal.

        Parameters
        ----------
        timeseries : pandas.Series, optional
            Absolute values already indexed by a DatetimeIndex (one year). Not
            possible in combination with series/shape/fix/master/timeindex.
        series : pandas.Series, optional
            Absolute values with a RangeIndex (no calendar). Not possible in
            combination with timeseries/shape/fix/master.
        timeindex : pandas.DatetimeIndex, optional
            Explicit calendar (one full year) for detached temporals. Not
            possible in combination with master.
        shape : pandas.Series, optional
            Relative profile (RangeIndex, sums to 1). Not with possible in
            combination with series/timeseries/fix/master.
        total : Number, optional
            Annual sum. Not possible in combination with fix
        fix : Number, optional
            Constant per-step value. Not possible in combination with
            series/timeseries/shape/total/master.
        master : Temporal, optional
            Reference whose shape & timeindex this instance will reuse. Will
            create a master-client relation. Not possible in combination with
            series/timeseries/shape/fix/timeindex.
        read_only : bool, default False
            If True, prohibits subsequent mutation (assigning new data, swapping).
        """
        # we don't need to have an id from the start as a Temporal may be
        # created only temporally. An id will be set when setting parent to an
        # Object, instead:
        super().__init__(set_id=False)

        self._constraints = {
            SERIES: False,
            SHAPE: False,
            TOTAL: False,
            FIX: False,
            TIMEINDEX: False,
            PARENT: False,
            MASTER: False,
        }

        if series is not None:
            if timeseries is not None:
                raise ValueError("You can't specify series and timeseries at the same time")
            if shape is not None:
                raise ValueError("You can't specify series and shape at the same time")
            if fix is not None:
                raise ValueError("You can't specify series and fix at the same time")
            if master is not None:
                raise ValueError("You can't specify series and master at the same time")

        if timeseries is not None:
            # series already checked
            if timeindex is not None:
                raise ValueError("You can't specify timeseries and timeindex at the same time")
            if shape is not None:
                raise ValueError("You can't specify timeseries and shape at the same time")
            if fix is not None:
                raise ValueError("You can't specify timeseries and fix at the same time")
            if master is not None:
                raise ValueError("You can't specify timeseries and master at the same time")

        if timeindex is not None:
            # timeseries already checked
            if master is not None:
                raise ValueError("You can't specify timeindex and master at the same time")

        if shape is not None:
            # series, timeseries already checked
            if fix is not None:
                raise ValueError("You can't specify shape and fix at the same time")
            if master is not None:
                raise ValueError("You can't specify shape and master at the same time")

        if total is not None:
            # series, timeseries already checked
            if fix is not None:
                raise ValueError("You can't specify total and fix at the same time")

        if fix is not None:
            # series, timeseries, shape already checked
            if master is not None:
                raise ValueError("You can't specify fix and master at the same time")

        self._clients = []

        if series is not None:
            self.series = series
        if timeseries is not None:
            self.timeseries = timeseries
        if timeindex is not None:
            self.timeindex = timeindex
        if shape is not None:
            self.shape = shape
        if total is not None:
            self.total = total
        if fix is not None:
            self.fix = fix
        if master is not None:
            typeerror_if_not_isinstance(master, Temporal)
            master.add_client(self)

        self._READ_ONLY = read_only

    # --------------------------------------------------------------------------
    # protected functions for main logic
    # --------------------------------------------------------------------------

    def _is_constrained_by(
        self,
        constraint: int,
    ) -> bool:
        """Return whether the temporal is constrained by the given attribute."""
        assert constraint in [TOTAL, SHAPE, SERIES, FIX, TIMEINDEX, PARENT, MASTER]
        return self._constraints[constraint]

    def _is_available(
        self,
        attribute: int,
    ) -> bool:
        """Return whether the given attribute can be calculated or accessed."""

        assert attribute in [
            SERIES,
            TIMESERIES,
            SHAPE,
            TIMESHAPE,
            TOTAL,
            FIX,
            TIMEINDEX,
            PARENT,
            MASTER,
        ]

        # series can be calculated from
        # - series
        # - fix and timeindex
        # - total and shape
        # - master and total
        if attribute == SERIES:
            if self._is_constrained_by(SERIES):
                return True
            elif self._is_constrained_by(FIX) and self._is_available(TIMEINDEX):
                return True
            elif self._is_constrained_by(SHAPE) and self._is_constrained_by(TOTAL):
                return True
            elif self._is_constrained_by(MASTER) and self._is_constrained_by(TOTAL):
                return True
            else:
                return False

        # shape can be calculated from
        # - shape
        # - fix and timeindex
        # - series
        # - master
        elif attribute == SHAPE:
            if self._is_constrained_by(SHAPE):
                return True
            elif self._is_constrained_by(FIX) and self._is_available(TIMEINDEX):
                return True
            elif self._is_constrained_by(SERIES):
                return True
            elif self._is_constrained_by(MASTER):
                return True
            else:
                return False

        # total can be calculated from
        # - total
        # - fix and timeindex
        # - series
        elif attribute == TOTAL:
            if self._is_constrained_by(TOTAL):
                return True
            elif self._is_constrained_by(FIX) and self._is_available(TIMEINDEX):
                return True
            elif self._is_constrained_by(SERIES):
                return True
            else:
                return False

        # fix can be calculated from
        # - fix
        elif attribute == FIX:
            if self._is_constrained_by(FIX):
                return True
            else:
                return False

        # timeseries can be calculated from
        # - timeindex and series
        elif attribute == TIMESERIES:
            if self._is_available(TIMEINDEX) and self._is_available(SERIES):
                return True
            else:
                return False

        # relative_timeseries can be calculated from
        # - timeindex and shape
        elif attribute == TIMESHAPE:
            if self._is_available(TIMEINDEX) and self._is_available(SHAPE):
                return True
            else:
                return False

        # timeindex can be calculated from
        # - timeindex
        # - parent, if it has a timeindex
        # - master
        elif attribute == TIMEINDEX:
            if self._is_constrained_by(TIMEINDEX):
                return True
            elif self._parent is not None and self._parent.timeindex is not None:
                return True
            elif self._is_constrained_by(MASTER) and self._master._is_available(TIMEINDEX):
                return True
            else:
                return False

        elif attribute == PARENT:
            return self._parent is not None

        elif attribute == MASTER:
            return self._master is not None

    def _get(
        self,
        attribute: int,
        not_available: Literal["none", "raise"] = "raise",
    ):
        """
        Get the value of an attribute that will be calculated from the
        given constraints.
        """
        assert attribute in [
            SERIES,
            TIMESERIES,
            SHAPE,
            TIMESHAPE,
            TIMEINDEX,
            PARENT,
            MASTER,
            TOTAL,
            FIX,
            LENGTH,
        ]

        if not_available not in ["none", "raise"]:
            raise ValueError("not_available must be 'none' or 'raise'")

        # series can be calculated from
        # - series
        # - fix and timeindex
        # - total and shape
        # - master and total
        if attribute == SERIES:

            new_series = None

            if self._is_constrained_by(SERIES):
                # convert if it's categorical:
                series = self._get_series()
                if isinstance(series.dtype, pd.CategoricalDtype):
                    return pd.to_numeric(series, errors="coerce")
                else:
                    return series.copy()

            elif self._is_constrained_by(FIX) and self._is_available(TIMEINDEX):
                ri = pd.RangeIndex(len(self.timeindex))
                new_series = pd.Series(self._fix, index=ri)

            elif self._is_constrained_by(SHAPE) and self._is_constrained_by(TOTAL):
                new_series = self._get_shape() * self._total

            elif self._is_constrained_by(MASTER) and self._is_available(TOTAL):
                return self._master.shape * self._total  # TODO make sure that master always stores shape

            elif not_available == "raise":
                raise ValueError(f"Attribute '{attribute}' is not available")

            if self._STORE_SERIES and new_series is not None:
                self._set_series(new_series)

            if new_series is not None:
                # might be compressed by using categorical dtype, so convert:
                if isinstance(new_series.dtype, pd.CategoricalDtype):
                    new_series = pd.to_numeric(new_series, errors="coerce")
            return new_series

        # shape can be calculated from
        # - shape
        # - fix and timeindex
        # - series
        # - master
        elif attribute == SHAPE:

            new_shape = None

            if self._is_constrained_by(SHAPE):
                return self._get_shape().copy()

            elif self._is_constrained_by(FIX) and self._is_available(TIMEINDEX):
                ri = pd.RangeIndex(len(self.timeindex))
                new_shape = pd.Series(1 / len(ri), index=ri)

            elif self._is_constrained_by(SERIES):
                series = self._get_series()
                new_shape = series / series.sum()

            elif self._is_constrained_by(MASTER):
                return self._master.shape.copy()  # TODO make sure that master always stores shape

            elif not_available == "raise":
                raise ValueError(f"Attribute '{attribute}' is not available")

            if self._STORE_SHAPE and new_shape is not None:
                if self._SWAP_MODE in ["lazy", "swapped"]:
                    raise Exception("Can't set shape when swap mode is 'lazy' or 'swapped'")
                self.__shape = new_shape

            return new_shape

        # total can be calculated from
        # - total
        # - fix and timeindex
        # - series
        elif attribute == TOTAL:
            if self._is_constrained_by(TOTAL):
                return self._total
            elif self._is_constrained_by(FIX) and self._is_available(TIMEINDEX):
                return self._fix * len(self.timeindex)
            elif self._is_constrained_by(SERIES):
                return self._get_series().sum()
            elif not_available == "raise":
                raise ValueError(f"Attribute '{attribute}' is not available")
            else:
                return None

        # fix can be calculated from
        # - fix
        elif attribute == FIX:
            if self._is_constrained_by(FIX):
                return self._fix
            elif not_available == "raise":
                raise ValueError(f"Attribute '{attribute}' is not available")
            else:
                return None

        # timeindex can be calculated from
        # - timeindex
        # - parent, if it has a timeindex
        # - master
        elif attribute == TIMEINDEX:
            if self._is_constrained_by(TIMEINDEX):
                return self._timeindex.copy()
            elif self._parent is not None and self._parent.timeindex is not None:
                return self._parent.timeindex.copy()
            elif self._is_constrained_by(MASTER):
                return self._master.timeindex.copy()
            elif not_available == "raise":
                raise ValueError(f"Attribute '{attribute}' is not available")
            else:
                return None

        elif attribute == PARENT:
            if self._parent is not None:
                return self._parent
            elif not_available == "raise":
                raise ValueError(f"Attribute '{attribute}' is not available")
            else:
                return None

        elif attribute == MASTER:
            if self._master is not None:
                return self._master
            elif not_available == "raise":
                raise ValueError(f"Attribute '{attribute}' is not available")
            else:
                return None

        # timeseries can be calculated from
        # - timeindex and series
        elif attribute == TIMESERIES:
            if self._is_available(TIMEINDEX) and self._is_available(SERIES):
                series = self._get(SERIES)
                return self._series_to_timeseries(series)
            elif not_available == "raise":
                raise ValueError(f"Attribute '{attribute}' is not available")
            else:
                return None

        # relative_timeseries can be calculated from
        # - timeindex and shape
        elif attribute == TIMESHAPE:
            if self._is_available(TIMEINDEX) and self._is_available(SHAPE):
                shape = self._get(SHAPE)
                return self._series_to_timeseries(shape)
            elif not_available == "raise":
                raise ValueError(f"Attribute '{attribute}' is not available")
            else:
                return None

        elif attribute == "length":
            if self._is_available(TIMEINDEX):
                return len(self.timeindex)
            elif self._is_available(SERIES):
                return len(self._get_series())
            elif not_available == "raise":
                raise ValueError(f"Attribute '{attribute}' is not available")
            else:
                return None

    def _set(
        self,
        attribute: int,
        value: float | pd.Series | pd.DatetimeIndex | None,
    ):
        """
        Set the value of an attribute and update constraints accordingly.

        Setting an attribute to None will remove stored data for that attribute
        and remove the constraint. However, the same attribute can still be
        available afterwards if it can be calculated from other attributes (i.e.
        if the temporal wasn't constrained by that attribute before).
        """

        def check_rangeindex(series: pd.Series):
            if not isinstance(series.index, pd.RangeIndex):
                msg = "A Temporal's series needs to have a RangeIndex. Did you mean to set timeseries instead?"
                raise TypeError(msg)

        def check_length(series: pd.Series):
            if len(series.index) != len(self.timeindex):
                raise ValueError("Length of series does not match length of timeindex")

        def check_numeric(series: pd.Series):
            if not pd.api.types.is_numeric_dtype(series):
                # check whether it's categorical:
                if pd.api.types.is_categorical_dtype(series):
                    # check whether all categories are numeric:
                    for cat in series.cat.categories:
                        if not isinstance(cat, Number):
                            raise TypeError("All series values must be numbers")
                else:
                    raise TypeError("All series values must be numbers")

        assert attribute in [SERIES, SHAPE, TOTAL, FIX, TIMEINDEX, TIMESERIES, TIMESHAPE]
        error_if_readonly(self)

        if attribute == SERIES:

            if value is None:

                self._set_constraints(series=False)
                self._set_series(None)  # might remove data from HDF
                # reset min, max, mean – might still be valid, but safer to
                # remove – can be calculated again from series on-demand:
                self._min = None
                self._max = None
                self._mean = None

            elif value is not None:

                # checks:
                # - value must be a pd.Series
                # - index must me a rangeindex
                # - length must match any present timeindex
                # - all values of the series must be numbers
                typeerror_if_not_isinstance(value, pd.Series)
                check_rangeindex(value)
                if self.has_timeindex:
                    check_length(value)
                check_numeric(value)

                if self.has_master:
                    self.remove_from_master()

                series = value.reset_index(drop=True)

                # write the series and reset total, fix, shape:
                self._set_constraints(series=True, shape=False, total=False, fix=False)
                self._set_shape(None)  # might remove data from HDF
                # series may be categorical, so convert to float:
                series = series.astype("float")
                self._set_series(series)  # might write data to HDF
                self._total = series.dropna().sum()
                self._min = series.min()
                self._max = series.max()
                self._mean = series.mean()
                self._fix = None

        elif attribute == SHAPE:

            if value is None:

                self._set_constraints(shape=False)
                self._set_shape(None)  # might remove data from HDF
                # reset min, max, mean – might still be valid, but safer to
                # remove – can be calculated again from series on-demand:
                self._min = None
                self._max = None
                self._mean = None

            elif value is not None:

                # checks:
                # - value must be a pd.Series
                # - index must me a rangeindex
                # - length must match any present timeindex
                # - all values of the series must be numbers
                typeerror_if_not_isinstance(value, pd.Series)
                check_rangeindex(value)
                if self.has_timeindex:
                    check_length(value)
                check_numeric(value)

                if self.has_master:
                    self.remove_from_master()

                # normalize the shape:
                shape = value.reset_index(drop=True)
                shape = shape / shape.sum()

                # if total is not yet a constraint but can be calculated, it will
                # become a constraint now:
                if not self._is_constrained_by(TOTAL) and self._is_available(TOTAL):
                    total = self._get(TOTAL)
                    assert total is not None
                    self._set_constraints(total=True)
                    self._total = total

                # if total is known, we can calculate min, max, mean:
                if self._is_available(TOTAL):
                    total = self._total
                    self._min = shape.min() * total
                    self._max = shape.max() * total
                    self._mean = shape.mean() * total

                # write the shape and reset fix and series:
                self._set_constraints(shape=True, series=False, fix=False)
                self._set_series(None)  # might remove data from HDF
                self._set_shape(shape)  # might write data to HDF
                self._fix = None

        elif attribute == TOTAL:

            if value is None:

                self._set_constraints(total=False)
                self._total = None

            elif value is not None:

                # checks:
                # - value must be a number
                typeerror_if_not_isinstance(value, Number)

                # write total, remove fix, min, mean, max:
                self._set_constraints(total=True, fix=False)
                self._total = value
                self._fix = None
                self._min = None
                self._max = None
                self._mean = None

                # if the temporal is constrained by the series, calculate the
                # shape from it and remove the series:
                if self._is_constrained_by(SERIES):
                    series = self._get_series()
                    shape = series / series.sum()
                    self._set_constraints(series=False, shape=True)
                    self._set_shape(shape)
                    self._set_series(None)

        elif attribute == FIX:

            if value is None:

                self._set_constraints(fix=False)
                self._fix = None
                # reset min, max, mean – might still be valid, but safer to
                # remove – can be calculated again from series on-demand:
                self._min = None
                self._max = None
                self._mean = None

            elif value is not None:

                # checks:
                # - value must be a number
                typeerror_if_not_isinstance(value, Number)

                if self.has_master:
                    self.remove_from_master()

                # write fix, min, max, mean, and remove total, series, shape:
                self._set_constraints(fix=True, total=False, series=False, shape=False)
                self._set_series(None)  # might remove data from HDF
                self._set_shape(None)  # might remove data from HDF
                self._fix = value
                self._min = value
                self._max = value
                self._mean = value
                self._total = None

        elif attribute == TIMEINDEX:

            if value is None:

                self._set_constraints(timeindex=False)
                self._timeindex = None

            elif value is not None:

                # checks:
                # - value must be a pd.DatetimeIndex
                # - temporal must not have clients
                # - temporal must hot have a parent
                # - temporal must hot have a master
                # - length must match any present series or shape
                if not isinstance(value, pd.DatetimeIndex):
                    raise TypeError("Expected a pandas Datetimeindex")
                if len(self._clients) > 0:
                    raise Exception("Can't set timeindex when clients are attached")
                if self.has_master:
                    raise Exception("Can't set timeindex when attached to a master")
                if self._parent is not None:
                    raise Exception("Can't set timeindex when parent is set")
                if self._is_constrained_by(SERIES):
                    if len(value) != len(self._get_series()):
                        raise Exception("Can't set timeindex: Series with different length already set")
                if self._is_constrained_by(SHAPE):
                    if len(value) != len(self._get_shape()):
                        raise Exception("Can't set timeindex: Relative seires with different length already set")

                # write timeindex and remove parent:
                self._set_constraints(timeindex=True)
                self._timeindex = value.copy()

        elif attribute == TIMESERIES:

            if value is None:

                self._set_constraints(series=False, timeindex=False)
                self._set_series(None)  # might remove data from HDF
                self._timeindex = None

            elif value is not None:

                index = value.index
                series = value.reset_index(drop=True)

                if self.has_timeindex and value.index.equals(self.timeindex):
                    # if the temporal already has a timeindex and the passed
                    # timeseries has the same index, we can just set the series:
                    self._set(SERIES, series)  # will do the checks and constraints

                else:
                    # remove the current shape and series to avoid length conflicts -
                    # this may also affect files and constraints:
                    self._set(SERIES, None)
                    self._set(SHAPE, None)
                    # set the new values. Checks and constraint setting will
                    # be done in the individual setters:
                    self._set(TIMEINDEX, index)
                    self._set(SERIES, series)

        elif attribute == TIMESHAPE:

            if value is None:

                self._set_constraints(shape=False, timeindex=False)
                self._set_shape(None)  # might remove data from HDF
                self._timeindex = None

            elif value is not None:

                index = value.index.copy()
                shape = value.reset_index(drop=True)

                if self.has_timeindex and value.index.equals(self.timeindex):
                    # if the temporal already has a timeindex and the passed
                    # timeseries has the same index, we can just set the shape:
                    self._set(SHAPE, shape)  # will do the checks and constraints

                else:
                    # remove the current shape and series to avoid length conflicts -
                    # this may also affect files and constraints:
                    self._set(SERIES, None)
                    self._set(SHAPE, None)
                    # set the new values. Checks and constraint setting will
                    # be done in the individual setters:
                    self._set(TIMEINDEX, index)
                    self._set(SHAPE, shape)

    def _set_constraints(
        self,
        total: bool | None = None,
        shape: bool | None = None,
        series: bool | None = None,
        fix: bool | None = None,
        timeindex: bool | None = None,
        master: bool | None = None,
        parent: bool | None = None,
    ):
        """
        Mark that the temporal is constrained by the given attributes.
        None means "don't change".
        """
        if total is not None:
            self._constraints[TOTAL] = total
        if shape is not None:
            self._constraints[SHAPE] = shape
        if series is not None:
            self._constraints[SERIES] = series
        if fix is not None:
            self._constraints[FIX] = fix
        if timeindex is not None:
            self._constraints[TIMEINDEX] = timeindex
        if master is not None:
            self._constraints[MASTER] = master
        if parent is not None:
            self._constraints[PARENT] = parent

    def _get_series(self) -> pd.Series | None:
        """
        Get the internal series from self or load it from file, according to
        swap mode. This may store the series in memory, according to swap mode.

        If the temporal is not constrained by the series, this will return None.
        """

        if not self._is_constrained_by(SERIES):
            # if the temporal is not constrained by the series, it may still be
            # available as cache. We won't interact with the HDF file in this
            # case:
            if self._STORE_SERIES:
                return self.__series
            return None

        else:
            self._n_accesses += 1
            # If the temporal is constrained by the series, it means
            # that the shape is unconstrained (i.e. not explicitly set).
            # If there's something in the HDF file, it will be the series.
            assert not self._is_constrained_by(SHAPE)

            if self._SWAP_MODE == "loaded":
                return self.__series
            elif self._SWAP_MODE == "lazy":
                if self._swapped:
                    assert self.__series is None
                    self.__series = self._series_from_hdf()
                return self.__series
            elif self._SWAP_MODE == "swapped":
                return self._series_from_hdf()

    def _get_shape(self) -> pd.Series | None:
        """
        Get the shape from self or load it from file, according to
        swap mode. This may store the series in memory, according to swap mode.
        """
        if not self._is_constrained_by(SHAPE):
            # if the temporal is not constrained by the shape, it may
            # still be available as cache. We won't interact with the HDF file
            # in this case:
            if self._STORE_SHAPE:
                return self.__shape
            return None

        else:
            self._n_accesses += 1
            # if the temporal is constrained by the shape, it means
            # that the series is unconstrained (i.e. not explicitly set).
            # If there's something in the HDF file, it will be the relative
            # series.
            assert not self._is_constrained_by(SERIES)

            if self._SWAP_MODE == "loaded":
                return self.__shape
            elif self._SWAP_MODE == "lazy":
                if self._swapped:
                    assert self.__shape is None
                    self.__shape = self._series_from_hdf()
                return self.__shape
            elif self._SWAP_MODE == "swapped":
                return self._series_from_hdf()

    def _set_series(self, series: pd.Series | None):
        """
        Set the internal series to `series` and write to file or remove from it
        (if necessary). This won't affect other attributes of the temporal.
        Especially the constraints won't be changed.

        If `series` is not None, it's required that the temporal is constrained
        by the series. If `series` is None`, it's required that the temporal is
        not constrained by the series. This means that constraints have to be
        updated before setting the actual series.
        """
        typeerror_if_not_isinstance_or_none(series, pd.Series)
        error_if_readonly(self)

        if series is None:

            # check that the constraint has been removed beforehand:
            assert not self._is_constrained_by(SERIES)

            # remove the series from hdf if necessary:
            if self._SWAP_MODE in ["lazy", "swapped"]:
                self._remove_series_from_hdf()
            self.__series = None

        else:

            # check that the constraint has been set beforehand:
            assert self._is_constrained_by(SERIES)

            assert isinstance(series.index, pd.RangeIndex)

            if self._SWAP_MODE == "loaded":
                self.__series = series.copy()
            elif self._SWAP_MODE == "lazy":
                self.__series = series.copy()
            elif self._SWAP_MODE == "swapped":
                self._series_to_hdf(series=series)
                self.__series = None

    def _set_shape(self, shape: pd.Series | None):
        """
        Set the internal shape to `shape` and write to file
        or remove from it (if necessary). This won't affect other attributes of
        the temporal. Especially the constraints won't be changed.

        If `shape` is not None, it's required that the temporal is
        constrained by the shape. If `shape is None`, it's
        required that the temporal is not constrained by the shape.
        This means that constraints have to be updated before setting the actual
        shape.
        """
        typeerror_if_not_isinstance_or_none(shape, pd.Series)
        error_if_readonly(self)

        if shape is None:

            # check that the constraint has been removed beforehand:
            assert not self._is_constrained_by(SHAPE)

            # remove the shape from hdf if necessary:
            if self._SWAP_MODE in ["lazy", "swapped"]:
                self._remove_series_from_hdf()
            self.__shape = None

        else:

            # check that the constraint has been set beforehand:
            assert self._is_constrained_by(SHAPE)

            assert isinstance(shape.index, pd.RangeIndex)

            if self._SWAP_MODE == "loaded":
                self.__shape = shape.copy()
            elif self._SWAP_MODE == "lazy":
                self.__shape = shape.copy()
            elif self._SWAP_MODE == "swapped":
                self._series_to_hdf(series=shape)
                self.__shape = None

    # --------------------------------------------------------------------------
    # Setters and getters for main attributes
    # --------------------------------------------------------------------------

    @property
    def series(self) -> pd.Series | None:
        """
        The absolute series with RangeIndex. When queried, this will return a
        copy.
        """
        return self._get(SERIES, not_available="none")

    @series.setter
    def series(self, series: pd.Series) -> None:
        """
        Setting the series will
        - update the total part,
        - update the relative part,
        - clear fix.

        Setting the series will detach the `Temporal` from its master, if
        present.
        """
        self._set(SERIES, series)

    @property
    def shape(self) -> pd.Series | None:
        """
        The shape with RangeIndex. Values will sum to 1. When queried,
        this will return a copy.
        """
        return self._get(SHAPE, not_available="none")

    @shape.setter
    def shape(self, shape: pd.Series):
        """
        Setting the shape will
        - set the relative part
        - clear fix

        The input shape can sum up to any value and will be rescaled
        when written to the Temporal.
        """
        self._set(SHAPE, shape)

    @property
    def total(self) -> float | None:
        """
        The total, i.e. the sum over the whole described period.
        """
        return self._get(TOTAL, not_available="none")

    @total.setter
    def total(self, total: Number | None) -> None:
        """
        Setting a not-none total will
        - update the total part,
        - clear fix.

        Setting a None total will
        - clear the total part,
        - clear the explicit series,
        - keep the relative part of the current series, if calculable
        - note that total might still be calculable if fix and timeseries weren't None.
        """
        self._set(TOTAL, total)

    @property
    def fix(self) -> float | None:
        """
        The fixed value of the Temporal, i.e. the constant value valid for any
        timestep of the described period.
        """
        return self._get(FIX, not_available="none")

    @fix.setter
    def fix(self, fix: Number | None) -> None:
        """
        Setting a not-none value will
        - update the relative part
        - update the total
        - set the fix value.

        Setting a value of None will
        - clear the fix value
        """
        self._set(FIX, fix)

    @property
    def timeindex(self) -> pd.DatetimeIndex | None:
        """
        The timeindex of type DatetimeIndex. When queried, this will return a
        copy.
        """
        return self._get(TIMEINDEX, not_available="none")

    @timeindex.setter
    def timeindex(self, timeindex: pd.DatetimeIndex | None):
        """
        Setting the timeindex will
        - update the index
        - clear the relative part if lengths differ.
        """
        self._set(TIMEINDEX, timeindex)

    @property
    def timeseries(self) -> pd.Series | None:
        """
        The absolute series with DatetimeIndex. When queried, this will return
        a copy.
        """
        return self._get(TIMESERIES, not_available="none")

    @timeseries.setter
    def timeseries(self, timeseries: pd.Series) -> None:
        """
        Setting the timeseries will
        - set the total part,
        - update the relative part,
        - clear fix,
        - update the index.

        Setting the timeseries is not possible
        - if a series of different length is set.

        Setting a timeseries with differing index is impossible if clients are
        attached. Setting the timeseries will detach the `Temporal` from
        its Master, if present.
        """
        self._set(TIMESERIES, timeseries)

    @property
    def timeshape(self) -> pd.Series | None:
        """
        The shape with DatetimeIndex. Values will sum to 1. When
        queried, this will return a copy.
        """
        return self._get(TIMESHAPE, not_available="none")

    @timeshape.setter
    def timeshape(self, relative_timeseries: pd.Series):
        """
        Setting the relative timeseries will
        - set the relative part,
        - clear fix,
        - update the index.

        The input relative timeseries can sum up to any value and will be
        rescaled when written to the Temporal.
        """
        self._set(TIMESHAPE, relative_timeseries)

    # --------------------------------------------------------------------------
    # Additional properties
    # --------------------------------------------------------------------------

    @property
    def rangeindex(self) -> pd.RangeIndex | None:
        """
        The index of type RangeIndex. When queried, this will return a copy.
        """
        if self.has_timeindex:
            return pd.RangeIndex(len(self.timeindex))
        elif self._is_available(SERIES):
            return self.series.index.copy()
        elif self._is_available(SHAPE):
            return self.shape.index.copy()

    @property
    def value(self) -> float | pd.Series | None:
        """
        The fixed value if present, else the series (with RangeIndex), else
        None. Useful for performant computations together with (other) pd.Series
        """
        if self._is_available(FIX):
            return self._get(FIX)
        elif self._is_available(SERIES):
            return self._get(SERIES)
        else:
            return None

    @property
    def timevalue(self) -> float | pd.Series | None:
        """
        The fixed value if present, else the series (with DatetimeIndex), else
        None. Useful for performant computations together with (other) pd.Series
        """
        if self._is_available(FIX):
            return self._get(FIX)
        elif self._is_available(TIMESERIES):
            return self._get(TIMESERIES)
        else:
            return None

    @property
    def length(self) -> int | None:
        """
        The length of the Temporal. This equals the length of
        - its timeindex, if present, or
        - its series or shape, if present
        If none of them are given, None will be returned.
        """
        return self._get(LENGTH, not_available="none")

    @property
    def has_series(self) -> bool:
        """
        Return whether the Temporal has a series, either stored directly or
        calculable from index and total or fix.
        """
        return self._is_available(SERIES)

    @property
    def has_shape(self) -> bool:
        """
        Return whether the shape is available (either explicitly as a constraint
        or implicitly). Equivalent to `temporal.shape is not None`, but more
        performant.
        """
        return self._is_available(SHAPE)

    @property
    def has_total(self) -> bool:
        """
        Return whether the total is available (either explicilty as a constraint
        or implicitly). Equivalent to `temporal.total is not None`, but more
        performant.
        """
        return self._is_available(TOTAL)

    @property
    def has_fix(self) -> bool:
        """
        Return whether the fix is available. Equivalent to `temporal.fix is not
        None`.
        """
        return self._is_available(FIX)

    @property
    def has_timeindex(self) -> bool:
        """
        Return whether the Temporal has an index, either stored locally or
        inherited from the parent object's timeindex.
        """
        return self._is_available(TIMEINDEX)

    @property
    def has_timeseries(self) -> bool:
        """
        Return whether the Temporal has a timeseries, either stored locally or
        inherited from the parent object's timeseries. Equivalent to
        `temporal.timeseries is not None`, but more performant.
        """
        return self._is_available(TIMESERIES)

    @property
    def has_timeshape(self) -> bool:
        """
        Return whether the Temporal has a timeshape, either stored locally or
        inherited from the parent object's timeshape. Equivalent to
        `temporal.timeshape is not None`, but more performant.
        """
        return self._is_available(TIMESHAPE)

    @property
    def is_empty(self) -> bool:
        """
        A temporal is considered empty if none of the following are available:
        - relative part
        - total part
        - explicit timeindex
        - fix

        Especially, having a parent doesn't prevent a temporal from being
        considered as empty.
        """
        return not (
            self._is_available(SHAPE)
            or self._is_available(SERIES)
            or self._is_available(TOTAL)
            or self._is_available(FIX)
            or self._timeindex is not None  # don't test for _is_available because could stem from parent
        )

    @property
    def is_constant(self) -> bool:
        """
        Return whether the series is constant (by analyzing the values). This
        would either be the case
        - if `fix` is set (regardless of whether an explicit or implicit
        timeindex is present),
        - or if the series is a series of constant values.
        """
        if self._is_available(FIX):
            return True
        elif not self._is_available(SHAPE):
            msg = "Can't determine whether the temporal is constant"
            raise Exception(msg)
        else:
            series = self._get_shape()
            if series is None:
                series = self._get_series()
            return (series.iloc[0] == series).all(0)

    @property
    def is_temporal(self) -> bool:
        """
        Whether the Temporal is temporally resolvable, i.e. timesteps can be
        resolved (even if the timeindex is unknown).
        """
        return self._is_available(SERIES)

    # --------------------------------------------------------------------------
    # Master-client related functions and properties
    # --------------------------------------------------------------------------

    @property
    def master(self) -> Temporal | None:
        return self._master

    @master.setter
    def master(self, master: Temporal | None) -> None:
        error_if_readonly(self)
        if master is not None:
            self.add_to_master(master)
        else:
            self.remove_from_master()

    @property
    def masters_recursive(self) -> list[Temporal]:
        """
        This Temporal's master, its respective master and so on.
        """
        l = [self._master, *self._master.masters_recursive] if self.has_master else []
        return [l for l in l if l is not None]

    @property
    def clients(self) -> list[Temporal]:
        return self._clients.copy()

    @property
    def clients_recursive(self) -> list[Temporal]:
        """
        This Temporal's clients, their respective clients and so on.
        """
        ret = self._clients
        for c in self._clients:
            ret += c.clients_recursive
        return ret

    @property
    def has_master(self) -> bool:
        return self._master is not None

    @property
    def has_clients(self) -> bool:
        return len(self._clients) > 0

    def add_client(self, client: Temporal) -> None:
        """
        Adding a temporal to a master will
        - link the client's timeindex to its master's
        - link the client's relative part to its master's
        - keep the client's total
        - leave the master unchanged
        """
        error_if_readonly(self)
        typeerror_if_not_isinstance(client, Temporal)
        if client in self.masters_recursive:
            raise Exception("Circular relationship!")
        if client.parent is not None and self.parent is not None and client.branch is not self.branch:
            raise Exception("Can't add a client with a parent from another branch")
        if not self.has_timeindex:
            raise Exception("Can't add a client to a non-temporal Temporal")
        self._clients.append(client)
        client._add_to_master(self)

    def remove_client(self, client: Temporal) -> None:
        """
        Removing a client from its master will
        - copy the master's timeindex to the client
        - copy the master's relative part to the client
        - keep the client's total
        - leave the master unchanged
        """
        error_if_readonly(self)
        if client not in self._clients:
            raise ValueError()
        client.remove_from_master()

    def add_to_master(self, master: Temporal) -> None:
        """
        Adding a timeseries to a master will
        - link the client's timeindex to its master's
        - link the client's relative part to its master's
        - keep the client's total
        - leave the master unchanged
        """
        error_if_readonly(self)
        typeerror_if_not_isinstance(master, Temporal)
        if master.parent is not None and self.parent is not None and master.branch is not self.branch:
            raise Exception("Can't set master with a parent from another branch")
        if not master.is_temporal:
            raise Exception("Can't add a client to a non-temporal Temporal")
        if self.master is not None:
            self.remove_from_master()
        master.add_client(self)

    def remove_from_master(self) -> None:
        """
        Removing a client from its master will
        - copy the master's index to the client
        - copy the master's relative part to the client
        - keep the client's total
        - leave the master unchanged
        """
        error_if_readonly(self)
        if self.has_master:
            timeseries = self.timeseries.copy()
            self._master._remove_client(self)
            self._master = None
            self._set_constraints(master=False)
            self.timeseries = timeseries
        else:
            raise Exception()

    def create_client(self, total: Number = None, factor: Number = None) -> Temporal:
        """
        Create a client that will either have a total of `total`, or of
        `factor` times this Temporal's total.
        """
        error_if_readonly(self)
        if total is not None:
            if factor is not None:
                raise Exception("You can't pass total and factor at the same time")
            total = float(total)
        elif factor is not None:
            if self.total is None:
                raise Exception()
            total = self.total * factor
        return Temporal(master=self, total=total)

    def _add_to_master(self, master: Temporal) -> None:
        """
        Don't call this method manually. Use `add_to_master` instead.
        """
        error_if_readonly(self)
        assert master is not self
        if self.has_master:
            self.remove_from_master()
        self._set_constraints(master=True, shape=False, series=False)
        self._master = master
        self._set_shape(None)
        self._set_series(None)

    def _remove_client(self, timeseries: Temporal) -> None:
        """
        Don't call this method manually. Use `remove_client` instead.
        """
        error_if_readonly(self)
        if timeseries not in self._clients:
            raise ValueError()
        self._clients.remove(timeseries)

    # --------------------------------------------------------------------------
    # Hierarchical related
    # --------------------------------------------------------------------------

    @property
    def parent(self) -> Object | None:
        return self._parent

    def _set_parent(self, parent: Object | None) -> None:
        """
        Setting the parent will
        - update the parent
        - remove any explicit timeindex
        - set an id (if not-none parent)

        This will not write any attribute in the parent to be set, or in the
        former parent (if available).
        """
        typeerror_if_not_isinstance_or_none(parent, Object)
        error_if_readonly(self)

        # check that the reverse link in the parent has been set or removed beforehand:

        # removing parent to None:
        if parent is None and self._parent is not None and self in self._parent.temporals:
            raise Exception("Call this function only after removing the temporal from the former parent")

        # switching parents:
        if (
            parent is not None
            and self._parent is not None
            and parent is not self._parent
            and self in self._parent.temporals
        ):
            raise Exception("Call this function only after removing the temporal from the former parent")

        # setting a parent for the first time:
        if parent is not None and self not in parent.temporals:
            raise Exception("Call this function only after establishing the reverse link in the parent")

        if parent is None:

            self._set_constraints(parent=False)
            self._parent = None

            # we could also remove the id here but it doesn't do any harm

        elif parent is not None:

            # when integrated in the object hierarchy, we need to have an id:
            self._set_new_id_from_authority()

            # if the parent provides a timeindex, we need to make sure that it
            # has the same length as any explicit timeindex, series or shape
            # already present in the temporal:
            if parent.timeindex is not None:
                if self._is_constrained_by(TIMEINDEX):
                    timeindex = self._get(TIMEINDEX)
                    if not timeindex.equals(parent.timeindex):
                        msg = (
                            "Tried to set a parent to a temporal where the",
                            "parent's timeindex has a different length than",
                            "the explicit timeindex already present in the",
                            "temporal.",
                        )
                        raise Exception(" ".join(msg))

                if self._is_constrained_by(SERIES) or self._is_constrained_by(SHAPE):
                    srs = self._get_series() if self._is_constrained_by(SERIES) else self._get_shape()
                    if len(srs) != len(parent.timeindex):
                        msg = (
                            "Tried to set a parent to a temporal where the",
                            "parent's timeindex has a different length than",
                            "the series or shape already present in the temporal.",
                        )
                        raise Exception(" ".join(msg))

            self._set_constraints(parent=True)
            self._parent = parent

        self._set_constraints(timeindex=False)
        self._timeindex = None

    @property
    def branch(self) -> Branch | None:
        if self._parent is not None:
            return self._parent.branch

    @property
    def has_parent(self) -> bool:
        return self._parent is not None

    @property
    def has_branch(self) -> bool:
        return self.branch is not None

    # --------------------------------------------------------------------------
    # Functions for swapping
    # --------------------------------------------------------------------------

    @property
    def swap_mode(self) -> Literal["lazy", "loaded", "swapped"]:
        """
        The swap mode of the temporal.

        Notes
        -----
        Possible swap modes are:
        - "loaded": The (relative or absolute) series data of the temporal will
        be kept in memory.
        - "swapped": The (relative or absolute) series data of the temporal
        won't be kept in memory but stored in a HDF file on the disk (requiring
        a parent, project and file adapter to be reachable)
        - "lazy": If data is in an HDF file but not in the memory, load it as
        soon as it is required - don't load unrequired data to memory.
        """
        return self._SWAP_MODE

    @swap_mode.setter
    def swap_mode(self, mode: Literal["lazy", "loaded", "swapped"]):
        """
        Setting the swap mode will load or swap the series if necessary.
        """
        error_if_readonly(self)
        if mode not in ["lazy", "loaded", "swapped"]:
            raise ValueError(f"Unknown swap mode: {mode}")

        if mode != self._SWAP_MODE:
            if mode == "loaded":
                if self._swapped:
                    self._load()

            elif mode == "swapped":
                if not self._swapped:
                    self._swap()

            elif mode == "lazy":
                pass  # keep it as it is

        self._SWAP_MODE = mode

    def _load(self):
        """
        Load the series from HDF and store it internally. Will raise an
        exception if no file adapter is present. This will delete the series
        in the HDF file.
        """
        assert not (self._is_constrained_by(SERIES) and self._is_constrained_by(SHAPE))

        if not self._swapped:
            raise Exception("Can't load series: Not swapped")

        srs = self._series_from_hdf()
        if self._is_constrained_by(SERIES):
            self.__series = srs
            self.__shape = None
        elif self._is_constrained_by(SHAPE):
            self.__shape = srs
            self.__series = None
        else:
            raise Exception()  # should not occur because _swapped would be False

        self._remove_series_from_hdf()
        self._swapped = False

    def _swap(self):
        """
        Store the series or shape (whatever the temporal is constrained
        by) to HDF file and delete it from the series. Constraints won't change.
        The temporal will be marked as `_swapped=True`. If the temporal is
        neither constrained by series nor shape, nothing will happen.
        If the series is already swapped, an Exception will be raised.
        """
        assert not (self._is_constrained_by(SERIES) and self._is_constrained_by(SHAPE))

        if self._swapped:
            raise Exception("Can't swap series: Already swapped")

        if self._is_constrained_by(SERIES):
            srs = self.__series
            self.__series = None

        elif self._is_constrained_by(SHAPE):
            srs = self.__shape
            self.__shape = None

        else:
            # we won't swap anything nor raise an Exception
            srs = None
            self.__series = None  # might have been cached etc.
            self.__shape = None  # might have been cached etc.

        if srs is not None:
            self._series_to_hdf(srs)
            self._swapped = True

    def _series_from_hdf(self) -> pd.Series:
        """
        Load the series from HDF and return it. Will raise an exception if no
        file adapter is present. The series won't be deleted in the file. The
        series won't be written to the temporal.
        """
        # make sure we can find the source of the data:
        error_if_readonly(self)
        if self._parent is None:
            raise Exception("Can't load series from HDF: No parent set")
        if self._parent.project is None:
            raise Exception("Can't load series from HDF: Parent isn't part of a project")
        if self._parent.project.file_adapter is None:
            raise Exception("Can't load series from HDF: Project doesn't have a file adapter")

        # get the file:
        hdf_file = self._parent.project.file_adapter.get_hdf_file_for_branch(self._parent.branch)

        # load the series:
        key = hdf_key_from_temporal(self)
        series = pd.Series(hdf_file[key])

        return series

    def _series_to_hdf(self, series: pd.Series):
        """
        Store the series to HDF. Will raise an exception if no file adapter
        is present. This will overwrite any existing data for this id in the
        HDF file.
        """
        # make sure we can find the destination for the data:
        error_if_readonly(self)
        if self._parent is None:
            raise Exception("Can't store series to HDF: No parent set")
        if self._parent.project is None:
            raise Exception("Can't store series to HDF: Parent isn't part of a project")
        if self._parent.project.file_adapter is None:
            raise Exception("Can't store series to HDF: Project doesn't have a file adapter")

        # get the file:
        hdf_file = self._parent.project.file_adapter.get_hdf_file_for_branch(self._parent.branch)

        # delete possibly existing data and write the series:
        key = hdf_key_from_temporal(self)
        if key in hdf_file:
            del hdf_file[key]
        hdf_file.create_dataset(key, data=series, compression="gzip", compression_opts=4)  # .values

    def _remove_series_from_hdf(self):
        """
        Remove the data of this temporal from HDF (be it the series, the
        shape, or none at all). Will raise an exception if no file
        adapter is present.
        """
        # get the file:
        hdf_file = self._parent.project.file_adapter.get_hdf_file_for_branch(self._parent.branch)

        # delete the key in the hdf file:
        key = hdf_key_from_temporal(self)
        if key in hdf_file:
            del hdf_file[key]

    def set_swap_mode_from_branch(self):
        if self.branch is not None and self.branch.temporal_manager is not None:
            self.parent.branch.temporal_manager.apply_settings_for_object(self)

    # ------------------------------------------------------------------
    # SQLite (de-)serialisation helpers
    # ------------------------------------------------------------------
    def _series_to_compressed_blob(
        self,
        series: pd.Series,
        *,
        compress: bool = True,
    ) -> tuple[bytes, str, int, int]:
        """Return a (blob, dtype, length, compressed_flag) tuple for `series`.

        Notes
        -----
        - Index is omitted (recreated as RangeIndex on load).
        - Data are stored in native numpy binary representation optionally
          gzip-compressed (zlib).
        - Dtype is recorded as string for round‑trip.
        """
        if not isinstance(series, pd.Series):
            raise TypeError("series must be a pandas Series")
        arr = series.to_numpy()
        raw = arr.tobytes()
        if compress:
            raw = zlib.compress(raw, level=6)
        return raw, str(arr.dtype), len(arr), int(compress)

    @staticmethod
    def _series_from_compressed_blob(
        blob: bytes,
        dtype: str,
        length: int,
        compressed: int,
    ) -> pd.Series:
        """Recreate a Series (RangeIndex) from blob metadata produced above."""
        if compressed:
            blob = zlib.decompress(blob)
        arr = np.frombuffer(blob, dtype=dtype, count=length)
        return pd.Series(arr.copy(), index=pd.RangeIndex(length))

    def to_compressed_record(self) -> dict:
        """
        Return a dict describing this Temporal as a compressed record, e.g.
        for SQL storage.

        The dict contains:
        - kind: 'series' | 'shape' | 'none'
        - blob / dtype / length / compressed (omitted if kind=='none')
        - total, fix (may be None)
        - constraints: bool dictionary indicating which constraints are present

        The dict does not contain:
        - id
        - master links
        - timeindex
        """
        kind = "none"
        blob = dtype = None
        length = compressed = None

        if self._is_constrained_by(TIMEINDEX):
            raise Exception("Can't store a temporal constrained by timeindex")

        # Determine authoritative representation (mirrors swap logic assumptions)
        if self._is_constrained_by(SERIES):
            s = self._get_series()
            if s is not None:
                kind = "series"
                blob, dtype, length, compressed = self._series_to_compressed_blob(series=s, compress=True)

        elif self._is_constrained_by(SHAPE):
            sh = self._get_shape()
            if sh is not None:
                kind = "shape"
                blob, dtype, length, compressed = self._series_to_compressed_blob(series=sh, compress=True)

        record = {
            "kind": kind,
            "total": self.total if self._is_available(TOTAL) else None,
            "fix": self.fix if self._is_available(FIX) else None,
            "constraints": {
                "series": self._constraints[SERIES],
                "shape": self._constraints[SHAPE],
                "total": self._constraints[TOTAL],
                "fix": self._constraints[FIX],
                "timeindex": self._constraints[TIMEINDEX],
                "master": self._constraints[MASTER],
            },
        }
        if kind != "none":
            record.update(
                {
                    "blob": blob,
                    "dtype": dtype,
                    "length": length,
                    "compressed": compressed,
                }
            )
        return record

    @classmethod
    def from_compressed_record(cls, record: dict, master: Temporal = None) -> Temporal:
        """
        Create a Temporal from a record produced by `to_compressed_record`.

        If `master` is given, it will be set as the master of the created
        Temporal. In this case, the record must indicate that the temporal is
        constrained by master.
        """
        t = cls()
        constraints = record["constraints"]
        assert not constraints["timeindex"]

        if master is not None:
            assert constraints["master"]
            t.master = master

        elif record.get("kind") == "series":
            assert constraints["series"]
            s = cls._series_from_compressed_blob(
                record["blob"],
                record["dtype"],
                record["length"],
                record["compressed"],
            )
            assert constraints["series"]
            t.series = s  # use setter, will set constraint

        elif record.get("kind") == "shape":
            assert constraints["shape"]
            sh = cls._series_from_compressed_blob(
                record["blob"],
                record["dtype"],
                record["length"],
                record["compressed"],
            )
            assert constraints["shape"]
            t.shape = sh  # use setter, will set constraint

        if constraints["total"]:
            t._total = record["total"]
            t._set_constraints(total=True)
        if constraints["fix"]:
            t._fix = record["fix"]
            t._set_constraints(fix=True)

        return t

    # --------------------------------------------------------------------------
    # Additional properties and functions
    # --------------------------------------------------------------------------

    @property
    def n_accesses(self) -> int:
        """
        Return the number of accesses to the series since the last reset.
        """
        return self._n_accesses

    @property
    def read_only(self) -> bool:
        return self._READ_ONLY

    @read_only.setter
    def read_only(self, read_only: bool):
        self._READ_ONLY = read_only

    def _reset_access_counter(self):
        """
        Set the access counter `_n_accesses` to 0. This may affect the swapping
        behaviour.
        """
        self._n_accesses = 0

    def _series_to_timeseries(self, series: pd.Series) -> pd.Series:
        """
        Return a copy of `series` with the DatetimeIndex set.
        Will raise an exception if no timeindex is set.
        """
        return series.set_axis(self.timeindex, axis=0).copy()

    def set_shape_or_series(self, shape: pd.Series):
        """
        Set `shape` as the shape. If no total is present, set `shape` as the
        series (i.e. also use the total).
        """
        if self._is_available(TOTAL):
            self.shape = shape  # will store total even if not constrained by it
        else:
            self.series = shape

    def set_timeshape_or_timeseries(self, timeshape: pd.Series):
        """
        Set `timeshape` as the timeshape. If no total is present, set `timeshape` as the
        timeseries (i.e. also use the total).
        """
        if self._total is not None or self.total is not None:
            self.timeshape = timeshape
        else:
            self.timeseries = timeshape

    def copy(self) -> Temporal:
        """
        Create a copy of the temporal The created copy won't have a parent
        set. If a Master is present, it will be set in the copy, too. Clients
        won't be present in the copy. Read-only will be set to False.
        """
        temporal = Temporal()
        temporal._constraints = self._constraints | {"parent": False, "master": False}

        temporal._STORE_SHAPE = self._STORE_SHAPE
        temporal._STORE_SERIES = self._STORE_SERIES

        temporal._set_series(self._get_series())
        temporal._set_shape(self._get_shape())
        temporal._total = self._total
        temporal._fix = self._fix
        temporal._timeindex = self._timeindex
        temporal._clients = []
        temporal._master = None

        if self._master is not None:
            temporal.add_to_master(master=self._master)

        return temporal

    def equals(self, other: Number | Temporal) -> bool:
        """
        Check whether temporals are equal in terms of resulting timeseries. This
        could return also return True if for example one Temporal has `total` or
        `fix` set and the other doesn't.
        """
        if isinstance(other, Number):
            return self.fix == other
        elif isinstance(other, Temporal):
            ret = self._total == other._total  # TODO is _total really always set?
            if self.fix is not None and other.fix is not None:
                ret &= self.fix == other.fix
            if self.has_timeindex and other.has_timeindex:
                ret &= self.timeindex.equals(other.timeindex)
            if (not self._series_none) or (not other._series_none):
                ret &= self.series.equals(other.series)
            elif self.__shape is not None and other.__shape is not None:
                ret &= self.__shape.equals(other.s_relative_serieseries)
        return ret

    def min(self) -> float | None:
        if self._min is not None:
            return self._min
        elif self._is_available(SERIES):
            self._min = self.series.min()
            return self._min

    def max(self) -> float | None:
        if self._max is not None:
            return self._max
        elif self._is_available(SERIES):
            self._max = self.series.max()
            return self._max

    def mean(self) -> float | None:
        if self._mean is not None:
            return self._mean
        elif self._is_available(TOTAL) and self.has_timeindex:
            return self.total / len(self.timeindex)
        elif self._is_available(SERIES):
            self._mean = self.series.mean()
            return self._mean

    def __add(self, other: Number | Temporal, factor: Literal[1, -1] = 1) -> Temporal:

        if self.is_empty:
            if isinstance(other, Temporal) and other.is_empty:
                return Temporal()
            else:
                return Temporal()
                # raise Exception("Can't add to an empty Temporal")

        elif isinstance(other, Number):

            if self.fix is not None:
                return Temporal(timeindex=self.timeindex, fix=self.fix + factor * other)
            else:
                if self.has_timeindex:
                    series = None
                    timeseries = self.timeseries
                else:
                    series = self.series
                    timeseries = None
                return Temporal(
                    timeseries=timeseries if self.master is None else None,  # not allowed if master!=None
                    series=series if self.master is None else None,  # not allowed if master!=None
                    total=self.total + factor * other,
                    master=self.master,
                )

        elif isinstance(other, Temporal):

            if other.is_empty:
                return Temporal()
                # raise Exception("Can't add an empty Temporal")
            elif self.branch is not None and other.branch is not None and self.branch is not other.branch:
                raise Exception("Can't add a Temporal with a parent from another branch")
            elif self.has_master and self.master is other.master:
                return self.master.create_client(total=self.total + factor * other.total)

            else:

                # get common timeindex:
                if self.timeindex is not None and other.timeindex is not None:
                    if not self.timeindex.equals(other.timeindex):
                        raise Exception("Timeindices are present but differ")
                    timeindex = next(t for t in [self.timeindex, other.timeindex] if t is not None)
                else:
                    timeindex = None

                if self.fix is not None and other.fix is not None:
                    return Temporal(
                        fix=self.fix + factor * other.fix,
                        timeindex=timeindex,
                    )

                if self.is_temporal and other.is_temporal:
                    return Temporal(
                        series=self.series + factor * other.series,
                        timeindex=timeindex,
                    )

                else:

                    if other.is_temporal and (not self.is_temporal):
                        return Temporal(timeseries=other.timeseries + factor * self.total)
                    elif self.is_temporal and (not other.is_temporal):
                        return Temporal(timeseries=self.timeseries + factor * other.total)
                    elif self.total is not None and other.total is not None:
                        return Temporal(timeindex=timeindex, total=self.total + factor * other.total)
                    else:
                        raise Exception()

        else:
            raise TypeError()

    def __add__(self, other: Number | Temporal):
        return self.__add(other, factor=1)

    def __sub__(self, other: Number | Temporal):
        return self.__add(other, factor=-1)

    def __mul__(self, other: Number | Temporal):

        if self.is_empty:
            if isinstance(other, Temporal) and other.is_empty:
                return Temporal()
            else:
                return Temporal()
                # raise Exception("Can't multiply an empty Temporal")

        elif isinstance(other, Number):

            if self.fix is not None:
                return Temporal(timeindex=self.timeindex, fix=self.fix * other)
            else:
                if self.has_timeindex:
                    series = None
                    timeseries = self.timeseries
                else:
                    series = self.series
                    timeseries = None
                return Temporal(
                    timeseries=timeseries if self.master is None else None,  # not allowed if master!=None
                    series=series if self.master is None else None,  # not allowed if master!=None
                    total=self.total * other,
                    master=self.master,
                )

        elif isinstance(other, Temporal):

            if other.is_empty:
                return Temporal()
                # raise Exception("Can't add an empty Temporal")
            elif self.branch is not None and other.branch is not None and self.branch is not other.branch:
                raise Exception("Can't add a Temporal with a parent from another branch")
            elif self.has_master and self.master is other.master:
                return self.master.create_client(total=self.total * other.total)

            else:

                # get common timeindex:
                if self.timeindex is not None and other.timeindex is not None:
                    if not self.timeindex.equals(other.timeindex):
                        raise Exception("Timeindices are present but differ")
                    timeindex = next(t for t in [self.timeindex, other.timeindex] if t is not None)
                else:
                    timeindex = None

                if self.fix is not None and other.fix is not None:
                    return Temporal(
                        fix=self.fix * other.fix,
                        timeindex=timeindex,
                    )

                if self.is_temporal and other.is_temporal:
                    return Temporal(
                        series=self.series * other.series,
                        timeindex=timeindex,
                    )

                else:
                    raise Exception("Unsupported operation for multiplication between temporals")

        else:
            raise TypeError("Unsupported type for multiplication: " + str(type(other)))

    def __truediv__(self, other: Number | Temporal) -> Temporal:

        if self.is_empty:
            if isinstance(other, Temporal) and other.is_empty:
                return Temporal()
            else:
                return Temporal()
                # raise Exception("Can't divide an empty Temporal")

        elif isinstance(other, Number):

            if self.fix is not None:
                return Temporal(timeindex=self.timeindex, fix=self.fix / other)
            else:
                if self.has_timeindex:
                    series = None
                    timeseries = self.timeseries
                else:
                    series = self.series
                    timeseries = None
                return Temporal(
                    timeseries=timeseries if self.master is None else None,  # not allowed if master!=None
                    series=series if self.master is None else None,  # not allowed if master!=None
                    total=self.total / other,
                    master=self.master,
                )

        elif isinstance(other, Temporal):

            if other.is_empty:
                return Temporal()
                # raise Exception("Can't add an empty Temporal")
            elif self.branch is not None and other.branch is not None and self.branch is not other.branch:
                raise Exception("Can't add a Temporal with a parent from another branch")
            elif other.has_master:
                raise Exception("Can't divide a Temporal by a Temporal having a master")

            else:

                # get common timeindex:
                if self.timeindex is not None and other.timeindex is not None:
                    if not self.timeindex.equals(other.timeindex):
                        raise Exception("Timeindices are present but differ")
                    timeindex = next(t for t in [self.timeindex, other.timeindex] if t is not None)
                else:
                    timeindex = None

                if self.fix is not None and other.fix is not None:
                    return Temporal(
                        fix=self.fix / other.fix,
                        timeindex=timeindex,
                    )

                if self.is_temporal and other.is_temporal:
                    return Temporal(
                        series=self.series / other.series,
                        timeindex=timeindex,
                    )

                else:
                    raise Exception("Unsupported operation for division between temporals")

        else:
            raise TypeError("Unsupported type for division: " + str(type(other)))

    def __repr__(self) -> str:
        s = f"{self.__class__.__name__}(id={self.id} "
        if self.has_total:
            if self._is_constrained_by(TOTAL):
                s += f"tot={self.total} "
            else:
                s += f"(tot={self.total}) "

        if self.has_fix:
            # will always be a constraint when available
            s += f"fix={self.fix} "

        if self.has_parent:
            # will always be a constraint when available
            s += f"par "

        if self.has_master:
            # will always be a constraint when available
            s += f"mas "

        if self.has_timeindex:
            if self._is_constrained_by(TIMEINDEX):
                s += f"idx "
            else:
                s += f"(idx) "

        if self.has_series:
            if self._is_constrained_by(SERIES):
                s += f"srs "
            else:
                s += f"(srs) "

        if self.has_shape:
            if self._is_constrained_by(SHAPE):
                s += f"shp "
            else:
                s += f"(shp) "

        if self.has_clients:
            s += f"clients={len(self._clients)}"

        if self.is_empty:
            s += "empty "

        s = s[:-1]
        s += ")"
        return s

    def __eq__(self, __o: object) -> bool:
        return id(__o) == id(self)

    def __hash__(self) -> int:
        # togehter with __eq__, this allows us to use an Object as a dict key
        return id(self)

    @classmethod
    def sum(cls, temporals: list[Temporal]) -> Temporal:
        """
        Sum `temporals`. If the temporals have conflicting timeindices, an
        exception will be raised. If only some timeindices are present or all
        timeindices are identical, the returned temporal will have that
        timeindex set as its explicit timeindex.
        """

        # find first temporal with total:
        ret = Temporal()
        i = 0
        while ret.total is None:
            if len(temporals) <= i:
                return Temporal()
            ret = temporals[i]
            i += 1

        # if more than one temporal has been passed, calculate the sum
        # iteratively:
        if len(temporals) > i:
            for dt in temporals[i:]:
                if dt.total is None:
                    continue
                ret += dt  # will raise exception if timeindices are not compatible
            return ret

        else:
            ret2 = ret.copy()  # this will copy an explicit timeindex but not an implicit one
            # the copied temporal might have a master. in that case it won't accept a timeindex:
            if not ret2.has_master:
                ret2.timeindex = ret.timeindex  # store possibly implicit timeindex as explicit one
            return ret2
