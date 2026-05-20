import unittest

from odeon.model.building import Building, Site, Household, StructureGroup, BuildingType, EfficiencyLevel
from odeon.model.geometry import NominalGeometry
from odeon.model import Project, Branch, Group


class TestGroupOfGroup(unittest.TestCase):
    def test_simple_group(self):
        # Empty Project
        p = Project()

        ref = Branch(year=2021)
        p.main_branch = ref

        b1 = Building()
        b2 = Building()
        ref.add_objects([b1, b2])

        # Group
        group = Group(branch=ref)
        group.add_members([b1, b2])

        assert group.project is p
        assert group.branch is ref
        assert b1.branch is ref
        assert b1.project is p
        assert b2.project is p

        assert b1 in group.members and b2 in group.members

    def test_add_group_to_group(self):
        building1 = Building()
        building2 = Building()

        sgroup1 = StructureGroup()
        sgroup1.add_structures([building1, building2])

        assert building1 in sgroup1.structures
        assert building2 in sgroup1.structures

        sgroup2 = StructureGroup()
        sgroup1.remove_structures(building2)
        sgroup2.add_structures([building2, sgroup1])

        assert building2 in sgroup2.structures
        assert sgroup1 in sgroup2.structures
        assert building1 in sgroup2.structures[-1].structures

        assert len(sgroup2._get_offspring_by_type(Building)) == 2
        assert all(isinstance(b, Building) for b in sgroup2._get_offspring_by_type(Building))

        sgroup2.remove_structures([building2, sgroup1])
        assert len(sgroup2._get_offspring_by_type(Building)) == 0


if __name__ == "__main__":
    TestGroupOfGroup().test_simple_group()
    TestGroupOfGroup().test_add_group_to_group()
