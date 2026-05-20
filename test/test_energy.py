from typing import List
import unittest
import networkx as nx
import matplotlib.pyplot as plt

from odeon.model.energy import DagNode, TypeDagNode, Medium, MediumManager

from utils import lists_equal


class TestMedium(unittest.TestCase):

    def test_energy_types(self):

        mm = MediumManager()
        mm2 = MediumManager()
        assert mm is mm2  # it's a singleton

        assert mm[Medium.GASEOUS_CHEMICAL_ENERGY].parents == [mm[Medium.CHEMICAL_ENERGY]]

        assert mm[Medium.GASEOUS_CHEMICAL_ENERGY].parents == [mm[Medium.CHEMICAL_ENERGY]]
        assert lists_equal(mm[Medium.GASEOUS_CHEMICAL_ENERGY].supers, [mm[Medium.CHEMICAL_ENERGY], mm[Medium.ENERGY]])
        assert mm[Medium.GASEOUS_CHEMICAL_ENERGY].roots == [mm[Medium.ENERGY]]

        assert mm[Medium.NATURAL_GAS] in mm[Medium.GASEOUS_CHEMICAL_ENERGY].children
        assert lists_equal(
            mm[Medium.GASEOUS_CHEMICAL_ENERGY].subs,
            [mm[Medium.NATURAL_GAS], mm[Medium.SYNGAS], mm[Medium.BIOGAS], mm[Medium.HYDROGEN]],
        )

        assert mm[Medium.GASEOUS_CHEMICAL_ENERGY].generalizes(mm[Medium.GASEOUS_CHEMICAL_ENERGY], include_same=True)
        assert not mm[Medium.GASEOUS_CHEMICAL_ENERGY].generalizes(
            mm[Medium.GASEOUS_CHEMICAL_ENERGY], include_same=False
        )
        assert mm[Medium.GASEOUS_CHEMICAL_ENERGY].generalizes(mm[Medium.NATURAL_GAS])

        assert mm[Medium.GASEOUS_CHEMICAL_ENERGY].specifies(mm[Medium.GASEOUS_CHEMICAL_ENERGY], include_same=True)
        assert not mm[Medium.GASEOUS_CHEMICAL_ENERGY].specifies(mm[Medium.GASEOUS_CHEMICAL_ENERGY], include_same=False)
        assert mm[Medium.GASEOUS_CHEMICAL_ENERGY].specifies(mm[Medium.ENERGY])

        assert not mm[Medium.GASEOUS_CHEMICAL_ENERGY].specifies(mm[Medium.BIOMASS])
        assert not mm[Medium.BIOMASS].specifies(mm[Medium.GASEOUS_CHEMICAL_ENERGY])

        assert mm[Medium.GASEOUS_CHEMICAL_ENERGY].closest_common_super(mm[Medium.BIOMASS]) is mm[Medium.CHEMICAL_ENERGY]

        digraph = mm[Medium.GASEOUS_CHEMICAL_ENERGY].digraph
        nx.draw_planar(digraph, with_labels=True)
        plt.show()

        assert mm[Medium.CHEMICAL_ENERGY].superiority(mm[Medium.GASEOUS_CHEMICAL_ENERGY]) == 1
        assert mm[Medium.CHEMICAL_ENERGY].superiority(mm[Medium.CHEMICAL_ENERGY]) == 0
        assert mm[Medium.GASEOUS_CHEMICAL_ENERGY].superiority(mm[Medium.CHEMICAL_ENERGY]) == -1
        assert mm[Medium.ENERGY].superiority(mm[Medium.BIOMASS]) == 3


if __name__ == "__main__":
    TestMedium().test_energy_types()
