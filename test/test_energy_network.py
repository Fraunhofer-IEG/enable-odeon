from odeon.model import (
    EnergyNetwork,
    Node,
    Edge,
    BuildingDhnConnection,
    TransferStation,
    WallBox,
)

import unittest


class TestEnergyNetwork(unittest.TestCase):

    def test_apply_connections_from_attachments(self):

        dhncon1 = BuildingDhnConnection()
        dhncon2 = BuildingDhnConnection()
        wallbox = WallBox()
        transfer_station = TransferStation()

        node1 = Node(attachment=dhncon1)
        node2 = Node(attachment=dhncon2)
        node3 = Node(attachment=transfer_station)

        energy_network = EnergyNetwork(nodes=[node1, node2, node3])

        energy_network.apply_connections_from_attachments(
            input_component_types=[TransferStation],
            output_component_types=[BuildingDhnConnection],
        )

        assert dhncon1 in energy_network.output_components
        assert dhncon2 in energy_network.output_components
        assert transfer_station in energy_network.input_components
        assert wallbox not in energy_network.input_components


if __name__ == "__main__":
    TestEnergyNetwork().test_apply_connections_from_attachments()
