import unittest

from odeon.model import  Bus, Medium, PhotovoltaicDevice, Battery, Heatpump, AssetDecision, DecisionState, DecisionType, Medium


class TestDevice(unittest.TestCase):
    def test_create(self):
        pv = PhotovoltaicDevice()
        assert pv.output_sockets[0].parent is pv
        assert pv.output_sockets[0].other is None
        assert pv.output_sockets[0].medium is Medium.ELECTRIC_ENERGY

        bat = Battery()
        assert bat.input_sockets[0].parent is bat
        assert bat.input_sockets[0].other is None
        assert bat.output_sockets[0].parent is bat
        assert bat.output_sockets[0].other is None
        assert bat.output_sockets[0].medium is Medium.ELECTRIC_ENERGY

        el = Bus()
        pv.set_output(el)
        bat.set_input(el)
        bat.set_output(el)
        assert pv in el.input_components and bat in el.input_components
        assert bat in el.output_components
        pv.set_output_factor(0.5)
        assert pv.get_output_factor(el).fix == 0.5
        assert pv.get_output_factor(Medium.ELECTRIC_ENERGY).fix == 0.5

        lo = Bus()
        hi = Bus()
        hp = Heatpump()
        hp.set_output_factor(3)
        hp.set_output(hi)
        hp.set_input(lo, at=Medium.THERMAL_ENERGY)
        hp.set_input(el, at=Medium.ELECTRIC_ENERGY)
        assert hp.get_output_factor().fix == 3
        assert len(el.input_components) == 2
        assert len(el.output_components) == 2

    def test_alteration(self):
        pv_1 = PhotovoltaicDevice()
        pv_2 = PhotovoltaicDevice()
        pv_2.exists = False
        d = AssetDecision(DecisionType.ONLY_ONE, devices=[pv_1, pv_2])
        assert not d.decided
        assert d.existing is pv_1
        assert pv_1.existence is DecisionState.UNDECIDED_EXISTING
        assert pv_2.existence is DecisionState.UNDECIDED_OPTION

        pv_2.exists = True
        assert d.existing is pv_2
        assert not pv_1.exists

        d.decided = True
        assert pv_1.existence is DecisionState.DECIDED_AGAINST
        assert pv_2.existence is DecisionState.DECIDED_FOR


if __name__ == "__main__":
    TestDevice().test_create()
    TestDevice().test_alteration()
