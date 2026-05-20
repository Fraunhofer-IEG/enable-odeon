import unittest
import numpy as np
import pandas as pd
from pandas.testing import assert_series_equal
import random

from odeon.model.base import Project, Branch, Object
from odeon.model.temporal import Temporal


def create_random_series(min_val: int = 0, max_val: int = 10, length: int = 10) -> pd.Series:
    s = pd.Series(random.choices(range(min_val, max_val + 1), k=length), dtype="float64")
    return s


def create_random_timeseries(min_val: int = 0, max_val: int = 10, length: int = 10) -> pd.Series:
    idx = pd.date_range("2023-01-01", periods=length, freq="h")
    ts = pd.Series(random.choices(range(min_val, max_val + 1), k=len(idx)), index=idx, dtype="float64")
    return ts


def assert_lists_equal(left, right):
    assert isinstance(left, list)
    assert isinstance(right, list)
    assert len(left) == len(right)
    assert all(i == j for i, j in zip(left, right))


class TemporalHavingObject(Object):

    _TEMPORAL_ATTRIBUTES = ["_temporal_1"]
    _temporal_1: None

    @property
    def temporal_1(self) -> Temporal:
        return self._temporal_1

    @temporal_1.setter
    def temporal_1(self, value: Temporal):
        self._set_simple_temporal("_temporal_1", value)


class TestTemporal(unittest.TestCase):

    def test_create_by_series(self):

        pd_s = pd.Series([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], dtype="float64")

        # need to use right parameter:
        self.assertRaises(
            Exception,
            lambda x: Temporal(timeseries=pd_s),
        )
        bt = Temporal(series=pd_s)

        # the set series will be a copy:
        assert bt.series is not pd_s

        # the set series equals the parameter:
        assert bt.series.equals(pd_s)
        assert bt.rangeindex.equals(pd_s.index)
        assert bt.total == pd_s.sum()

        # shape is accessible:
        assert bt.shape.equals(pd_s / pd_s.sum())

        # parent, timeindex and timeseries are not:
        assert bt.parent is None
        assert bt.branch is None
        assert not bt.has_timeindex
        assert bt.timeindex is None
        assert bt.timeshape is None

        # test further predicates:
        assert not bt.fix
        assert not bt.is_empty
        assert bt.is_temporal

    def test_create_by_timeseries(self):

        pd_ts = create_random_timeseries()
        pd_ts.iloc[-1] = pd_ts.iloc[0] + 1  # make sure it's not constant for further tests
        pd_s = pd_ts.reset_index(drop=True)

        # need to use right parameter:
        self.assertRaises(
            Exception,
            lambda: Temporal(series=pd_ts),
        )
        bt = Temporal(timeseries=pd_ts)

        # the set timeseries will be a copy:
        assert bt.timeseries is not pd_ts

        # the set timeseries equals the parameter:
        assert bt.timeseries.equals(pd_ts)
        assert bt.timeindex.equals(pd_ts.index)
        assert bt.total == pd_ts.sum()

        # timeindex has been set locally:
        assert bt.has_timeindex

        # series has been created:
        assert bt.series.equals(pd_s)
        assert bt.rangeindex.equals(pd_s.index)

        # shape and timeseries are accessible:
        assert bt.shape.equals(pd_s / pd_s.sum())
        assert bt.timeshape.equals(pd_ts / pd_ts.sum())

        # parent is not:
        assert bt.parent is None
        assert bt.branch is None

        # test further predicates:
        assert not bt.fix
        assert not bt.is_empty
        assert bt.is_temporal

    def test_create_by_series_and_timeindex(self):

        pd_ts = create_random_timeseries()
        pd_ts.iloc[-1] = pd_ts.iloc[0] + 1  # make sure it's not constant for further tests
        pd_s = pd_ts.reset_index(drop=True)
        ti = pd_ts.index.copy()
        ri = pd_s.index.copy()

        # need to use right parameter:
        self.assertRaises(
            Exception,
            lambda: Temporal(timeseries=pd_ts, timeindex=ti),
        )
        self.assertRaises(
            Exception,
            lambda: Temporal(timeseries=pd_ts, series=pd_s, timeindex=ti),
        )
        self.assertRaises(
            Exception,
            lambda: Temporal(timeseries=pd_ts, series=pd_s),
        )
        self.assertRaises(
            Exception,
            lambda: Temporal(series=pd_s, timeindex=ri),
        )
        bt = Temporal(series=pd_s, timeindex=ti)

        # the set series will be a copy:
        assert bt.series is not pd_s

        # and equal the parameter:
        assert bt.series.equals(pd_s)
        assert bt.rangeindex.equals(pd_s.index)
        assert bt.total == pd_ts.sum()

        # timeindex has been set locally and equals the parameter:
        assert bt.has_timeindex
        assert bt.timeindex.equals(ti)

        # shape and timeseries are accessible:
        assert bt.timeseries.equals(pd_ts)
        assert bt.shape.equals(pd_s / pd_s.sum())
        assert bt.timeshape.equals(pd_ts / pd_ts.sum())

        # parent is not:
        assert bt.parent is None
        assert bt.branch is None

        # test further predicates:
        assert not bt.fix
        assert not bt.is_empty
        assert bt.is_temporal  # equals bt.has_timeindex

    def test_create_by_timeindex(self):

        pd_ts = create_random_timeseries()
        ti = pd_ts.index

        bt = Temporal(timeindex=ti)

        # timeindex has been set locally:
        assert bt.has_timeindex
        assert bt.timeindex.equals(pd_ts.index)
        assert bt.total is None

        assert bt.timeseries is None

    def test_create_by_timeindex_and_total(self):
        pd_ts = create_random_timeseries()
        ti = pd_ts.index

        bt = Temporal(timeindex=ti, total=100)

        # Timeindex and total are present:
        assert bt.has_timeindex
        assert bt.timeindex.equals(pd_ts.index)
        assert bt.total == 100

        # series are not yet accessible:
        assert bt.timeseries is None
        assert not bt.has_shape
        assert bt.has_total

        # we can fill the series with a constant instead:
        s = pd.Series([1] * 10)
        bt.shape = s
        assert bt.timeseries is not None
        assert bt.timeseries.sum() == 100
        assert bt.series.sum() == 100
        assert np.isclose(bt.timeshape.sum(), 1, 1e-9)
        assert np.isclose(bt.shape.sum(), 1, 1e-9)

        # temporal is analytically constant:
        assert bt.is_constant
        assert bt.fix is None

    def test_create_by_timeindex_and_fix(self):
        pd_ts = create_random_timeseries()
        ti = pd_ts.index

        bt = Temporal(timeindex=ti, fix=0.1)

        # constant is present, and timeseries is also constant:
        assert bt.fix == 0.1
        assert bt.is_constant

        # Total is accessible
        assert bt.total == 0.1 * 10

        # All series and indices are accessible:
        assert bt.has_timeindex
        assert bt.timeindex.equals(pd_ts.index)
        assert bt.timeseries is not None
        assert bt.timeseries.sum() == 0.1 * 10
        assert bt.series.sum() == 0.1 * 10
        assert np.isclose(bt.timeshape.sum(), 1, 1e-9)
        assert np.isclose(bt.shape.sum(), 1, 1e-9)

    def test_create_by_total(self):

        bt = Temporal(total=5)

        # Total has been set:
        assert bt.total == 5

        # Everything else is None:
        assert bt.series is None
        assert bt.shape is None
        assert bt.timeseries is None
        assert bt.timeindex is None
        assert bt.fix is None

    def test_create_by_constant(self):

        bt = Temporal(fix=5)

        # Constant has been set:
        assert bt.fix == 5

        # Everything else is None:
        assert bt.series is None
        assert bt.shape is None
        assert bt.timeseries is None
        assert bt.timeindex is None
        assert bt.total is None

    def test_set_parent_having_parent(self):

        b1 = Branch(year=2021)
        o1 = TemporalHavingObject(branch=b1)
        ti1 = o1.timeindex.copy()
        pd_s1 = create_random_series(length=len(b1.timeindex))

        b2 = Branch(year=2022)
        o2 = TemporalHavingObject(branch=b2)
        ti2 = o2.timeindex.copy()
        pd_s2 = create_random_series(length=len(b2.timeindex))
        pd_ts2 = pd.Series(pd_s2.values, index=b2.timeindex)

        b3 = Branch(year=2024)  # leap year
        o3 = TemporalHavingObject(branch=b3)

        bt1 = Temporal(series=pd_s1)
        o1.temporal_1 = bt1

        assert bt1.timeindex.equals(ti1)

        # changing timeindex is not possible:
        self.assertRaises(
            Exception,
            lambda: bt1.timeindex.fset(ti2),  # call the setter
        )

        # changing timeseries is not possible:
        self.assertRaises(
            Exception,
            lambda: bt1.timeseries.fset(pd_ts2),  # call the setter
        )

        # changing the series is possible:
        bt1.series = pd_s2

        # changing the parent is possible and will alter the timeindex:
        o2.temporal_1 = bt1
        assert bt1.parent is o2
        assert bt1.branch is b2
        assert bt1.timeindex.equals(o2.timeindex)

        # changing the parent isn't possible when timeindex length differs:
        assert len(bt1.timeindex) != len(o3.timeindex)  # o3 = leap year
        self.assertRaises(
            Exception,
            lambda x: bt1.set_parent(o3),
        )
        assert bt1.parent is o2
        assert bt1.branch is b2
        assert bt1.timeindex.equals(o2.timeindex)

    def test_set_timeindex_having_series(self):
        pd_ts = create_random_timeseries()
        pd_s = pd_ts.reset_index(drop=True)
        ti = pd_ts.index.copy()
        ri = pd_s.index.copy()

        bt = Temporal(series=pd_s)

        # timeseries not available:
        assert bt.timeseries is None

        # needs to be a timeindex:
        self.assertRaises(
            Exception,
            lambda: bt.timeindex.fset(ri),
        )
        bt.timeindex = ti

        # timeindex is present as a copy:
        assert bt.has_timeindex
        assert bt.timeindex is not ti
        assert bt.timeindex.equals(ti)

        # series is still available:
        assert bt.series.equals(pd_s)

    def test_set_timeindex_having_total(self):
        pd_ts = create_random_timeseries()
        ti = pd_ts.index.copy()

        bt = Temporal(total=100)

        # timeseries not available:
        assert bt.timeseries is None

        bt.timeindex = ti

        # timeindex is available, timeseries still isn't:
        assert bt.has_timeindex
        assert bt.timeindex.equals(ti)
        assert bt.total == 100
        assert bt.has_total
        assert not bt.has_shape
        assert bt.timeseries is None

    def test_set_timeindex_having_constant(self):
        pd_ts = create_random_timeseries()
        ti = pd_ts.index.copy()

        bt = Temporal(fix=0.1)
        pd_ts = pd.Series(0.1, index=ti)
        pd_s = pd_ts.reset_index(drop=True)

        bt.timeindex = ti

        # timeseries and timeindex are available now:
        assert bt.has_timeindex
        assert bt.timeindex.equals(ti)
        assert bt.series.equals(pd_s)
        assert bt.timeseries.equals(pd_ts)
        assert bt.fix == 0.1
        assert bt.total == 0.1 * len(ti)
        assert bt.is_constant

    def test_set_parent_having_series(self):
        b = Branch(year=2021)
        o = TemporalHavingObject(branch=b)
        ti = o.timeindex.copy()
        pd_ts = pd.Series(100 / 8760, index=ti)
        pd_s = pd_ts.reset_index(drop=True)

        bt = Temporal(total=100, series=pd_s)

        o.temporal_1 = bt

        # timeseries and timeindex are available now:
        assert bt.has_timeindex
        assert bt.timeindex.equals(ti)
        assert bt.series.equals(pd_s)
        assert bt.timeseries.equals(pd_ts)
        assert bt.total == 100
        assert bt.is_constant
        assert bt.series.iloc[0] == 100 / len(ti)

    def test_set_parent_having_constant(self):
        bt = Temporal(fix=0.1)

        b = Branch(year=2021)
        o = TemporalHavingObject(branch=b)
        ti = o.timeindex.copy()
        pd_ts = pd.Series(0.1, index=ti)
        pd_s = pd_ts.reset_index(drop=True)

        o.temporal_1 = bt

        # timeseries and timeindex are available now:
        assert bt.has_timeindex
        assert bt.timeindex.equals(ti)
        assert bt.series.equals(pd_s)
        assert bt.timeseries.equals(pd_ts)
        assert bt.fix == 0.1
        assert np.isclose(bt.total, 0.1 * len(ti), rtol=1e-9)
        assert bt.is_constant

    def test_set_series_having_parent(self):

        b = Branch(year=2021)
        o = TemporalHavingObject(branch=b)
        ti = o.timeindex.copy()
        pd_s1 = create_random_series(length=len(b.timeindex))
        pd_s2 = create_random_series(length=len(b.timeindex))

        bt = Temporal()
        o.temporal_1 = bt

        assert bt.timeindex.equals(ti)

        bt.series = pd_s1

        assert bt.has_timeindex
        assert bt.timeseries is not None
        assert bt.series.equals(pd_s1)

        bt.series = pd_s2
        assert bt.timeseries is not None
        assert bt.series.equals(pd_s2)

    def test_set_timeseries_having_parent(self):

        b = Branch(year=2021)
        o = TemporalHavingObject(branch=b)
        ti = o.timeindex.copy()
        pd_s1 = create_random_series(length=len(b.timeindex))
        pd_ts1 = pd.Series(pd_s1.values, index=b.timeindex)
        pd_s2 = create_random_series(length=len(b.timeindex))
        pd_ts2 = pd.Series(pd_s1.values, index=b.timeindex)

        bt = Temporal()
        o.temporal_1 = bt

        bt.timeseries = pd_ts1

        assert bt.has_timeindex
        assert bt.timeseries is not None
        assert bt.timeseries.equals(pd_ts1)

        bt.timeseries = pd_ts2
        assert bt.timeseries is not None
        assert bt.timeseries.equals(pd_ts2)

    def test_add_client_to_master(self):

        pd_ts = create_random_timeseries()
        ts1 = Temporal(timeseries=pd_ts)
        ts2 = Temporal()
        ts2.add_to_master(ts1)

        assert ts2.has_master
        assert ts2.master is ts1
        assert ts2.masters_recursive == [ts1]
        assert ts2 in ts1.clients
        assert ts2.has_timeindex
        assert ts2.timeindex is not ts1.timeindex
        assert ts2.timeindex.equals(ts1.timeindex)
        assert ts2.timeseries is None
        assert ts2.total is None

        # writing total at client makes it a series:
        ts2.total = ts1.total
        assert_series_equal(ts2.timeseries, ts1.timeseries)
        assert ts2.total == ts1.total

        # changing total in master won't affect the client:
        bt = ts2.total
        ts1.total = bt * 2
        assert ts1.total == bt * 2
        assert ts2.total == bt
        ts1.total = bt

        # detaching the series won't change anything in the values:
        ts2.remove_from_master()
        assert not ts1.clients
        assert not ts2.has_master
        assert ts2.total == ts1.total
        assert ts2.timeindex.equals(ts1.timeindex)
        assert_series_equal(ts1.timeseries, ts2.timeseries)
        assert_series_equal(ts1.shape, ts2.shape)

    def test_create_client_from_master(self):

        pd_ts = create_random_timeseries()
        tsa = Temporal(timeindex=pd_ts.index)
        tsb = tsa.create_client(total=5)

        assert tsb.master is tsa
        assert tsa.clients == [tsb]

        # writing total at client makes it a series:
        assert tsb.total == 5
        assert tsb.timeindex.equals(tsa.timeindex)

    def test_master_chain(self):

        pd_ts = create_random_timeseries()
        ts1 = Temporal(timeindex=pd_ts.index)
        ts2 = Temporal(master=ts1, total=5)
        ts3 = Temporal(timeindex=pd_ts.index, total=100)
        ts2.add_client(ts3)

        assert ts1.clients == [ts2]
        assert ts2.clients == [ts3]
        assert ts2.master is ts1
        assert ts3.master is ts2
        assert set(ts1.clients_recursive) == set([ts2, ts3])
        assert set(ts3.masters_recursive) == set([ts1, ts2])

        assert ts2.total == 5
        assert ts3.total == 100

    def test_adding_to_temporal(self):

        pd_ts = create_random_timeseries()
        t1 = Temporal(timeseries=pd_ts)

        # scalars:

        t2 = t1 + 2
        assert t2.total == t1.total + 2

        t2 = t1 - 2
        assert t2.total == t1.total - 2

        t2 = t1 * 2
        assert t2.total == 2 * t1.total

        # isolated timeseries:

        srs2 = create_random_timeseries()
        t2 = Temporal(timeseries=srs2)

        t_sum = t1 + t2
        assert t_sum.total == t1.total + t2.total
        assert_series_equal(t_sum.timeseries, t1.timeseries.add(t2.timeseries))

        t_dif = t1 - t2
        assert t_dif.total == t1.total - t2.total
        assert_series_equal(t_dif.timeseries, t1.timeseries.sub(t2.timeseries))

        t_mul = t1 * t2
        assert_series_equal(t_mul.timeseries, t1.timeseries.mul(t2.timeseries))

        # timeseries with master:

        t1 = Temporal(timeseries=pd_ts)

        pd_ts2 = create_random_timeseries()
        t2m = Temporal(timeseries=pd_ts2)
        t2c = Temporal(master=t2m, total=10)

        t3 = t1 + t2c
        assert np.isclose(t3.total, t1.total + t2c.total, rtol=1e-10)  # rounding errors when summing series

        # timeseries with parent:

        # TODO

    def test_adding_to_constant_temporal(self):
        ...
        # TODO

    def test_adding_to_total_temporal(self):
        ...
        # TODO

    def test_adding_to_temporal_with_parent(self):
        ...
        # TODO

    def test_adding_to_temporal_with_master(self):
        ...
        # TODO


if __name__ == "__main__":
    # TestTemporal().test_create_by_series()
    # TestTemporal().test_create_by_timeseries()
    TestTemporal().test_create_by_series_and_timeindex()
    # TestTemporal().test_create_by_series_and_parent() # remove
    TestTemporal().test_create_by_timeindex()
    TestTemporal().test_create_by_timeindex_and_fix()
    TestTemporal().test_create_by_constant()
    TestTemporal().test_create_by_total()
    TestTemporal().test_create_by_timeindex_and_total()
    TestTemporal().test_set_parent_having_parent()
    TestTemporal().test_set_timeindex_having_series()
    TestTemporal().test_set_timeindex_having_total()
    TestTemporal().test_set_timeindex_having_constant()
    TestTemporal().test_set_parent_having_series()  # adapt
    TestTemporal().test_set_parent_having_constant()  # adapt
    TestTemporal().test_set_series_having_parent()  # adapt
    TestTemporal().test_set_timeseries_having_parent()  # adapt

    TestTemporal().test_add_client_to_master()
    TestTemporal().test_create_client_from_master()
    TestTemporal().test_master_chain()
    TestTemporal().test_adding_to_temporal()
    TestTemporal().test_adding_to_constant_temporal()
    TestTemporal().test_adding_to_total_temporal()
    TestTemporal().test_adding_to_temporal_with_parent()  # adapt
    TestTemporal().test_adding_to_temporal_with_master()
