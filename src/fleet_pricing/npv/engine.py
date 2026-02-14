from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NpvBreakdown:
    pv_lease_revenue: float
    pv_costs: float
    pv_resale: float
    pv_terminal_payoff: float
    npv: float


def _monthly_rate_from_annual(annual_rate: float) -> float:
    # Effective annual rate -> effective monthly
    return (1.0 + annual_rate) ** (1.0 / 12.0) - 1.0


def npv_of_lease(
    *,
    term_months: int,
    num_vehicles: int,
    monthly_fee: float,
    loan_payment_monthly: float,
    loan_payment_months: int | None = None,
    loan_payoff_end_total: float = 0.0,
    maintenance_monthly: float,
    overhead_monthly: float,
    inflation_annual: float,
    discount_annual: float,
    resale_value_end_total: float,
    resale_risk_factor: float = 1.0,
    fee_inflates: bool = False,
) -> NpvBreakdown:
    if term_months <= 0:
        raise ValueError("term_months must be > 0")
    if num_vehicles <= 0:
        raise ValueError("num_vehicles must be > 0")
    if discount_annual < -0.99:
        raise ValueError("discount_annual too small")
    if not (0.0 <= resale_risk_factor <= 1.0):
        raise ValueError("resale_risk_factor must be in [0, 1]")

    infl_m = _monthly_rate_from_annual(inflation_annual)
    disc_m = _monthly_rate_from_annual(discount_annual)

    pv_rev = 0.0
    pv_costs = 0.0

    loan_months = term_months if loan_payment_months is None else int(loan_payment_months)
    if loan_months < 0:
        raise ValueError("loan_payment_months must be >= 0")

    for m in range(1, term_months + 1):
        df = 1.0 / ((1.0 + disc_m) ** m)

        fee_m = monthly_fee * ((1.0 + infl_m) ** (m - 1) if fee_inflates else 1.0)
        maint_m = maintenance_monthly * ((1.0 + infl_m) ** (m - 1))
        overhead_m = overhead_monthly * ((1.0 + infl_m) ** (m - 1))

        rev = fee_m * num_vehicles
        loan_m = loan_payment_monthly if m <= loan_months else 0.0
        costs = (loan_m + maint_m + overhead_m) * num_vehicles

        pv_rev += rev * df
        pv_costs += costs * df

    resale_adj = resale_value_end_total * resale_risk_factor
    pv_resale = resale_adj / ((1.0 + disc_m) ** term_months)

    pv_payoff = float(loan_payoff_end_total) / ((1.0 + disc_m) ** term_months)
    npv = pv_rev + pv_resale - pv_costs - pv_payoff
    return NpvBreakdown(
        pv_lease_revenue=float(pv_rev),
        pv_costs=float(pv_costs),
        pv_resale=float(pv_resale),
        pv_terminal_payoff=float(pv_payoff),
        npv=float(npv),
    )


def solve_min_monthly_fee(
    *,
    term_months: int,
    num_vehicles: int,
    loan_payment_monthly: float,
    loan_payment_months: int | None = None,
    loan_payoff_end_total: float = 0.0,
    maintenance_monthly: float,
    overhead_monthly: float,
    inflation_annual: float,
    discount_annual: float,
    resale_value_end_total: float,
    target_profit_pv: float,
    resale_risk_factor: float = 1.0,
    fee_inflates: bool = False,
    max_fee: float = 50_000.0,
    tol: float = 1e-6,
) -> tuple[float, NpvBreakdown]:
    """
    Binary search for the minimum monthly fee such that NPV >= target_profit_pv.
    Returns (fee, breakdown_at_fee).
    """
    lo = 0.0
    hi = float(max_fee)

    def f(fee: float) -> NpvBreakdown:
        return npv_of_lease(
            term_months=term_months,
            num_vehicles=num_vehicles,
            monthly_fee=fee,
            loan_payment_monthly=loan_payment_monthly,
            loan_payment_months=loan_payment_months,
            loan_payoff_end_total=loan_payoff_end_total,
            maintenance_monthly=maintenance_monthly,
            overhead_monthly=overhead_monthly,
            inflation_annual=inflation_annual,
            discount_annual=discount_annual,
            resale_value_end_total=resale_value_end_total,
            resale_risk_factor=resale_risk_factor,
            fee_inflates=fee_inflates,
        )

    b_hi = f(hi)
    if b_hi.npv < target_profit_pv:
        raise ValueError(
            "target_profit_pv unreachable under max_fee; "
            f"npv_at_max_fee={b_hi.npv:.2f} target={target_profit_pv:.2f} max_fee={max_fee:.2f}"
        )

    # If even a zero fee meets the target, return 0.
    b_lo = f(lo)
    if b_lo.npv >= target_profit_pv:
        return 0.0, b_lo

    # Binary search in fee-space.
    for _ in range(200):
        mid = (lo + hi) / 2.0
        b_mid = f(mid)
        if b_mid.npv >= target_profit_pv:
            hi = mid
            b_hi = b_mid
        else:
            lo = mid
            b_lo = b_mid
        if (hi - lo) <= tol * max(1.0, hi):
            break

    return float(hi), b_hi
