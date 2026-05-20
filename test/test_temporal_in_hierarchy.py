import unittest

import pandas as pd
from odeon.model import Temporal, Structure, Building, Branch, Project

from odeon.model.device import HeatDemand


class TestTemporalInHierarchy(unittest.TestCase):

    def test_with_branch(self):
        branch = Branch(year=2025)

        assert isinstance(branch.timeindex, pd.DatetimeIndex)
        assert len(branch.timeindex) == 8760

        heat_demand = HeatDemand()
        branch.add_objects(heat_demand)

        assert isinstance(heat_demand.input_flow, Temporal)
        assert heat_demand.input_flow.is_empty

        # setting attribute to a Temporal will create a copy:

        temporal = Temporal(fix=5)

        assert not temporal.is_temporal

        heat_demand.input_flow = temporal

        assert isinstance(heat_demand.input_flow, Temporal)
        assert heat_demand.input_flow is not temporal  # has been copied
        assert heat_demand.input_flow.fix == 5
        assert heat_demand.input_flow.timeindex.equals(branch.timeindex)
        assert len(heat_demand.input_flow.timeseries) == 8760
        assert heat_demand.input_flow.timeseries.index.equals(branch.timeindex)
        assert heat_demand.input_flow.series.loc[0] == 5

        # setting attribute to None will create an empty Temporal:

        heat_demand.input_flow = None

        assert isinstance(heat_demand.input_flow, Temporal)
        assert heat_demand.input_flow.is_empty

        # setting attribute to a Number will set it as the fix value of a new Temporal:

        heat_demand.input_flow = 120  # will set fix

        assert isinstance(heat_demand.input_flow, Temporal)
        assert heat_demand.input_flow.fix == 120

        # setting attribute to a Series with RangeIndex will wrap it in a Temporal:

        heat_demand.input_flow = pd.Series([2] * 8760)

        assert isinstance(heat_demand.input_flow, Temporal)
        assert heat_demand.input_flow.is_constant
        assert heat_demand.input_flow.series.loc[0] == 2
        # will also set timeseries:
        assert len(heat_demand.input_flow.timeseries) == 8760
        assert heat_demand.input_flow.timeindex.equals(branch.timeindex)

        # setting attribute to a Series with DatetimeIndex will wrap it in a Temporal:

        heat_demand.input_flow = pd.Series([2] * 8760, index=branch.timeindex)

        assert isinstance(heat_demand.input_flow, Temporal)
        assert heat_demand.input_flow.is_constant
        assert heat_demand.input_flow.series.loc[0] == 2
        # will also set timeseries:
        assert len(heat_demand.input_flow.timeseries) == 8760
        assert heat_demand.input_flow.timeindex.equals(branch.timeindex)

    def test_fix_without_branch(self):
        branch = Branch(year=2025)

        assert isinstance(branch.timeindex, pd.DatetimeIndex)
        assert len(branch.timeindex) == 8760

        heat_demand = HeatDemand()  # don't add it to the branch yet

        # setting attribute to a Temporal will create a copy:

        temporal = Temporal(fix=5)
        heat_demand.input_flow = temporal

        assert isinstance(heat_demand.input_flow, Temporal)
        assert heat_demand.input_flow is not temporal  # has been copied
        assert heat_demand.input_flow.fix == 5
        assert heat_demand.input_flow.timeseries is None

        # adding the building to the branch will provide an index leading to a timeseries:

        branch.add_objects(heat_demand)
        assert heat_demand.input_flow.timeseries is not None

    def test_timeseries_without_branch(self):
        branch = Branch(year=2025)

        assert isinstance(branch.timeindex, pd.DatetimeIndex)
        assert len(branch.timeindex) == 8760

        heat_demand = HeatDemand()  # don't add it to the branch yet

        # setting attribute to a Series with DatetimeIndex will wrap it in a Temporal:

        heat_demand.input_flow = pd.Series([2] * 8760, index=branch.timeindex)

        assert isinstance(heat_demand.input_flow, Temporal)
        assert heat_demand.input_flow.is_constant

        # the original Temporal had a timeindex but as the parent building doesn't have a
        # timeindex (=doesn't have a branch), timeindex will reset and timeseries is unavailable:
        assert heat_demand.input_flow.timeseries is None
        # series is still available, though:
        assert heat_demand.input_flow.series is not None

        # adding the building to the branch will provide an index leading to a timeseries:
        branch.add_objects(heat_demand)
        assert heat_demand.input_flow.timeseries.iloc[0] == 2

    def test_get_all_temporals(self):
        branch = Branch(year=2025)
        heat_demand = HeatDemand()
        branch.add_objects(heat_demand)

        assert len(branch.temporals_recursive()) == 2  # flow and factor


if __name__ == "__main__":
    TestTemporalInHierarchy().test_with_branch()
    TestTemporalInHierarchy().test_fix_without_branch()
    TestTemporalInHierarchy().test_timeseries_without_branch()
    TestTemporalInHierarchy().test_get_all_temporals()
