"""
Property purchase, appreciation, and mortgage amortization.

Mirrors Excel Projection columns M (purchase outflow), U (property market value),
V (mortgage balance).
"""

from __future__ import annotations


def property_outflow(
    year: int,
    buy_property: bool,
    purchase_year: int,
    property_cost: float,
    use_mortgage: bool,
    down_payment: float,
    closing_cost_pct: float = 0.025,
) -> float:
    """Dollar outflow from portfolio in `year` for property purchase.

    Only non-zero in the purchase year itself. Includes closing costs
    (title, inspection, origination, escrow — typically 2-3% of price).
    If using a mortgage, outflow = down payment + closing costs.
    If paying cash, outflow = full property cost + closing costs.
    """
    if not buy_property or year != purchase_year:
        return 0.0
    closing = property_cost * closing_cost_pct
    if use_mortgage:
        return down_payment + closing
    return property_cost + closing


def property_market_value(
    year: int,
    buy_property: bool,
    purchase_year: int,
    property_cost: float,
    appreciation: float,
) -> float:
    """Market value of property in `year`.

    Excel U: PropertyCost * (1 + PropertyAppreciation)^(year - purchase_year).
    Zero before purchase.
    """
    if not buy_property or year < purchase_year:
        return 0.0
    return property_cost * (1.0 + appreciation) ** (year - purchase_year)


def mortgage_monthly_p_and_i(
    property_cost: float,
    down_payment: float,
    annual_rate: float,
    term_years: int,
) -> float:
    """Monthly principal + interest payment (PMT formula).

    Excel B71: =IF(AND(in_BuyProperty="Yes", in_Mortgage="Yes"),
                  PMT(rate/12, term*12, -(cost-down)), 0)
    """
    if annual_rate <= 0 or term_years <= 0:
        return 0.0
    principal = property_cost - down_payment
    if principal <= 0:
        return 0.0
    monthly_rate = annual_rate / 12.0
    n_months = term_years * 12
    # Standard PMT formula
    factor = (1 + monthly_rate) ** n_months
    return principal * monthly_rate * factor / (factor - 1.0)


def mortgage_interest_for_year(
    year: int,
    buy_property: bool,
    purchase_year: int,
    property_cost: float,
    use_mortgage: bool,
    down_payment: float,
    annual_rate: float,
    term_years: int,
) -> float:
    """Annual mortgage interest paid in `year`.

    Interest = beginning-of-year balance * annual rate, approximated as
    sum of 12 monthly interest payments. Used for mortgage interest
    deduction (itemized deduction on federal taxes, post-TCJA cap $750K).
    """
    if not buy_property or not use_mortgage or year < purchase_year:
        return 0.0
    years_since_purchase = year - purchase_year
    if years_since_purchase >= term_years:
        return 0.0

    principal = property_cost - down_payment
    if principal <= 0 or annual_rate <= 0:
        return 0.0

    monthly_rate = annual_rate / 12.0
    pmt = mortgage_monthly_p_and_i(property_cost, down_payment, annual_rate, term_years)

    # Walk 12 monthly payments for this year to sum interest
    # Start from the balance at beginning of this year
    if years_since_purchase == 0:
        balance = principal
    else:
        n_months_prior = years_since_purchase * 12
        factor = (1 + monthly_rate) ** n_months_prior
        balance = max(0.0, principal * factor - pmt * (factor - 1.0) / monthly_rate)

    total_interest = 0.0
    for _ in range(12):
        if balance <= 0:
            break
        month_interest = balance * monthly_rate
        total_interest += month_interest
        balance = balance - (pmt - month_interest)

    return total_interest


def mortgage_balance(
    year: int,
    buy_property: bool,
    purchase_year: int,
    property_cost: float,
    use_mortgage: bool,
    down_payment: float,
    annual_rate: float,
    term_years: int,
) -> float:
    """Outstanding mortgage balance at end of `year`.

    Excel V: future value of the mortgage given payments made so far.
    """
    if not buy_property or not use_mortgage or year < purchase_year:
        return 0.0
    years_since_purchase = year - purchase_year
    if years_since_purchase >= term_years:
        return 0.0
    if years_since_purchase == 0:
        # End of purchase year — we've made 0 full-year payments? Actually Excel's formula
        # returns cost - down_payment in the purchase year (V4 when A4=purchase_year).
        return property_cost - down_payment

    # Compute using the amortization identity:
    #   balance_after_n_months = principal * (1+r)^n - pmt * ((1+r)^n - 1) / r
    principal = property_cost - down_payment
    monthly_rate = annual_rate / 12.0
    pmt = mortgage_monthly_p_and_i(property_cost, down_payment, annual_rate, term_years)
    n_months = years_since_purchase * 12
    if monthly_rate == 0:
        return max(0.0, principal - pmt * n_months)
    factor = (1 + monthly_rate) ** n_months
    balance = principal * factor - pmt * (factor - 1.0) / monthly_rate
    return max(0.0, balance)
