"""Build docs/index.html from results/run.json. Run after every recorded run."""

from __future__ import annotations

import html
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "notice-simulator"
Q_LABEL = {
    "banked": "Has a bank account",
    "has_card": "Has a credit card",
    "carried_balance": "Carried a card balance",
    "used_bnpl": "Used Buy Now, Pay Later",
    "paid_overdraft": "Paid an overdraft fee",
    "card_fraud": "Had credit card fraud",
    "nonbank_check": "Used a check casher or money order",
}


def esc(s: object) -> str:
    return html.escape(str(s), quote=True)


def calib_svg(result: dict) -> str:
    """Signature visual: every segment's seven simulated shares against the SHED answer, to scale."""
    tol = result["rule"]["tolerance_points"]
    segs = result["segments"]
    qs = list(Q_LABEL)
    left, top, cw, rh, gap = 230, 34, 116, 28, 12
    width = left + cw * len(qs) + 8
    rows = []
    y = top
    for s in segs:
        trusted = s["calibration"]["trusted"]
        rows.append(
            f'<text x="0" y="{y + 19}" class="sl">{esc(s["label"])}</text>'
            f'<text x="{left - 14}" y="{y + 19}" class="st {"ok" if trusted else "no"}" text-anchor="end">'
            f"{s['calibration']['within']}/7</text>"
        )
        for i, row in enumerate(s["calibration"]["rows"]):
            x0 = left + i * cw
            err = row["error"]
            # gap bar: centre line is the SHED answer, the bar runs to the simulated share; 1 point = 1px
            scale = 2.0
            cx = x0 + cw / 2
            band = tol * scale
            rows.append(
                f'<rect x="{cx - band:.1f}" y="{y + 4}" width="{2 * band:.1f}" height="{rh - 8}" class="band"/>'
                f'<line x1="{cx}" x2="{cx}" y1="{y + 2}" y2="{y + rh - 2}" class="truth"/>'
            )
            if err is not None:
                ex = cx + max(-cw / 2 + 2, min(cw / 2 - 2, err * scale))
                cls = "dot in" if row["within"] else "dot out"
                if abs(err) * scale > cw / 2 - 2:
                    cls += " far"
                rows.append(
                    f'<circle cx="{ex:.1f}" cy="{y + rh / 2}" r="6.5" class="{cls}">'
                    f"<title>{esc(s['label'])}, {esc(Q_LABEL[row['question']])}: simulated {row['simulated']}%, "
                    f"SHED {row['shed']}% ({err:+g} points)</title></circle>"
                )
        y += rh + gap
    heads = "".join(
        f'<text x="{left + i * cw + cw / 2}" y="18" class="qh" text-anchor="middle">{i + 1}</text>'
        for i in range(len(qs))
    )
    h = y
    return (
        f'<svg class="calib" viewBox="0 0 {width} {h}" role="img" aria-label="Simulated shares against SHED, '
        f'by segment and question">{heads}{"".join(rows)}</svg>'
    )


def build(result: dict) -> str:
    data = json.dumps(result, ensure_ascii=False).replace("</", "<\\/")
    run = result["run"]
    rule = result["rule"]
    qlist = "".join(f"<li>{esc(v)}</li>" for v in Q_LABEL.values())
    n_seg = len(result["segments"])
    first_trusted = next((s for s in result["segments"] if s["calibration"]["trusted"]), result["segments"][0])
    desc = (
        f"A Claude persona panel predicts how cardholder segments react to three account-move notices; "
        f"{result['trusted']} of {n_seg} segments matched the Federal Reserve's 2025 household survey closely enough to trust."
    )
    template = (ROOT / "docs" / "template.html").read_text(encoding="utf-8")
    page = (
        template.replace("{{DESC}}", esc(desc))
        .replace("{{DATA}}", data)
        .replace("{{CALIB_SVG}}", calib_svg(result))
        .replace("{{QLIST}}", qlist)
        .replace("{{TRUSTED}}", str(result["trusted"]))
        .replace("{{NSEG}}", str(n_seg))
        .replace("{{TOL}}", f"{rule['tolerance_points']:g}")
        .replace("{{MIN}}", str(rule["min_within"]))
        .replace("{{OF}}", str(rule["of"]))
        .replace("{{PEOPLE}}", str(run["people"]))
        .replace("{{PER_SEG}}", str(run["people"] // n_seg))
        .replace("{{CALLS}}", str(run["calls"]))
        .replace("{{COST}}", f"{run['cost_usd']:.2f}")
        .replace("{{LAT}}", f"{run['mean_latency_s']:g}")
        .replace("{{MODEL}}", esc(run["model"]))
        .replace("{{FIRST}}", esc(first_trusted["id"]))
    )
    return page


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "results" / "run.json"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "docs" / "index.html"
    result = json.loads(src.read_text(encoding="utf-8"))
    out.write_text(build(result), encoding="utf-8")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "demo_chrome.py"), str(out), "--repo", REPO], check=True)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
