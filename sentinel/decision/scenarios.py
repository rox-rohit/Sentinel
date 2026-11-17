"""Saved maintenance scenarios and side-by-side comparison.

A scenario is a fully computed optimisation plan (selection, strategy costs and
assumptions) persisted in the metadata store. Comparison only reads stored
plans, so a saved scenario stays comparable even after the fleet is rebuilt.
"""

from __future__ import annotations

from sentinel.store.db import get_scenario


def summarize_plan(plan: dict, *, scenario_id: int | None = None, name: str = "",
                   note: str | None = None, created_at: str | None = None) -> dict:
    """Flatten one optimisation plan into the fields the comparison needs."""
    strategies = {row["strategy"]: row for row in plan.get("scenarios", [])}
    selected = plan.get("selected", [])
    spent = float(plan.get("spent", 0.0))
    avoided = float(plan.get("expected_avoided_loss", 0.0))
    return {
        "id": scenario_id,
        "name": name,
        "note": note,
        "created_at": created_at,
        "budget": float(plan.get("budget", 0.0)),
        "spent": spent,
        "expected_avoided_loss": avoided,
        "expected_downtime_hours": float(plan.get("expected_downtime_hours", 0.0)),
        "assets_serviced": len(selected),
        "asset_count": len(plan.get("deferred", [])) + len(selected),
        "predictive_cost": float(strategies.get("predictive", {}).get("cost", 0.0)),
        "reactive_cost": float(strategies.get("reactive", {}).get("cost", 0.0)),
        "preventive_cost": float(strategies.get("preventive", {}).get("cost", 0.0)),
        "selected_assets": [row["asset_id"] for row in selected],
        "avoided_per_1000_spent": round(avoided / spent * 1000, 2) if spent > 0 else None,
    }


METRICS = (
    ("expected_avoided_loss", "Expected avoided loss", "currency", "higher"),
    ("predictive_cost", "Predictive total cost", "currency", "lower"),
    ("spent", "Planned spend", "currency", "lower"),
    ("expected_downtime_hours", "Planned downtime", "hours", "lower"),
    ("assets_serviced", "Assets serviced", "count", "higher"),
    ("avoided_per_1000_spent", "Avoided loss per 1,000 spent", "currency", "higher"),
)


def compare(scenarios: list[dict]) -> dict:
    """Side-by-side comparison of two or more saved scenario summaries."""
    if len(scenarios) < 2:
        raise ValueError("Comparison needs at least two scenarios.")

    metrics = []
    for key, label, unit, better in METRICS:
        values = {
            str(scenario["id"]): scenario.get(key)
            for scenario in scenarios
            if scenario.get(key) is not None
        }
        best_ids = []
        if values:
            target = max(values.values()) if better == "higher" else min(values.values())
            best_ids = [sid for sid, value in values.items() if value == target]
        metrics.append({
            "key": key,
            "label": label,
            "unit": unit,
            "better": better,
            "values": values,
            "best_ids": best_ids,
        })

    asset_sets = {
        str(scenario["id"]): set(scenario.get("selected_assets", [])) for scenario in scenarios
    }
    union = set().union(*asset_sets.values()) if asset_sets else set()
    intersection = set.intersection(*asset_sets.values()) if asset_sets else set()
    unique = {
        sid: sorted(assets - set().union(*(other for other_id, other in asset_sets.items()
                                            if other_id != sid)) if len(asset_sets) > 1 else assets)
        for sid, assets in asset_sets.items()
    }

    baseline = scenarios[0]
    deltas = {
        str(scenario["id"]): {
            key: (
                None if scenario.get(key) is None or baseline.get(key) is None
                else round(float(scenario[key]) - float(baseline[key]), 2)
            )
            for key, _, _, _ in METRICS
        }
        for scenario in scenarios
    }

    return {
        "scenarios": scenarios,
        "metrics": metrics,
        "deltas_vs_first": deltas,
        "assets": {
            "shared": sorted(intersection),
            "shared_count": len(intersection),
            "union_count": len(union),
            "unique": unique,
        },
        "note": (
            "All scenarios use the same fleet, cost model and predicted risk; only the budget "
            "and timing of the saved run differ. Values are model-based estimates, not measured "
            "plant savings."
        ),
    }


def compare_saved(scenario_ids: list[int]) -> dict:
    """Load stored scenarios in the requested order and compare them."""
    unique_ids: list[int] = []
    for scenario_id in scenario_ids:
        if scenario_id not in unique_ids:
            unique_ids.append(scenario_id)
    scenarios = []
    for scenario_id in unique_ids:
        record = get_scenario(scenario_id)
        if record is None:
            raise KeyError(scenario_id)
        scenarios.append({key: value for key, value in record.items() if key != "plan"})
    return compare(scenarios)
