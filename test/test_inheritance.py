import unittest
from odeon.model import (
    BuildingElement,
    Wall,
    SolarSurfaceHost,
    SubelementHost,
    ElementPhysics,
)


class TestInheritance(unittest.TestCase):
    def test(self):
        w = Wall()
        assert set(w._children_attributes) == set(["_solar_surface", "_element_physics", "_sub_elements"])

        # these should pass and trigger an exception:
        with self.assertRaises(Exception) as context:
            Wall(not_a_valid_param=10)
        print(Wall().__class__.__name__)
        print(str(context.exception))
        self.assertEqual(
            str(context.exception), f"Unconsumed kwargs creating {Wall().__class__.__name__}: ['not_a_valid_param']"
        )
        with self.assertRaises(Exception) as context:
            ElementPhysics(material="my_material", not_a_valid_param=15)
        self.assertEqual(
            str(context.exception),
            f"Unconsumed kwargs creating {ElementPhysics().__class__.__name__}: ['not_a_valid_param']",
        )


if __name__ == "__main__":
    TestInheritance().test()
