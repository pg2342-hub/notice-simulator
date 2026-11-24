# notice-simulator

[![CI](https://github.com/pg2342-hub/notice-simulator/actions/workflows/ci.yml/badge.svg)](https://github.com/pg2342-hub/notice-simulator/actions/workflows/ci.yml)

Demo page: https://pranavgudise.dev/notice-simulator/ (pick a notice and a segment, see the predicted reaction and whether that segment's panel can be trusted; no install needed)

When a bank moves millions of card accounts to a new platform, every cardholder gets a notice asking them to set up a new login. Each wave of notices goes out once, so a weak notice cannot be tested again on the same people. This tool tests notice versions on a simulated panel first, and says which customer segments the simulation can be trusted on.

## What it does

1. **Simulate a panel.** Claude writes 20 distinct people per call from one segment (four income bands, four age bands), two calls per segment.
2. **Check it against real answers.** Every simulated person answers seven questions the Federal Reserve asked about 13,000 adults in its 2025 Survey of Household Economics and Decisionmaking (bank account, credit card, carried a balance, Buy Now Pay Later, overdraft fee, card fraud, check cashing). Shares use the same base as the report.
3. **Trust rule, fixed before the first run.** A segment is trusted when its panel is within 10 points of the published answer on at least 6 of 7 questions.
4. **React to the notices.** Card holders react to each notice: set up the new login within a week, first suspect a scam, and keep, use less, or close the card. The best notice per segment is only a recommendation when the segment is trusted.

```
$ noticesim run notices/*.md
Trusted segments: N of 8 (within 10 points of SHED on 6 of 7 questions)
Income under $25K      TRUSTED      6/7 within, mean gap ... pts
    Plain facts      login in a week ...%  suspects scam ...%  close or move ...%
...
```

## Run it

```
pip install -e ".[dev]"
noticesim run notices/*.md            # replays recordings/panel.jsonl, no key needed
NOTICESIM_LIVE=1 noticesim run notices/*.md   # new live panel (needs ANTHROPIC_API_KEY)
pytest -q
```

Add your own notice as a markdown file with `id` and `name` front matter in `notices/`. A changed notice or prompt changes the call fingerprint, so a replay will refuse to reuse an old answer and asks for a live run.

## Files

| Path | What it is |
|---|---|
| `noticesim/panel.py` | Prompt, structured-output schema, live call (Claude Opus 5.5) and fingerprinted record/replay |
| `noticesim/score.py` | Shares on the report's base, the trust rule, reactions, best notice, cost |
| `data/shed_2025.json` | The published SHED 2025 answers by income and age band, with table numbers and links |
| `notices/` | Three invented notices (a fictional bank acquisition): plain facts, benefits first, security first |
| `scripts/build_demo.py` | Builds `docs/index.html` from `results/run.json` |
| `.github/workflows/record.yml` | Records a live run with the repo's `ANTHROPIC_API_KEY` secret, rebuilds and publishes the demo |

## Limits

- Trust is measured on survey questions, not on reactions to notices. A real pilot would back-test reactions against a wave that already went out.
- Passing is a low bar: a plain guess with no model (each question's average across the eight groups, used for every group) lands within 10 points on 48 of 56 answers and passes 5 of 8 groups. The check rules a panel out better than it proves one right.
- The security-first notice says how to know it is real, and the panel mostly believes it; real cardholders and phishers may not.
- Run 1 (`results/run1.json`, `recordings/run1_panel.jsonl`) trusted no segment: the panels overstated overdraft fees, Buy Now, Pay Later and check cashing in every group. Run 2 grounds each group in its SHED 2025 share doing okay financially (Table 1, not one of the checked questions) and asks for a random sample rather than memorable hardship. The trust rule did not change, but run 2's brief was written after seeing run 1's misses, so it is a second attempt, not an independent test.
- The model may have read the Federal Reserve report in training, which would flatter the match.
- 40 people per segment means sampling noise of up to about 8 points on a share; the tolerance is 10.

Data: Board of Governors of the Federal Reserve System, *Economic Well-Being of U.S. Households in 2025* (May 2026), tables 31, 32, 35, 40 and 41. Everything else is simulated or invented.
