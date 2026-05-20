import pandas as pd

from .base import Object


class Contract(Object):
    energy_price: pd.Series = None  # [EUR/kWh] # TODO make temporal
    limit_power: float = None  # [kW]
    delivered_energy: pd.Series = None  # [kWh] # TODO make temporal
    energy_cost: pd.Series = None  # [EUR] # TODO make temporal
    contract_type: str = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class DeliveryContract(Contract):
    shutoff_time_hp: dict = None  # TODO: pd.Series? # TODO unit?
    shutoff_time_charging_pole: dict = None  # TODO: pd.Series? # TODO unit?

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class FeedInContract(Contract): ...
