import math
import unittest
import warnings
from datetime import datetime

from odeon.model.building import (
    Building,
    BuildingType,
    Use,
    StructureGroup,
    BuildingAgeGroup,
    RefurbishmentStatus,
)
from odeon.model.building_element import Roof, Wall, ElementPhysics
from odeon.model.geometry import NominalGeometry
from odeon.model.building_unit import Household, Commercial, CommercialType, ScalingReference
from odeon.model.decision import BuildingDecision, DecisionType, DecisionState
from odeon.model.expense import BuildingConstructionExpense, BuildingTransformationExpense
from test_base import create_random_series


class TestBuilding(unittest.TestCase):
    def test_building_type_and_use(self):
        # Building 1 (more than 5 Units -> Apartmentblock)
        building1 = Building(name="mfh1", number_of_floors=3)
        building1.building_type = BuildingType.DETACHED
        for i in range(13):
            household = Household(name=f"mfh1_household{i+1}")
            building1.add_building_units(household)

        assert building1.building_type == BuildingType.DETACHED
        building1.usable_area = 0
        assert building1.use == Use.APARTMENTBLOCK

        # Building 2 (5 Units -> Multifamily)
        building2 = Building(name="mfh2", number_of_floors=2)
        building2.building_type = BuildingType.DETACHED
        for i in range(12):
            household = Household(name=f"mfh2_household{i+1}")
            building2.add_building_units(household)
        building2.usable_area = 0
        assert building2.building_type == BuildingType.DETACHED
        assert building2.use == Use.MULTI_FAMILY

        # Building 3 (1 Unit -> Singlefamily)
        building3 = Building(name="efh", number_of_floors=3)
        building3.building_type = BuildingType.TERRACED
        household = Household(name="efh_household")
        building3.add_building_units(household)
        building3.usable_area = 0

        assert building3.building_type == BuildingType.TERRACED
        assert building3.use == Use.SINGLE_FAMILY

        # Building 4 (10 Commercial unit -> Commerical)
        building4 = Building(name="officeblock", number_of_floors=10)
        building4.building_type = BuildingType.HIGHRISE
        for i in range(10):
            office = Commercial(name=f"officeblock_office{i+1}")
            building4.add_building_units(office)
        building4.usable_area = 0
        assert building4.building_type == BuildingType.HIGHRISE
        assert building4.use == Use.COMMERCIAL

        # Building 5 (3 Households, 1 Restaurant -> Mixed)
        building5 = Building(name="mixedbuilding", number_of_floors=4)
        building5.building_type = BuildingType.DETACHED
        restaurant = Commercial(name="mixedbuilding_restaurant")
        building5.add_building_units(restaurant)
        for i in range(3):
            household = Household(name=f"mixedbuilding_household{i+1}")
            building5.add_building_units(household)
        building5.usable_area = 0
        assert building5.building_type == BuildingType.DETACHED
        assert building5.use == Use.MIXED

        # Building 6 (0 Units -> Unknown)
        building6 = Building(name="emptybuilding", number_of_floors=1)
        building6.building_type = BuildingType.MINOR

        building6.usable_area = 0
        assert building6.building_type == BuildingType.MINOR
        assert building6.use == Use.MINOR

    def test_scaling_reference(self):
        # Building 1 (Hospital -> ScalingReference == Beds)
        hospital = Building(name="hospital", number_of_floors=15)
        hospital.building_type = BuildingType.HIGHRISE
        hospital_unit = Commercial(name="hospitalunit")
        hospital_unit.commercial_type = CommercialType.HOSPITAL
        hospital.add_building_units(hospital_unit)
        hospital.usable_area = 0
        beds = ScalingReference(name="beds", amount=200)
        hospital_unit.scaling_reference = beds

        assert isinstance(hospital.building_units[0], Commercial)
        assert hospital.building_units[0].commercial_type == CommercialType.HOSPITAL
        assert hospital.building_units[0].scaling_reference.amount == 200
        assert hospital.building_type == BuildingType.HIGHRISE
        assert hospital.use == Use.COMMERCIAL

    def test_decisions(self):
        b1 = Building()
        b2 = Building()
        b2.exists = False
        d = BuildingDecision(DecisionType.ONLY_ONE, buildings=[b1, b2])
        assert not d.decided
        assert d.existing is b1
        assert b1.existence is DecisionState.UNDECIDED_EXISTING
        assert b2.existence is DecisionState.UNDECIDED_OPTION

        b2.exists = True
        assert d.existing is b2
        assert not b1.exists
        assert b1.existence is DecisionState.UNDECIDED_OPTION
        assert b2.existence is DecisionState.UNDECIDED_EXISTING

        d.decided = True
        assert b1.existence is DecisionState.DECIDED_AGAINST
        assert b2.existence is DecisionState.DECIDED_FOR

        b3 = Building()
        b3.exists = False
        d.add_building(b3)
        assert b1.existence is DecisionState.DECIDED_AGAINST
        assert b2.existence is DecisionState.DECIDED_FOR
        assert b3.existence is DecisionState.DECIDED_AGAINST

    def test_building_construction_expense(self):
        b = Building()
        bce = BuildingConstructionExpense(name="Construction", fix_value=1000)
        b.add_expenses(bce)
        assert b.expenses != []
        assert all([isinstance(e, BuildingConstructionExpense) for e in b.expenses])

    def test_building_transformation_expense(self):
        b = Building()
        bce = BuildingTransformationExpense(name="Transformation Wall", fix_value=1000)
        b.add_expenses(bce)
        assert b.expenses != []
        assert all([isinstance(e, BuildingTransformationExpense) for e in b.expenses])
        assert b.transformation_expenses[0].fix_value == 1000

    def test_building_envelope_area(self):
        b = Building()
        ## Create elements
        wall_N = Wall()
        wall_N_geo = NominalGeometry(area_nominal=40, height=5)
        wall_N.element_geometry = wall_N_geo
        wall_N_phy = ElementPhysics(material="concrete", u_value_w_per_sqm_k=0.25)
        wall_N.element_physics = wall_N_phy

        wall_E = Wall()
        wall_E_geo = NominalGeometry(dimensions_nominal=(None, 8), height=5)
        wall_E.element_geometry = wall_E_geo
        wall_E_phy = ElementPhysics(material="concrete", u_value_w_per_sqm_k=0.2)
        wall_E.element_physics = wall_E_phy

        wall_S = Wall()
        wall_S_geo = NominalGeometry(dimensions_nominal=(5, 8), height=5)
        wall_S.element_geometry = wall_S_geo
        wall_S_phy = ElementPhysics(material="concrete", u_value_w_per_sqm_k=0.22)
        wall_S.element_physics = wall_S_phy

        # Building Element with no area
        wall_W = Wall()
        wall_W_geo = NominalGeometry(height=5)
        wall_W.element_geometry = wall_W_geo
        wall_W_phy = ElementPhysics(material="concrete", u_value_w_per_sqm_k=0.23)
        wall_W.element_physics = wall_W_phy

        # BuildingElement with no Geometry
        roof = Roof()
        roof_phy = ElementPhysics(u_value_w_per_sqm_k=0.3)
        roof.element_physics = roof_phy

        b.add_building_elements([wall_N, wall_E, wall_S, wall_W, roof])  # Add elements to building

        assert b.envelope_surface_area == 80

    def test_building_age(self):
        b = Building()
        b.year_of_construction = 1985
        assert b.year_of_construction_range == (1985, 1985)
        assert b.building_age_group is BuildingAgeGroup.BETWEEN_1984_AND_1994

        b2 = Building()
        b2.year_of_construction_range = (-9999, 1980)
        assert b2.year_of_construction_range == (-9999, 1980)
        assert b2.building_age_group is None

        b2.year_of_construction_range = (1900, 1910)
        assert b2.building_age_group is BuildingAgeGroup.BETWEEN_1860_AND_1918
        assert b2.building_age_group < b.building_age_group
        assert b.building_age_group > b2.building_age_group

        b.year_of_construction = None
        b.building_age_group = BuildingAgeGroup.ABOVE_2010
        assert b.year_of_construction_range == (2011, 9999)

    def test_building_refurbishment_status(self):
        b = Building()
        b.refurbishment_status = RefurbishmentStatus.EXISTING_STATE
        b2 = Building()
        b2.refurbishment_status = RefurbishmentStatus.AMBITIOUS_REFURBISHMENT
        assert b2.refurbishment_status > b.refurbishment_status

    def test_holidays_and_vacations(self):

        b1 = Building()
        b1.usable_area = 100
        b1_bu1 = Household()
        b1.add_building_units(b1_bu1)

        b2 = Building()
        b2.usable_area = 100
        b2_bu1 = Commercial()
        b2.add_building_units(b2_bu1)

        buildings = [b1, b2]

        for b in buildings:
            for bu in b.building_units:
                assert bu.holidays is None
                assert bu.vacations is None
                holiday1 = [datetime(2022, 1, 1)]
                vacation1 = [datetime(2022, 8, 1)]
                list_of_holidays = [datetime(2022, 2, 1), datetime(2022, 2, 2), datetime(2022, 2, 3)]
                list_of_vacations = [datetime(2022, 5, 1), datetime(2022, 5, 2), datetime(2022, 5, 3)]

                bu.holidays = holiday1
                assert len(bu.holidays) == 1
                bu.holidays.extend(list_of_holidays)
                assert len(bu.holidays) == 4

                bu.vacations = [vacation1]
                bu.vacations.extend(list_of_vacations)
                bu.vacations.remove(datetime(2022, 5, 1))
                assert len(bu.vacations) == 3

                bu.holidays.clear()
                bu.vacations.clear()


if __name__ == "__main__":
    TestBuilding().test_building_type_and_use()
    TestBuilding().test_scaling_reference()
    TestBuilding().test_decisions()
    TestBuilding().test_building_construction_expense()
    TestBuilding().test_building_transformation_expense()
    TestBuilding().test_building_envelope_area()
    TestBuilding().test_building_age()
    TestBuilding().test_building_refurbishment_status()
    TestBuilding().test_holidays_and_vacations()
