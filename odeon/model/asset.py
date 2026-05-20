from __future__ import annotations
from typing import TYPE_CHECKING, Any, Dict, Type, Union, Literal

from .base import GeometryObject
from .decision import DecisionState, DecisionType, AssetDecision
from ..processing.utils.utils import typeerror_if_not_list_isinstance, typeerror_if_not_isinstance

if TYPE_CHECKING:
    from .expense import Expense, ExpenseType

import odeon.model as om


# ----------------------------------------------------------------------------------------------------------------------
# Asset
# ----------------------------------------------------------------------------------------------------------------------


class Asset(GeometryObject):
    """
    At the moment, an abstract class bundling economic data, location and
    decisions for energy system objects.

    An Asset is characterized by a scalar dimension.

    Attributes
    ----------
    - `type`: can hold any information
    """

    _CHILDREN_ATTRIBUTES = {"_expenses": "Expense[]"}
    _expenses: list["Expense"] = None

    _ASSOCIATED_ATTRIBUTES = ["_decision"]
    _decision: AssetDecision = None

    # additional attributes:
    dimension: float = None
    dimension_min: float = None
    dimension_max: float = None
    _exists: bool = True
    type: dict[str, Any] = None
    lifetime_nominal: float = None  # [a]
    lifetime_remaining: float = None  # [a]
    space: float = None  # [m²] # TODO change to consumptions: dict[str, Any]?

    def __init__(self, **kwargs):
        self._expenses = []
        self.type = {}
        self._decision = None
        super().__init__(**kwargs)

    @property
    def expenses(self) -> list["Expense"]:
        if self._expenses is None:  # TODO Just a fix for older pickles in vista. Remove again later
            self._expenses = []
        return self._expenses.copy()

    def add_expenses(self, expenses: Expense | list["Expense"]):
        if not isinstance(expenses, list):
            expenses = [expenses]
        for expense in expenses:
            typeerror_if_not_isinstance(expense, om.Expense)
            assert expense.parent is None or expense.parent is self.branch
            self._expenses.append(expense)
            expense._set_parent(self)

    def remove_expenses(self, expenses: Expense | list["Expense"]):
        if not isinstance(expenses, list):
            expenses = [expenses]
        expenses_copy = self._expenses.copy()
        for expense in expenses:
            typeerror_if_not_isinstance(expense, om.Expense)
            expenses_copy.remove(expense)
            expense.remove_from_parent()
        self._expenses = expenses_copy

    @property
    def existence(self) -> DecisionState:
        if self._decision is None:
            return DecisionState.UNKNOWN
        elif self._decision.type_ is DecisionType.INDEPENDENT_SCALING:
            if self._decision.decided:
                return DecisionState.DECIDED_SCALING
            else:
                return DecisionState.UNDECIDED_SCALING
        elif self._exists:
            if self._decision is None:
                return DecisionState.FIXED
            elif self._decision.decided:
                return DecisionState.DECIDED_FOR
            else:
                return DecisionState.UNDECIDED_EXISTING
        else:
            if self._decision.decided:
                return DecisionState.DECIDED_AGAINST
            else:
                return DecisionState.UNDECIDED_OPTION

    @property
    def exists(self):
        return self._exists

    @exists.setter
    def exists(self, value: bool):
        typeerror_if_not_isinstance(value, bool)
        if self._decision:
            self._decision.set_existing(self, value)
        else:
            self._exists = value

    @property
    def decision(self):
        return self._decision

    def calc_expenses(
        self,
        expense_types: ExpenseType | list["ExpenseType"] | None = None,
        exclude_expense_types: ExpenseType | list["ExpenseType"] | None = None,
        expense_classes: Type | list[Type] | None = None,
        exclude_expense_classes: Type | list[Type] | None = None,
        name: str | None = None,
        include_virtuals: bool = True,
    ):
        expenses = self.get_expenses(
            expense_types=expense_types,
            exclude_expense_types=exclude_expense_types,
            expense_classes=expense_classes,
            exclude_expense_classes=exclude_expense_classes,
            name=name,
        )  # will typecheck
        typeerror_if_not_isinstance(include_virtuals, bool)
        res = 0.0
        for e in expenses:
            if (not include_virtuals) or not e.is_virtual:
                res += e.calc()
        return res

    def calc_annuities(
        self,
        expense_types: ExpenseType | list["ExpenseType"] | None = None,
        exclude_expense_types: ExpenseType | list["ExpenseType"] | None = None,
        expense_classes: Type | list[Type] | None = None,
        exclude_expense_classes: Type | list[Type] | None = None,
        name: str | None = None,
        include_virtuals: bool = True,
    ) -> float:
        expenses = self.get_expenses(
            expense_types=expense_types,
            exclude_expense_types=exclude_expense_types,
            expense_classes=expense_classes,
            exclude_expense_classes=exclude_expense_classes,
            name=name,
        )  # will typecheck
        typeerror_if_not_isinstance(include_virtuals, bool)
        res = 0.0
        for e in expenses:
            if (not include_virtuals) or not e.is_virtual:
                res += e.calc_annuity()
        return res

    def get_expenses(
        self,
        expense_types: ExpenseType | list["ExpenseType"] | None = None,
        exclude_expense_types: ExpenseType | list["ExpenseType"] | None = None,
        expense_classes: Type | list[Type] | None = None,
        exclude_expense_classes: Type | list[Type] | None = None,
        name: str | None = None,
    ):
        if expense_types is None:
            expenses = self.expenses.copy()
        else:
            if not isinstance(expense_types, list):
                expense_types = [expense_types]
            typeerror_if_not_list_isinstance(expense_types, om.ExpenseType)
            expenses = [e for e in self.expenses if e.type in expense_types]
        if exclude_expense_types is not None:
            if not isinstance(exclude_expense_types, list):
                exclude_expense_types = [exclude_expense_types]
            typeerror_if_not_list_isinstance(exclude_expense_types, om.ExpenseType)
            expenses = [e for e in expenses if e.type not in exclude_expense_types]

        if expense_classes is not None:
            if not isinstance(expense_classes, list):
                expense_classes = [expense_classes]
            typeerror_if_not_list_isinstance(expense_classes, type)
            expenses = [e for e in expenses if isinstance(e, tuple(expense_classes))]

        if exclude_expense_classes is not None:
            if not isinstance(exclude_expense_classes, list):
                exclude_expense_classes = [exclude_expense_classes]
            typeerror_if_not_list_isinstance(exclude_expense_classes, type)
            expenses = [e for e in expenses if not isinstance(e, tuple(exclude_expense_classes))]

        if name is not None:
            typeerror_if_not_isinstance(name, str)
            expenses = [e for e in expenses if e.name == name]
        return expenses

    def get_expense(
        self,
        expense_types: ExpenseType | list["ExpenseType"] | None = None,
        exclude_expense_types: ExpenseType | list["ExpenseType"] | None = None,
        expense_classes: Type | list[Type] | None = None,
        exclude_expense_classes: Type | list[Type] | None = None,
        name: str | None = None,
        not_found: Literal["none", "error"] = "error",
    ) -> Union["Expense", None]:
        if not_found not in ["none", "error"]:
            raise ValueError("not_found must be either 'none' or 'error'.")

        expenses = self.get_expenses(
            expense_types=expense_types,
            exclude_expense_types=exclude_expense_types,
            expense_classes=expense_classes,
            exclude_expense_classes=exclude_expense_classes,
            name=name,
        )  # will typecheck
        if len(expenses) == 1:
            return expenses[0]
        elif len(expenses) > 1:
            raise Exception(f"Expected at most one expense, but found {len(expenses)}.")
        elif len(expenses) == 0:
            if not_found == "error":
                raise Exception(f"Expected exactly one expense, but found {len(expenses)}.")
            else:
                return None


class CombiAsset(Asset):
    _CHILDREN_ATTRIBUTES = {"_assets": "Asset[]"}
    _assets: list[Asset] = None

    # additional attributes:
    _ASSET_TYPES: list[Type] = None

    def __init__(self, **kwargs):
        self._assets = []
        self._ASSET_TYPES = []
        super().__init__(**kwargs)
        assert all(d.__class__ in self._ASSET_TYPES for d in self._assets)
        for at in self._ASSET_TYPES:
            if not any(d.__class__ is at for d in self._assets):
                self._assets.append(at())

    def get_asset(self, asset_type: type) -> Asset | list[Asset]:
        typeerror_if_not_isinstance(asset_type, type)
        assets = [x for x in self._assets if isinstance(x, asset_type)]
        return assets[0] if len(assets) == 1 else assets

    def calc_expenses(self, expense_types: list["ExpenseType"] = None, name: str | None = None):
        ret = super().calc_expenses(expense_types, name=name)  # will typecheck
        for d in self._assets:
            ret += d.calc_expenses(expense_types, name=name)  # will typecheck
        return ret


class AssetGroup(Asset):
    _CHILDREN_ATTRIBUTES = {"_assets": "Asset[]"}
    _assets: list[Asset] = None

    _ALLOWED_ASSET_TYPES: list[Type] = None

    def __init__(self, assets: list[Asset] = None, **kwargs):
        self._assets = []
        self._allowed_asset_types = self._ALLOWED_ASSET_TYPES.copy()
        super().__init__(**kwargs)
        if assets is not None:
            for asset in assets:
                self.add_asset(asset)

    @property
    def assets(self) -> list[Asset]:
        return self._assets.copy()

    def add_asset(self, asset: Asset):
        typeerror_if_not_isinstance(asset, Asset)
        if not any(isinstance(asset, aat) for aat in self._allowed_asset_types):
            raise TypeError()
        if asset in self._assets:
            raise ValueError()
        self._assets.append(asset)
        assert asset.parent is None
        asset._set_parent(self)

    def remove_asset(self, asset: Asset):
        typeerror_if_not_isinstance(asset, Asset)
        if asset not in self._assets:
            raise ValueError()
        self._assets.remove(asset)
        asset.remove_from_parent()
