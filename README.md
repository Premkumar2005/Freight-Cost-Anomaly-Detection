# Freight Cost Watch

Spots freight routes whose **cost per tonne-km** is rising in a way that looks unjustified, and explains each
verdict in plain English using only the notes in `context_notes.csv`.

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # pandas (+ pytest for tests)
python -m costwatch.cli run              # writes outputs/output.csv and outputs/cost_log.json
python -m costwatch.cli ask "why did Chennai-Bangalore get pricier in March?"   # stretch goal
python -m pytest -q                      # unit + integration tests
python -m costwatch.evaluation           # labeled-set eval + fabrication audit
./repro_check.sh                         # 3 runs, compares SHA-256
```
No API keys, no network, no `.env` needed (nothing secret exists in this project).

## How it works
`loader` (validate CSVs) -> `metrics` (weekly cost/tonne-km, baselines) -> `is_candidate` (flag policy) ->
`retrieval` (TF-IDF ranks notes) -> `verdict` (gate decides justified vs unexplained) -> `output.csv`.

1. **Grouping & weeks.** By `route` (origin-destination) and the provided `route_type`. `week_of` = Monday of the
   Mon-Sun week. Weekly cost per tonne-km = sum(cost) / sum(tonnes x km) for that week.
2. **Baselines (exactly as the brief defines).**
   - *vs own history*: mean of the route's weekly values over the prior 8 calendar weeks, strictly before the current week.
     **If fewer than 8 prior weeks exist, all available prior weeks are used (no padding/extrapolation).**
     56 route-weeks (the first 8 weeks of each route) are in that situation; no flag is raised with fewer than 4 prior weeks.
   - *vs similar routes*: mean of the other routes' weekly values with the same `route_type` in the same week (self excluded).
   - Reproduces all three rows of the sample file exactly (4.17/+35.5%/+21.0%, 3.29/+29.5%/+22.5%, 3.98/+9.2%/+23.6%).
3. **Flag policy (my choice; the brief leaves it open, thresholds live in `config.py`).** A route-week is a candidate when
   `vs_own >= +5%` AND (`vs_own >= +15%` OR `vs_similar >= +15%`). Rationale: ordinary weekly noise is about +/-4%, so a
   rise needs to clear it; then it must be either a big jump by itself or sit well above comparable routes.
   Only candidate weeks appear in the output (flagged, or justified by a note).
4. **Retrieval.** A small dependency-free TF-IDF index over the 10 notes ranks them for each route (top 5).
   Deterministic, free, no embeddings model to download. It only *ranks*; it can never justify anything alone.
5. **Verdict gate (anti-hallucination).** A note justifies a rise only if it (a) covers the route (or All Routes),
   (b) its effect window overlaps that week, (c) says costs went **up**, and (d) if it quotes a % range, the observed rise
   is not more than 3 points above the range. Otherwise the row is **flagged / unexplained** with `matched_note_id` blank.
   Windows and effects come from `data/note_facts.json`, a hand-checked structured reading of the 10 notes.
   Explanations are templates filled from that file, so wording cannot invent facts.

### Judgment calls worth knowing
- **Chennai-Bangalore, weeks of Mar 10 and Mar 17 2025 are flagged, not justified.** N001's flood window ends Mar 8 and
  N009 says the route was back to normal from Mar 9, yet costs stayed ~14-22% above history. The week of Mar 3 overlaps
  the window, so it is justified by N001.
- **N003 (diesel, +5-7%, from 2025-05-05)** is treated as a level shift that justifies deviation from the trailing
  8-week baseline only until that baseline has absorbed it (8 weeks) and only if the rise is within ~7% + 3 pts. Later
  Mumbai-Pune creep (up to ~+9% per week, ~+30% over the Jan-2024 level) is therefore flagged.
- Notes that say "no effect" (N004-N010 except as above) can never justify a rise. They are only quoted as "closest note, does not apply".
- `N004` names routes outside the dataset, so it applies to nothing here.

## Results (this dataset)
17 rows: 13 flagged, 4 justified (N002 x1, N001 x2, N003 x1). Delhi-Jaipur (Nov 2024, 2 weeks) and Mumbai-Pune
(a steady 2025 creep) are the main unexplained findings. See `outputs/output.csv`.
Output file quotes the `reason` column properly (the sample file has an unquoted comma in one row, so it is not strictly valid CSV).

## How I convinced myself it is right
- `pytest` (11 tests): week boundaries, no look-ahead, self-excluded peers, <8-week history, bad input handling,
  gate rejects wrong route / wrong window / "no effect" / oversized rise, retrieval determinism, output contract, Q&A.
- `python -m costwatch.evaluation`: 9 hand-labelled rows (incl. the 3 sample rows) all match; 3 decoy weeks correctly absent;
  an automatic **fabrication audit** re-checks every "justified" row against the gate. Caveat: the labels are small and written by
  the same person as the rules - a sanity check, not an independent benchmark.
- **Threshold sensitivity**: varying each threshold (rise 4-6%, peer 12-20%, strong 10-20%) changes only the borderline
  Mumbai-Pune creep rows (14-19 rows in total); the 7 rows for the planted events (Delhi-Jaipur, Ahmedabad-Mumbai, Chennai-Bangalore) never change.

## Reproducibility
Nothing random and no LLM is used. `./repro_check.sh` runs 3 times; output SHA-256 identical
(`6ac41593...a1397`, recorded in `outputs/repro_check.txt`).

## Cost / tokens (one full run)
LLM calls: **0**. Input tokens: **0**. Output tokens: **0**. Cost: **$0.00** (`outputs/cost_log.json`).
Deliberate trade-off: with 10 notes, a rules + TF-IDF design is cheaper, fully reproducible and cannot hallucinate.
An LLM would only help to phrase explanations or parse notes in free text at scale; at temperature 0 it
would still sit *behind* the same verdict gate.

## Limitations / next steps
- Flag thresholds are heuristics; a production version would calibrate them on labelled history (or use a robust z-score).
- `note_facts.json` is curated by hand; for many notes an LLM (temperature 0) could extract it, with the same gate and human spot-check.
- `ask` understands route names, month and year only (keyword parsing); an LLM could be added on top, answering strictly from `output.csv`.
- Weekly values with only 3-5 shipments are noisy; the pipeline does not model shipment mix (material, transporter).
"# Freight-Cost-Anomaly-Detection" 
