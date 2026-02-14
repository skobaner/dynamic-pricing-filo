from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from typing import Any

import pandas as pd

from fleet_pricing.financing.loan import map_loan_into_lease_cashflows
from fleet_pricing.npv.engine import solve_min_monthly_fee
from fleet_pricing.pricing.client_adjustments import ClientAdjustments, apply_client_adjustments
from fleet_pricing.resale.model import load_resale_model, predict_resale, save_resale_model, train_resale_model


def _mkdirp(path: str) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)


def cmd_train_resale(args: argparse.Namespace) -> int:
    df = pd.read_csv(args.train_csv)
    pipe, metrics = train_resale_model(
        df,
        args.target_col,
        test_frac=args.test_frac,
        random_state=args.random_state,
    )
    _mkdirp(args.model_out)
    save_resale_model(pipe, args.model_out)
    out = {
        "model_out": args.model_out,
        "metrics": asdict(metrics),
    }
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def cmd_predict_resale(args: argparse.Namespace) -> int:
    pipe = load_resale_model(args.model)
    df = pd.read_csv(args.csv)
    if args.target_col and args.target_col in df.columns:
        df = df.drop(columns=[args.target_col])
    pred = predict_resale(pipe, df)
    out_df = df.copy()
    out_df["predicted_resale_value_end"] = pred
    _mkdirp(args.out_csv)
    out_df.to_csv(args.out_csv, index=False)
    print(json.dumps({"out_csv": args.out_csv, "n_rows": int(len(out_df))}, indent=2, sort_keys=True))
    return 0


def _load_vehicle_json(vehicle_json: str) -> dict[str, Any]:
    try:
        d = json.loads(vehicle_json)
    except json.JSONDecodeError as e:
        raise SystemExit(f"--vehicle-json must be valid JSON: {e}") from e
    if not isinstance(d, dict):
        raise SystemExit("--vehicle-json must decode to an object/dict")
    return d


def cmd_price_lease(args: argparse.Namespace) -> int:
    # Resale (either provided or predicted)
    resale_total = args.resale_value_end_total
    predicted_resale = None
    if resale_total is None:
        if not args.resale_model or not args.vehicle_json:
            raise SystemExit("provide --resale-value-end-total OR (--resale-model and --vehicle-json)")
        pipe = load_resale_model(args.resale_model)
        v = _load_vehicle_json(args.vehicle_json)
        X = pd.DataFrame([v])
        predicted_resale = float(predict_resale(pipe, X)[0])
        resale_total = predicted_resale * args.num_vehicles

    # Loan: either a provided per-vehicle installment, or computed from purchase price + APR.
    # Project assumption: loan term always matches lease term.
    loan_payment_monthly = args.loan_payment_monthly
    loan_payoff_end_total = 0.0
    loan_detail = None

    if loan_payment_monthly is None:
        if args.vehicle_purchase_price is None or args.loan_apr is None:
            raise SystemExit("provide --loan-payment-monthly OR (--vehicle-purchase-price and --loan-apr)")
        loan_term = args.term_months
        mapping = map_loan_into_lease_cashflows(
            vehicle_purchase_price=args.vehicle_purchase_price,
            down_payment=args.down_payment,
            apr=args.loan_apr,
            loan_term_months=loan_term,
            lease_term_months=args.term_months,
            balloon=args.loan_balloon,
            assume_payoff_at_lease_end_if_loan_longer=True,
        )
        loan_payment_monthly = mapping.loan_payment_monthly_per_vehicle
        loan_payoff_end_total = mapping.payoff_at_lease_end_per_vehicle * args.num_vehicles
        loan_detail = {
            "vehicle_purchase_price": args.vehicle_purchase_price,
            "down_payment": args.down_payment,
            "loan_apr": args.loan_apr,
            "loan_term_months": loan_term,
            "loan_balloon": args.loan_balloon,
            "computed_monthly_payment_per_vehicle": loan_payment_monthly,
            "computed_payoff_at_lease_end_total": loan_payoff_end_total,
            "assumption": "loan_term_months == lease_term_months",
        }

    base_fee, breakdown = solve_min_monthly_fee(
        term_months=args.term_months,
        num_vehicles=args.num_vehicles,
        loan_payment_monthly=float(loan_payment_monthly),
        loan_payment_months=args.term_months,
        loan_payoff_end_total=float(loan_payoff_end_total),
        maintenance_monthly=args.maintenance_monthly,
        overhead_monthly=args.overhead_monthly,
        inflation_annual=args.inflation_annual,
        discount_annual=args.discount_annual,
        resale_value_end_total=float(resale_total),
        target_profit_pv=args.target_profit_pv,
        resale_risk_factor=args.resale_risk_factor,
        fee_inflates=args.fee_inflates,
        max_fee=args.max_fee,
    )

    adj = ClientAdjustments(
        credit_risk_premium_pct=args.credit_risk_premium_pct,
        volume_discount_pct=args.volume_discount_pct,
        relationship_incentive=args.relationship_incentive,
    )
    final_fee = apply_client_adjustments(base_fee, adj)

    out = {
        "predicted_resale_value_end_per_vehicle": predicted_resale,
        "resale_value_end_total": float(resale_total),
        "loan_detail": loan_detail,
        "inputs": {
            "term_months": args.term_months,
            "num_vehicles": args.num_vehicles,
            "loan_payment_monthly": float(loan_payment_monthly),
            "loan_payment_months": int(args.term_months),
            "loan_payoff_end_total": float(loan_payoff_end_total),
            "maintenance_monthly": args.maintenance_monthly,
            "overhead_monthly": args.overhead_monthly,
            "inflation_annual": args.inflation_annual,
            "discount_annual": args.discount_annual,
            "target_profit_pv": args.target_profit_pv,
            "resale_risk_factor": args.resale_risk_factor,
            "fee_inflates": bool(args.fee_inflates),
        },
        "base_fee_per_vehicle_per_month": float(base_fee),
        "client_adjustments": asdict(adj),
        "final_fee_per_vehicle_per_month": float(final_fee),
        "npv_breakdown_at_base_fee": {
            "pv_lease_revenue": breakdown.pv_lease_revenue,
            "pv_costs": breakdown.pv_costs,
            "pv_resale": breakdown.pv_resale,
            "pv_terminal_payoff": breakdown.pv_terminal_payoff,
            "npv": breakdown.npv,
        },
    }
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fleet-pricing")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("train-resale", help="Train a ridge regression resale model from a CSV.")
    t.add_argument("--train-csv", required=True)
    t.add_argument("--target-col", required=True)
    t.add_argument("--model-out", required=True)
    t.add_argument("--test-frac", type=float, default=0.2)
    t.add_argument("--random-state", type=int, default=0)
    t.set_defaults(func=cmd_train_resale)

    pr = sub.add_parser("predict-resale", help="Predict resale values for rows in a CSV.")
    pr.add_argument("--model", required=True)
    pr.add_argument("--csv", required=True)
    pr.add_argument("--out-csv", required=True)
    pr.add_argument("--target-col", default=None, help="If provided and present, will be dropped before predicting.")
    pr.set_defaults(func=cmd_predict_resale)

    pl = sub.add_parser("price-lease", help="Solve for minimum monthly lease fee via NPV and apply adjustments.")
    pl.add_argument("--term-months", type=int, required=True)
    pl.add_argument("--num-vehicles", type=int, required=True)
    pl.add_argument(
        "--loan-payment-monthly",
        type=float,
        default=None,
        help="Per-vehicle monthly installment (if already known).",
    )
    pl.add_argument("--vehicle-purchase-price", type=float, default=None, help="Per-vehicle purchase price.")
    pl.add_argument("--down-payment", type=float, default=0.0, help="Per-vehicle down payment.")
    pl.add_argument("--loan-apr", type=float, default=None, help="Nominal annual loan rate (e.g. 0.08).")
    pl.add_argument("--loan-balloon", type=float, default=0.0, help="Per-vehicle balloon due at loan end.")
    pl.add_argument("--maintenance-monthly", type=float, required=True)
    pl.add_argument("--overhead-monthly", type=float, required=True)
    pl.add_argument("--inflation-annual", type=float, required=True)
    pl.add_argument("--discount-annual", type=float, required=True)
    pl.add_argument("--target-profit-pv", type=float, required=True)

    pl.add_argument("--resale-value-end-total", type=float, default=None)
    pl.add_argument("--resale-model", default=None)
    pl.add_argument("--vehicle-json", default=None)
    pl.add_argument("--resale-risk-factor", type=float, default=1.0)
    pl.add_argument("--fee-inflates", action="store_true", default=False)
    pl.add_argument("--max-fee", type=float, default=50_000.0)

    pl.add_argument("--credit-risk-premium-pct", type=float, default=0.0)
    pl.add_argument("--volume-discount-pct", type=float, default=0.0)
    pl.add_argument("--relationship-incentive", type=float, default=0.0)
    pl.set_defaults(func=cmd_price_lease)

    return p


def main(argv: list[str] | None = None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
