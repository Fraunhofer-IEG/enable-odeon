from __future__ import annotations
import logging
from datetime import datetime
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderUnavailable
import holidays

from ..model.base import Branch

logger = logging.getLogger(name=f"enable.{__name__}")


def add_holidays(branch: Branch, coordinates: tuple[float, float] = None):
    """Populate `holidays` for the branch year.

    Parameters
    ----------
    coordinates : (float, float), optional
        Latitude / longitude used to derive the German federal state. If
        missing or lookup fails, nationwide holidays are used.
    """

    def get_state_from_coordinates(coordinates):
        if coordinates:
            try:
                geolocator = Nominatim(user_agent="german_state_locator")
                location = geolocator.reverse(coordinates, language="de")
            except GeocoderUnavailable:
                print("Nominatim is currently unreachable, adding common German Holidays for now")
                return None
            if location and "address" in location.raw:
                address = location.raw["address"]
                if "state" in address:
                    return address["state"]
        else:
            print("No or invalid coordinates provided, adding common German Holidays for now")
            return None

    def generate_holidays_from_state(state: str, year: int) -> list[datetime]:
        state_mapping = {
            "Baden-Württemberg": "BW",
            "Bayern": "BY",
            "Berlin": "BE",
            "Brandenburg": "BB",
            "Bremen": "HB",
            "Hamburg": "HH",
            "Hessen": "HE",
            "Mecklenburg-Vorpommern": "MV",
            "Niedersachsen": "NI",
            "Nordrhein-Westfalen": "NW",
            "Rheinland-Pfalz": "RP",
            "Saarland": "SL",
            "Sachsen": "SN",
            "Sachsen-Anhalt": "ST",
            "Schleswig-Holstein": "SH",
            "Thüringen": "TH",
        }

        if state:
            state_code = state_mapping.get(state)
            if state_code:
                german_holidays = holidays.Germany(subdiv=state_code, years=year)
            else:
                raise ValueError(f"Invalid state: {state}")
        else:
            german_holidays = holidays.Germany(years=year)

        holiday_dates = [date for date in german_holidays]
        return holiday_dates

    year = branch.year
    state = get_state_from_coordinates(coordinates)

    holiday_dates = generate_holidays_from_state(state, year)

    branch.holidays = holiday_dates