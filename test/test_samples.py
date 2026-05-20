import unittest
from odeon.model import (
    Branch,
    BuildingType,
    RefurbishmentStatus,
    Building,
    Household,
    Commercial,
    CommercialType,
    Use,
)
from odeon.samples.building import sample_building
from odeon.samples.base import sample_branch


class TestSamples(unittest.TestCase):
    def test_sample_building(self):
        branch = Branch(year=2021)
        b = sample_building(branch, random_sample=False)

        assert b.year_of_construction == 1958
        assert b.usable_area == 450
        assert b.building_type == BuildingType.DETACHED
        assert b.refurbishment_status == RefurbishmentStatus.STANDARD_REFURBISHMENT

        assert len(b.building_elements) == 24
        assert len([be for be in b.building_elements if be.element_geometry is not None]) == 24
        assert len([be for be in b.building_elements if be.element_geometry.polygon is not None]) == 24

        assert len([be for be in b.building_elements if be.element_physics is not None]) == 24
        assert len([be for be in b.building_elements if be.element_physics.u_value_w_per_sqm_k is not None]) == 24
        assert len([be for be in b.building_elements if be.element_physics.transparency is not None]) == 24
        assert len([be for be in b.building_elements if be.adjacent_environment is not None]) == 24

        assert len(b.building_units) == 6
        households = [bu for bu in b.building_units if isinstance(bu, Household)]
        assert len(households) == 3
        assert len(households[0].residents) == 3
        assert len(households[1].residents) == 3
        commercials = [bu for bu in b.building_units if isinstance(bu, Commercial)]
        assert len(commercials) == 3
        assert commercials[0].commercial_type is CommercialType.GROCERIES
        assert commercials[1].commercial_type is CommercialType.GROCERIES
        assert len([c for c in commercials if c.scaling_reference.name == "Erwerbstaetige"]) == 3
        assert len([c for c in commercials if c.scaling_reference.amount == 20]) == 3

        assert round(b.heating_demand.total) == 1096924
        assert round(b.dhw_demand.total) == 1096924
        assert round(b.electricity_demand.total) == 1096924

    def test_sample_building_residential(self):
        branch = Branch(year=2021)
        b = sample_building(branch, random_sample=False, type="residential")

        assert b.year_of_construction == 1958
        assert b.usable_area == 450
        assert b.building_type == BuildingType.DETACHED
        assert b.refurbishment_status == RefurbishmentStatus.STANDARD_REFURBISHMENT

        assert len(b.building_elements) == 24
        assert len([be for be in b.building_elements if be.element_geometry is not None]) == 24
        assert len([be for be in b.building_elements if be.element_geometry.polygon is not None]) == 24

        assert len([be for be in b.building_elements if be.element_physics is not None]) == 24
        assert len([be for be in b.building_elements if be.element_physics.u_value_w_per_sqm_k is not None]) == 24
        assert len([be for be in b.building_elements if be.element_physics.transparency is not None]) == 24
        assert len([be for be in b.building_elements if be.adjacent_environment is not None]) == 24

        assert len(b.building_units) == 6
        households = [bu for bu in b.building_units if isinstance(bu, Household)]
        assert len(households) == 6
        assert len([hh for hh in households if len(hh.residents) == 3]) == 6
        commercials = [bu for bu in b.building_units if isinstance(bu, Commercial)]
        assert len(commercials) == 0

        assert round(b.heating_demand.total) == 1096924
        assert round(b.dhw_demand.total) == 1096924
        assert round(b.electricity_demand.total) == 1096924

    def test_sample_building_commercial(self):
        branch = Branch(year=2021)
        b = sample_building(branch, random_sample=False, type="commercial")

        assert b.year_of_construction == 1958
        assert b.usable_area == 450
        assert b.building_type == BuildingType.DETACHED
        assert b.refurbishment_status == RefurbishmentStatus.STANDARD_REFURBISHMENT

        assert len(b.building_elements) == 24
        assert len([be for be in b.building_elements if be.element_geometry is not None]) == 24
        assert len([be for be in b.building_elements if be.element_geometry.polygon is not None]) == 24

        assert len([be for be in b.building_elements if be.element_physics is not None]) == 24
        assert len([be for be in b.building_elements if be.element_physics.u_value_w_per_sqm_k is not None]) == 24
        assert len([be for be in b.building_elements if be.element_physics.transparency is not None]) == 24
        assert len([be for be in b.building_elements if be.adjacent_environment is not None]) == 24

        assert len(b.building_units) == 4
        households = [bu for bu in b.building_units if isinstance(bu, Household)]
        assert len(households) == 0

        commercials = [bu for bu in b.building_units if isinstance(bu, Commercial)]
        assert len(commercials) == 4
        assert len([c for c in commercials if c.commercial_type == CommercialType.GROCERIES]) == 4
        assert len([c for c in commercials if c.scaling_reference.name == "Erwerbstaetige"]) == 4
        assert len([c for c in commercials if c.scaling_reference.amount == 20]) == 4

    def test_sample_branch(self):
        branch = sample_branch(year=2019, n_buildings=20, type="residential")

        assert len(branch.objects) == 20

        assert branch.timeindex is not None
        assert branch.timeindex[0].year == 2019
        assert branch.timeindex[-1].year == 2019

        assert branch.weather.ambient_temperature.series.values is not None
        assert all(branch.weather.ambient_temperature.timeindex == branch.timeindex)

        assert all([isinstance(b, Building) for b in branch.objects])
        assert all([b.usable_area is not None for b in branch.objects])
        assert all([all(b.timeindex == branch.timeindex) for b in branch.objects])
        assert all([all(b.timeindex == branch.timeindex) for b in branch.objects])


if __name__ == "__main__":
    TestSamples().test_sample_building()
    TestSamples().test_sample_building_residential()
    TestSamples().test_sample_building_commercial()
    TestSamples().test_sample_branch()
