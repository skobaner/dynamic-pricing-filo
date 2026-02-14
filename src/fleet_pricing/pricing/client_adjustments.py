from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClientAdjustments:
    # All adjustments apply per-vehicle per-month.
    credit_risk_premium_pct: float = 0.0  # e.g. 0.05 adds 5% to base fee
    volume_discount_pct: float = 0.0  # e.g. 0.03 subtracts 3% from base fee
    relationship_incentive: float = 0.0  # fixed amount subtracted from base fee


def apply_client_adjustments(base_fee: float, adj: ClientAdjustments) -> float:
    if base_fee < 0:
        raise ValueError("base_fee must be >= 0")
    fee = base_fee * (1.0 + adj.credit_risk_premium_pct)
    fee = fee * (1.0 - adj.volume_discount_pct)
    fee = fee - adj.relationship_incentive
    return max(0.0, float(fee))

