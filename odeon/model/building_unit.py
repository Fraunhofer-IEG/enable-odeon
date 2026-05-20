from numbers import Number
from datetime import datetime

from .base import Object, StrEnum
from .energy_system import EnergySystemHost
from .contract import DeliveryContract, FeedInContract
from .building_physics import BuildingThermalZone

from ..processing.utils.utils import typeerror_if_not_isinstance, typeerror_if_not_isinstance_or_none


class CommercialType(StrEnum):
    CONSTRUCTION = "construction"
    OFFICE = "office"
    BANK = "bank"
    PUBLISHER = "publisher"
    OTHERSERVICES = "other_services"
    LOCALAUTHORITIES = "local_authorities"
    POSTAL = "postal"
    TELECOMMUNICATION = "telecommunication"
    RAILWAY = "railway"
    INDUSTRYMETAL = "metal_industry"
    INDUSTRYMOTOR = "motor_industry"
    INDUSTRYWOOD = "wood_industry"
    INDUSTRYPAPER = "paper_and_printing_industry"
    TRADERETAILFOOD = "retail_trade_food"
    TRADERETAILNONFOOD = "retail_trade_nonfood"
    TRADEWHOLESALEFOOD = "wholesale_food"
    TRADEWHOLESALENONFOOD = "wholesale_nonfood"
    TRADEAGENCIES = "trade_agency"
    HOSPITAL = "hospital"
    SCHOOL = "school"
    BATH = "public_bath"
    LODGINGINDUSTRY = "lodging_industry"
    CATERINGINDUSTRY = "restaurant"
    SHELTER = "non-profit_organization_and_shelter"
    BAKERY = "bakery"
    BUTCHER = "butcher_shop"
    INDUSTRYFOOD = "rest_of_food_industry"
    LAUNDRY = "laundries_and_(dry)_cleaners"
    AGRICULTURE = "agriculture"
    HORTICULTURE = "horticulture_and_gardening"
    AIRPORT = "airport"
    TEXTILE = "clothing_leather_textile"
    SHIPPING = "shipping_storage_transportation"
    MARKETSTALLS = "market_stall_etc."
    METALPLASTICRUBBER = "non-ferrous_metal_plastic_rubber"
    COLDSTORE = "cold_store"
    WATERSEWAGE = "water_supply_and_sewage_disposal"
    DATACENTER = "data_center"
    NONGHD = "not_considered_of_the_GHD_sector"
    INDUSTRY = "industry"
    STREETLIGHTING = "street_lighting"
    MFHFACILITIES = "community_facility_mfh"
    MILITARY = "military"
    OTHER = "other"
    INSURANCE = "insurance"
    GROCERIES = "groceries"


class ResidentAgeGroup(StrEnum):
    BELOW_18 = "18_or_below"
    BETWEEN_18_AND_65 = "above_18_and_65_or_below"
    ABOVE_65 = "above_65"


class SourceOfIncome(StrEnum):
    OCCUPIED = "occupied"
    PUBLIC_SUPPORT = "public_support"
    RETIRED = "retired"
    FAMILY_SUPPORT = "family_support"
    OWN_WEALTH = "own_wealth"


class BuildingUnit(EnergySystemHost):

    # children attributes:
    _CHILDREN_ATTRIBUTES = {"_building_physics": "BuildingThermalZone"}
    _building_physics: BuildingThermalZone = None

    # additional attributes:
    base_area: float = None  # [m²]
    _net_floor_area: float = None  # [m²]
    holidays: list[datetime] = None
    vacations: list[datetime] = None

    # additional methods:

    @property
    def feed_in_contract(self) -> FeedInContract:
        return self._feed_in_contract

    @feed_in_contract.setter
    def feed_in_contract(self, feed_in_contract: FeedInContract):
        typeerror_if_not_isinstance_or_none(feed_in_contract, FeedInContract)
        self._feed_in_contract = feed_in_contract

    @property
    def delivery_contract(self) -> DeliveryContract:
        return self._delivery_contract

    @delivery_contract.setter
    def delivery_contract(self, delivery_contract: DeliveryContract):
        typeerror_if_not_isinstance_or_none(delivery_contract, DeliveryContract)
        self._delivery_contract = delivery_contract

    @property
    def building_physics(self) -> BuildingThermalZone:
        return self._building_physics

    @building_physics.setter
    def building_physics(self, building_physics: BuildingThermalZone | None):
        typeerror_if_not_isinstance_or_none(building_physics, BuildingThermalZone)
        # TODO remove current building physics if present
        self._building_physics = building_physics
        building_physics._set_parent(self)

    @property
    def net_floor_area(self):
        return self._net_floor_area

    @net_floor_area.setter
    def net_floor_area(self, net_floor_area: Number):
        if self.parent is not None:
            assert (
                self.parent.usable_area_unassigned > net_floor_area
            ), f"not enough unassigned building area left to change unit {self.id}s area to {net_floor_area}"
        self._net_floor_area = net_floor_area


class Resident(Object):
    age: ResidentAgeGroup = None
    source_of_income: SourceOfIncome = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class Household(BuildingUnit):
    _CHILDREN_ATTRIBUTES = {"_residents": "Resident[]"}
    _residents: Resident = None

    # additional attributes:
    _size: int = None

    def __init__(self, **kwargs):
        self._residents = []
        super().__init__(**kwargs)

    @property
    def residents(self) -> Resident:
        return self._residents

    @property
    def size(self) -> int:
        return len(self._residents) or self._size

    @size.setter
    def size(self, size: int):
        assert not self._residents, "can't set size when individual residents have been added"
        assert size is None or (type(size) is int and size > 0), "only positive integer values or None allowed"
        self._size = size

    def add_residents(self, residents: Resident | list[Resident]):
        if isinstance(residents, Resident):
            residents = [residents]
        for resident in residents:
            typeerror_if_not_isinstance(resident, Resident)
            if not isinstance(resident, Resident):
                raise Exception(f"{resident} is not an instance of {Resident}")
            self._residents.append(resident)
            resident._set_parent(self)

    def remove_residents(self, *residents: Resident | int):
        residents_copy = self._residents.copy()
        for r in residents:
            resident = r
            if isinstance(r, int):
                resident = self._residents[r]
            residents_copy.remove(resident)

        self._residents = residents_copy


class ScalingReference(Object):
    amount: float = None  # no common unit

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class Commercial(BuildingUnit):
    _CHILDREN_ATTRIBUTES = {"_scaling_reference": "ScalingReference"}
    _scaling_reference: ScalingReference = None

    # additional attributes:
    _commercial_type: CommercialType = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def scaling_reference(self) -> ScalingReference | None:
        return self._scaling_reference

    @scaling_reference.setter
    def scaling_reference(self, scaling_reference: ScalingReference | None):
        typeerror_if_not_isinstance_or_none(scaling_reference, ScalingReference)
        self._scaling_reference = scaling_reference
        scaling_reference._set_parent(self)

    @property
    def commercial_type(self) -> CommercialType | None:
        return self._commercial_type

    @commercial_type.setter
    def commercial_type(self, commercial_type: CommercialType | None):
        typeerror_if_not_isinstance_or_none(commercial_type, CommercialType)
        self._commercial_type = commercial_type
