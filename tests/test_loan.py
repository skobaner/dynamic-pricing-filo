from __future__ import annotations

from fleet_pricing.financing.loan import map_loan_into_lease_cashflows, monthly_payment, remaining_balance


def test_monthly_payment_zero_rate():
    pmt = monthly_payment(principal=1200, apr=0.0, term_months=12, balloon=0.0)
    assert abs(pmt - 100.0) < 1e-9


def test_remaining_balance_term_end_equals_balloon():
    bal = remaining_balance(principal=10_000, apr=0.08, term_months=60, payments_made=60, balloon=2500.0)
    assert abs(bal - 2500.0) < 1e-6


def test_map_loan_into_lease_cashflows_payoff_when_loan_longer():
    m = map_loan_into_lease_cashflows(
        vehicle_purchase_price=40_000,
        down_payment=0.0,
        apr=0.08,
        loan_term_months=60,
        lease_term_months=36,
        balloon=0.0,
        assume_payoff_at_lease_end_if_loan_longer=True,
    )
    assert m.loan_payment_monthly_per_vehicle > 0
    assert m.loan_payment_months_within_lease == 36
    assert m.payoff_at_lease_end_per_vehicle > 0


def test_map_loan_into_lease_cashflows_balloon_due_at_lease_end_when_terms_match():
    m = map_loan_into_lease_cashflows(
        vehicle_purchase_price=40_000,
        down_payment=0.0,
        apr=0.08,
        loan_term_months=36,
        lease_term_months=36,
        balloon=5000.0,
        assume_payoff_at_lease_end_if_loan_longer=True,
    )
    assert abs(m.payoff_at_lease_end_per_vehicle - 5000.0) < 1e-4
