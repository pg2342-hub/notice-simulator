"""Turn simulated people into segment results: calibration against SHED, trust, and reactions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .panel import CALIBRATION_KEYS, Call
from .segments import BY_ID

# Which simulated people each SHED share is computed over (matches the report's base).
BASE = {"carried_balance": "has_card", "paid_overdraft": "banked"}

# Trust rule, fixed before any live run. With about 40 simulated people a share moves in
# 2.5-point steps and carries sampling noise of up to about 8 points, so the tolerance is 10.
TOLERANCE = 10.0
MIN_WITHIN = 6  # of 7 questions

# Dollar figures used for cost per run (Claude Opus 5.5 list price, per million tokens).
PRICE_IN, PRICE_OUT = 4.00, 20.00


def share(values: list[bool]) -> float | None:
    return round(100.0 * sum(values) / len(values), 1) if values else None


def calibration(people: list[dict[str, Any]], truth: dict[str, float]) -> dict[str, Any]:
    rows = []
    for key in CALIBRATION_KEYS:
        base_key = BASE.get(key)
        pool = [p["answers"] for p in people if base_key is None or p["answers"][base_key]]
        sim = share([bool(a[key]) for a in pool if a[key] is not None])
        err = None if sim is None else round(sim - truth[key], 1)
        rows.append(
            {
                "question": key,
                "simulated": sim,
                "shed": truth[key],
                "error": err,
                "within": err is not None and abs(err) <= TOLERANCE,
                "n": len(pool),
            }
        )
    within = sum(r["within"] for r in rows)
    mae = round(sum(abs(r["error"]) for r in rows if r["error"] is not None) / len(rows), 1)
    return {"rows": rows, "within": within, "mae": mae, "trusted": within >= MIN_WITHIN}


def reactions(people: list[dict[str, Any]], notice_ids: list[str]) -> dict[str, Any]:
    out = {}
    holders = [p for p in people if p["answers"]["has_card"]]
    for nid in notice_ids:
        rs = [r for p in holders for r in p["reactions"] if r["notice_id"] == nid]
        out[nid] = {
            "n": len(rs),
            "setup_within_week": share([r["setup_within_week"] for r in rs]),
            "suspects_scam": share([r["suspects_scam"] for r in rs]),
            "close_or_move": share([r["card_plan"] == "close_or_move" for r in rs]),
            "use_less": share([r["card_plan"] == "use_less" for r in rs]),
            "quotes": [r["reason"] for r in rs[:4]],
        }
    return out


def best_notice(react: dict[str, Any]) -> str:
    """Most people set up the login in a week; ties go to fewer scam suspicions."""
    return max(react, key=lambda k: (react[k]["setup_within_week"] or 0, -(react[k]["suspects_scam"] or 0)))


def score(calls: list[Call], notices: list[Any], shed: dict[str, Any]) -> dict[str, Any]:
    ids = [n.id for n in notices]
    by_seg: dict[str, list[dict[str, Any]]] = {}
    for c in calls:
        by_seg.setdefault(c.segment, []).extend(c.people)
    segments = []
    for seg_id, people in by_seg.items():
        cal = calibration(people, shed["segments"][seg_id])
        react = reactions(people, ids)
        pick = best_notice(react)
        segments.append(
            {
                "id": seg_id,
                "label": BY_ID[seg_id].label,
                "people": len(people),
                "calibration": cal,
                "reactions": react,
                "best_notice": pick,
                "recommendation": pick if cal["trusted"] else None,
            }
        )
    tin = sum(c.input_tokens for c in calls)
    tout = sum(c.output_tokens for c in calls)
    cost = tin / 1e6 * PRICE_IN + tout / 1e6 * PRICE_OUT
    return {
        "notices": [{"id": n.id, "name": n.name, "text": n.text} for n in notices],
        "rule": {"tolerance_points": TOLERANCE, "min_within": MIN_WITHIN, "of": len(CALIBRATION_KEYS)},
        "segments": segments,
        "trusted": sum(s["calibration"]["trusted"] for s in segments),
        "run": {
            "model": calls[0].model if calls else None,
            "calls": len(calls),
            "people": sum(len(c.people) for c in calls),
            "input_tokens": tin,
            "output_tokens": tout,
            "cost_usd": round(cost, 2),
            "mean_latency_s": round(sum(c.latency_s for c in calls) / len(calls), 1) if calls else None,
        },
        "source": {"name": shed["source"], "pages": shed["pages"]},
    }


def write(result: dict[str, Any], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
