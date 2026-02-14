from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--rows", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)

    models = ["Transit", "Sprinter", "ProMaster", "F-150", "Silverado", "RAV4", "CR-V"]
    trims = ["Base", "XL", "XLT", "Limited", "Sport"]
    regions = ["NE", "SE", "MW", "SW", "W"]

    model = rng.choice(models, size=args.rows)
    trim = rng.choice(trims, size=args.rows)
    region = rng.choice(regions, size=args.rows)

    age_months = rng.integers(0, 120, size=args.rows)
    mileage = (age_months * rng.normal(1200, 300, size=args.rows)).clip(0)
    inflation_cpi = rng.normal(0.03, 0.01, size=args.rows).clip(-0.02, 0.10)
    consumer_confidence = rng.normal(95, 10, size=args.rows).clip(50, 140)

    base_price = np.select(
        [model == "Sprinter", model == "Transit", model == "ProMaster", model == "F-150", model == "Silverado"],
        [52000, 42000, 39000, 48000, 50000],
        default=35000,
    ).astype(float)

    trim_bump = np.select(
        [trim == "Base", trim == "XL", trim == "XLT", trim == "Limited", trim == "Sport"],
        [0, 1200, 2400, 4500, 3000],
        default=0,
    ).astype(float)

    region_factor = np.select(
        [region == "NE", region == "SE", region == "MW", region == "SW", region == "W"],
        [1.02, 0.98, 1.00, 0.99, 1.03],
        default=1.0,
    )

    # Synthetic depreciation: non-linear in age + mileage, mildly supported by macro indicators.
    age_years = age_months / 12.0
    depreciation = 0.15 * age_years + 0.02 * (age_years**2) + (mileage / 100000.0) * 0.18
    macro = 1.0 + 0.6 * (consumer_confidence - 95.0) / 100.0 - 0.4 * (inflation_cpi - 0.03)

    noise = rng.normal(0, 1800, size=args.rows)

    resale_value_end = (base_price + trim_bump) * region_factor * macro * (1.0 - depreciation)
    resale_value_end = resale_value_end + noise
    resale_value_end = resale_value_end.clip(2000, None)

    df = pd.DataFrame(
        {
            "model": model,
            "trim": trim,
            "region": region,
            "age_months": age_months.astype(int),
            "mileage": mileage.astype(int),
            "inflation_cpi": inflation_cpi.astype(float),
            "consumer_confidence": consumer_confidence.astype(float),
            "resale_value_end": resale_value_end.astype(float),
        }
    )

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"wrote {args.out} rows={len(df)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

