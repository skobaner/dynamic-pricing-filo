from __future__ import annotations

from dataclasses import dataclass


def _monthly_rate_from_apr(apr: float) -> float:
    # Treat APR as nominal annual with monthly compounding for payments.
    return apr / 12.0


def monthly_payment(
    *,
    principal: float,
    apr: float,
    term_months: int,
    balloon: float = 0.0,
) -> float:
    """
    Standard fixed-rate loan payment.

    principal: amount borrowed today
    apr: nominal annual interest rate (e.g. 0.08 for 8%)
    term_months: number of monthly payments
    balloon: remaining balance due at the end (0 for fully amortizing)
    """
    if term_months <= 0:
        raise ValueError("term_months must be > 0")
    if principal < 0:
        raise ValueError("principal must be >= 0")
    if balloon < 0:
        raise ValueError("balloon must be >= 0")
    if apr < -0.99:
        raise ValueError("apr too small")

    r = _monthly_rate_from_apr(apr)
    n = term_months
    pv = float(principal)
    fv = float(balloon)

    if abs(r) < 1e-12:
        return (pv - fv) / n if pv >= fv else 0.0

    # PV = pmt*(1-(1+r)^-n)/r + FV*(1+r)^-n
    disc = (1.0 + r) ** (-n)
    ann = (1.0 - disc) / r
    pmt = (pv - fv * disc) / ann
    return float(pmt)


def remaining_balance(
    *,
    principal: float,
    apr: float,
    term_months: int,
    payments_made: int,
    balloon: float = 0.0,
) -> float:
    """
    Remaining balance immediately after `payments_made` payments.
    For balloon loans, balance at term end equals `balloon`.
    """
    if payments_made < 0:
        raise ValueError("payments_made must be >= 0")
    if payments_made > term_months:
        raise ValueError("payments_made must be <= term_months")

    r = _monthly_rate_from_apr(apr)
    n = term_months
    k = payments_made
    pv = float(principal)
    fv = float(balloon)

    if n == 0:
        return pv

    pmt = monthly_payment(principal=pv, apr=apr, term_months=n, balloon=fv)

    if abs(r) < 1e-12:
        # Linear payoff towards balloon.
        paid_principal = pmt * k
        bal = max(fv, pv - paid_principal)
        return float(bal)

    # Balance formula at time k:
    # B_k = pmt*(1-(1+r)^-(n-k))/r + FV*(1+r)^-(n-k)
    rem = n - k
    disc_rem = (1.0 + r) ** (-rem)
    ann_rem = (1.0 - disc_rem) / r
    bal = pmt * ann_rem + fv * disc_rem
    return float(max(0.0, bal))


@dataclass(frozen=True)
class LoanLeaseMapping:
    loan_payment_monthly_per_vehicle: float
    loan_payment_months_within_lease: int
    payoff_at_lease_end_per_vehicle: float


def map_loan_into_lease_cashflows(
    *,
    vehicle_purchase_price: float,
    down_payment: float,
    apr: float,
    loan_term_months: int,
    lease_term_months: int,
    balloon: float = 0.0,
    assume_payoff_at_lease_end_if_loan_longer: bool = True,
) -> LoanLeaseMapping:
    """
    Converts a vehicle purchase financing plan into lease-period costs:
    - monthly installment within lease window
    - optional terminal payoff at lease end (if lease ends before loan term)
    """
    if vehicle_purchase_price <= 0:
        raise ValueError("vehicle_purchase_price must be > 0")
    if down_payment < 0 or down_payment > vehicle_purchase_price:
        raise ValueError("down_payment must be in [0, vehicle_purchase_price]")
    if lease_term_months <= 0:
        raise ValueError("lease_term_months must be > 0")
    if loan_term_months <= 0:
        raise ValueError("loan_term_months must be > 0")

    principal = float(vehicle_purchase_price - down_payment)
    pmt = monthly_payment(principal=principal, apr=apr, term_months=loan_term_months, balloon=balloon)

    months_paid = min(lease_term_months, loan_term_months)

    payoff = 0.0
    # If the lease ends on/before the loan's scheduled end, the outstanding balance at that point
    # (typically 0 for fully amortizing loans, or the balloon for balloon loans) is treated as a
    # terminal cash outflow at lease end.
    if assume_payoff_at_lease_end_if_loan_longer and lease_term_months <= loan_term_months:
        payoff = remaining_balance(
            principal=principal,
            apr=apr,
            term_months=loan_term_months,
            payments_made=lease_term_months,
            balloon=balloon,
        )

    return LoanLeaseMapping(
        loan_payment_monthly_per_vehicle=float(pmt),
        loan_payment_months_within_lease=int(months_paid),
        payoff_at_lease_end_per_vehicle=float(payoff),
    )
