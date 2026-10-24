# SignalDesk AI — Prompt Iteration & Evaluation Log

## Project question
Can an AI-assisted intake tool turn messy updates into useful action candidates without inventing owners, deadlines, commitments, or dependencies?

## Test input (fictional)
> We should try to finish the payment bug before Friday if possible. Ananya may check it, but she is waiting on the API team. The release might move to Monday. Raj said he would investigate the timeout issue, although nobody confirmed whether it is the same bug.

## Iteration 1 — naive extraction
**Prompt intent:** extract tasks, owners, and dates as JSON.

**Observed failure modes in the baseline test record:**
- “before Friday” was converted to a firm calendar date;
- Ananya and Raj were treated as confirmed owners based on tentative or reported wording;
- the timeout issue was merged with the payment bug without confirmation;
- all actions were labeled committed with high confidence;
- the API team blocker was omitted;
- a schedule uncertainty became an action (“Move release to Monday”);
- “Check it” retained an unresolved pronoun.

The failure categories above are the useful evidence; they motivated each rule in Iteration 2.

## Iteration 2 — evidence-first prompt
Changes added:
1. Require verbatim evidence quotes and sentence indices.
2. Separate confirmed, tentative, self-declared, and unknown ownership.
3. Preserve weekday phrases as text; only use ISO dates if the full date appears in the source.
4. Separate tentative, reported intent, and committed language.
5. Prohibit automatic issue merging; uncertain relations require human clarification.
6. Represent schedule changes as schedule signals, not tasks.
7. Preserve blockers and ask for missing ETA.
8. Make uncertainty and missing information explicit.
9. Cap confidence for hedged, second-hand, or inferred evidence.
10. Keep priority scoring separate from extraction.

## Validation and critical reading
A schema alone is insufficient. Lightweight validators can catch some contradictions, such as:
- evidence quote not present in the source;
- unsupported ISO date;
- firm deadline based on hedged wording;
- committed status despite hedged or reported language;
- high confidence despite uncertainty;
- missing fields without clarification questions.

The Python app's own checks live in `tests/test_core.py` (run with `python -m unittest discover -s tests -v`).

## Limitations
- Demo mode is deterministic and deliberately conservative; it is not a general-purpose language model.
- Optional real AI extraction has not been tested against a live provider in this environment.
- Validation checks are partial and cannot prove that an extraction is factually correct.
- Priority is a configurable heuristic, not an objective measure of business value.
