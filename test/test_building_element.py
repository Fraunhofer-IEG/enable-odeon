import unittest

from odeon.model import (
    Wall,
    Roof,
    RoofType,
    ElementPhysics,
    Building,
    BuildingThermalZone,
    PhotovoltaicDevice,
    SolarSurface,
    EnergySystem,
    BuildingDhnConnection,
    NominalGeometry,
    Window,
    Door,
)


class TestBuildingElement(unittest.TestCase):
    def test_simple_building_with_walls(self):
        ## Create simple building with it's own building-specific physics
        building = Building(name="Building_1", usable_area=100)
        building_physics = BuildingThermalZone(name="Physics_1", heated_area=80)
        building.building_thermal_zone = building_physics

        assert building._building_thermal_zone is building_physics

        ## Building gets a dhnConnection
        host = EnergySystem()
        building.energy_system = host
        dhn_connection = BuildingDhnConnection()
        host.add_components(dhn_connection)

        assert building.energy_system is host
        assert building.energy_system.parent is building
        assert building.energy_system.components == [dhn_connection]
        assert building.energy_system.components[0].parent is host

        ## Create elements
        wall_north = Wall()
        wall_north_geo = NominalGeometry(area_nominal=40, height=5)
        wall_north.element_geometry = wall_north_geo
        wall_north_phy = ElementPhysics(material="concrete", u_value_w_per_sqm_k=0.25)
        wall_north.element_physics = wall_north_phy

        wall_east = Wall()
        wall_east_geo = NominalGeometry(area_nominal=40, height=5)
        wall_east.element_geometry = wall_east_geo
        wall_east_phy = ElementPhysics(material="concrete", u_value_w_per_sqm_k=0.2)
        wall_east.element_physics = wall_east_phy

        wall_south = Wall()
        wall_south_geo = NominalGeometry(area_nominal=40, height=5)
        wall_south.element_geometry = wall_south_geo
        wall_south_phy = ElementPhysics(material="concrete", u_value_w_per_sqm_k=0.22)
        wall_south.element_physics = wall_south_phy

        wall_west = Wall()
        wall_west_geo = NominalGeometry(area_nominal=40, height=5)
        wall_west.element_geometry = wall_west_geo
        wall_west_phy = ElementPhysics(material="concrete", u_value_w_per_sqm_k=0.23)
        wall_west.element_physics = wall_west_phy

        roof = Roof()
        roof_geo = NominalGeometry(dimensions_nominal=(8, 8))
        roof.element_geometry = roof_geo
        roof_phy = ElementPhysics(u_value_w_per_sqm_k=0.3)
        roof.element_physics = roof_phy

        building.add_building_elements([wall_north, wall_east, wall_south, wall_west, roof])  # Add elements to building

        assert all(
            element in building._building_elements for element in [roof, wall_north, wall_east, wall_south, wall_west]
        )
        assert all(element._element_geometry is not None for element in building._building_elements)
        assert all(element._element_physics is not None for element in building._building_elements)

        ## Add PV on roof
        surface = SolarSurface(factor_existing_pv=1, factor_occupied_nonsolar=0.5, possible_number_modules=1)
        roof.solar_surface = surface
        pv = PhotovoltaicDevice()
        pv2 = PhotovoltaicDevice()
        pv3 = PhotovoltaicDevice()
        pv4 = PhotovoltaicDevice()
        pv5 = PhotovoltaicDevice()
        surface.add_solar_transformers([pv, pv2, pv3, pv4, pv5])  # will add devices to building's device host

        assert roof.solar_surface is surface
        assert roof.solar_surface.parent is roof
        assert roof.solar_surface.devices == [pv, pv2, pv3, pv4, pv5]
        assert all(device.parent is building.energy_system for device in roof.solar_surface.devices)
        assert all(device.solar_surface is surface for device in roof.solar_surface.devices)

        ## Testing method to get all pv devices
        pv_devices = building._get_offspring_by_type(PhotovoltaicDevice)
        assert len(pv_devices) == 5

        ## Test remove device from surface
        surface.remove_solar_transformers([pv2, pv3, pv5])
        assert roof.solar_surface.devices == [pv, pv4]
        assert all(pv_device.parent is building.energy_system for pv_device in [pv2, pv3, pv5])
        assert all(pv_device.solar_surface is None for pv_device in [pv2, pv3, pv5])
        assert all(pv_device.solar_surface is surface for pv_device in [pv, pv4])

        ## Test remove device from host
        building.energy_system.remove_components([pv4])  # will remove the device from the solar surface
        assert roof.solar_surface.devices == [pv]
        assert all(pv_device.parent is None for pv_device in [pv4])
        assert all(pv_device.parent is building.energy_system for pv_device in [pv])

        window_north = Window()
        wall_north.add_sub_elements(window_north)
        door_east = Door()
        window_east = Window()
        wall_east.add_sub_elements([door_east, window_east])

        assert len(building.building_elements) == 8

    def test_property_setter(self):
        # Create element and Geomentry
        wall = Wall()
        wall_geo = NominalGeometry(area_nominal=40, height=5)
        assert not wall._element_geometry  # assert wall_north. is None somehow causes problems for me?!

        # Test setting value via property setter
        wall.element_geometry = wall_geo
        assert wall._element_geometry is wall_geo

        # Test setting None
        wall.element_geometry = None
        assert not wall._element_geometry

        # Test other property setter
        wall_phy = ElementPhysics(material="concrete", u_value_w_per_sqm_k=0.25)
        wall.element_physics = wall_phy
        assert wall._element_physics is wall_phy


if __name__ == "__main__":
    TestBuildingElement().test_simple_building_with_walls()
    TestBuildingElement().test_property_setter()
