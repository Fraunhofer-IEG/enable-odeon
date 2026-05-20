from abc import ABC
from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Callable, TYPE_CHECKING

import pandas as pd

from .temporal import Temporal
from .base import Object
from .device import Asset
from .component import Socket

from ..processing.utils.utils import (
    typeerror_if_not_isinstance_or_none,
)
from ..processing.utils.finance import (    
    calc_capital_cost_annuity,
    calc_cash_value_factor,
    calc_annuity_factor,
    calc_annual_cost_annuity,
    calc_selected_period_annuity,
)

if TYPE_CHECKING:
    from .device import Asset


class ExpenseType(str, Enum):
    CAPEX = "capex"
    OPERATION = "operation"
    MAINTENANCE = "maintenance"
    COMMODITY = "commodity"
    REVENUE = "revenue"
    FUNDING = "funding"
    OTHER = "other"
    UNKNOWN = "unknown"


class Actor(Object): ...


@dataclass
class Financing:
    """
    Attributes
    ----------
    interest_rate : float
        The interest rate for the financing, e.g. 0.03 for 3% interest.
    observation_period : float
        The observation period in years, e.g. 20 for 20 years.
    price_change_factors : Dict[ExpenseType, float]
        A dictionary mapping ExpenseTypes to their price change factors.
        This can be used to model different price changes for different
        types of expenses, e.g. maintenance costs might increase at a different
        rate than operation costs. A price change factor of 1 corresponds to
        no change, while a factor of 1.03 corresponds to a 3% increase per year.
    """

    interest_rate: float = 0  # e.g. 0.03 = 3% interest
    observation_period: float | None = None  # [a]
    price_change_factors: dict[ExpenseType, float] = field(default_factory=lambda: {})

    def copy(self) -> "Financing":
        """
        Returns a copy of the Financing object.
        """
        return Financing(
            interest_rate=self.interest_rate,
            observation_period=self.observation_period,
            price_change_factors=self.price_change_factors.copy(),
        )


def _segmented_y(segments: dict[float, float], x: float) -> float:
    """
    Return a linearly interpolated value for `x` based on segmented data.

    Parameters
    ----------
    segments : Dict[float, float]
        Mapping of x-values to y-values. Values are linearly interpolated
        between neighboring keys. Outside the range, the closest value is
        used (constant extrapolation).
    x : float
        The x-value to evaluate.

    Returns
    -------
    float
        Interpolated (or extrapolated) y-value for `x`.
    """
    segments = dict(sorted(segments.items()))
    keys = [*segments.keys()]
    if keys[0] > -math.inf:
        segments = {-math.inf: segments[keys[0]], **segments}
    keys = [*segments.keys()]
    if keys[-1] < math.inf:
        segments = {**segments, math.inf: segments[keys[-1]]}
    keys = [*segments.keys()]
    for xl, xu in zip(keys[:-1], keys[1:]):
        if x >= xl and x <= xu:
            yl = segments[xl]
            yu = segments[xu]
            if xl == -math.inf:
                return yl
            elif xu == math.inf:
                return yu
            else:
                return (yu - yl) / (xu - xl) * (x - xl) + yl


class Expense(Object):
    """
    Base class for expenses.
    """

    _ASSOCIATED_ATTRIBUTES = ["_relative_expense"]
    _relative_expense: tuple["Expense", float] | None = None

    # other attributes:
    _sender: Actor | None = None
    _receiver: Actor | None = None
    type: ExpenseType | None = None
    is_annuity: bool = False
    price_change_factor: float | None = None

    def __init__(
        self,
        type: ExpenseType = ExpenseType.UNKNOWN,
        sender: Actor | None = None,
        receiver: Actor | None = None,
        financing: Financing | None = None,
        is_annuity: bool = False,
        relative_expense: tuple["Expense", float] | None = None,
        price_change_factor: float | None = None,
        **kwargs,
    ) -> None:
        """
        Parameters
        ----------
        type : ExpenseType
            Expense type classification.
        sender : Actor or None
            Sender of the expense.
        receiver : Actor or None
            Receiver of the expense.
        financing : Financing or None
            Financing settings to apply for annuity calculations. If no
            financing is given, the branch's financing will be used if
            available.
        is_annuity : bool
            Whether the costs described by the values and functions are already
            annuities. If they are, calculation of annuity will be skipped in
            `calc_annuity`, and `calc` will already return the annuity. This can
            be used if the costs are already given as annuities, or if they are
            due annually and the price change factor already includes the
            interest rate, so that calculation of annuity according to VDI2067
            would lead to double counting of the interest.
        relative_expense : Tuple[Expense, float] or None
            Reference expense and factor to express this expense relative to
            another expense.
        price_change_factor : float or None
            Factor by which the expense changes per year.
        **kwargs : Any
            Passed to `Object`.

        Notes
        -----
        Subclasses may add further parameters and should keep the parameter
        order consistent with their `__init__` signature.

        """
        self.type = type
        self._sender = sender  # call setter
        self._receiver = receiver  # call setter
        self._financing = financing
        self.is_annuity = is_annuity
        self._relative_expense = relative_expense
        self._price_change_factor = price_change_factor
        super().__init__(**kwargs)

    @property
    def sender(self) -> Actor:
        return self._sender

    @property
    def receiver(self) -> Actor:
        return self._receiver

    @sender.setter
    def sender(self, sender: Actor | None):
        assert isinstance(sender, Actor) or sender is None
        self._sender = sender
        # TODO alert sender

    @receiver.setter
    def receiver(self, receiver: Actor | None):
        assert isinstance(receiver, Actor) or receiver is None
        self._receiver = receiver
        # TODO alert receiver

    @property
    def financing(self) -> Financing | None:
        if self._financing is not None:
            return self._financing
        elif self.branch is not None:
            return self.branch.financing

    @financing.setter
    def financing(self, financing: Financing | None):
        typeerror_if_not_isinstance_or_none(financing, Financing)
        self._financing = financing

    @property
    def price_change_factor(self) -> float:
        if self._price_change_factor is not None:
            return self._price_change_factor
        elif self.financing is not None:
            return self.financing.price_change_factors.get(self.type, 1.0)

    @property
    def is_virtual(self) -> bool:
        """
        Returns whether the Expense is virtual. An expense is virtual if it's
        sender equals it's receiver (both not being None).
        """
        return self._sender is self._receiver and self._sender is not None

    def calc(self, **kwargs) -> pd.Series | float:
        raise NotImplementedError("abstract base method")

    def calc_annuity(self, **kwargs) -> pd.Series | float:
        raise NotImplementedError("abstract base method")


# TODO introduce class AssetExpense as intermediate
class FixExpense(Expense):
    """
    An expense than doesn't depend on anything, not even lifetime nor period
    """

    value: float | pd.Series = None  # TODO make temporal?

    def __init__(
        self,
        value: float | pd.Series | None = None,
        asset_function: Callable[[Asset], float] | None = None,
        type: ExpenseType | None = None,
        **kwargs,
    ) -> None:
        """
        Parameters
        ----------
        value : float or pandas.Series or None
            Fixed expense value.
        asset_function : Callable[[Asset], float] or None
            Function to compute the expense based on the asset.
        type : ExpenseType or None
            Expense type classification.
        **kwargs : Any
            Passed to `Expense`.
        """
        super().__init__(type=type, **kwargs)
        self.value = value
        self.asset_function = asset_function

    def calc(self, **kwargs) -> pd.Series | float:
        """
        Calculate the fixed expense.

        Parameters
        ----------
        **kwargs : Any
            Passed to `asset_function` if used.

        Returns
        -------
        float or pandas.Series
            Calculated expense value.
        """
        if self.value is not None:
            return self.value

        elif self.asset_function is not None:
            return self.asset_function(self.parent, **kwargs)


class PerPeriodExpense(Expense):  # PerLifeExpense ist im Grunde auch eine PerPeriodExpense -> merge?
    """
    An expense that is due once in a period, e.g. once per year.
    """

    fix_value: float | None = None
    per_dimension_value: float | None = None
    period: int | None = None
    dimension_function: Callable[[float], float] | None = None
    dimension_function_kwargs: dict[str, Any] | None = None
    asset_function: Callable[[Asset], float] | None = None
    asset_function_kwargs: dict[str, Any] | None = None

    def __init__(
        self,
        fix_value: float = 0,
        per_dimension_value: float = 0,
        per_dimension_segments: dict[float, float] | None = None,
        dimension_function: Callable[[float], float] | None = None,
        dimension_function_kwargs: dict[str, Any] | None = None,
        asset_function: Callable[[Asset], float] | None = None,
        asset_function_kwargs: dict[str, Any] | None = None,
        relative_expense: tuple[Expense, float] | None = None,
        price_change_factor: float = 1,
        period: int = 1,
        period_indices: list[int] | None = None,
        financing: Financing | None = None,
        is_annuity: bool = False,
        type: ExpenseType | None = None,
        sender: Actor | None = None,
        receiver: Actor | None = None,
        **kwargs,
    ) -> None:
        """
        Parameters
        ----------
        fix_value : float
            Fixed amount due each period.
        per_dimension_value : float
            Amount due each period scaled by the asset's dimension.
        per_dimension_segments : Dict[float, float] or None
            Piecewise linear mapping from dimension to amount. Values are
            interpolated; outside the range, the closest value is used.
        dimension_function : Callable[[float], float] or None
            Function to calculate the expense based on the asset's dimension.
        dimension_function_kwargs : Dict[str, Any] or None
            Keyword arguments for `dimension_function`.
        asset_function : Callable[[Asset], float] or None
            Function to calculate the expense based on the asset.
        asset_function_kwargs : Dict[str, Any] or None
            Keyword arguments for `asset_function`.
        relative_expense : Tuple[Expense, float] or None
            Reference expense and factor to express this expense relative to
            another expense.
        price_change_factor : float
            Factor by which the expense changes per year.
        period : int
            Period length in years.
        period_indices : List[int] or None
            Period indices for which the payment is due. If None, it is due
            for all periods.
        financing : Financing or None
            Financing settings to apply for annuity calculations. If no
            financing is given, the branch's financing will be used if
            available.
        is_annuity : bool
            Whether the costs described by the values and functions are already
            annuities. If they are, calculation of annuity will be skipped in
            `calc_annuity`, and `calc` will already return the annuity.
        type : ExpenseType or None
            Expense type classification.
        sender : Actor or None
            Sender of the expense.
        receiver : Actor or None
            Receiver of the expense.
        **kwargs : Any
            Passed to `Expense`.
        """
        self.fix_value = fix_value
        self.per_dimension_value = per_dimension_value
        self.per_dimension_segments = per_dimension_segments
        self.period = period
        self.period_indices = period_indices
        self.dimension_function = dimension_function
        self.dimension_function_kwargs = dimension_function_kwargs
        self.asset_function = asset_function
        self.asset_function_kwargs = asset_function_kwargs
        super().__init__(
            type=type,
            sender=sender,
            receiver=receiver,
            financing=financing,
            is_annuity=is_annuity,
            relative_expense=relative_expense,
            price_change_factor=price_change_factor,
            **kwargs,
        )

    def calc_annuity(self) -> float:
        """
        Calc annuity of periodical costs (according to VDI2067).

        If `is_annuity` is True, this will return the calculated value based
        directly on parameters. Otherwise, the Expense's `financing` will be
        applied.
        """
        if self.is_annuity:
            return self.calc()

        if self.period == 1 and not self.period_indices:
            return self._calc_annuity_annual_payment()

        else:
            return self._calc_annuity_complex_payment()

    def _calc_annuity_annual_payment(self) -> float:
        """
        Calc the annuity of periodical costs that are due annually.
        """
        if self.financing is not None:
            observation_period = self.financing.observation_period
            interest_factor = 1.0 + self.financing.interest_rate
        else:
            observation_period = self.parent.lifetime_nominal
            interest_factor = 1.0

        return calc_annual_cost_annuity(
            cost_first_year=self.calc(),
            price_change_factor=self.price_change_factor,
            interest_factor=interest_factor,
            observation_period=observation_period,
        )

    def _calc_annuity_complex_payment(self) -> float:
        """
        Calc the annuity of periodical costs that are due each x years, maybe
        intermittent
        """
        if self.financing is not None:
            observation_period = self.financing.observation_period
            interest_factor = 1.0 + self.financing.interest_rate
        else:
            observation_period = self.parent.lifetime_nominal
            interest_factor = 1.0

        return calc_selected_period_annuity(
            periodical_amount=self.calc(),
            price_change_factor=self.price_change_factor,
            interest_factor=interest_factor,
            observation_period=observation_period,
            period=self.period,
            period_indices=self.period_indices,
        )

    def calc(self) -> float:
        """
        Calc the value of the first payment (today)

        If `is_annuity` is True, this will already return the annuity (and thus
        have the same value as `calc_annuity`), otherwise it will return the
        value of the first payment, which may be different from the annuity if
        the costs are not due annually or if the price change factor includes
        the interest rate.
        """

        res = 0

        if self.fix_value != 0:
            res += self.fix_value

        if self.per_dimension_value != 0 and self.parent.dimension is not None:
            res += self.per_dimension_value * self.parent.dimension

        if self.per_dimension_segments is not None and self.parent.dimension is not None:
            res += _segmented_y(segments=self.per_dimension_segments, x=self.parent.dimension)

        if self.dimension_function is not None and self.parent.dimension is not None:
            res += self.dimension_function(self.parent.dimension, **(self.asset_function_kwargs or {}))

        if self.asset_function is not None:
            res += self.asset_function(self.parent, **(self.asset_function_kwargs or {}))

        # TODO should go to super?
        if self._relative_expense is not None:
            res += self._relative_expense[0].calc() * self._relative_expense[1]

        return res


class PerLifeExpense(PerPeriodExpense):
    """
    An expense that is due once per lifetime of an Asset. It may depend on the
    Asset's dimension or other attributes.
    """

    def __init__(
        self,
        fix_value: float = 0,
        per_dimension_value: float = 0,
        per_dimension_segments: dict[float, float] | None = None,
        dimension_function: Callable[[float], float] | None = None,
        asset_function: Callable[[Asset], float] | None = None,
        relative_expense: tuple[Expense, float] | None = None,
        price_change_factor: float | None = None,
        financing: Financing | None = None,
        is_annuity: bool = False,
        type: ExpenseType | None = None,
        sender: Actor | None = None,
        receiver: Actor | None = None,
        **kwargs,
    ) -> None:
        """
        Parameters
        ----------
        fix_value : float
            Fixed amount due once per lifetime.
        per_dimension_value : float
            Amount due once per lifetime scaled by the asset's dimension.
        per_dimension_segments : Dict[float, float] or None
            Piecewise linear mapping from dimension to amount. Values are
            interpolated; outside the range, the closest value is used.
        dimension_function : Callable[[float], float] or None
            Function to calculate the expense based on the asset's dimension.
        asset_function : Callable[[Asset], float] or None
            Function to calculate the expense based on the asset.
        relative_expense : Tuple[Expense, float] or None
            Reference expense and factor to express this expense relative to
            another expense.
        price_change_factor : float or None
            Factor by which the expense changes per year.
        financing : Financing or None
            Financing settings to apply for annuity calculations. If no
            financing is given, the branch's financing will be used if
            available.
        is_annuity : bool
            Whether the costs described by the values and functions are already
            annuities. If they are, calculation of annuity will be skipped in
            `calc_annuity`, and `calc` will already return the annuity.
        type : ExpenseType or None
            Expense type classification.
        sender : Actor or None
            Sender of the expense.
        receiver : Actor or None
            Receiver of the expense.
        **kwargs : Any
            Passed to `PerPeriodExpense`.
        """
        super().__init__(
            fix_value=fix_value,
            per_dimension_value=per_dimension_value,
            per_dimension_segments=per_dimension_segments,
            dimension_function=dimension_function,
            asset_function=asset_function,
            relative_expense=relative_expense,
            price_change_factor=price_change_factor,
            period=None,
            financing=financing,
            is_annuity=is_annuity,
            type=type,
            sender=sender,
            receiver=receiver,
            **kwargs,
        )

    def calc_annuity(self) -> float:
        """
        Calc annuity.

        This will use the formula for annuity of capial costs (according to
        VDI2067).

        If `is_annuity` is True, this will return the calculated value based
        directly on parameters. Otherwise, the Expense's `financing` will be
        applied.
        """
        costs = self.calc()

        if self.is_annuity:
            return costs

        else:
            if self.financing is None:
                raise Exception("No financing given")
            if self.parent.lifetime_nominal is None:
                raise Exception("No lifetime given")

            return calc_capital_cost_annuity(
                investment_amount=costs,
                service_life=self.parent.lifetime_nominal,
                price_change_factor=(
                    self.price_change_factor if self.price_change_factor is not None else 1.0
                ),  # TODO fix for old pickle in ZZV - remove later
                interest_factor=1.0 + self.financing.interest_rate,
                observation_period=self.financing.observation_period,
            )


class _DeviceExpense(Expense, ABC): ...


class PerThroughputExpense(_DeviceExpense):
    """
    An expense that is due per throughput on a specific socket.
    """

    _ASSOCIATED_ATTRIBUTES = ["socket"]
    socket: Socket | None = None
    value: float | pd.Series | None = None  # TODO make temporal?

    def __init__(
        self,
        value: float | pd.Series | None = None,
        temporal_function: Callable[[Temporal], float | pd.Series] | None = None,
        socket: Socket | None = None,
        price_change_factor: float = 1.0,
        financing: Financing | None = None,
        is_annuity: bool = False,
        type: ExpenseType | None = None,
        sender: Actor | None = None,
        receiver: Actor | None = None,
        **kwargs,
    ) -> None:
        """
        Parameters
        ----------
        value : float or pandas.Series or None
            Amount due per unit throughput.
        temporal_function : Callable[[Temporal], float or pandas.Series] or None
            Function to calculate the throughput-based amount.
        socket : Socket or None
            Unambiguous description of the concerned input or output. Optional
            if the component has only one input or output.
        price_change_factor : float
            Factor by which the expense changes per year.
        financing : Financing or None
            Financing settings to apply for annuity calculations. If no
            financing is given, the branch's financing will be used if
            available.
        is_annuity : bool
            Whether the costs described by the values and functions are already
            annuities. If they are, calculation of annuity will be skipped in
            `calc_annuity`, and `calc` will already return the annuity.
        type : ExpenseType or None
            Expense type classification.
        sender : Actor or None
            Sender of the expense.
        receiver : Actor or None
            Receiver of the expense.
        **kwargs : Any
            Passed to `Expense`.
        """
        self.value = value
        self.socket = socket
        self.temporal_function = temporal_function
        super().__init__(
            type=type,
            sender=sender,
            receiver=receiver,
            financing=financing,
            is_annuity=is_annuity,
            price_change_factor=price_change_factor,
            **kwargs,
        )

    def calc_annuity(self) -> float:
        """
        Calc annuity (according to VDI2067).

        If `is_annuity` is True, this will return the calculated value based
        directly on parameters. Otherwise, the Expense's `financing` will be
        applied.
        """
        if self.is_annuity:
            return self.calc()

        else:
            if self.financing is not None:
                observation_period = self.financing.observation_period
                interest_factor = 1.0 + self.financing.interest_rate
            else:
                return self.calc()

            return (
                self.calc()
                * calc_cash_value_factor(
                    price_change_factor=self.price_change_factor,
                    interest_factor=interest_factor,
                    observation_period=observation_period,
                )
                * calc_annuity_factor(
                    interest_factor=interest_factor,
                    observation_period=observation_period,
                )
            )

    def calc(self) -> float:
        """
        Calc the value of the throughput expense in the current year / today.

        If `is_annuity` is True, this will already return the annuity.
        """
        flow = self.parent.get_flow(self.socket)

        if self.value is not None:
            if flow is None or flow.total is None:
                res = 0
            elif flow.is_constant:
                res = self.value * flow.total
            else:
                res = self.value * flow.series  # TODO does this work for two series?

        elif self.temporal_function is not None:
            res = self.temporal_function(flow)

        if isinstance(res, pd.Series):
            res = res.sum()

        if pd.isna(res):
            res = 0

        return res

    def value_as_annuity(self) -> float | pd.Series | None:
        """
        Return the `value` attribute of the Asset, as an annuity.
        """
        if self.is_annuity:
            return self.value

        if self.value is not None:

            if self.financing is not None:
                observation_period = self.financing.observation_period
                interest_factor = 1.0 + self.financing.interest_rate
            else:
                observation_period = self.parent.lifetime_nominal
                interest_factor = 1.0

            res = self.value
            res *= calc_cash_value_factor(
                price_change_factor=self.price_change_factor,
                interest_factor=interest_factor,
                observation_period=observation_period,
            )
            res *= calc_annuity_factor(
                interest_factor=interest_factor,
                observation_period=observation_period,
            )
            if isinstance(res, pd.Series):
                return res.copy()
            else:
                return res  # float


class _TransformerExpense(Expense, ABC): ...


class PerUsageTimeExpense(_TransformerExpense):
    """
    An expense that is due per hour an asset is in use.
    """

    value: float = None

    def __init__(
        self,
        value: float,
        type: ExpenseType | None = None,
        sender: Actor | None = None,
        receiver: Actor | None = None,
        **kwargs,
    ) -> None:
        """
        Parameters
        ----------
        value : float
            Amount due per hour in use.
        type : ExpenseType or None
            Expense type classification.
        sender : Actor or None
            Sender of the expense.
        receiver : Actor or None
            Receiver of the expense.
        **kwargs : Any
            Passed to `Expense`.
        """
        self.value = value
        super().__init__(
            type=type,
            sender=sender,
            receiver=receiver,
            **kwargs,
        )

    def calc(self) -> float:
        assert isinstance(self.value, (float, int))
        return self.parent.usage_time * self.value


class PerUsageExpense(_TransformerExpense):
    """
    An absolute expense that is due per contiguous period of usage.
    """

    value: float = None

    def __init__(
        self,
        value: float,
        type: ExpenseType | None = None,
        sender: Actor | None = None,
        receiver: Actor | None = None,
        **kwargs,
    ) -> None:
        """
        Parameters
        ----------
        value : float
            Amount due per usage period.
        type : ExpenseType or None
            Expense type classification.
        sender : Actor or None
            Sender of the expense.
        receiver : Actor or None
            Receiver of the expense.
        **kwargs : Any
            Passed to `Expense`.
        """
        self.value = value
        super().__init__(
            type=type,
            sender=sender,
            receiver=receiver,
            **kwargs,
        )

    def calc(self) -> float:
        assert isinstance(self.value, (float, int))
        return self.parent.usage_count * self.value


class BuildingTransformationExpense(PerLifeExpense): ...


class BuildingConstructionExpense(PerLifeExpense): ...
