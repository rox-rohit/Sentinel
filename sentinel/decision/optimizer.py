"""Maintenance decision intelligence.

Converts risk, RUL and cost assumptions into a prioritised, budget-constrained
plan. The selection problem is a 0/1 knapsack solved exactly with dynamic
programming over integer cost units: each candidate maintenance action has a
cost and an expected avoided loss, and we maximise avoided loss under the budget.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sentinel.config import CostModel, settings


@dataclass
class Candidate:
    asset_id: str
    criticality: int
    failure_risk: float
    predicted_rul: float
    planned_cost: float
    expected_failure_cost: float
    downtime_hours: float

    @property
    def expected_benefit(self) -> float:
        """Expected avoided loss from servicing now, minus the service cost."""
        return self.failure_risk * self.expected_failure_cost - self.planned_cost

    @property
    def priority_score(self) -> float:
        urgency = 1.0 + max(0.0, (30.0 - self.predicted_rul)) / 30.0
        return (self.failure_risk * self.expected_failure_cost * self.criticality * urgency
                / max(1.0, self.planned_cost))


@dataclass
class MaintenancePlan:
    budget: float
    selected: list[dict] = field(default_factory=list)
    deferred: list[dict] = field(default_factory=list)
    spent: float = 0.0
    expected_avoided_loss: float = 0.0
    expected_downtime_hours: float = 0.0
    scenarios: list[dict] = field(default_factory=list)
    assumptions: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _knapsack(candidates: list[Candidate], budget: float, unit: float = 25.0) -> list[Candidate]:
    capacity = int(budget // unit)
    if capacity <= 0 or not candidates:
        return []
    weights = [max(1, int(round(c.planned_cost / unit))) for c in candidates]
    values = [max(0, int(round(c.expected_benefit))) for c in candidates]
    n = len(candidates)
    table = [[0] * (capacity + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        w, v = weights[i - 1], values[i - 1]
        for cap in range(capacity + 1):
            table[i][cap] = table[i - 1][cap]
            if w <= cap:
                table[i][cap] = max(table[i][cap], table[i - 1][cap - w] + v)
    chosen: list[Candidate] = []
    cap = capacity
    for i in range(n, 0, -1):
        if table[i][cap] != table[i - 1][cap]:
            chosen.append(candidates[i - 1])
            cap -= weights[i - 1]
    return chosen


def build_plan(
    assets: list[dict],
    *,
    budget: float | None = None,
    costs: CostModel | None = None,
) -> MaintenancePlan:
    """`assets` items need: asset_id, criticality, failure_risk, predicted_rul and
    optional planned_cost / downtime_hours."""
    budget = budget if budget is not None else settings.maintenance_budget
    costs = costs or settings.costs

    candidates = [
        Candidate(
            asset_id=str(asset["asset_id"]),
            criticality=int(asset.get("criticality", settings.criticality_default)),
            failure_risk=float(asset.get("failure_risk", 0.0)),
            predicted_rul=float(asset.get("predicted_rul", 0.0)),
            planned_cost=float(asset.get("planned_cost", costs.planned_maintenance_cost)),
            expected_failure_cost=float(
                asset.get("expected_failure_cost", costs.unplanned_failure_cost)
            ),
            downtime_hours=float(asset.get("downtime_hours", costs.planned_downtime_hours)),
        )
        for asset in assets
    ]
    # Only actions with positive expected benefit are worth considering.
    viable = [c for c in candidates if c.expected_benefit > 0]
    viable.sort(key=lambda c: c.priority_score, reverse=True)
    selected = _knapsack(viable, budget)
    selected_ids = {c.asset_id for c in selected}
    deferred = [c for c in candidates if c.asset_id not in selected_ids]

    def row(candidate: Candidate, action: str) -> dict:
        return {
            "asset_id": candidate.asset_id,
            "action": action,
            "criticality": candidate.criticality,
            "failure_risk": round(candidate.failure_risk, 4),
            "predicted_rul": round(candidate.predicted_rul, 1),
            "planned_cost": round(candidate.planned_cost, 2),
            "expected_failure_cost": round(candidate.expected_failure_cost, 2),
            "expected_benefit": round(candidate.expected_benefit, 2),
            "priority_score": round(candidate.priority_score, 3),
            "downtime_hours": candidate.downtime_hours,
            "window": (
                "immediate" if candidate.predicted_rul <= 15
                else "next_30_cycles" if candidate.predicted_rul <= 30
                else "monitor"
            ),
        }

    selected_rows = [row(c, "schedule_maintenance") for c in
                     sorted(selected, key=lambda c: c.predicted_rul)]
    deferred_rows = [row(c, "monitor") for c in sorted(deferred, key=lambda c: c.failure_risk,
                                                       reverse=True)]
    spent = sum(c.planned_cost for c in selected)
    avoided = sum(c.failure_risk * c.expected_failure_cost - c.planned_cost for c in selected)
    downtime = sum(c.downtime_hours for c in selected)

    total_unplanned_loss = sum(c.failure_risk * c.expected_failure_cost for c in candidates)
    reactive = {
        "strategy": "reactive",
        "label": "Reactive (run to failure)",
        "cost": round(total_unplanned_loss, 2),
        "downtime_hours": round(sum(c.failure_risk * costs.unplanned_downtime_hours for c in candidates), 2),
        "serviced": 0,
        "description": "No planned work; every failure is an unplanned stop at full loss.",
    }
    preventive_all = len(candidates) * costs.planned_maintenance_cost
    preventive = {
        "strategy": "preventive",
        "label": "Scheduled preventive (service all)",
        "cost": round(preventive_all, 2),
        "downtime_hours": round(len(candidates) * costs.planned_downtime_hours, 2),
        "serviced": len(candidates),
        "description": "Service every asset on a fixed interval regardless of condition.",
    }
    predictive_cost = spent + sum(
        c.failure_risk * c.expected_failure_cost for c in deferred
    )
    predictive = {
        "strategy": "predictive",
        "label": "Predictive (budget-constrained)",
        "cost": round(predictive_cost, 2),
        "downtime_hours": round(
            downtime + sum(c.failure_risk * costs.unplanned_downtime_hours for c in deferred), 2
        ),
        "serviced": len(selected),
        "description": "Service the highest expected-benefit assets within budget; monitor the rest.",
    }

    notes = [
        f"Knapsack capacity {budget:.0f} cost units in steps of 25; optimal for the stated assumptions.",
        f"{len(viable)} of {len(candidates)} assets had positive expected benefit.",
    ]
    if spent > budget:
        notes.append("Selected cost exceeds budget; check the cost model inputs.")

    return MaintenancePlan(
        budget=budget,
        selected=selected_rows,
        deferred=deferred_rows,
        spent=round(spent, 2),
        expected_avoided_loss=round(avoided, 2),
        expected_downtime_hours=round(downtime, 2),
        scenarios=[reactive, preventive, predictive],
        assumptions={**costs.__dict__, "budget": budget,
                     "acute_risk_window_cycles": 30},
        notes=notes,
    )
