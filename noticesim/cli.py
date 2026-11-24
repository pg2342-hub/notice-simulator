"""noticesim run notices/*.md  |  noticesim report results/run.json"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .notices import load_notices
from .panel import run_panel
from .score import score, write
from .segments import BY_ID, SEGMENTS


def report(result: dict) -> str:
    lines = [
        (
            f"Trusted segments: {result['trusted']} of {len(result['segments'])} "
            f"(within {result['rule']['tolerance_points']:g} points of SHED on "
            f"{result['rule']['min_within']} of {result['rule']['of']} questions)"
        ),
        "",
    ]
    names = {n["id"]: n["name"] for n in result["notices"]}
    for s in result["segments"]:
        cal = s["calibration"]
        tag = "TRUSTED" if cal["trusted"] else "NOT TRUSTED"
        lines.append(f"{s['label']:<22} {tag:<12} {cal['within']}/7 within, mean gap {cal['mae']} pts")
        for nid, r in s["reactions"].items():
            mark = "  <- best" if nid == s["best_notice"] else ""
            lines.append(
                f"    {names[nid]:<16} login in a week {r['setup_within_week']}%  "
                f"suspects scam {r['suspects_scam']}%  close or move {r['close_or_move']}%{mark}"
            )
    run = result["run"]
    lines += [
        "",
        f"{run['calls']} calls, {run['people']} people, ${run['cost_usd']}, {run['mean_latency_s']} s per call",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="noticesim")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="simulate the panel (replays the recording unless NOTICESIM_LIVE=1)")
    r.add_argument("notices", nargs="+")
    r.add_argument("--people", type=int, default=20, help="people per call")
    r.add_argument("--batches", type=int, default=2, help="calls per segment")
    r.add_argument("--segments", default="all", help="comma-separated segment ids, or all")
    r.add_argument("--shed", default="data/shed_2025.json")
    r.add_argument("--recording", default="recordings/panel.jsonl")
    r.add_argument("--out", default="results/run.json")
    p = sub.add_parser("report", help="print a results file")
    p.add_argument("path")
    args = ap.parse_args(argv)

    if args.cmd == "report":
        print(report(json.loads(Path(args.path).read_text(encoding="utf-8"))))
        return 0
    segs = SEGMENTS if args.segments == "all" else [BY_ID[s] for s in args.segments.split(",")]
    notices = load_notices(args.notices)
    shed = json.loads(Path(args.shed).read_text(encoding="utf-8"))
    calls = run_panel(segs, notices, args.people, args.batches, args.recording)
    result = score(calls, notices, shed)
    write(result, args.out)
    print(report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
