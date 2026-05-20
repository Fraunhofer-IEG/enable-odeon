import unittest
import random
import math
import pandas as pd
from pandas.testing import assert_series_equal
from copy import deepcopy
from datetime import datetime

from odeon.model import (
    Project,
    Branch,
    Building,
    Bus,
    StructureGroup,
    EnergySystem,
    Boiler,
    RoofType,
    Household,
    Resident,
    BuildingDecision,
    DecisionType,
    Object,
    AirWaterHeatpump,
    Medium,
    Group,
    Organizer,
    Structure,
    Component,
    Socket,
    BuildingThermalZone,
)


def simple_relative_factory(series: pd.Series):
    # Sets same value for every element in series (So for a series of 10 entries every value in relative will be 0.1)
    return pd.Series(1 / len(series), index=series.index)


def create_random_series(min_val: int, max_val: int, length: int) -> pd.Series:
    idx = pd.date_range("2023-01-01", periods=length, freq="h")
    ts = pd.Series(random.choices(range(min_val, max_val + 1), k=len(idx)), index=idx, dtype="float64")
    return ts


class TestCopyObject(unittest.TestCase):
    def test_copy_objects(self):

        # Define building to be copied
        r = Resident(name="Max Mustermann")

        bu = Household(name="super_duper_unit")
        bu.heating_demand = create_random_series(min_val=0, max_val=1000, length=8760)
        bu.add_residents(r)

        b = Building(name="super_nice_test_building")
        b.building_geometry_nominal.roof_type = RoofType.FLAT
        b.usable_area = 200
        b.electricity_demand = create_random_series(min_val=0, max_val=1000, length=8760)
        b.add_building_units(bu)

        hp = AirWaterHeatpump()
        bus = Bus()
        b.energy_system.add_components([hp, bus])

        # Copy building defined above
        cb = b.deepcopy(down=True, up=False, sideways=False)

        # basic properties are identical except for id:
        assert cb.id != b.id
        assert isinstance(cb, Building)
        assert cb.building_geometry_nominal.roof_type == RoofType.FLAT
        assert cb.name == b.name
        assert cb.usable_area == 200

        # temporals are new objects with same data:
        assert_series_equal(cb.electricity_demand.series, b.electricity_demand.series)
        temporals_original = [t for o in b.offspring for t in o.temporals]
        temporals_copy = [t for o in cb.offspring for t in o.temporals]
        assert not (set(temporals_copy) & set(temporals_original))  # no overlap

        # basic properties of building unit are identical except for id:
        assert cb.building_units[0].name == b.building_units[0].name
        assert cb.building_units[0].id != b.building_units[0].id
        assert cb.building_units[0].residents[0].name == b.building_units[0].residents[0].name
        assert cb.building_units[0].residents[0].id != b.building_units[0].residents[0].id

        # energy system has changed:
        assert cb.energy_system is not b.energy_system
        assert cb.energy_system.parent is not b
        assert cb.energy_system.parent is cb
        assert not (set(cb.energy_system.components) & set(b.energy_system.components))  # no common elements

    def test_copy_structure_group(self):
        sg = StructureGroup()
        sg2 = StructureGroup()
        building = Building()
        sg.add_structures(building)
        sg2.add_structures(sg)
        csg = sg2.deepcopy(down=True, up=False, sideways=False)
        assert csg.id != sg2.id
        assert csg.structures[0].id != sg2.structures[0].id
        assert csg.structures[0].structures[0].id != sg2.structures[0].structures[0].id


class TestHierarchy(unittest.TestCase):
    def test_affiliations(self):
        project = Project()
        branch = Branch(project=project, year=2021)

        obj1 = Object()
        branch.add_objects(obj1)
        org1 = Group()
        branch.add_organizers(org1)
        org1.add_members(obj1)
        assert org1 in obj1.affiliations
        assert org1 in obj1.affiliations_recursive
        assert org1 in branch.organizers
        assert obj1 in branch.offspring
        assert obj1 in branch.objects

        org2 = Group()
        branch.add_organizers(org2)
        org2.add_members(org1)
        assert org2 in org1.affiliations
        assert org1 in org2.members
        assert org2 in obj1.affiliations_recursive
        assert org2 in branch.organizers

        es = EnergySystem()
        s = Structure()
        s.energy_system = es  # will set parent
        branch.add_objects([s])
        assert es in s.children
        assert es in s.offspring
        assert es in branch.offspring
        assert es.parent is es.root is s
        assert es.branch is branch
        assert s.parent is branch
        assert s.root is s

        org1.add_members(s)
        assert s in org1.members
        assert org1 in s.affiliations
        assert org1 not in es.affiliations
        assert org1 in es.affiliations_recursive

    def test_hierarchy(self):
        building = Building()
        assert building.parent is None
        assert building.building_geometry_nominal.parent is building
        household1 = Household()
        household2 = Household()
        household3 = Household()
        building.add_building_units([household1, household2, household3])

        decision = BuildingDecision(type_=DecisionType.ONLY_ONE, buildings=[building])
        es = EnergySystem()
        household1.energy_system = es
        device = Boiler()
        household1.energy_system.add_components(device)

        assert all(u.parent is building for u in building.building_units)
        assert set(building.children) == set(
            [building.building_geometry_nominal, *building.building_units, building.energy_system]
        )
        assert decision.parent is None
        assert building.associated == [decision]
        assert device.get_ancestors_of_type(Object) == [household1.energy_system, household1, building]
        assert device.get_ancestors_of_type(Building) == [building]
        assert device.get_ancestors_of_type(Household) == [household1]
        assert device.get_ancestors_of_type(EnergySystem) == [household1.energy_system]
        assert set(building._get_offspring_by_type(Object)) == set(
            [
                building.building_geometry_nominal,
                *building.building_units,
                building.energy_system,
                household1.energy_system,
                household2.energy_system,
                household3.energy_system,
                device,
                *device.sockets,
            ]
            + [s.link for s in device.sockets]
        )

    def test_unspecified_children_setters(self):
        """
        Test whether parent-child relationships can be successfully created by
        using `parent.add_children()` and `child.set_parent()`.
        """
        # Create objects
        project = Project()
        branch = Branch(year=2023)
        building = Building()
        building_thermal_zone = BuildingThermalZone()
        household = Household()
        resident = Resident()

        # Set relationships using `add_children()` - this should work if
        # possible children types are unambiguous:
        project.add_branches(branch)
        branch.add_objects(building)
        building.add_children(household)
        building.add_children(building_thermal_zone)
        household.add_children(resident)

        # We can't add the same child twice:
        with self.assertRaises(Exception):
            building.add_children(household)

        # We can't set the same child twice:
        with self.assertRaises(Exception):
            building.add_children(building_thermal_zone)

        # Verify relationships
        assert branch in project.branches
        assert building in branch.objects
        assert building_thermal_zone is building.building_thermal_zone
        assert household in building.building_units
        assert resident in household.residents

        # Dissolve relationships by setting parent to None:
        resident.parent = None
        assert resident.parent is None
        assert resident not in household.residents

        # For classes with ambiguous possible children types, calling add_children()
        # without specifying the type should raise an error:
        with self.assertRaises(Exception):
            component = Component()
            socket = Socket()
            component.add_children(socket)  # Ambiguous: Input sockets and output sockets


class TestBranch(unittest.TestCase):
    def test_simple_branches(self):
        project = Project()
        main_branch = Branch(year=2023)
        b1 = Building()
        b2 = Building()
        b3 = Building()
        main_branch.add_objects([b1, b2, b3])
        project.main_branch = main_branch

        assert b1.branch == main_branch
        assert b2.branch == main_branch
        assert b3.branch == main_branch
        assert b1.project == project
        assert b2.project == project
        assert b3.project == project

        branch1 = Branch(year=2035)
        b4 = Building()
        b5 = Building()
        b6 = Building()
        branch1.add_objects([b4, b5, b6])
        project.add_branches(branch1)

        assert b4.branch == branch1
        assert b5.branch == branch1
        assert b6.branch == branch1
        assert b4.project == project
        assert b5.project == project
        assert b6.project == project

        branch2 = Branch(year=2060)
        b7 = Building()
        b8 = Building()
        b9 = Building()
        branch2.add_objects([b7, b8, b9])
        project.add_branches(branch2)

        assert b7.branch == branch2
        assert b8.branch == branch2
        assert b9.branch == branch2
        assert b7.project == project
        assert b8.project == project
        assert b9.project == project

        branch3 = project.bifurcate_from_branch(branch1)
        print(branch3)

        # sze3 = deepcopy(project.reference)  # MJ: Not working yet. Needs overwrite in Szenario

    def test_management_methods(self):
        project = Project()
        project.main_branch = Branch(year=2023)
        b_main = Building(name="my_name")
        project.main_branch.add_objects(b_main)

        branch1 = project.bifurcate_from_main()
        b_branch1 = branch1.find_objects(Building)[0]
        assert b_branch1.name == "my_name"

        branch2 = project.bifurcate_from_branch(source_branch=branch1)
        b_branch2 = branch2.find_objects(Building)[0]
        assert b_branch2.name == "my_name"

        assert Branch.get_chained_reference(object=b_branch2) is b_main
        assert branch2.get_object_by_chained_reference(reference=b_branch1) is b_branch2
        assert branch2.get_object_by_chained_reference(reference=b_main) is b_branch2


if __name__ == "__main__":
    # TestBranch().test_simple_branches()
    # TestBranch().test_management_methods()
    # TestCopyObject().test_copy_objects()
    # TestCopyObject().test_copy_structure_group()
    # TestHierarchy().test_affiliations()
    # TestHierarchy().test_hierarchy()
    TestHierarchy().test_unspecified_children_setters()
