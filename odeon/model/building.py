import math
from dataclasses import dataclass
from typing import TYPE_CHECKING
from shapely import GeometryCollection, MultiPolygon, Polygon

from .base import Object, StrEnum, GeometryObject, UniqueEnum
from .building_element import (
    BuildingElement,
    Floor,
    Roof,
    SubelementHost,
    Wall,
    Window,
    Door,
)
from .building_geometry import (
    RoofedCuboidBuildingGeometry,
    FootprintNominalBuildingGeometry,
)
from .building_physics import BuildingThermalZone
from .building_unit import BuildingUnit, Household, Commercial, Resident, CommercialType
from .energy_system import EnergySystemHost
from .device import (
    BuildingDhnConnection,
    ElectricityGridConnection,
    ElectricityGridConnection,
    WallBox,
    SolarSurfaceHost,
)
from .decision import BuildingDecision, DecisionState
from .environment import Weather
from .expense import (
    Expense,
    ExpenseType,
    BuildingConstructionExpense,
    BuildingTransformationExpense,
)
from .geometry import Geometry, MultiGeometry

from ..processing.utils.utils import typeerror_if_not_isinstance, typeerror_if_not_isinstance_or_none

if TYPE_CHECKING:
    from .building_unit import CommercialType
    from .building_geometry import BuildingGeometry


class EfficiencyLevel(StrEnum):
    WSVO77 = "WSVO 77"
    WSVO82 = "WSVO 82"
    WSVO95 = "WSVO 95"

    ENEV2002_NIEDGRIGENERGIEHAUS = "EnEV 2002 - Niedrigenergiehaus"

    ENEV2004_KFW_60 = "EnEV 2004 - KfW-60"
    ENEV2004_KFW_40 = "EnEV 2004 - KfW-40"

    ENEV2007_KFW_70 = "EnEV 2007 - KfW-70"
    ENEV2007_KFW_55 = "EnEV 2007 - KfW-55"

    ENEV2009_KFW_100 = "EnEV 2009 - KfW-100"
    ENEV2009_KFW_85 = "EnEV 2009 - KfW-85"
    ENEV2009_KFW_70 = "EnEV 2009 - KfW-70"
    ENEV2009_KFW_55 = "EnEV 2009 - KfW-55"
    ENEV2009_KFW_40 = "EnEV 2009 - KfW-40"

    ENEV2014_KFW_DENKMAL = "EnEV 2014 - KfW-Denkmal"
    ENEV2014_KFW_115 = "EnEV 2014 - KfW-115"
    ENEV2014_KFW_100 = "EnEV 2014 - KfW-100"
    ENEV2014_KFW_85 = "EnEV 2014 - KfW-85"
    ENEV2014_KFW_70 = "EnEV 2014 - KfW-70"
    ENEV2014_KFW_55 = "EnEV 2014 - KfW-55"
    ENEV2014_KFW_40 = "EnEV 2014 - KfW-40"

    GEG2020 = "GEG 2020"
    GEG2023 = "GEG 2023"

    PASSIVHAUS = "Passivhaus"
    SONNENHAUS = "Sonnenhaus"
    NULLENERGIEHAUS = "Nullenergiehaus"
    PLUSENERGIEHAUS = "Plusenergiehaus"

    EG_40 = "EG 40"
    EG_55 = "EG 55"

    EGB_40 = "EGB 40"
    EGB_55 = "EGB 55"


class BuildingAgeGroup(UniqueEnum):
    # Tabula building age groups
    BELOW_1860 = ("1859_or_below", -9999, 1859)
    BETWEEN_1860_AND_1918 = ("between_1860_and_1918", 1860, 1918)
    BETWEEN_1919_AND_1948 = ("between_1919_and_1948", 1919, 1948)
    BETWEEN_1949_AND_1957 = ("between_1949_and_1957", 1949, 1957)
    BETWEEN_1958_AND_1968 = ("between_1958_and_1968", 1958, 1968)
    BETWEEN_1969_AND_1978 = ("between_1969_and_1978", 1969, 1978)
    BETWEEN_1979_AND_1983 = ("between_1979_and_1983", 1979, 1983)
    BETWEEN_1984_AND_1994 = ("between_1984_and_1994", 1984, 1994)
    BETWEEN_1995_AND_2001 = ("between_1995_and_2001", 1995, 2001)
    BETWEEN_2002_AND_2009 = ("between_2002_and_2009", 2002, 2009)
    BETWEEN_2010_AND_2015 = ("between_2010_and_2015", 2010, 2015)
    ABOVE_2015 = ("above_2015", 2016, 9999)

    # ENOB:data age groups
    BELOW_1979 = ("1978_or_below", -9999, 1978)
    BETWEEN_1979_AND_2010 = ("between_1979_and_2009", 1979, 2010)
    ABOVE_2010 = ("2010_or_above", 2011, 9999)

    def __init__(self, identifier, start, end):
        self.identifier = identifier
        self.start = start
        self.end = end

    def __lt__(self, __x) -> bool:
        return self.start < __x.start and self.end < __x.end

    def __gt__(self, __x) -> bool:
        return self.start > __x.start and self.end > __x.end


class RefurbishmentStatus(UniqueEnum):
    EXISTING_STATE = ("existing_state", 0)
    STANDARD_REFURBISHMENT = ("standard_refurbishment", 1)
    AMBITIOUS_REFURBISHMENT = ("ambitious_refurbishment", 2)
    INDIVIDUAL_REFURBISHMENT = ("individual_refurbishment", 3)

    def __init__(self, identifier, ordering):
        self.identifier = identifier
        self.ordering = ordering

    def __lt__(self, __x) -> bool:
        return self.ordering < __x.ordering

    def __gt__(self, __x) -> bool:
        return self.ordering > __x.ordering


class BuildingType(StrEnum):
    DETACHED = "detached"
    TERRACED = "terraced"
    MINOR = "minor"
    HIGHRISE = "highrise"


@dataclass
class Address:
    country: str = None
    state: str = None
    province: str = None
    city: str = None
    postalcode: str = None
    street: str = None
    housenumber: str = None

    def to_string(self) -> str:
        parts = []
        if self.street:
            street_part = self.street
            if self.housenumber:
                street_part += f" {self.housenumber}"
            parts.append(street_part)
        if self.postalcode or self.city:
            city_part = ""
            if self.postalcode:
                city_part += self.postalcode
            if self.city:
                if city_part:
                    city_part += " "
                city_part += self.city
            parts.append(city_part)
        if self.state:
            parts.append(self.state)
        if self.country:
            parts.append(self.country)
        return ", ".join(parts)


class Use(StrEnum):
    UNKNOWN = "unknown"
    MIXED = "mixed"  # >=1 Household, >= 1 Commercial
    COMMERCIAL = "commercial"  # >= 1 Commercial, no Household
    SINGLE_FAMILY = "singlefamily"  # 1 Household
    MULTI_FAMILY = "multifamily"  # 2..12 Households
    APARTMENTBLOCK = "apartmentblock"  # >12 Households
    RESIDENTIAL = "residential"  # 0 Commercial units, >= 1 Household
    MINOR = "minor"  # garage, shed, shelter etc. – no energy demand, no devices


USE_MAPPING = {
    # Residential size based on Tabula and Zensus definition
    # https://www.iwu.de/fileadmin/publikationen/gebaeudebestand/episcope/2015_IWU_LogaEtAl_Deutsche-Wohngeb%C3%A4udetypologie.pdf
    # https://www.zensus2011.de/SharedDocs/Downloads/DE/Fragebogen/Fragebogen_Gebaeude_und_Wohnungszaehlung.pdf?__blob=publicationFile&v=2
    Use.RESIDENTIAL: {"n_hh_min": 1, "n_hh_max": math.inf, "n_com_min": 0, "n_com_max": 0, "com_types": []},
    Use.SINGLE_FAMILY: {"n_hh_min": 1, "n_hh_max": 1, "n_com_min": 0, "n_com_max": 0, "com_types": []},
    Use.MULTI_FAMILY: {"n_hh_min": 2, "n_hh_max": 12, "n_com_min": 0, "n_com_max": 0, "com_types": []},
    Use.APARTMENTBLOCK: {"n_hh_min": 13, "n_hh_max": math.inf, "n_com_min": 0, "n_com_max": 0, "com_types": []},
    Use.UNKNOWN: {"n_hh_min": 0, "n_hh_max": math.inf, "n_com_min": 0, "n_com_max": math.inf},
    Use.COMMERCIAL: {"n_hh_min": 0, "n_hh_max": 0, "n_com_min": 1, "n_com_max": math.inf},
    Use.MINOR: {"n_hh_min": 0, "n_hh_max": 0, "n_com_min": 0, "n_com_max": 0, "com_types": []},
    Use.MIXED: {"n_hh_min": 1, "n_hh_max": math.inf, "n_com_min": 1, "n_com_max": math.inf},
}
MIN_BUILDING_UNIT_NET_FLOOR_AREA = 35


class Vicinity(EnergySystemHost):
    """
    The project location that can be used to store data that is valid for all
    entities in a Branch -- especially devices (e.g. electricity grid,
    infrastructure etc.)
    """

    ...


class WeatherHost(Object):
    """
    Mixin class for objects that have weather information.

    Note that the weather is not a child of the object, but an associated
    attribute. This means that the weather needs to be stored in the branch
    manually as an object.
    """

    _ASSOCIATED_ATTRIBUTES = ["_weather"]
    _weather: Weather = None

    @property
    def weather(self) -> Weather | None:
        if self._weather is not None:
            return self._weather
        elif self.branch is not None and self.branch.weather is not None:
            return self.branch.weather

    @weather.setter
    def weather(self, weather: Weather):
        typeerror_if_not_isinstance_or_none(weather, Weather)
        self._weather = weather


class Site(GeometryObject, SolarSurfaceHost, EnergySystemHost, WeatherHost):

    # additional attributes:
    suitable: dict[str, bool] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.suitable = {"Solar": False, "Wind": False, "Geothermal": False}


class Structure(EnergySystemHost, WeatherHost):

    # children attributes:
    _CHILDREN_ATTRIBUTES = {"_site": "Site"}
    _site: Site = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    # properties for children, associated and inherited:

    @property
    def site(self) -> Site:
        return self._site

    @site.setter
    def site(self, site: Site):
        typeerror_if_not_isinstance_or_none(site, Site)
        self._site = site
        assert site.parent is None
        site._set_parent(self)

    @property
    def geometry(self) -> Geometry | None:
        # included for consistency with StructureGroup and Building which both
        # have this property. Hopefully gets reworked with the whole
        # StructureGroup thing
        return None

    # additional methods:

    def get_dominant_building_unit_type(self) -> CommercialType | type | None:
        """
        Returns the dominant building unit type in this structure, i.e. the
        type of building unit with the largest total net floor area. Possible
        values are CommercialType enum values, Household type, or None (if no
        building units are present or if there is a tie).
        """
        d = {}
        for u in self.find_objects(BuildingUnit):
            if isinstance(u, Commercial):
                d[u.commercial_type] = d.get(u.commercial_type, 0) + (u.net_floor_area or 0)
            elif isinstance(u, Household):
                d[Household] = d.get(Household, 0) + (u.net_floor_area or 0)
        if d:
            max_ = max(d.values())
            argmax = [x for x, y in d.items() if y == max_]
            return argmax[0] if len(argmax) == 1 else None


class Building(Structure):
    """
    Notes
    -----
    - regarding the relation of `BuildingElement`s and `ElementGeometry`s:
        - in property `building_elements`, any elements can be stored. These
        can have an `ElementGeometry` set or not. In the building's geometries
        (`building_geometry_nominal` and `building_geometry_cuboid`), element
        geometries can be stored. The following rule should be followed by
        user: The geometry of every `BuildingElement` with an `ElementGeometry`
        should be contained either in `building_geometry_nominal` or
        `building_geometry_cuboid`.
        - for `building_geometry_cuboid`, it's not allowed to add element
        geometries manually. Instead, they must be added by the respective
        method in `RoofedCuboidBuildingGeometry` and can be referenced
        afterwards by a `BuildingElement` in `Building.building_elements`.
    """

    # children attributes:
    _CHILDREN_ATTRIBUTES = {
        "_building_thermal_zone": "BuildingThermalZone",
        "_building_geometry_nominal": "FootprintNominalBuildingGeometry",
        "_building_geometry_cuboid": "RoofedCuboidBuildingGeometry",
        "_building_elements": "BuildingElement[]",
        "_building_units": "BuildingUnit[]",
    }
    _building_thermal_zone: BuildingThermalZone = None
    _building_geometry_nominal: FootprintNominalBuildingGeometry = None
    _building_geometry_cuboid: RoofedCuboidBuildingGeometry = None
    _building_elements: list[BuildingElement] = None
    _building_units: list[BuildingUnit] = None

    # associated attributes:
    _ASSOCIATED_ATTRIBUTES = ["_decision"]
    _decision: BuildingDecision = None

    # additional attributes:
    unit_distribution: dict = None  # used to bridge data from OsmLoader to enhancer and count units
    heating_system_info: dict = None  # used to bridge data from enhancer to device processor
    number_of_floors: int = None  # [1]
    _expenses: list[Expense] = None
    _postal_code: str = None
    _nuts_3: str = None
    _exists: bool = True
    _year_of_construction: int = None
    _year_of_construction_range: tuple[int, int] = None
    _usable_area: float = None  # [m²]
    _gross_floor_area: float = None  # [m²]
    _building_type: BuildingType = None
    _refurbishment_status: RefurbishmentStatus = None
    _detailed_refurbishment_status: dict = None
    _efficiency_level: EfficiencyLevel = None
    _norm_heating_load: float = None  # [kW]
    _address: Address = None

    def __init__(self, **kwargs):
        self.building_geometry_nominal = FootprintNominalBuildingGeometry()  # call setter
        self._building_elements = []
        self._building_units = []
        self._expenses = []
        self.unit_distribution = {"n_hh_min": 0, "n_hh_max": math.inf, "n_com_min": 0, "n_com_max": math.inf}
        self.heating_system_info = {}
        super().__init__(**kwargs)

    @property
    def geometry(self) -> Geometry | None:
        """The footprint of the building, if it has a `BuildingGeometry`."""
        if self.building_geometry_nominal is not None:
            return self.building_geometry_nominal.footprint
        elif self.building_geometry_cuboid is not None:
            return self.building_geometry_cuboid.footprint

    @property
    def detailed_refurbishment_status(self) -> dict[type, RefurbishmentStatus]:
        if self._detailed_refurbishment_status is None:
            return {
                Wall: self.refurbishment_status,
                Roof: self.refurbishment_status,
                Window: self.refurbishment_status,
                Floor: self.refurbishment_status,
                Door: self.refurbishment_status,
            }
        return self._detailed_refurbishment_status

    @detailed_refurbishment_status.setter
    def detailed_refurbishment_status(self, detailed_state: dict[BuildingElement, RefurbishmentStatus]):
        self._detailed_refurbishment_status = detailed_state

    @property
    def postal_code(self) -> str:
        return self._postal_code

    @postal_code.setter
    def postal_code(self, pc: str):
        typeerror_if_not_isinstance_or_none(pc, str)
        self._postal_code = pc

    @property
    def address(self) -> Address:
        return self._address

    @address.setter
    def address(self, address: Address):
        typeerror_if_not_isinstance(address, Address)
        self._address = address

    @property
    def nuts_3(self) -> str:
        return self._nuts_3

    @nuts_3.setter
    def nuts_3(self, nuts: str):
        typeerror_if_not_isinstance_or_none(nuts, str)
        self._nuts_3 = nuts

    @property
    def building_type(self) -> BuildingType:
        return self._building_type

    @building_type.setter
    def building_type(self, building_type: BuildingType):
        typeerror_if_not_isinstance_or_none(building_type, BuildingType)
        self._building_type = building_type

    @property
    def refurbishment_status(self) -> RefurbishmentStatus:
        return self._refurbishment_status

    @refurbishment_status.setter
    def refurbishment_status(self, refurbishment_status: RefurbishmentStatus):
        typeerror_if_not_isinstance_or_none(refurbishment_status, RefurbishmentStatus)
        self._refurbishment_status = refurbishment_status

    @property
    def efficiency_level(self) -> EfficiencyLevel:
        return self._efficiency_level

    @efficiency_level.setter
    def efficiency_level(self, efficiency_level: EfficiencyLevel):
        typeerror_if_not_isinstance_or_none(efficiency_level, EfficiencyLevel)
        self._efficiency_level = efficiency_level

    @property
    def norm_heating_load(self) -> float:
        return self._norm_heating_load

    @norm_heating_load.setter
    def norm_heating_load(self, value: float) -> None:
        typeerror_if_not_isinstance_or_none(value, float)
        self._norm_heating_load = value

    @property
    def year_of_construction(self) -> int | None:
        if self._year_of_construction is not None:
            return self._year_of_construction
        else:
            if self.building_age_group is not None:
                return int((self.building_age_group.start + self.building_age_group.end) / 2)
            else:
                return None

    @year_of_construction.setter
    def year_of_construction(self, year: int | None):
        typeerror_if_not_isinstance_or_none(year, int)
        self._year_of_construction = year

    @property
    def year_of_construction_range(self) -> tuple[int | None, int | None]:
        if self._year_of_construction_range is None:
            if self._year_of_construction is not None:
                return (self._year_of_construction, self._year_of_construction)
            else:
                return (None, None)
        else:
            return self._year_of_construction_range

    @year_of_construction_range.setter
    def year_of_construction_range(self, range: tuple[int, int]):
        if self._year_of_construction is not None:
            raise Exception("can't set year_of_construction_range when a year_of_construction is set")
        if (
            not isinstance(range, tuple)
            or len(range) != 2
            or not all(isinstance(r, int) or math.isinf(r) for r in range)
        ):
            raise TypeError()
        if range[0] > range[1]:
            raise ValueError()
        self._year_of_construction_range = range

    @property
    def building_age_group(self) -> BuildingAgeGroup | None:
        if all(year is not None for year in self.year_of_construction_range):
            yoc_start, yoc_end = self.year_of_construction_range
            for name, bag in BuildingAgeGroup.__members__.items():
                if bag.start <= yoc_start and yoc_end <= bag.end:
                    return bag

    @building_age_group.setter
    def building_age_group(self, building_age_group: BuildingAgeGroup | None):
        typeerror_if_not_isinstance_or_none(building_age_group, BuildingAgeGroup)
        self.year_of_construction_range = (
            building_age_group.start,
            building_age_group.end,
        )

    @property
    def building_thermal_zone(self) -> BuildingThermalZone:
        return self._building_thermal_zone

    @building_thermal_zone.setter
    def building_thermal_zone(self, building_thermal_zone: BuildingThermalZone | None):
        typeerror_if_not_isinstance_or_none(building_thermal_zone, BuildingThermalZone)
        old = self._building_thermal_zone
        if old is not None:
            old.remove_from_parent()
        self._building_thermal_zone = building_thermal_zone
        if building_thermal_zone is not None:
            assert building_thermal_zone.parent in [None, self.branch]
            building_thermal_zone._set_parent(self)

    @property
    def building_geometry_nominal(self) -> FootprintNominalBuildingGeometry:
        return self._building_geometry_nominal

    @building_geometry_nominal.setter
    def building_geometry_nominal(self, geometry: FootprintNominalBuildingGeometry):
        typeerror_if_not_isinstance_or_none(geometry, FootprintNominalBuildingGeometry)
        old = self._building_geometry_nominal
        if old is not None:
            old.remove_from_parent()
        self._building_geometry_nominal = geometry
        if geometry is not None:
            assert geometry.parent in [None, self.branch]
            geometry._set_parent(self)

    @property
    def building_geometry_cuboid(self) -> RoofedCuboidBuildingGeometry:
        return self._building_geometry_cuboid

    @building_geometry_cuboid.setter
    def building_geometry_cuboid(self, geometry: RoofedCuboidBuildingGeometry):
        typeerror_if_not_isinstance_or_none(geometry, RoofedCuboidBuildingGeometry)
        old = self._building_geometry_cuboid
        if old is not None:
            old.remove_from_parent()
        self._building_geometry_cuboid = geometry
        if geometry is not None:
            assert geometry.parent in [None, self.branch]
            geometry._set_parent(self)

    @property
    def building_geometry(self) -> "BuildingGeometry":
        if self._building_geometry_cuboid is not None:
            return self._building_geometry_cuboid
        else:
            return self._building_geometry_nominal

    @property
    def envelope_surface_area(
        self,
    ) -> float:  # kg: auch aus building_geometry ableitbar. Was soll wann geschehen? 24.05.2024
        if self.building_elements is None:
            return None
        return sum(
            [
                eli.element_geometry.area
                for eli in self.building_elements
                if eli.element_geometry is not None and eli.element_geometry.area is not None
            ]
        )

    @property
    def net_site_area(self) -> float | None:
        if self.site is not None:
            if self.site.geometry is not None:
                return self.site.geometry.area - self.building_geometry.footprint_area

    @property
    def building_elements(self) -> list[BuildingElement]:
        return self._get_offspring_by_type(BuildingElement)

    @property
    def building_units(self) -> list[BuildingUnit]:
        return self._building_units.copy()

    @property
    def households(self) -> list[Household]:
        return [bu for bu in self._building_units if isinstance(bu, Household)]

    @property
    def commercials(self) -> list[Commercial]:
        return [bu for bu in self._building_units if isinstance(bu, Commercial)]

    @property
    def residents(self) -> list[Resident]:
        return [r for h in self.households for r in h.residents]

    @property
    def commercial_types(self) -> list["CommercialType"]:
        """
        List of contained commercial types, may contain duplicates.
        """
        return [c.commercial_type for c in self.commercials]

    @property
    def dominant_commercial_type(self) -> CommercialType | None:
        """
        Returns the commercial type with the largest (summed) net_floor_area
        """
        unique_commerical_types = list(set(self.commercial_types))
        if len(unique_commerical_types) == 0:
            return None
        elif len(unique_commerical_types) == 1:
            dominant_commercial_type = unique_commerical_types[0]
        else:
            # dictionary with commerical type as key and net_floor_area (summed) as value
            nfa_dict = dict.fromkeys(unique_commerical_types, 0)
            for c in self.commercials:
                nfa_dict[c.commercial_type] += c.net_floor_area

            # Find key which has the largest value
            dominant_commercial_type = max(nfa_dict, key=nfa_dict.get)

        return dominant_commercial_type

    @property
    def gross_floor_area(self) -> float | None:
        if self._gross_floor_area is not None:
            return self._gross_floor_area
        elif self.number_of_floors is not None and self.building_geometry_nominal.footprint_area is not None:
            return self.number_of_floors * self.building_geometry_nominal.footprint_area

    @gross_floor_area.setter
    def gross_floor_area(self, gross_floor_area: float | None):
        self._gross_floor_area = gross_floor_area

    @property
    def usable_area(self) -> float | None:
        if self._usable_area is not None:
            return self._usable_area
        elif self.gross_floor_area is not None:
            return (
                self.gross_floor_area * 0.68
            )  # https://repositum.tuwien.at/bitstream/20.500.12708/15291/2/Vujicic%20Dragan%20-%202020%20-%20Das%20Verhaeltnis%20der%20Nutzungsflaeche%20zu...pdf

    @usable_area.setter
    def usable_area(self, usable_area: float | None):
        self._usable_area = usable_area

    @property
    def usable_area_unassigned(self) -> float | None:
        ua = self.usable_area
        if ua is not None:
            return float(ua - sum([bu.net_floor_area for bu in self.building_units if bu.net_floor_area is not None]))

    @property
    def use(self) -> Use:
        from_bu = False
        if self.usable_area is not None:
            if self.usable_area_unassigned < MIN_BUILDING_UNIT_NET_FLOOR_AREA:  # only if all building_units are defined
                from_bu = True
        if from_bu:
            n_hh = len([u for u in self._building_units if isinstance(u, Household)])
            n_com = len([u for u in self._building_units if isinstance(u, Commercial)])
            if n_hh > 0 and n_com == 0:
                if n_hh == 1:
                    return Use.SINGLE_FAMILY
                elif n_hh > 1 and n_hh <= 12:
                    return Use.MULTI_FAMILY
                elif n_hh >= 13:
                    return Use.APARTMENTBLOCK
                else:
                    return Use.RESIDENTIAL
            elif n_hh > 0 and n_com > 0:
                return Use.MIXED
            elif n_hh == 0 and n_com > 0:
                return Use.COMMERCIAL
            elif n_hh == 0 and n_com == 0:
                return Use.MINOR

        if self.unit_distribution["n_hh_min"] > 0 and self.unit_distribution["n_com_min"] == 0:
            if self.unit_distribution["n_hh_min"] == self.unit_distribution["n_hh_max"] == 1:
                return Use.SINGLE_FAMILY
            elif self.unit_distribution["n_hh_min"] > 1 and self.unit_distribution["n_hh_max"] <= 12:
                return Use.MULTI_FAMILY
            elif self.unit_distribution["n_hh_min"] >= 13:
                return Use.APARTMENTBLOCK
            else:
                return Use.RESIDENTIAL
        elif self.unit_distribution["n_hh_min"] > 0 and self.unit_distribution["n_com_min"] > 0:
            return Use.MIXED
        elif self.unit_distribution["n_hh_min"] == 0 and self.unit_distribution["n_com_min"] > 0:
            return Use.COMMERCIAL
        elif self.unit_distribution["n_hh_max"] == 0 and self.unit_distribution["n_com_max"] == 0:
            return Use.MINOR

        return Use.UNKNOWN

    @use.setter
    def use(self, use: Use):
        typeerror_if_not_isinstance_or_none(use, Use)
        unit_count = len(self._building_units)
        area_left = self.usable_area_unassigned
        updated_use = USE_MAPPING[use]
        if unit_count >= 1:
            n_hh = len([u for u in self._building_units if isinstance(u, Household)])
            n_com = len([u for u in self._building_units if isinstance(u, Commercial)])
            if n_hh > updated_use["n_hh_max"]:
                raise AssertionError(
                    f"You cannot overwrite the attribute use. There already exists more households than allowed for buildings of type {use}"
                )
            if n_com > updated_use["n_com_max"]:
                raise AssertionError(
                    f"You cannot overwrite the attribute use. There already exists more commercial units than allowed for buildings of type {use}"
                )
        else:
            n_hh = n_com = 0
        delta_units = max(updated_use["n_hh_min"] - n_hh, 0) + max(updated_use["n_com_min"] - n_com, 0)
        if (n_hh < updated_use["n_hh_min"] or n_com < updated_use["n_com_min"]) and delta_units > 0:
            if area_left is not None:
                if area_left - MIN_BUILDING_UNIT_NET_FLOOR_AREA * delta_units < 0:
                    raise AssertionError(
                        f"You cannot overwrite the attribute [use]. For '{self.name}' there is not enough free building area available to fullfill the minimum unit requirements for a building of type {use}"
                    )

        self.unit_distribution.update({k: updated_use[k] for k in updated_use if k in self.unit_distribution})

    @property
    def existence(self) -> DecisionState:
        if self._exists:
            if self._decision is None:
                return DecisionState.FIXED
            elif self._decision.decided:
                return DecisionState.DECIDED_FOR
            else:
                return DecisionState.UNDECIDED_EXISTING
        else:
            assert self._decision is not None
            if self._decision.decided:
                return DecisionState.DECIDED_AGAINST
            else:
                return DecisionState.UNDECIDED_OPTION

    @property
    def exists(self):
        return self._exists

    @exists.setter
    def exists(self, value: bool):
        if self._decision:
            self._decision.set_existing(self, value)
        else:
            self._exists = value

    @property
    def decision(self) -> BuildingDecision:
        return self._decision

    @property
    def expenses(self) -> list[Expense]:
        return self._expenses

    @property
    def transformation_expenses(self) -> list[BuildingTransformationExpense]:
        return [expense for expense in self._expenses if type(expense) == BuildingTransformationExpense]

    @property
    def construction_expenses(self) -> list[BuildingConstructionExpense]:
        return [expense for expense in self._expenses if type(expense) == BuildingConstructionExpense]

    @property
    def n_wallboxes(self) -> int:
        return len(self._get_offspring_by_type(WallBox))

    def add_expenses(self, expense: Expense):
        typeerror_if_not_isinstance_or_none(expense, Expense)
        self._expenses.append(expense)

    def get_expenses(self, expense_types: list[ExpenseType]):
        return [e for e in self.expenses if e.type in expense_types]

    def add_building_elements(self, building_elements: BuildingElement | list[BuildingElement]):
        if isinstance(building_elements, BuildingElement):
            building_elements = [building_elements]
        for element in building_elements:
            typeerror_if_not_isinstance_or_none(element, BuildingElement)
            assert element.parent in [None, self.branch]
            if isinstance(element, SubelementHost):
                assert all([e not in self.building_elements for e in element.sub_elements])
            self._building_elements.append(element)
            element._set_parent(self)

    def remove_building_elements(self, building_elements: BuildingElement | list[BuildingElement]):
        if isinstance(building_elements, BuildingElement):
            building_elements = [building_elements]
        be_copy = self._building_elements.copy()
        for be in building_elements:
            building_element = be
            be_copy.remove(building_element)
            building_element.remove_from_parent()  # TODO could also set it o self.branch
        self._building_elements = be_copy

    def add_building_units(self, building_units: BuildingUnit | list[BuildingUnit]):
        if isinstance(building_units, BuildingUnit):
            building_units = [building_units]
        for unit in building_units:
            typeerror_if_not_isinstance(unit, BuildingUnit)
            assert unit.parent in [None, self.branch]
            if unit.net_floor_area is not None:
                assert (
                    self.usable_area_unassigned is not None
                ), "you are trying to add a building unit with a set area to a building without a set area. Please set usable area for the building first."
                assert (
                    self.usable_area_unassigned + 0.01 >= unit.net_floor_area  # +0.01 to prevent rounding issues
                ), f"Can not add building Unit of area {unit.net_floor_area}, not enough unassigned usable area left ({self.usable_area_unassigned})"
            self._building_units.append(unit)
            unit._set_parent(self)

    def remove_building_units(self, building_units: BuildingUnit | list[BuildingUnit]):
        if isinstance(building_units, BuildingUnit):
            building_units = [building_units]
        bu_copy = self._building_units.copy()
        for building_unit in building_units:
            bu_copy.remove(building_unit)
            building_unit.remove_from_parent()  # TODO could also set it to self.branch
        self._building_units = bu_copy

    # TODO remove?
    def has_dhn_connection(self) -> bool:
        return self.get_dhn_connection() is not None

    # TODO remove?
    def get_dhn_connection(self) -> BuildingDhnConnection | None:
        dhncons = self.find_objects(BuildingDhnConnection)
        if len(dhncons) > 1:
            raise Exception("building has more than one dhn connection, don't know what to do")
        elif len(dhncons) == 1:
            return dhncons[0]

    # TODO remove? => used in electra
    def get_deg_connection(self) -> ElectricityGridConnection:
        degcons = self.find_objects(ElectricityGridConnection)
        if len(degcons) > 1:
            raise Exception("building has more than one dhn connection, don't know what to do")
        elif len(degcons) == 1:
            return degcons[0]



class StructureGroup(Structure):
    _CHILDREN_ATTRIBUTES = {"_structures": "Structure[]"}
    _structures: list[Structure] = None

    def __init__(self, **kwargs):
        self._structures = []
        super().__init__(**kwargs)

    @property
    def structures(self) -> list[Structure]:
        return self._structures.copy()

    @property
    def geometry(self) -> MultiGeometry | None:
        """
        Get the joined geometry of all contained buildings (The structure group
        itself doesn't have a geometry).
        """
        shapes = []
        for structure in self._structures:
            if (
                hasattr(structure, "geometry")  # = the footprint if it's a Building
                and structure.geometry is not None
                and structure.geometry.shape is not None
            ):
                shapes.append(structure.geometry.shape)
        if shapes:
            if all(isinstance(shape, Polygon) for shape in shapes):
                shape = MultiPolygon(shapes)
            else:
                shape = GeometryCollection(shapes)
            geometry = MultiGeometry(shape=shape)
            return geometry

    def add_structures(self, structures: Structure | list[Structure]):
        if isinstance(structures, Structure):
            structures = [structures]
        for structure in structures:
            typeerror_if_not_isinstance_or_none(structure, Structure)
            assert structure.parent is None or structure.parent is self.branch
            self._structures.append(structure)
            structure._set_parent(self)

    def remove_structures(self, structures: Structure | list[Structure]):
        if isinstance(structures, Structure):
            structures = [structures]
        structures_copy = self._structures.copy()
        for structure in structures:
            structures_copy.remove(structure)
            structure.remove_from_parent()  # TODO could also set it to self.branch
        self._structures = structures_copy
