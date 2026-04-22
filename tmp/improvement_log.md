# Scout overnight improvement log

Baseline captured 2026-04-22 19:34 on feat/auto-improve-1.

- validate: 0 (clean)
- wiring: 6/6
- behavioral: 25/26 — 1 flaky (scout_update_round_trip; passed on re-run)
- judges: 7/7 — all 10.0 (ceiling; rubrics may be too generous)

## e782fbc — 2026-04-22 — iter 1
- Action: P3 — add scout_save_follow_through (known manual gap, two-turn save-from-context)
- Before: validate 0, wiring 6/6, behavioral 25/26 (1 flaky), judges 7/7 avg 10.0
- After:  validate 0, wiring 6/6, behavioral 27/27, judges 7/7 avg 10.0
- Notes: new case passed on first try. scout_update_round_trip flake not reproducing.

## iter 2 — 2026-04-22
- Action: P3 — add scout_crm_user_isolation; P4 — stabilize scout_save_follow_through + broaden scout_empty_gdrive paraphrase regex
- Before: validate 0, wiring 6/6, behavioral 27/27 (with 2 LLM flakes on first full run)
- After:  validate 0, wiring 6/6, behavioral 28/28, judges 7/7 avg 10.0
- Notes: follow-through case flaked when Scout saved in turn 1 proactively — added a question to turn 1 so Scout answers, not saves; turn 2 now "please save Alice to my contacts" is the unambiguous update_crm trigger. empty_gdrive regex missed "empty/zero" variants Scout uses.
