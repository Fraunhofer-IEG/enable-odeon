def calc_annuity_factor(
    interest_factor: float,
    observation_period: int,
) -> float:
    """
    According to VDI 2067.

    Parameters
    ----------
    interest_factor : float
        Interest factor, >=0. 1 equals 0%
    observation_period : int
        Observation period in years
    """
    assert isinstance(observation_period, int)
    assert observation_period > 0
    assert interest_factor >= 0
    if interest_factor == 1.0:
        return 1.0
    else:
        return (interest_factor - 1) / (1 - interest_factor**-observation_period)


def calc_cash_value_factor(
    price_change_factor: float,
    interest_factor: float,
    observation_period: int,
) -> float:
    """
    According to VDI 2067.

    Parameters
    ----------
    price_change_factor : float
        Price change factor, >=0. 1 equals 0%
    interest_factor : float
        Interest factor, >=0. 1 equals 0%
    observation_period : int
        Observation period in years
    """
    assert isinstance(observation_period, int)
    assert observation_period > 0
    assert interest_factor >= 0
    if interest_factor == price_change_factor:
        return observation_period  # interest_factor == price_change_factor --> cash value = observation_period / interest_factor
    else:
        return (1 - (price_change_factor / interest_factor) ** observation_period) / (
            interest_factor - price_change_factor
        )


def calc_capital_cost_annuity(
    investment_amount: float,
    service_life: int,
    price_change_factor: float,
    interest_factor: float,
    observation_period: int,
) -> float:
    """
    According to VDI 2067.

    Parameters
    ----------
    investment_amount : float
        The investment amount for the component (e.g. in €)
    service_life : int
        The lifetime of the purchased component, in years
    price_change_factor : float
        Price change factor, >=0. 1 equals 0%
    interest_factor : float
        Interest factor, >=0. 1 equals 0%
    observation_period : int
        Observation period in years
    """
    assert isinstance(service_life, int)
    assert service_life > 0
    assert interest_factor >= 0
    assert isinstance(observation_period, int)
    assert observation_period > 0

    i_period = 0
    cash_values = [investment_amount]
    residual_value = 0
    period_remaining = observation_period - service_life

    while True:
        i_period += 1

        if period_remaining > 0:  # additional investment
            cash_value = (
                investment_amount
                * price_change_factor ** (i_period * service_life)
                / interest_factor ** (i_period * service_life)
            )
            cash_values.append(cash_value)

        if 0 < period_remaining < service_life:  # residual value present
            residual_value = (
                investment_amount
                * price_change_factor ** (i_period * service_life)
                * ((i_period + 1) * service_life - observation_period)
                / service_life
                / interest_factor**observation_period  #!!!
            )

        period_remaining -= service_life

        if period_remaining <= 0:
            break

    capital_costs = sum(cash_values) - residual_value
    annuity_factor = calc_annuity_factor(
        interest_factor=interest_factor,
        observation_period=observation_period,
    )
    capital_cost_annuity = capital_costs * annuity_factor
    return capital_cost_annuity


def calc_selected_period_annuity(
    periodical_amount: float,
    price_change_factor: float,
    interest_factor: float,
    observation_period: int,
    period: int = 1,  # in years
    period_indices: list[int] = None,
    refund_residual_value: bool = True,
) -> float:
    """
    Calculate the annuity of a periodical payment. The frequency must be a
    multiple of one year. The periodical payment may occur only in certain
    period indices.

    Parameters
    ----------
    periodical_amount : float
        The cash amount that is due per period
    price_change_factor : float
        Price change factor, >=0. 1 equals 0%
    interest_factor : float
        Interest factor, >=0. 1 equals 0%
    observation_period : int
        Observation period in years
    period : int
        The period one payment lasts, in years
    period_indices : list[int]
        List of period indices for which the periodical payment is due. If None,
        it's due for all periods.
    refund_residual_values : bool
        Whether to include the residual value that may occur if
        `observation_period` isn't a multiple of `period`
    """
    assert isinstance(period, int)
    assert period > 0
    assert interest_factor >= 0
    assert isinstance(observation_period, int)
    assert observation_period > 0
    assert period_indices is None or (
        all(isinstance(period_index, int) for period_index in period_indices)
        and max(period_indices) <= observation_period / period
    )

    if period_indices is None:
        period_indices = [*range(math.ceil(observation_period / period))]  # = all periods

    i_period = 0
    cash_values = [periodical_amount] if i_period in period_indices else []
    residual_value = 0
    period_remaining = observation_period - period

    while True:
        i_period += 1

        if period_remaining > 0:  # additional payment
            if i_period in period_indices:
                cash_value = (
                    periodical_amount
                    * price_change_factor ** (i_period * period)
                    / interest_factor ** (i_period * period)
                )
                cash_values.append(cash_value)

        if 0 < period_remaining < period:  # residual value applies
            if refund_residual_value:
                if i_period in period_indices:  # only refundable if paid in first place
                    residual_value = (
                        periodical_amount
                        * price_change_factor ** (i_period * period)
                        * ((i_period + 1) * period - observation_period)
                        / period
                        / interest_factor**observation_period
                    )

        period_remaining -= period

        if period_remaining <= 0:
            break

    costs = sum(cash_values) - residual_value
    if interest_factor == 1.0:
        annuity = costs / observation_period
    else:
        annuity_factor = calc_annuity_factor(
            interest_factor=interest_factor,
            observation_period=observation_period,
        )
        annuity = costs * annuity_factor
    return annuity


def calc_annual_cost_annuity(
    cost_first_year: float,
    price_change_factor: float,
    interest_factor: float,
    observation_period: int,
) -> float:
    """
    According to VDI 2067.

    Calculate the annuity of a cost that is due each year in the observation
    period.

    Parameters
    ----------
    cost_first_year : float
        The cost in the first year (e.g. in €)
    price_change_factor : float
        Price change factor, >=0. 1 equals 0%
    interest_factor : float
        Interest factor, >=0. 1 equals 0%
    observation_period : int
        Observation period in years
    """
    cash_value_factor = calc_cash_value_factor(
        price_change_factor=price_change_factor,
        interest_factor=interest_factor,
        observation_period=observation_period,
    )
    annuity_factor = calc_annuity_factor(
        interest_factor=interest_factor,
        observation_period=observation_period,
    )
    annual_cost_annuity = cost_first_year * annuity_factor * cash_value_factor
    return annual_cost_annuity