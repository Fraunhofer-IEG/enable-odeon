import unittest

from odeon.processing.utils.address import standardize_street_name, standardize_house_number


class TestStandardization(unittest.TestCase):
    def test_standardize_street_name(self):

        # Test basic replacements
        self.assertEqual(standardize_street_name("Musterstraße"), "musterstr.")
        self.assertEqual(standardize_street_name("Musterstrasse"), "musterstr.")
        self.assertEqual(standardize_street_name("Muster Straße"), "muster str.")
        self.assertEqual(standardize_street_name("Musterstraße  "), "musterstr.")
        self.assertEqual(standardize_street_name("  Musterstraße"), "musterstr.")
        self.assertEqual(standardize_street_name("Müsterstraße"), "muesterstr.")
        self.assertEqual(standardize_street_name("Müllerstraße"), "muellerstr.")
        self.assertEqual(standardize_street_name("Goethestraße"), "goethestr.")
        self.assertEqual(standardize_street_name("Schönstraße"), "schoenstr.")

        # Test special character replacements
        self.assertEqual(standardize_street_name("Straße"), "str.")
        self.assertEqual(standardize_street_name("Strasse"), "str.")
        self.assertEqual(standardize_street_name("äöüß"), "aeoeuess")
        self.assertEqual(standardize_street_name("éèê"), "eee")

        # Test diacritical marks removal
        self.assertEqual(standardize_street_name("Café"), "cafe")
        self.assertEqual(standardize_street_name("façade"), "facade")

        # Test multiple spaces and trimming
        self.assertEqual(standardize_street_name("  Hauptstraße   "), "hauptstr.")
        self.assertEqual(standardize_street_name("  Straße  des   17. Juni "), "str. des 17. juni")

        # Test empty input
        self.assertEqual(standardize_street_name(""), "")

    def test_standardize_house_number(self):
        # Test None input
        self.assertEqual(standardize_house_number(None), [None])

        # Test single house numbers
        self.assertEqual(standardize_house_number("35"), ["35"])
        self.assertEqual(standardize_house_number("35a"), ["35a"])
        self.assertEqual(standardize_house_number("35 a"), ["35a"])
        self.assertEqual(standardize_house_number(" a 35 "), ["35a"])
        self.assertEqual(standardize_house_number(" 35A "), ["35a"])
        self.assertEqual(standardize_house_number("b35"), ["35b"])

        # Test ranges
        self.assertEqual(standardize_house_number("1-5"), ["1", "3", "5"])  # Odd range
        self.assertEqual(standardize_house_number("2-6"), ["2", "4", "6"])  # Even range

        # Test multiple numbers
        self.assertEqual(standardize_house_number("35, 36, 37"), ["35", "36", "37"])
        self.assertEqual(standardize_house_number("35 / 36"), ["35", "36"])
        self.assertEqual(standardize_house_number("35,36/37"), ["35", "36", "37"])
        self.assertEqual(standardize_house_number("a35, 36, 37"), ["35a", "36", "37"])
        self.assertEqual(standardize_house_number("a 35, 36, 37"), ["35a", "36", "37"])
        self.assertEqual(standardize_house_number("35 A, 36, 37"), ["35a", "36", "37"])

        # Test invalid input
        self.assertEqual(standardize_house_number("invalid"), ["invalid"])


if __name__ == "__main__":
    TestStandardization().test_standardize_street_name()
    TestStandardization().test_standardize_house_number()
