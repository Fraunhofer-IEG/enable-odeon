from typing import Literal

from ..model.base import Object
from ..model.expense import PerLifeExpense, PerPeriodExpense, PerThroughputExpense, ExpenseType, Expense
from .utils.utils import typeerror_if_not_isinstance, typeerror_if_not_list_isinstance


def per_life_capex(**kwargs):
    return PerLifeExpense(type=ExpenseType.CAPEX, **kwargs)


def per_life_funding(**kwargs):
    return PerLifeExpense(type=ExpenseType.FUNDING, **kwargs)


def per_year_maintenance(**kwargs):
    return PerPeriodExpense(type=ExpenseType.MAINTENANCE, **kwargs)


def per_year_operation(**kwargs):
    return PerPeriodExpense(type=ExpenseType.OPERATION, **kwargs)


def per_throughput_commodity(**kwargs):
    return PerThroughputExpense(type=ExpenseType.COMMODITY, **kwargs)


def per_throughput_revenue(**kwargs):
    return PerThroughputExpense(type=ExpenseType.REVENUE, **kwargs)


def calc_expenses(
    include_objects: Object | list[Object],
    expense_types: ExpenseType | list[ExpenseType] | None = None,
    *,
    exclude_expense_types: ExpenseType | list[ExpenseType] | None = None,
    expense_classes: type | list[type] | None = None,
    exclude_expense_classes: type | list[type] | None = None,
    name: str | None = None,
    include_virtuals: bool = True,
):
    expenses = get_expenses(
        include_objects=include_objects,
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
    include_objects: Object | list[Object],
    expense_types: ExpenseType | list[ExpenseType] | None = None,
    *,
    exclude_expense_types: ExpenseType | list[ExpenseType] | None = None,
    expense_classes: type | list[type] | None = None,
    exclude_expense_classes: type | list[type] | None = None,
    name: str | None = None,
    include_virtuals: bool = True,
) -> float:
    expenses = get_expenses(
        include_objects=include_objects,
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
    include_objects: Object | list[Object],
    expense_types: ExpenseType | list[ExpenseType] | None = None,
    *,
    exclude_expense_types: ExpenseType | list[ExpenseType] | None = None,
    expense_classes: type | list[type] | None = None,
    exclude_expense_classes: type | list[type] | None = None,
    name: str | None = None,
):
    expenses = []
    if not isinstance(include_objects, list):
        include_objects = [include_objects]

    for o in include_objects:
        typeerror_if_not_isinstance(o, Object)
        expenses += o.find_objects(Expense)

    if expense_types is not None:
        if not isinstance(expense_types, list):
            expense_types = [expense_types]
        typeerror_if_not_list_isinstance(expense_types, ExpenseType)
        expenses = [e for e in expenses if e.type in expense_types]

    if exclude_expense_types is not None:
        if not isinstance(exclude_expense_types, list):
            exclude_expense_types = [exclude_expense_types]
        typeerror_if_not_list_isinstance(exclude_expense_types, ExpenseType)
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
        expenses = [e for e in expenses if e.name == name]
    return expenses


def get_expense(
    include_objects: Object | list[Object],
    expense_types: ExpenseType | list[ExpenseType] | None = None,
    *,
    exclude_expense_types: ExpenseType | list[ExpenseType] | None = None,
    expense_classes: type | list[type] | None = None,
    exclude_expense_classes: type | list[type] | None = None,
    name: str = None,
    not_found: Literal["none", "error"] = "error",
) -> Expense | None:
    if not_found not in ["none", "error"]:
        raise ValueError("not_found must be either 'none' or 'error'.")

    expenses = get_expenses(
        include_objects=include_objects,
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
