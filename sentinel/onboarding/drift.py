"""Schema-drift comparison between a saved mapping profile and a new export.

A profile records the source columns it was built from. A later file may add a
column (usually harmless), rename one (the mapping must follow it), or lose one
(the data the mapping promised is gone). Added columns are reported; renames are
matched conservatively and require acknowledgement; missing mapped columns block
until accepted, because silently dropping them would change what the asset
means.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from sentinel.onboarding.plant import suggest_target

RENAME_THRESHOLD = 0.8


def _normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _rename_confidence(expected: str, candidate: str) -> float:
    if _normalise(expected) == _normalise(candidate):
        return 1.0
    return SequenceMatcher(None, _normalise(expected), _normalise(candidate)).ratio()


def compare_columns(expected_columns: list[str], current_columns: list[str],
                    mapping: dict[str, str]) -> dict:
    """Compare a profile's schema with a new file and carry the mapping forward."""
    current = list(current_columns)
    expected = list(expected_columns)
    added = [column for column in current if column not in expected]
    missing = [column for column in expected if column not in current]

    renames: list[dict] = []
    unresolved: list[str] = []
    for old in missing:
        best_name, best_score = None, 0.0
        for candidate in added:
            score = _rename_confidence(old, candidate)
            if score > best_score:
                best_name, best_score = candidate, score
        if best_name is not None and best_score >= RENAME_THRESHOLD:
            renames.append({
                "from": old,
                "to": best_name,
                "confidence": round(best_score, 3),
                "target": mapping.get(old),
            })
            added.remove(best_name)
        else:
            unresolved.append(old)

    applied = dict(mapping)
    for rename in renames:
        target = applied.pop(rename["from"], None)
        if target:
            applied[rename["to"]] = target
    dropped_targets = [applied.pop(column, None) for column in unresolved]
    dropped_targets = [target for target in dropped_targets if target]

    expected_set = set(expected)
    genuinely_added = [column for column in added if column not in expected_set]
    suggestions = []
    for column in genuinely_added:
        target, confidence = suggest_target(column)
        suggestions.append({"source": column, "target": target, "confidence": confidence})

    # Renames change which source feeds a canonical field, so they need explicit
    # acknowledgement even when the match is confident. Added columns do not,
    # because they remain unmapped.
    blocking = bool(unresolved or renames)
    changed = bool(missing or genuinely_added)
    reason = None
    if unresolved:
        reason = (
            f"{len(unresolved)} mapped column(s) are absent with no confident rename: "
            f"{unresolved[:6]}. Import is blocked until the drift is accepted."
        )
    elif renames:
        reason = (
            f"{len(renames)} column(s) were renamed; the mapping follows them but requires "
            "acknowledgement before import."
        )
    elif genuinely_added:
        reason = f"{len(genuinely_added)} new column(s) were added; they stay unmapped."

    return {
        "profile_id": None,
        "status": "drift" if changed else "unchanged",
        "changed": changed,
        "blocking": blocking,
        "expected_columns": expected,
        "current_columns": current,
        "added": genuinely_added,
        "missing": unresolved,
        "renamed": renames,
        "suggestions": suggestions,
        "dropped_targets": dropped_targets,
        "mapping": applied,
        "requires_acknowledgement": bool(changed),
        "reason": reason,
    }
