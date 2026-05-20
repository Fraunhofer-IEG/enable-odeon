import unittest

import pandas as pd
import numpy as np

from odeon.model.expense import (
    ExpenseType,
    FixExpense,
    Actor,
    Financing,
    PerPeriodExpense,
    PerLifeExpense,
    PerThroughputExpense,
    PerUsageExpense,
    PerUsageTimeExpense,
)
from odeon.model.asset import Asset
from odeon.model.base import Branch
from odeon.model.device import BiomassChp, PhotovoltaicDevice
from odeon.model.energy import Medium
from odeon.model.temporal import Temporal


class TestExpense(unittest.TestCase):

    def test_per_life_expense(self):
        ref = Branch(year=2017)

        asset = Asset(dimension=1.0, lifetime_nominal=1)
        ref.add_objects(asset)

        capex_a = PerLifeExpense(fix_value=100)
        capex_b = PerLifeExpense(fix_value=100, per_dimension_value=100)
        capex_c = PerLifeExpense(per_dimension_segments={1.0: 100, 2.0: 400, 4.0: 800})

        # Expenses need a parent:
        asset.add_expenses(capex_a)
        asset.add_expenses(capex_b)
        asset.add_expenses(capex_c)

        assert capex_a.calc() == 100
        assert capex_b.calc() == 200

        # changing the asset's dimension will affect the values of the expenses:
        asset.dimension = 0.5
        assert capex_c.calc() == 100
        asset.dimension = 1.5
        assert capex_c.calc() == 250
        asset.dimension = 5.0
        assert capex_c.calc() == 800
        asset.dimension = 100.0
        assert capex_c.calc() == 800

    def test_per_life_expense_annuity(self):
        ref = Branch(year=2017, financing=Financing(interest_rate=0.03, observation_period=4))

        asset = Asset(dimension=1.0, lifetime_nominal=4)
        ref.add_objects(asset)

        capex_a = PerLifeExpense(fix_value=100)
        asset.add_expenses(capex_a)
        assert round(capex_a.calc_annuity(), 3) == 26.903

        # overwrite financing locally in capex:
        capex_a.financing = Financing(interest_rate=0.03, observation_period=10)
        assert round(capex_a.calc_annuity(), 3) == 27.032

    def test_per_output_expense(self):
        ref = Branch(year=2017)

        pv = PhotovoltaicDevice()
        pv.set_output_flow(
            flow=Temporal(
                fix=0.1,
                timeindex=ref.timeindex,
            ),
        )
        ref.add_objects(pv)

        opex_var = PerThroughputExpense(value=1, socket=pv.get_output_socket())
        pv.add_expenses(opex_var)
        assert np.isclose(opex_var.calc(), 876, rtol=1e-10)

        opex_var = PerThroughputExpense(
            value=pd.Series(1, index=ref.timeindex),
            socket=pv.get_output_socket(),
        )
        pv.add_expenses(opex_var)
        assert np.isclose(opex_var.calc(), 876 * 8760, rtol=1e-10)

    def test_multiple_expenses(self):
        ref = Branch(year=2017)

        chp = BiomassChp(lifetime_nominal=30)
        chp.power_nominal = 5.0
        chp.set_input_flow(flow=Temporal(fix=0.1, timeindex=ref.timeindex))
        ref.add_objects(chp)

        financing = Financing(0.07, observation_period=30)
        e1 = PerLifeExpense(fix_value=100, financing=financing)
        e2 = PerThroughputExpense(value=0.03, socket=Medium.BIOMASS, financing=financing)

        chp.add_expenses(e1)
        chp.add_expenses(e2)

        assert round(chp.calc_annuities(), 3) == 26.28 + 8.059


if __name__ == "__main__":
    TestExpense().test_per_life_expense()
    TestExpense().test_per_life_expense_annuity()
    TestExpense().test_per_output_expense()
    TestExpense().test_multiple_expenses()