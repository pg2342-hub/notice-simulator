"""The persona panel: one Claude call simulates a batch of people from one segment.

Each simulated person answers seven yes/no questions that the Federal Reserve's SHED survey
also asked (so the panel can be checked against real answers), then reacts to every notice.

Live calls are recorded to JSONL. Replays read the recording back, keyed by a fingerprint of
the prompt and model, so a changed prompt never silently reuses an old answer.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .notices import Notice
from .segments import Segment

MODEL = "claude-opus-5-5"
CALIBRATION_KEYS = [
    "banked",
    "has_card",
    "carried_balance",
    "used_bnpl",
    "paid_overdraft",
    "card_fraud",
    "nonbank_check",
]
CARD_PLANS = ["keep_using", "use_less", "close_or_move"]

SYSTEM = """You run a simulated survey panel for consumer research. You write realistic,
individual people and answer as each of them would. Draw them the way a random sample of the
segment would turn out, not the most memorable cases: for most people most years are
financially uneventful, and hardship should be as common as it really is, no more and no less.
Do not aim for any published statistic in the questions. Vary age, job, household, region, and
attitudes within the segment you are given."""

QUESTIONS = """Calibration questions (answer for each person about the past 12 months):
- banked: they or their spouse/partner have a checking, savings, or money market account
- has_card: they have a credit card
- carried_balance: they carried a credit card balance at least once (null if has_card is false)
- used_bnpl: they used Buy Now, Pay Later
- paid_overdraft: they paid an overdraft fee (null if banked is false)
- card_fraud: they had credit card fraud (a charge they did not make)
- nonbank_check: they used a nonbank check casher or bought a money order"""

REACTION = """Then, ONLY for people with a credit card, imagine the card in the notice is one they
own and use. For each notice, record how this person would most likely react in the next week:
- setup_within_week: they would set up the new login within a week of reading it
- suspects_scam: their first reaction is to suspect the message is a phishing scam
- card_plan: keep_using, use_less (move some spending to another card), or close_or_move
- reason: one short sentence in their own voice
People without a credit card get an empty reactions list."""


def schema(notice_ids: list[str]) -> dict[str, Any]:
    bool_or_null = {"type": ["boolean", "null"]}
    reaction = {
        "type": "object",
        "properties": {
            "notice_id": {"type": "string", "enum": notice_ids},
            "setup_within_week": {"type": "boolean"},
            "suspects_scam": {"type": "boolean"},
            "card_plan": {"type": "string", "enum": CARD_PLANS},
            "reason": {"type": "string"},
        },
        "required": ["notice_id", "setup_within_week", "suspects_scam", "card_plan", "reason"],
        "additionalProperties": False,
    }
    answers = {
        "type": "object",
        "properties": {k: bool_or_null for k in CALIBRATION_KEYS},
        "required": CALIBRATION_KEYS,
        "additionalProperties": False,
    }
    person = {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            "answers": answers,
            "reactions": {"type": "array", "items": reaction},
        },
        "required": ["profile", "answers", "reactions"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"people": {"type": "array", "items": person}},
        "required": ["people"],
        "additionalProperties": False,
    }


def build_prompt(segment: Segment, notices: list[Notice], n: int, batch: int) -> str:
    blocks = "\n\n".join(f'<notice id="{x.id}">\n{x.text}\n</notice>' for x in notices)
    return (
        f"Segment: {segment.who}.\n"
        f"Grounding from the same survey (not one of the questions below): {segment.doing_okay}% of "
        f"this group say they are doing okay or living comfortably financially, and the rest say they "
        f"are just getting by or finding it difficult. Write a group with about that mix, and let each "
        f"person's answers follow from their situation.\n"
        f"Write {n} different people from this segment (batch {batch + 1}; make them distinct "
        f"from people another batch would write). Give each a one-line profile.\n\n"
        f"{QUESTIONS}\n\n{REACTION}\n\nNotices:\n\n{blocks}"
    )


def fingerprint(prompt: str, model: str) -> str:
    return hashlib.sha256(f"{model}\n{SYSTEM}\n{prompt}".encode()).hexdigest()[:16]


@dataclass
class Call:
    segment: str
    batch: int
    fingerprint: str
    model: str
    people: list[dict[str, Any]]
    input_tokens: int
    output_tokens: int
    latency_s: float

    def to_json(self) -> str:
        return json.dumps(self.__dict__, ensure_ascii=False)


def validate_people(people: list[dict[str, Any]], notice_ids: list[str]) -> list[str]:
    """Problems that make a simulated person unusable. Empty list means the batch is fine."""
    problems = []
    for i, p in enumerate(people):
        a = p["answers"]
        if any(a[k] is None for k in CALIBRATION_KEYS if k not in ("carried_balance", "paid_overdraft")):
            problems.append(f"person {i}: missing a yes/no answer")
        if a["has_card"] and a["carried_balance"] is None:
            problems.append(f"person {i}: card holder with no balance answer")
        if a["banked"] and a["paid_overdraft"] is None:
            problems.append(f"person {i}: banked with no overdraft answer")
        got = sorted(r["notice_id"] for r in p["reactions"])
        want = sorted(notice_ids) if a["has_card"] else []
        if got != want:
            problems.append(f"person {i}: reactions {got}, expected {want}")
    return problems


def call_live(segment: Segment, notices: list[Notice], n: int, batch: int, model: str = MODEL) -> Call:
    import anthropic

    client = anthropic.Anthropic()
    prompt = build_prompt(segment, notices, n, batch)
    ids = [x.id for x in notices]
    start = time.monotonic()
    # Streamed because max_tokens is large; get_final_message() returns the whole reply.
    with client.beta.messages.stream(
        model=model,
        max_tokens=32000,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema(ids)}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    ) as stream:
        response = stream.get_final_message()
    latency = time.monotonic() - start
    if response.stop_reason == "refusal":
        raise RuntimeError(f"{segment.id} batch {batch}: the model declined")
    if response.stop_reason == "max_tokens":
        raise RuntimeError(f"{segment.id} batch {batch}: output cut off at max_tokens")
    text = next(b.text for b in response.content if b.type == "text")
    people = json.loads(text)["people"]
    return Call(
        segment=segment.id,
        batch=batch,
        fingerprint=fingerprint(prompt, model),
        model=response.model,
        people=people,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        latency_s=round(latency, 1),
    )


def load_recording(path: str | Path) -> dict[str, Call]:
    calls: dict[str, Call] = {}
    p = Path(path)
    if not p.exists():
        return calls
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            c = Call(**json.loads(line))
            calls[c.fingerprint] = c
    return calls


def run_panel(
    segments: list[Segment],
    notices: list[Notice],
    n: int,
    batches: int,
    recording: str | Path,
    live: bool | None = None,
    model: str = MODEL,
) -> list[Call]:
    """Live when NOTICESIM_LIVE=1 (or live=True): call Claude and append to the recording.
    Otherwise replay the recording and fail loudly on any call it does not hold."""
    live = os.environ.get("NOTICESIM_LIVE") == "1" if live is None else live
    recorded = load_recording(recording)
    ids = [x.id for x in notices]
    calls = []
    for seg in segments:
        for b in range(batches):
            fp = fingerprint(build_prompt(seg, notices, n, b), model)
            if fp in recorded:
                calls.append(recorded[fp])
                continue
            if not live:
                raise LookupError(
                    f"no recorded answer for {seg.id} batch {b + 1} (fingerprint {fp}); "
                    "run live with NOTICESIM_LIVE=1 and an API key"
                )
            call = None
            for attempt in range(2):
                call = call_live(seg, notices, n, b, model)
                problems = validate_people(call.people, ids)
                if not problems:
                    break
                if attempt == 1:
                    raise ValueError(f"{seg.id} batch {b + 1}: {problems[:3]}")
            with Path(recording).open("a", encoding="utf-8") as f:
                f.write(call.to_json() + "\n")
            calls.append(call)
            print(f"  {seg.id} batch {b + 1}: {len(call.people)} people, {call.latency_s}s", flush=True)
    return calls
