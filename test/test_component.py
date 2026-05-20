import unittest

import pandas as pd

from odeon.model import Branch, Component, Socket, FixedComponent, Link, ThermalComponent, EnergySystem, Medium, Temporal
from odeon.samples import sample_series


class TestSocket(unittest.TestCase):

    def test_socket_other(self):
        s1 = Socket()
        assert s1.is_abstract

        s2 = Socket()
        s1.other = s2
        assert not s1.is_abstract

        assert s1.other is s2
        assert s2.other is s1

        s2.remove_other()
        assert s2.other is None
        assert s1.other is None

        s2.other = s1
        assert s2.other is s1
        assert s1.other is s2

    def test_socket_flow(self):
        flow = Temporal(total=5)
        s1 = Socket()
        s2 = Socket()

        # setting the flow in socket 1...
        s1.flow = flow
        assert s1.flow.total == 5

        # ...will also make it available in socket 2 when linked
        s1.other = s2
        assert s2.flow is s1.flow

        # ... when untied, the flow remains in socket 1 and is lost in socket 2:
        s1.other = None
        assert s1.flow.total == 5
        assert s2.flow.is_empty

        # when linking from the other side, the flow of socket 1 will be
        # available in socket 1 again:
        flow2 = Temporal(total=9)
        s2.other = s1
        assert s2.flow.total == 5

        # setting the flow will also affect the value in socket 1:
        s2.flow = flow2
        assert s1.flow.total == 9

        # when untieing, flow will be kept in original socket (2):
        s1.other = None
        assert s1.flow.is_empty
        assert s2.flow.total == 9

        # this also works the other way round:
        s2.other = s1
        assert s1.flow.total == s2.flow.total == 9
        s2.other = None
        assert s2.flow.total == 9

    def test_socket_link_1(self):
        flow = Temporal(total=5)
        s1 = Socket(medium=Medium.AIR_THERMAL_ENERGY)
        s2 = Socket(flow=flow, other=s1)

        s2.medium = Medium.WATER_THERMAL_ENERGY

        l = s1.link

        assert l.parent is s2
        assert l.sockets == [s2, s1]
        assert s2.link is l
        assert l.flow.total == 5
        assert l.medium is Medium.THERMAL_ENERGY

    def test_socket_link_2(self):
        flow = Temporal(total=5)

        c1 = Component()
        c2 = Component()
        c1.add_output(c2, medium=Medium.AIR_THERMAL_ENERGY, flow=flow)

        s1 = c1.output_socket
        s2 = c2.input_socket

        l = s1.link
        assert s2.link is l
        assert l.sockets == [s2, s1]
        assert l.other_component(c1) is c2
        assert l.other_component(c2) is c1
        assert l.flow.total == 5
        assert l.medium is Medium.AIR_THERMAL_ENERGY

        # dissolving the connection will remove the link and replace it by two new ones:
        s1.other = None

        l1 = s1.link
        l2 = s2.link
        assert l.parent is None
        assert l.sockets == []
        assert l is not l1
        assert l is not l2
        assert l1 is not l2

        assert l1.flow.total == 5
        assert l1.medium is Medium.AIR_THERMAL_ENERGY

        assert l2.flow.is_empty
        assert l2.medium is None

    def test_socket_add_in_component(self):
        flow = Temporal(total=5)
        s1 = Socket(medium=Medium.AIR_THERMAL_ENERGY)
        s2 = Socket(flow=flow, other=s1)

        c1 = Component()
        c2 = Component()
        c1.add_output_socket(s1)

        # can't add a Socket as output if its other socket is already an output socket:
        self.assertRaises(
            Exception,
            lambda: c2.add_output_socket(s2),
        )

        c1.add_input_socket(s2)
        assert s1.other is s2
        assert s2.other is s1

    def test_socket_activity(self):
        srs = sample_series()
        ts = Temporal(timeseries=srs)
        s = Socket(flow=ts.copy())

        s.activity = True
        s.apply_activity()
        assert s.flow.total == ts.total

        s.activity = False
        s.apply_activity(reset_activity=False)
        assert s.flow.total == 0

        s.apply_activity(reset_activity=True)
        assert s.flow.total == 0

        s.flow = ts.copy()
        s.apply_activity()
        assert s.flow.total == ts.total

        a = ts.timeseries > ts.timeseries.mean()

        b = Branch(year=2022)
        b.add_objects(s)
        s.flow = ts.copy()
        s.activity = a
        s.apply_activity()
        assert 0 < s.flow.total < ts.total


class TestComponent(unittest.TestCase):

    def test_component_general(self):
        c1 = Component()
        s1 = Socket(medium=Medium.BIOMASS, flow=Temporal(total=10))
        c1.add_input_socket(s1)

        assert c1.is_sink
        assert not c1.is_intermediate
        assert not c1.is_source

        assert c1.children == [s1]
        assert s1.parent is c1

        assert c1.get_input_mediums() == [Medium.BIOMASS]
        assert c1.get_input_factor(s1).fix == 1.0  # default value
        assert c1.get_input_flow().total == 10

        c1.set_input_factor(5)

        assert c1.get_input_factor().fix == 5
        assert c1.get_input_factor(Medium.BIOMASS).fix == 5

    def test_component_get_socket(self):
        c1 = Component()
        s1 = Socket(medium=Medium.BIOMASS)
        c1.add_input_socket(s1)

        assert c1.get_input_sockets() == [s1]
        assert c1.get_output_sockets() == []
        assert c1.get_input_sockets(s1) == [s1]
        assert c1.get_input_sockets(Medium.BIOMASS) == [s1]
        assert c1.get_input_sockets(Medium.CHEMICAL_ENERGY) == []
        assert c1.get_input_sockets(Medium.CHEMICAL_ENERGY, medium_relation="socket_specifies") == [s1]
        assert c1.get_input_sockets(Medium.CHEMICAL_ENERGY, medium_relation="socket_generalizes") == []
        assert c1.get_input_sockets(Medium.BIOMASS_PELLETS, medium_relation="socket_generalizes") == [s1]
        assert c1.get_input_sockets(Medium.BIOMASS_PELLETS, medium_relation="socket_specifies") == []
        assert c1.get_input_sockets(Medium.BIOMASS_PELLETS, medium_relation="linear") == [s1]
        assert c1.get_input_sockets(Medium.ELECTRIC_ENERGY, medium_relation="linear") == []

        s2 = Socket(medium=Medium.BIOGAS)
        c2 = Component(output_sockets=[s2])
        s2.other = s1

        assert s1.link.medium is Medium.CHEMICAL_ENERGY
        assert c1.get_input_sockets(Medium.CHEMICAL_ENERGY, medium_considered="link") == [s1]
        assert c1.get_input_sockets(Medium.CHEMICAL_ENERGY, medium_considered="socket") == []

    def test_component_add_medium(self):
        c1 = Component()

        ts = Temporal(total=4)
        c1.add_output(new=Medium.ELECTRIC_ENERGY, flow=ts, factor=0.5)

        assert c1.get_output_mediums() == [Medium.ELECTRIC_ENERGY]
        assert c1.get_output_factor().fix == 0.5

    def test_component_add_set_component(self):
        c1 = Component()
        c2 = Component()

        ts = Temporal(total=4)
        c1.add_output(c2, medium=Medium.ELECTRIC_ENERGY, flow=ts)

        assert c1.output_components == [c2]
        assert c2.input_components == [c1]
        assert len(c2.input_flows) == 1 and c2.input_flows[0].total == ts.total
        assert len(c1.output_flows) == 1 and c1.output_flows[0].total == ts.total

        c2_2 = Component()
        c1.set_output(new=c2_2)

        assert c2_2.input_components == [c1]
        assert c2.input_components == []
        assert c1.output_components == [c2_2]
        assert c2_2.get_input_flow().total == 4
        assert c2.get_input_flow().is_empty

    def test_component_activity(self):

        f = sample_series()
        false_srs = pd.Series(False, index=f.index)
        true_srs = pd.Series(True, index=f.index)
        mixed_srs = f > f.max() * 0.3
        mixed_srs_2 = f < f.max() * 0.8

        b = Branch(year=2022)
        c = Component(branch=b)
        s1 = Socket(flow=Temporal(timeseries=f), medium=Medium.ENERGY)
        c.add_output_socket(s1)

        c.activity = True
        c.apply_activity()
        assert c.get_output_flow().total == f.sum()

        c.activity = mixed_srs
        c.apply_activity()
        assert c.get_output_flow().total == (mixed_srs * f).sum()

        c.set_output_flow(Temporal(timeseries=f))
        c.activity = mixed_srs
        c.get_output_socket().activity = mixed_srs_2
        c.apply_activity()
        assert 0 < c.get_output_flow().total < (f * mixed_srs).sum()

    def test_component_following_previous(self):
        a = Component()
        b = Component()
        c1 = Component()
        c2 = Component()

        a.add_output(b)
        b.add_output(c1)
        b.add_output(c2)

        assert set(a.following_components) == set([b, c1, c2])
        assert set(c2.previous_components) == set([a, b])

        # linked components will always return self:
        assert set(c2.linked_components) == set([a, b, c1, c2])

        # introduce loop:
        d = Component()
        d.add_input(c1)
        d.add_output(b)

        assert set(a.following_components) == set([b, c1, c2, d])

        # calling this for components in loops will also return the component itself:
        assert set(b.following_components) == set([b, c1, c2, d])
        assert set(c1.following_components) == set([b, c1, c2, d])
        assert set(d.previous_components) == set([a, b, c1, d])

        # linked components will always return self:
        assert set(d.linked_components) == set([a, b, c1, c2, d])


class TestThermalComponent(unittest.TestCase):

    def test(self):
        a = ThermalComponent()
        b = ThermalComponent()

        a.add_output(b, medium=Medium.AIR_THERMAL_ENERGY)

        temp_tsrs = Temporal(total=5)

        a.set_flow_forward_temperature(flow_temperature=temp_tsrs)

        # forward temperature is available now in a:
        assert a.get_flow_forward_temperature().total == temp_tsrs.total
        assert a.get_flow_return_temperature().is_empty

        # shorthands are available, but can lead to exceptions:
        assert a.output_forward_temperature.total == temp_tsrs.total
        assert a.output_return_temperature.is_empty
        self.assertRaises(Exception, a.input_forward_temperature)

        # and also in b if we check symmetrically:
        assert b.get_flow_forward_temperature().is_empty
        assert b.get_flow_forward_temperature(symmetric=True).total == temp_tsrs.total
        assert b.input_forward_temperature.is_empty

        # removing temperature in b will not remove it from a:
        b.set_flow_forward_temperature(flow_temperature=None)
        assert b.get_flow_forward_temperature(symmetric=True).total is temp_tsrs.total
        assert a.get_flow_forward_temperature().total is temp_tsrs.total

        # unless we use symmetry:
        b.set_flow_forward_temperature(flow_temperature=None, symmetric=True)
        assert b.get_flow_forward_temperature(symmetric=True).is_empty
        assert a.get_flow_forward_temperature().is_empty


if __name__ == "__main__":
    # TestSocket().test_socket_other()
    # TestSocket().test_socket_flow()
    TestSocket().test_socket_link_1()
    TestSocket().test_socket_link_2()
    TestSocket().test_socket_add_in_component()
    TestSocket().test_socket_activity()
    TestComponent().test_component_general()
    TestComponent().test_component_get_socket()
    TestComponent().test_component_add_medium()
    TestComponent().test_component_add_set_component()
    TestComponent().test_component_activity()
    TestComponent().test_component_following_previous()
    TestThermalComponent().test()
