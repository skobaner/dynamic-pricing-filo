from __future__ import annotations

from fleet_pricing.npv.engine import npv_of_lease, solve_min_monthly_fee


def test_npv_monotonic_in_fee():
    b1 = npv_of_lease(
        term_months=12,
        num_vehicles=1,
        monthly_fee=100.0,
        loan_payment_monthly=80.0,
        maintenance_monthly=10.0,
        overhead_monthly=5.0,
        inflation_annual=0.0,
        discount_annual=0.0,
        resale_value_end_total=0.0,
    )
    b2 = npv_of_lease(
        term_months=12,
        num_vehicles=1,
        monthly_fee=200.0,
        loan_payment_monthly=80.0,
        maintenance_monthly=10.0,
        overhead_monthly=5.0,
        inflation_annual=0.0,
        discount_annual=0.0,
        resale_value_end_total=0.0,
    )
    assert b2.npv > b1.npv


def test_solve_min_monthly_fee_hits_target():
    target = 1000.0
    fee, breakdown = solve_min_monthly_fee(
        term_months=10,
        num_vehicles=2,
        loan_payment_monthly=100.0,
        maintenance_monthly=0.0,
        overhead_monthly=0.0,
        inflation_annual=0.0,
        discount_annual=0.0,
        resale_value_end_total=0.0,
        target_profit_pv=target,
        max_fee=10_000.0,
    )
    assert fee >= 0.0
    assert breakdown.npv >= target
