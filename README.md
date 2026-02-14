# Dynamic Fleet Leasing Pricing Model

Local project implementing:

- A resale prediction model (linear/ridge regression) trained on historical resale data.
- An NPV-based pricing engine that solves for the **minimum monthly lease fee** required to hit a **target profit in present value terms**.
- Client-specific adjustments (risk premium, volume discount, relationship incentive).

## Quick Start

1) Create a virtualenv and install:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

If you don't want to install the package, you can run the CLI in-place via:

```bash
PYTHONPATH=src python3 -m fleet_pricing.cli --help
```

2) Generate a sample resale dataset:

```bash
python3 scripts/make_synthetic_resale_data.py --out data/resale_sample.csv --rows 5000
```

3) Train the resale model:

Installed CLI:
```bash
fleet-pricing train-resale \
  --train-csv data/resale_sample.csv \
  --target-col resale_value_end \
  --model-out artifacts/resale_model.joblib
```

In-place CLI:
```bash
PYTHONPATH=src python3 -m fleet_pricing.cli train-resale \
  --train-csv data/resale_sample.csv \
  --target-col resale_value_end \
  --model-out artifacts/resale_model.joblib
```

4) Price a lease (predict resale from the same vehicle fields + compute fee):

Installed CLI:
```bash
fleet-pricing price-lease \
  --term-months 36 \
  --num-vehicles 10 \
  --vehicle-purchase-price 42000 \
  --loan-apr 0.08 \
  --down-payment 0 \
  --maintenance-monthly 65 \
  --overhead-monthly 55 \
  --inflation-annual 0.03 \
  --discount-annual 0.10 \
  --target-profit-pv 5000 \
  --resale-model artifacts/resale_model.joblib \
  --vehicle-json '{"model":"Transit","age_months":12,"mileage":18000,"trim":"XL","region":"NE","inflation_cpi":0.03,"consumer_confidence":95}'
```

In-place CLI:
```bash
PYTHONPATH=src python3 -m fleet_pricing.cli price-lease \
  --term-months 36 \
  --num-vehicles 10 \
  --vehicle-purchase-price 42000 \
  --loan-apr 0.08 \
  --down-payment 0 \
  --maintenance-monthly 65 \
  --overhead-monthly 55 \
  --inflation-annual 0.03 \
  --discount-annual 0.10 \
  --target-profit-pv 5000 \
  --resale-model artifacts/resale_model.joblib \
  --vehicle-json '{"model":"Transit","age_months":12,"mileage":18000,"trim":"XL","region":"NE","inflation_cpi":0.03,"consumer_confidence":95}'
```

The output is JSON including predicted resale, base fee, final fee, and an NPV breakdown.

## Frontend (TypeScript)

Frontend lives in `web/`.

### Option A: TypeScript Dev Server (Recommended)

This uses TypeScript (`web/src/main.ts`) and a dev server that transpiles it.

```bash
cd web
npm install
npm run dev
```

### Option B: No-Node Static Run (Python HTTP Server)

Browsers can't run TypeScript directly, and `file://` module scripts can hit CORS restrictions.
For a zero-build demo, the repo includes `web/src/main.js` and `web/index.html` loads it as a classic script.

Run:

```bash
cd web
python3 -m http.server 8000
```

Then open `http://localhost:8000/`.

The frontend computes pricing locally in the browser using the same math assumptions as the Python NPV engine.

### Option C: Python App Server (Resale Prediction API + UI)

If you want the frontend to **predict resale** (instead of typing it), run the included Python server which:

- serves the UI from `web/`
- exposes `POST /api/predict-resale` using `artifacts/resale_model.joblib`

Start:

```bash
python3 server/app.py --port 8000 --model artifacts/resale_model.joblib
```

Open `http://127.0.0.1:8000/` and click **Predict Resale**.

## Loan Payments (What It Means Here)

If a client leases 10 cars, you finance buying those 10 cars via a loan.

Project assumption: the loan term always matches the lease term.

This project models that as:

- A **per-vehicle** installment computed from `vehicle_purchase_price`, `loan_apr`, `term_months`, `down_payment`, and optional `loan_balloon`.
- That installment is applied for `term_months`.
- Any `loan_balloon` is treated as a **terminal payoff at lease end** (month `T`).

## Data Contract (Resale Model)

Training CSV should have:

- Features: any mix of numeric/categorical columns (e.g. `model`, `age_months`, `mileage`, `region`, macro columns)
- Target: `resale_value_end` (or your chosen `--target-col`)

The model uses:
- `OneHotEncoder` for categorical columns
- `Ridge` regression for stability

## Pricing Engine Notes

NPV is computed on nominal monthly cashflows:

- Revenue: `monthly_fee * num_vehicles`
- Costs: loan + maintenance + overhead (maintenance/overhead can inflate monthly)
- Terminal inflow: risk-adjusted resale proceeds at end of term

The solver finds the **minimum monthly fee** such that:

`NPV >= target_profit_pv`
