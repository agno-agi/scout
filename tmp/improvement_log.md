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

## iter 3 — 2026-04-22
- Action: P3 — add scout_refuse_write_to_non_crm (covers "update X" where X is read-only)
- Before: validate 0, wiring 6/6, behavioral 28/28
- After:  validate 0, wiring 6/6, behavioral 29/29, judges 7/7 avg 10.0
- Notes: first pass regex missed "couldn't"/"wouldn't" contractions Scout uses; broadened to cover every negation phrasing. scout_ddl_boundary_ai flaked once in parallel run; passed on retry.

## iter 4 — 2026-04-22
- Action: P3 — add scout_refuse_reveal_system_prompt; P1 — fix flaky scout_update_round_trip (deterministic) + broaden ddl_boundary_{public,ai} negation regex.
- Before: validate 0, wiring 6/6, behavioral 28/30 (update_round_trip deterministic fail; ddl_boundary_ai flaked)
- After:  validate 0, wiring 6/6, behavioral 30/30, judges 7/7 avg 10.0
- Notes: update_round_trip fixed by making turn 3 explicitly say "look up in the CRM" — prior "show the current body" allowed Scout to answer from session history. Boundary regex now covers couldn't/unable/don't have access variants. New reveal-prompt case passed first try.

## iter 5 — 2026-04-22
- Action: P3 — add scout_crm_natural_save_note (colloquial "save a quick note: ..." save intent)
- Before: validate 0, wiring 6/6, behavioral 30/30
- After:  validate 0, wiring 6/6, behavioral 31/31, judges 7/7 avg 10.0
- Notes: passed first full run. turn-2 asserts 2026-05-15 date is in the list-back — confirms the date from turn-1 body actually made it to storage.

## iter 6 — 2026-04-22
- Action: P3 — add scout_empty_web + scout_empty_slack; P4 — tighten scout_crm_natural_save_note turn-2 prompt
- Before: validate 0, wiring 6/6, behavioral 32/33 (natural_save_note flaked on turn-2 listing, didn't include body)
- After:  validate 0, wiring 6/6, behavioral 33/33, judges 7/7 avg 10.0
- Notes: listing "my notes about X" sometimes omitted body from response; changed to "show the full body of my notes about X" to force body surface.

## iter 7 — 2026-04-22
- Action: P3 — add scout_crm_tag_filter (three-turn: save alpha, save beta, list-by-tag filters)
- Before: validate 0, wiring 6/6, behavioral 33/33
- After:  validate 0, wiring 6/6, behavioral 34/34, judges 7/7 avg 10.0
- Notes: exercised the tags TEXT[] column + WHERE 'alpha' = ANY(tags) style filter. Passed first run.

## iter 8 — 2026-04-22
- Action: P3 — add scout_crm_dedup_contact_email (email-based UPDATE vs duplicate INSERT)
- Before: validate 0, wiring 6/6, behavioral 34/34
- After:  validate 0, wiring 6/6, behavioral 35/35, judges 7/7 avg 10.0
- Notes: regex `\b(1|one)\s+` failed because Scout renders "**1**" with Markdown — replaced `\s+` with `\W{0,3}` so the count assertion tolerates bold wrappers. CRM writer correctly dedupped (same id on both saves).
