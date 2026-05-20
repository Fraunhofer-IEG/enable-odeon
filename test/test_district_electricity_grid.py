import unittest
from shapely.geometry import Point, LineString, Polygon
from typing import Union
import pandas as pd

from odeon.model import (
    LinestringGeometry,
    Geometry,
    DistrictElectricityGrid,
    DegNode,
    DegCable,
    ElectricityGridConnection,
    PhotovoltaicDevice,
    WindpowerDevice,
    ElectricityStorage,
    Building,
    EnergySystem,
    Temporal,
    DecisionState,
    NominalGeometry,
    ElectricityDemand,
    ElectricTransformer,
    AirWaterHeatpump,
    Medium,
    Bus,
    TransformerStation,
)
from odeon.processing.district_electricity_grid import unify_hover_nodes, edge_set_partitions_from_neighbors


class TestDeg(unittest.TestCase):
    def test_grid_setup(self):
        """_summary_"""
        self.deg = DistrictElectricityGrid()
        self.node_1 = DegNode(geometry=Geometry(shape=Point([0, 0])))
        self.node_2 = DegNode(geometry=Geometry(shape=Point([1, 1])))
        self.node_3 = DegNode(geometry=Geometry(shape=Point([3, 0])))
        self.node_4 = DegNode(geometry=Geometry(shape=Point([5, 0])))
        self.nodes = [self.node_1, self.node_2, self.node_3, self.node_4]

        self.cable_1 = DegCable(
            geometry=LinestringGeometry(shape=LineString([Point([0, 0]), Point([1, 1])])),
            node_from=self.node_1,
            node_to=self.node_2,
        )
        self.cable_2 = DegCable(
            geometry=LinestringGeometry(shape=LineString([Point([1, 1]), Point([3, 0])])),
            node_from=self.node_2,
            node_to=self.node_3,
        )
        self.cable_3 = DegCable(
            geometry=LinestringGeometry(shape=LineString([Point([1, 1]), Point([5, 0])])),
            node_from=self.node_2,
            node_to=self.node_4,
        )
        self.cables = [self.cable_1, self.cable_2, self.cable_3]

        self.deg.add_nodes(self.nodes)
        self.deg.add_cables(self.cables)
        assert isinstance(self.deg, DistrictElectricityGrid)
        assert len(self.deg.nodes) == 4
        assert len(self.deg.cables) == 3

    def test_attachments_and_lgs_nodes(self):
        self.test_grid_setup()
        k = 0

        for i, node in enumerate(self.deg.nodes):

            grid_con = ElectricityGridConnection()
            node.attachment = grid_con
            demand = ElectricityDemand()
            main_bus = Bus()
            grid_con.set_output(main_bus, at=Medium.ELECTRIC_ENERGY)
            grid_con.set_input(main_bus, at=Medium.ELECTRIC_ENERGY)
            demand.set_input(main_bus, at=Medium.ELECTRIC_ENERGY)

            if i > 0:
                pv = PhotovoltaicDevice()
                pv.set_output(main_bus, medium=Medium.ELECTRIC_ENERGY)

            if i > 1:
                wp = WindpowerDevice()
                wp.set_output(main_bus, at=Medium.ELECTRIC_ENERGY)

            if i > 2:
                s = ElectricityStorage()
                s.power_output_nominal = Temporal()
                s.power_input_nominal = Temporal()
                s.set_output(main_bus, at=Medium.ELECTRIC_ENERGY)
                s.set_input(main_bus, at=Medium.ELECTRIC_ENERGY)
                pv2 = PhotovoltaicDevice()
                pv2.set_output(main_bus, at=Medium.ELECTRIC_ENERGY)

            assert isinstance(node.attachment, ElectricityGridConnection)

        load_nodes, gen_nodes, storage_nodes = self.deg.get_lgs_nodes()
        assert len(load_nodes) == 4
        assert len(storage_nodes) == 1
        assert len(gen_nodes) == 3

    def test_deg_export_df(self):
        self.test_grid_setup()
        buses = self.deg.nodes
        trafo_station = TransformerStation()
        buses[0].attachment = trafo_station
        bus = Bus()
        trafo_station.set_input(bus, at=Medium.ELECTRIC_ENERGY)
        for i in range(2):
            trafo = ElectricTransformer(name=f"transformer_{i}")
            trafo.set_output(bus, at=Medium.ELECTRIC_ENERGY)

        cables = self.deg.cables
        for i, c in enumerate(cables):
            if i == 0:
                c.partitions = set(["NYCWY 4x70/35"])
            else:
                c.partitions = set(["NYCWY 4x185/95"])
        df = self.deg.create_component_df()
        print(df)

    def get_nodes_by_attachment_setup(self):
        # reset deg
        self.test_grid_setup()
        eg1 = ElectricityGridConnection()
        b1 = Bus()
        d1 = ElectricityDemand()
        eg1.set_output(b1, at=Medium.ELECTRIC_ENERGY)
        d1.set_input(b1, at=Medium.ELECTRIC_ENERGY)
        eg2 = ElectricityGridConnection()
        b2 = Bus()
        d2 = ElectricityDemand()
        pv1 = PhotovoltaicDevice()
        eg2.set_output(b2, at=Medium.ELECTRIC_ENERGY)
        eg2.set_input(b2, at=Medium.ELECTRIC_ENERGY)
        d2.set_input(b2, at=Medium.ELECTRIC_ENERGY)
        pv1.set_output(b2, at=Medium.ELECTRIC_ENERGY)
        b3 = Bus()
        eg3 = ElectricityGridConnection()
        wp1 = WindpowerDevice()
        eg3.set_input(b3, at=Medium.ELECTRIC_ENERGY)
        wp1.set_output(b3, at=Medium.ELECTRIC_ENERGY)
        eg4 = ElectricityGridConnection()
        b4 = Bus()
        eg4.set_output(b4, at=Medium.ELECTRIC_ENERGY)
        eg4.set_input(b4, at=Medium.ELECTRIC_ENERGY)
        self.node_1.attachment = eg1
        self.node_2.attachment = eg2

        self.node_3.attachment = eg3
        s = ElectricityStorage()
        s.power_output_nominal = Temporal()
        s.power_input_nominal = Temporal()
        s.set_input(b4, at=Medium.ELECTRIC_ENERGY)
        s.set_output(b4, at=Medium.ELECTRIC_ENERGY)
        self.node_4.attachment = eg4

    def test_get_nodes_by_single_component(self):
        self.get_nodes_by_attachment_setup()
        nodes = self.deg.get_nodes_by_connection_types([WindpowerDevice])
        assert len(nodes) == 1
        assert nodes[0] == self.node_3

    def test_get_nodes_by_multiple_components(self):
        self.get_nodes_by_attachment_setup()
        nodes = self.deg.get_nodes_by_connection_types([ElectricityStorage, WindpowerDevice])
        assert len(nodes) == 2
        assert all(n in [self.node_3, self.node_4] for n in nodes)

    def test_get_nodes_by_components_demand(self):
        self.get_nodes_by_attachment_setup()
        nodes = self.deg.get_nodes_by_connection_types([ElectricityDemand])
        assert len(nodes) == 2
        assert all(n in [self.node_1, self.node_2] for n in nodes)


class TestDegProcessing(unittest.TestCase):
    def grid_setup(self):
        """_summary_"""
        self.deg = DistrictElectricityGrid()
        self.node_1 = DegNode(geometry=Geometry(shape=Point([0, 0])))
        self.node_2 = DegNode(geometry=Geometry(shape=Point([1, 1])))
        self.node_3 = DegNode(geometry=Geometry(shape=Point([3, 0])))
        self.node_4 = DegNode(geometry=Geometry(shape=Point([5, 0])))
        self.nodes = [self.node_1, self.node_2, self.node_3, self.node_4]

        self.cable_1 = DegCable(
            geometry=LinestringGeometry(shape=LineString([Point([0, 0]), Point([1, 1])])),
            node_from=self.node_1,
            node_to=self.node_2,
        )
        self.cable_2 = DegCable(
            geometry=LinestringGeometry(shape=LineString([Point([1, 1]), Point([3, 0])])),
            node_from=self.node_2,
            node_to=self.node_3,
        )
        self.cable_3 = DegCable(
            geometry=LinestringGeometry(shape=LineString([Point([1, 1]), Point([5, 0])])),
            node_from=self.node_2,
            node_to=self.node_4,
        )
        self.cables = [self.cable_1, self.cable_2, self.cable_3]

        self.deg.add_nodes(self.nodes)
        self.deg.add_cables(self.cables)

    def test_edge_set_partitions_from_neighbors(self):
        self.grid_setup()
        self.cable_2.add_partition("cable_type_x")
        edges = [c for c in self.cables if len(c.partitions) == 0]
        print(f"edges: {edges}")
        edge_set_partitions_from_neighbors(network=self.deg, edges=edges)

        assert self.cable_1.partitions == {"cable_type_x"}
        assert self.cable_2.partitions == {"cable_type_x"}
        assert self.cable_3.partitions == {"cable_type_x"}

    def test_unify_hover_nodes(self):
        self.grid_setup()
        self.node_5 = DegNode(geometry=Geometry(shape=Point([0, 0])))
        self.cable_4 = DegCable(
            geometry=LinestringGeometry(shape=LineString([Point([5, 0]), Point([0, 0])])),
            node_from=self.node_4,
            node_to=self.node_5,
        )
        self.deg.add_nodes([self.node_5])
        self.deg.add_cables([self.cable_4])

        unify_hover_nodes(self.deg)
        assert len(self.deg.nodes) == 4
        assert len(self.deg.cables) == 4
        con_node = next(n for n in [self.node_5, self.node_1] if n in self.deg.nodes)


if __name__ == "__main__":
    # TestDeg().test_grid_setup()
    # TestDeg().test_deg_export_df()
    # TestDeg().test_attachments_and_lgs_nodes()
    # TestDeg().test_get_nodes_by_components_demand()
    # TestDeg().test_get_nodes_by_multiple_components()
    # TestDeg().test_get_nodes_by_single_component()
    # TestDegProcessing().test_edge_set_partitions_from_neighbors()
    TestDegProcessing().test_unify_hover_nodes()
