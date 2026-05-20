from typing import Literal
import warnings

from ..model.temporal import Temporal

def check_temporal_validity(
    temporal: Temporal,
    no_total_allowed: bool = True,
    no_series_or_fix_allowed: bool = True,
    min_value: float = None,
    max_value: float = None,
    min_total: float = None,
    max_total: float = None,
    action: Literal["raise", "warn", "return_bool"] = "raise",
) -> bool:
    """
    Check the validity of a Temporal instance. This function checks if the
    temporal instance has a valid total and series, and if the values fall
    within specified minimum and maximum bounds. Depending on the `action`
    parameter, it can raise an exception, issue a warning, or return a boolean
    indicating validity.

    Parameters
    ----------
    temporal : Temporal
        Temporal instance to check.
    no_total_allowed : bool
        If True, allows the total to be None.
    no_series_or_fix_allowed : bool
        If True, allows both the series and the fix to be None.
    min_value : float
        Minimum value allowed for the series or fix (if present).
    max_value : float
        Maximum value allowed for the series or fix (if present).
    min_total : float
        Minimum total value allowed (if present).
    max_total : float
        Maximum total value allowed (if present).
    action : Literal["raise", "warn", "return_bool"]
        Action to take if the checks fail. Can be "raise", "warn", or
        "return_bool".

    Returns
    -------
    bool : 
        Returns True if the temporal instance is valid, False otherwise.
    """

    if not isinstance(temporal, Temporal):
        msg = "No temporal instance provided."
        if action == "raise":
            raise TypeError(msg)
        elif action == "warn":
            warnings.warn(msg)
            return False
        elif action == "return_bool":
            return False

    if temporal.total is None and not no_total_allowed:
        msg = "The total value of the temporal is None, which is not allowed."
        if action == "raise":
            raise ValueError(msg)
        elif action == "warn":
            warnings.warn(msg)
            return False
        elif action == "return_bool":
            return False

    if temporal.series is None and temporal.fix is None and not no_series_or_fix_allowed:
        msg = "Both the series and the fix of the temporal are None, which is not allowed."
        if action == "raise":
            raise ValueError(msg)
        elif action == "warn":
            warnings.warn(msg)
            return False
        elif action == "return_bool":
            return False

    if temporal.fix is not None or temporal.series is not None:
        if temporal.fix is not None:
            max_value_ = temporal.fix
            min_value_ = temporal.fix
        elif temporal.series is not None:
            max_value_ = temporal.series.max()
            min_value_ = temporal.series.min()
        if min_value is not None:
            if min_value_ < min_value:
                msg = f"Minimum value {min_value_} is less than the allowed minimum {min_value}."
                if action == "raise":
                    raise ValueError(msg)
                elif action == "warn":
                    warnings.warn(msg)
                    return False
                elif action == "return_bool":
                    return False
        if max_value is not None:
            if max_value_ > max_value:
                msg = f"Maximum value {max_value_} is greater than the allowed maximum {max_value}."
                if action == "raise":
                    raise ValueError(msg)
                elif action == "warn":
                    warnings.warn(msg)
                    return False
                elif action == "return_bool":
                    return False

    if temporal.total is not None:
        if min_total is not None:
            if temporal.total < min_total:
                msg = f"Total value {temporal.total} is less than the allowed minimum {min_total}."
                if action == "raise":
                    raise ValueError(msg)
                elif action == "warn":
                    warnings.warn(msg)
                    return False
                elif action == "return_bool":
                    return False
        if max_total is not None:
            if temporal.total > max_total:
                msg = f"Total value {temporal.total} is greater than the allowed maximum {max_total}."
                if action == "raise":
                    raise ValueError(msg)
                elif action == "warn":
                    warnings.warn(msg)
                    return False
                elif action == "return_bool":
                    return False
