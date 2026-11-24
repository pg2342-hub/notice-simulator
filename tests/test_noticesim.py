import json
from pathlib import Path

import pytest

from noticesim.notices import load_notices
from noticesim.panel import Call, build_prompt, fingerprint, run_panel, schema, validate_people
from noticesim.score import TOLERANCE, best_notice, calibration, reactions, score
from noticesim.segments import BY_ID, SEGMENTS

ROOT = Path(__file__).resolve().parents[1]
NOTICES = sorted((ROOT / "notices").glob("*.md"))
SHED = json.loads((ROOT / "data" / "shed_2025.json").read_text())


def person(banked=True, card=True, balance=False, bnpl=False, overdraft=False, fraud=False, nonbank=False, react=None):
    ids = [n.id for n in load_notices(NOTICES)]
    return {
        "profile": "test",
        "answers": {
            "banked": banked,
            "has_card": card,
            "carried_balance": balance if card else None,
            "used_bnpl": bnpl,
            "paid_overdraft": overdraft if banked else None,
            "card_fraud": fraud,
            "nonbank_check": nonbank,
        },
        "reactions": [
            {
                "notice_id": i,
                "setup_within_week": (react or {}).get(i, True),
                "suspects_scam": False,
                "card_plan": "keep_using",
                "reason": "fine",
            }
            for i in ids
        ]
        if card
        else [],
    }


def test_notices_load_with_ids():
    notices = load_notices(NOTICES)
    assert [n.id for n in notices] == ["a_plain", "b_benefits", "c_security"]
    assert all("Harbor Bank" in n.text for n in notices)


def test_segments_match_shed_rows():
    assert {s.id for s in SEGMENTS} == set(SHED["segments"])
    for row in SHED["segments"].values():
        assert set(row) == set(SHED["questions"])


def test_shares_use_the_report_base():
    # 10 people, 8 banked; of the 8 banked, 2 paid an overdraft fee -> 25%, not 20%
    people = [person(overdraft=i < 2) for i in range(8)] + [person(banked=False) for _ in range(2)]
    rows = {r["question"]: r for r in calibration(people, SHED["segments"]["inc_lt25"])["rows"]}
    assert rows["banked"]["simulated"] == 80.0
    assert rows["paid_overdraft"]["simulated"] == 25.0
    assert rows["paid_overdraft"]["n"] == 8


def test_trust_rule_counts_questions_within_tolerance():
    truth = {k: 50 for k in SHED["questions"]}
    # every answer yes -> 100% on all 7 questions, 50 points off each
    people = [person(balance=True, bnpl=True, overdraft=True, fraud=True, nonbank=True) for _ in range(4)]
    cal = calibration(people, truth)
    assert cal["within"] == 0 and not cal["trusted"]
    # half yes, half no on everything -> exactly 50%
    people = [person(balance=b, bnpl=b, overdraft=b, fraud=b, nonbank=b, banked=True) for b in (True, False)] * 2
    truth2 = dict(truth, banked=100, has_card=100)
    cal = calibration(people, truth2)
    assert cal["within"] == 7 and cal["trusted"]
    assert TOLERANCE == 10.0


def test_reactions_only_count_card_holders_and_best_notice():
    people = [person(react={"a_plain": False, "b_benefits": True, "c_security": True}) for _ in range(3)]
    people += [person(card=False)]
    r = reactions(people, ["a_plain", "b_benefits", "c_security"])
    assert r["a_plain"]["n"] == 3 and r["a_plain"]["setup_within_week"] == 0.0
    assert r["b_benefits"]["setup_within_week"] == 100.0
    r["c_security"]["suspects_scam"] = 0.0
    r["b_benefits"]["suspects_scam"] = 33.3
    assert best_notice(r) == "c_security"


def test_validation_catches_missing_reactions():
    ids = ["a_plain", "b_benefits", "c_security"]
    good = person()
    assert validate_people([good], ids) == []
    bad = person()
    bad["reactions"] = bad["reactions"][:1]
    assert validate_people([bad], ids)
    no_card = person(card=False)
    no_card["reactions"] = good["reactions"]
    assert validate_people([no_card], ids)


def test_schema_is_strict():
    s = schema(["a_plain"])
    person_schema = s["properties"]["people"]["items"]
    assert person_schema["additionalProperties"] is False
    assert set(person_schema["properties"]["answers"]["required"]) == set(SHED["questions"])


def test_fingerprint_changes_with_prompt():
    notices = load_notices(NOTICES)
    seg = BY_ID["age_60p"]
    a = fingerprint(build_prompt(seg, notices, 20, 0), "m")
    assert a == fingerprint(build_prompt(seg, notices, 20, 0), "m")
    assert a != fingerprint(build_prompt(seg, notices, 20, 1), "m")
    assert a != fingerprint(build_prompt(seg, notices[:2], 20, 0), "m")


def test_replay_reads_recording_and_refuses_missing(tmp_path):
    notices = load_notices(NOTICES)
    seg = BY_ID["age_60p"]
    rec = tmp_path / "rec.jsonl"
    with pytest.raises(LookupError):
        run_panel([seg], notices, 20, 1, rec, live=False, model="m")
    fp = fingerprint(build_prompt(seg, notices, 20, 0), "m")
    call = Call("age_60p", 0, fp, "m", [person() for _ in range(5)], 1000, 2000, 30.0)
    rec.write_text(call.to_json() + "\n")
    calls = run_panel([seg], notices, 20, 1, rec, live=False, model="m")
    result = score(calls, notices, SHED)
    assert result["run"]["people"] == 5
    assert result["run"]["cost_usd"] == round(1000 / 1e6 * 4 + 2000 / 1e6 * 20, 2)
    seg_result = result["segments"][0]
    assert seg_result["recommendation"] in (None, seg_result["best_notice"])


def test_committed_results_match_recording():
    """If a live run is committed, replaying it must reproduce results/run.json exactly."""
    rec = ROOT / "recordings" / "panel.jsonl"
    out = ROOT / "results" / "run.json"
    if not rec.exists() or not rec.read_text().strip():
        pytest.skip("no live run recorded yet")
    notices = load_notices(NOTICES)
    from noticesim.panel import MODEL

    calls = run_panel(SEGMENTS, notices, 20, 2, rec, live=False, model=MODEL)
    assert score(calls, notices, SHED) == json.loads(out.read_text())
