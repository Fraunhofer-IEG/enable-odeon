import unittest
from datetime import datetime

from odeon.model import (
    Branch,
)
from odeon.processing.holidays import add_holidays


class TestAddHolidays(unittest.TestCase):
    def add_country_level_holidays_without_geographic_info(self):

        coords = None
        root = Branch(year=2022)
        add_holidays(branch=root, coordinates=coords)

        german_holidays_2022 = [
            datetime(2022, 1, 1).date(),  # New Year's Day
            datetime(2022, 4, 15).date(),  # Good Friday
            datetime(2022, 4, 18).date(),  # Easter Monday
            datetime(2022, 5, 1).date(),  # Labour Day
            datetime(2022, 5, 26).date(),  # Ascension Day
            datetime(2022, 6, 6).date(),  # Whit Monday
            datetime(2022, 10, 3).date(),  # Day of German Unity
            datetime(2022, 12, 25).date(),  # Christmas Day
            datetime(2022, 12, 26).date(),  # Boxing Day
        ]

        assert len(root.holidays) == len(german_holidays_2022)
        assert all([holiday in german_holidays_2022 for holiday in root.holidays])

        root.holidays.clear()

    def add_state_level_holidays_with_geographic_info(self):

        coords = [50.93402853080979, 6.4531968222830605]  # Somewhere in NRW :)
        root = Branch(year=2022)
        add_holidays(branch=root, coordinates=coords)

        nrw_holidays_2022 = [
            datetime(2022, 1, 1).date(),
            datetime(2022, 4, 15).date(),
            datetime(2022, 4, 18).date(),
            datetime(2022, 5, 1).date(),
            datetime(2022, 5, 26).date(),
            datetime(2022, 6, 6).date(),
            datetime(2022, 6, 16).date(),  # Corpus Christi (Extra)
            datetime(2022, 10, 3).date(),
            datetime(2022, 11, 1).date(),  # All Saints' Day (Extra)
            datetime(2022, 12, 25).date(),
            datetime(2022, 12, 26).date(),
        ]

        assert len(root.holidays) == len(nrw_holidays_2022)
        assert all([holiday in nrw_holidays_2022 for holiday in root.holidays])

        root.holidays.clear()


if __name__ == "__main__":
    TestAddHolidays().add_country_level_holidays_without_geographic_info()
    TestAddHolidays().add_state_level_holidays_with_geographic_info()
