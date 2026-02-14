import "./style.css";

type LoanMode = "compute" | "manual";

type Inputs = {
  termMonths: number;
  numVehicles: number;
  targetProfitPv: number;

  inflationAnnual: number; // effective annual
  discountAnnual: number; // effective annual

  maintenanceMonthly: number; // per vehicle, month 1
  overheadMonthly: number; // per vehicle, month 1

  loanMode: LoanMode;
  purchasePrice?: number; // per vehicle
  downPayment?: number; // per vehicle
  loanApr?: number; // nominal
  loanBalloon?: number; // per vehicle (terminal outflow at T)
  loanPaymentMonthly?: number; // per vehicle

  resaleRiskFactor: number; // 0..1
  resalePerVehicle: number; // per vehicle, at end

  creditRiskPremiumPct: number;
  volumeDiscountPct: number;
  relationshipIncentive: number; // $ per vehicle per month
};

type NpvBreakdown = {
  pvLeaseRevenue: number;
  pvCosts: number;
  pvResale: number;
  pvTerminalPayoff: number;
  npv: number;
};

type Output = {
  resaleValueEndTotal: number;
  loanPaymentMonthly: number;
  loanPayoffEndTotal: number;
  baseFee: number;
  finalFee: number;
  breakdown: NpvBreakdown;
};

function $(id: string): HTMLElement {
  const el = document.getElementById(id);
  if (!el) throw new Error(`missing element #${id}`);
  return el;
}

function readNumber(id: string): number {
  const el = $(id) as HTMLInputElement;
  const v = Number(el.value);
  if (!Number.isFinite(v)) throw new Error(`Invalid number: ${id}`);
  return v;
}

function monthlyRateFromAnnualEffective(annual: number): number {
  return Math.pow(1 + annual, 1 / 12) - 1;
}

function monthlyRateFromAprNominal(apr: number): number {
  return apr / 12;
}

function monthlyPayment(principal: number, apr: number, termMonths: number, balloon: number): number {
  if (termMonths <= 0) throw new Error("termMonths must be > 0");
  if (principal < 0) throw new Error("principal must be >= 0");
  if (balloon < 0) throw new Error("balloon must be >= 0");

  const r = monthlyRateFromAprNominal(apr);
  const n = termMonths;

  if (Math.abs(r) < 1e-12) {
    return principal >= balloon ? (principal - balloon) / n : 0;
  }

  // PV = pmt*(1-(1+r)^-n)/r + FV*(1+r)^-n
  const disc = Math.pow(1 + r, -n);
  const ann = (1 - disc) / r;
  return (principal - balloon * disc) / ann;
}

function npvOfLease(args: {
  termMonths: number;
  numVehicles: number;
  monthlyFee: number;
  loanPaymentMonthly: number;
  maintenanceMonthly: number;
  overheadMonthly: number;
  inflationAnnual: number;
  discountAnnual: number;
  resaleValueEndTotal: number;
  resaleRiskFactor: number;
  loanPayoffEndTotal: number;
}): NpvBreakdown {
  const inflM = monthlyRateFromAnnualEffective(args.inflationAnnual);
  const discM = monthlyRateFromAnnualEffective(args.discountAnnual);

  let pvRev = 0;
  let pvCosts = 0;

  for (let m = 1; m <= args.termMonths; m++) {
    const df = 1 / Math.pow(1 + discM, m);
    const maintM = args.maintenanceMonthly * Math.pow(1 + inflM, m - 1);
    const overheadM = args.overheadMonthly * Math.pow(1 + inflM, m - 1);

    const rev = args.monthlyFee * args.numVehicles;
    const costs = (args.loanPaymentMonthly + maintM + overheadM) * args.numVehicles;

    pvRev += rev * df;
    pvCosts += costs * df;
  }

  const resaleAdj = args.resaleValueEndTotal * args.resaleRiskFactor;
  const pvResale = resaleAdj / Math.pow(1 + discM, args.termMonths);

  const pvPayoff = args.loanPayoffEndTotal / Math.pow(1 + discM, args.termMonths);

  const npv = pvRev + pvResale - pvCosts - pvPayoff;
  return {
    pvLeaseRevenue: pvRev,
    pvCosts,
    pvResale,
    pvTerminalPayoff: pvPayoff,
    npv
  };
}

function solveMinMonthlyFee(args: {
  termMonths: number;
  numVehicles: number;
  loanPaymentMonthly: number;
  maintenanceMonthly: number;
  overheadMonthly: number;
  inflationAnnual: number;
  discountAnnual: number;
  resaleValueEndTotal: number;
  resaleRiskFactor: number;
  loanPayoffEndTotal: number;
  targetProfitPv: number;
  maxFee: number;
}): { fee: number; breakdown: NpvBreakdown } {
  const f = (fee: number) =>
    npvOfLease({
      termMonths: args.termMonths,
      numVehicles: args.numVehicles,
      monthlyFee: fee,
      loanPaymentMonthly: args.loanPaymentMonthly,
      maintenanceMonthly: args.maintenanceMonthly,
      overheadMonthly: args.overheadMonthly,
      inflationAnnual: args.inflationAnnual,
      discountAnnual: args.discountAnnual,
      resaleValueEndTotal: args.resaleValueEndTotal,
      resaleRiskFactor: args.resaleRiskFactor,
      loanPayoffEndTotal: args.loanPayoffEndTotal
    });

  let lo = 0;
  let hi = args.maxFee;

  let bHi = f(hi);
  if (bHi.npv < args.targetProfitPv) {
    throw new Error(
      `Target profit unreachable under max fee. NPV@maxFee=${bHi.npv.toFixed(2)} target=${args.targetProfitPv.toFixed(
        2
      )}`
    );
  }

  let bLo = f(lo);
  if (bLo.npv >= args.targetProfitPv) return { fee: 0, breakdown: bLo };

  for (let i = 0; i < 200; i++) {
    const mid = (lo + hi) / 2;
    const bMid = f(mid);
    if (bMid.npv >= args.targetProfitPv) {
      hi = mid;
      bHi = bMid;
    } else {
      lo = mid;
      bLo = bMid;
    }
    if (hi - lo <= 1e-6 * Math.max(1, hi)) break;
  }

  return { fee: hi, breakdown: bHi };
}

function applyClientAdjustments(baseFee: number, adj: Pick<Inputs, "creditRiskPremiumPct" | "volumeDiscountPct" | "relationshipIncentive">): number {
  let fee = baseFee * (1 + adj.creditRiskPremiumPct);
  fee = fee * (1 - adj.volumeDiscountPct);
  fee = fee - adj.relationshipIncentive;
  return Math.max(0, fee);
}

function formatMoney(x: number): string {
  const s = x.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 2 });
  return `$${s}`;
}

function showError(msg: string): void {
  const box = $("errorBox");
  box.textContent = msg;
  box.classList.remove("hidden");
}

function clearError(): void {
  const box = $("errorBox");
  box.textContent = "";
  box.classList.add("hidden");
}

function readInputs(): Inputs {
  const loanMode = (document.querySelector('input[name="loanMode"]:checked') as HTMLInputElement).value as LoanMode;

  const termMonths = readNumber("termMonths");
  const numVehicles = readNumber("numVehicles");

  const inflationAnnual = readNumber("inflationAnnual");
  const discountAnnual = readNumber("discountAnnual");

  const targetProfitPv = readNumber("targetProfit");
  const maintenanceMonthly = readNumber("maintenanceMonthly");
  const overheadMonthly = readNumber("overheadMonthly");

  const resaleRiskFactor = readNumber("resaleRiskFactor");
  const resalePerVehicle = readNumber("resalePerVehicle");

  const creditRiskPremiumPct = readNumber("creditRiskPremiumPct");
  const volumeDiscountPct = readNumber("volumeDiscountPct");
  const relationshipIncentive = readNumber("relationshipIncentive");

  const out: Inputs = {
    termMonths,
    numVehicles,
    targetProfitPv,
    inflationAnnual,
    discountAnnual,
    maintenanceMonthly,
    overheadMonthly,
    loanMode,
    resaleRiskFactor,
    resalePerVehicle,
    creditRiskPremiumPct,
    volumeDiscountPct,
    relationshipIncentive
  };

  if (loanMode === "compute") {
    out.purchasePrice = readNumber("purchasePrice");
    out.downPayment = readNumber("downPayment");
    out.loanApr = readNumber("loanApr");
    out.loanBalloon = readNumber("loanBalloon");
  } else {
    out.loanPaymentMonthly = readNumber("loanPaymentMonthly");
    out.loanBalloon = readNumber("loanBalloonManual");
  }

  return out;
}

function validate(i: Inputs): void {
  if (i.termMonths <= 0) throw new Error("Term must be > 0 months.");
  if (i.numVehicles <= 0) throw new Error("# Vehicles must be > 0.");
  if (i.resaleRiskFactor < 0 || i.resaleRiskFactor > 1) throw new Error("Resale risk factor must be in [0, 1].");
  if (i.resalePerVehicle < 0) throw new Error("Resale per vehicle must be >= 0.");
  if (i.loanMode === "compute") {
    if ((i.purchasePrice ?? 0) <= 0) throw new Error("Purchase price must be > 0.");
    if ((i.downPayment ?? 0) < 0) throw new Error("Down payment must be >= 0.");
    if ((i.downPayment ?? 0) > (i.purchasePrice ?? 0)) throw new Error("Down payment cannot exceed purchase price.");
    if (!Number.isFinite(i.loanApr ?? NaN)) throw new Error("Loan APR is required.");
  } else {
    if (!Number.isFinite(i.loanPaymentMonthly ?? NaN)) throw new Error("Manual monthly loan payment is required.");
    if ((i.loanPaymentMonthly ?? 0) < 0) throw new Error("Loan payment must be >= 0.");
  }
}

function compute(i: Inputs): Output {
  const resaleValueEndTotal = i.resalePerVehicle * i.numVehicles;

  let loanPaymentMonthly: number;
  let loanPayoffEndTotal: number;

  const balloon = i.loanBalloon ?? 0;
  loanPayoffEndTotal = balloon * i.numVehicles;

  if (i.loanMode === "compute") {
    const principal = (i.purchasePrice ?? 0) - (i.downPayment ?? 0);
    loanPaymentMonthly = monthlyPayment(principal, i.loanApr ?? 0, i.termMonths, balloon);
  } else {
    loanPaymentMonthly = i.loanPaymentMonthly ?? 0;
  }

  const solved = solveMinMonthlyFee({
    termMonths: i.termMonths,
    numVehicles: i.numVehicles,
    loanPaymentMonthly,
    maintenanceMonthly: i.maintenanceMonthly,
    overheadMonthly: i.overheadMonthly,
    inflationAnnual: i.inflationAnnual,
    discountAnnual: i.discountAnnual,
    resaleValueEndTotal,
    resaleRiskFactor: i.resaleRiskFactor,
    loanPayoffEndTotal,
    targetProfitPv: i.targetProfitPv,
    maxFee: 50_000
  });

  const baseFee = solved.fee;
  const finalFee = applyClientAdjustments(baseFee, i);

  return {
    resaleValueEndTotal,
    loanPaymentMonthly,
    loanPayoffEndTotal,
    baseFee,
    finalFee,
    breakdown: solved.breakdown
  };
}

function render(o: Output, i: Inputs): void {
  const results = $("results");
  results.classList.remove("empty");

  results.innerHTML = `
    <div class="cards">
      <div class="card">
        <div class="card__label">Resale (End, Total, Risk-Adj)</div>
        <div class="card__value"><span class="accent2">${formatMoney(o.resaleValueEndTotal * i.resaleRiskFactor)}</span></div>
      </div>
      <div class="card">
        <div class="card__label">Loan Installment (Per Vehicle)</div>
        <div class="card__value">${formatMoney(o.loanPaymentMonthly)}</div>
      </div>
      <div class="card">
        <div class="card__label">Base Fee (Per Vehicle / Month)</div>
        <div class="card__value"><span class="accent">${formatMoney(o.baseFee)}</span></div>
      </div>
      <div class="card">
        <div class="card__label">Final Fee (After Adjustments)</div>
        <div class="card__value"><span class="accent">${formatMoney(o.finalFee)}</span></div>
      </div>
    </div>

    <div class="table">
      <div class="row">
        <div class="k">NPV (at Base Fee)</div>
        <div class="v">${formatMoney(o.breakdown.npv)}</div>
      </div>
      <div class="row">
        <div class="k">PV Lease Revenue</div>
        <div class="v">${formatMoney(o.breakdown.pvLeaseRevenue)}</div>
      </div>
      <div class="row">
        <div class="k">PV Costs (Loan + Maint + Overhead)</div>
        <div class="v">${formatMoney(o.breakdown.pvCosts)}</div>
      </div>
      <div class="row">
        <div class="k">PV Resale (Risk-Adj)</div>
        <div class="v">${formatMoney(o.breakdown.pvResale)}</div>
      </div>
      <div class="row">
        <div class="k">PV Terminal Payoff (Balloon)</div>
        <div class="v">${formatMoney(o.breakdown.pvTerminalPayoff)}</div>
      </div>
    </div>
  `;
}

function setLoanMode(mode: LoanMode): void {
  const compute = $("loanCompute");
  const manual = $("loanManual");
  if (mode === "compute") {
    compute.classList.remove("hidden");
    manual.classList.add("hidden");
  } else {
    manual.classList.remove("hidden");
    compute.classList.add("hidden");
  }
}

function fillDemo(): void {
  (document.querySelector('input[name="loanMode"][value="compute"]') as HTMLInputElement).checked = true;
  setLoanMode("compute");

  ( $("termMonths") as HTMLInputElement).value = "36";
  ( $("numVehicles") as HTMLInputElement).value = "10";
  ( $("targetProfit") as HTMLInputElement).value = "5000";

  ( $("inflationAnnual") as HTMLInputElement).value = "0.03";
  ( $("discountAnnual") as HTMLInputElement).value = "0.10";

  ( $("maintenanceMonthly") as HTMLInputElement).value = "65";
  ( $("overheadMonthly") as HTMLInputElement).value = "55";

  ( $("purchasePrice") as HTMLInputElement).value = "42000";
  ( $("downPayment") as HTMLInputElement).value = "0";
  ( $("loanApr") as HTMLInputElement).value = "0.08";
  ( $("loanBalloon") as HTMLInputElement).value = "0";

  ( $("resaleRiskFactor") as HTMLInputElement).value = "0.9";
  ( $("resalePerVehicle") as HTMLInputElement).value = "27270";

  ( $("creditRiskPremiumPct") as HTMLInputElement).value = "0.06";
  ( $("volumeDiscountPct") as HTMLInputElement).value = "0.03";
  ( $("relationshipIncentive") as HTMLInputElement).value = "20";
}

function main(): void {
  const form = $("pricingForm") as HTMLFormElement;

  document.querySelectorAll('input[name="loanMode"]').forEach((el) => {
    el.addEventListener("change", () => {
      const mode = (document.querySelector('input[name="loanMode"]:checked') as HTMLInputElement).value as LoanMode;
      setLoanMode(mode);
      clearError();
    });
  });

  $("btnFillDemo").addEventListener("click", () => {
    fillDemo();
    clearError();
  });

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    clearError();
    try {
      const i = readInputs();
      validate(i);
      const o = compute(i);
      render(o, i);
    } catch (err) {
      showError(err instanceof Error ? err.message : String(err));
    }
  });
}

main();

