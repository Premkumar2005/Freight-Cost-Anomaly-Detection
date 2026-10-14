"""Eval harness: scores the pipeline against a small hand-labeled set + automatic fabrication audit."""
import sys

import pandas as pd

from .config import Config
from .pipeline import run
from .verdict import check_note, load_note_facts
from .loader import load_notes

# Hand labels from reading the raw notes + weekly series. Small (9 rows) and written by the same person who
# wrote the rules, so this is a sanity check, not an independent benchmark.
# (route, week_of) -> (expected flagged value, expected matched_note_id)
LABELS = {
    ("Delhi-Jaipur", "2024-11-11"): ("Yes", ""),            # sample row; N007 is wrong date + not a cost note
    ("Delhi-Jaipur", "2024-11-18"): ("Yes", ""),
    ("Ahmedabad-Mumbai", "2025-01-20"): ("No (justified)", "N002"),   # sample row
    ("Chennai-Bangalore", "2025-02-24"): ("No (justified)", "N001"),
    ("Chennai-Bangalore", "2025-03-03"): ("No (justified)", "N001"),  # overlaps Feb24-Mar8 window
    ("Chennai-Bangalore", "2025-03-10"): ("Yes", ""),       # after Mar 8; N009 says normal -> unexplained
    ("Chennai-Bangalore", "2025-03-17"): ("Yes", ""),
    ("Mumbai-Pune", "2025-09-15"): ("Yes", ""),             # sample row; N006 says stable demand
    ("Mumbai-Pune", "2025-12-08"): ("Yes", ""),
}
# Weeks that must NOT appear (normal noise, or a fake-event decoy)
MUST_BE_ABSENT = [
    ("Mumbai-Delhi", "2024-07-29"),   # N005 maintenance week, costs unaffected
    ("Delhi-Chennai", "2025-02-17"),  # noisy week, no real rise vs its own history
    ("Kolkata-Bhubaneswar", "2025-06-09"),
]


def score(df: pd.DataFrame):
    idx = {(r.route, r.week_of): r for r in df.itertuples()}
    ok, fails = 0, []
    for key, (flag, nid) in LABELS.items():
        r = idx.get(key)
        got = (r.flagged, "" if pd.isna(r.matched_note_id) else r.matched_note_id) if r is not None else None
        if got == (flag, nid):
            ok += 1
        else:
            fails.append((key, (flag, nid), got))
    absent_fail = [k for k in MUST_BE_ABSENT if k in idx]
    return ok, len(LABELS), fails, absent_fail


def fabrication_audit(df: pd.DataFrame, cfg: Config):
    """Every 'justified' row must cite a note that covers the route, overlaps the week, raises cost."""
    notes = load_notes(cfg.notes_path)
    facts = load_note_facts(cfg.note_facts_path, notes)
    bad = []
    for r in df[df.flagged != "Yes"].itertuples():
        wk = pd.Timestamp(r.week_of)
        rise = float(r.vs_own_history.split("%")[0])
        nid = r.matched_note_id
        valid = isinstance(nid, str) and nid in facts and nid in r.reason
        if valid:
            valid, _ = check_note(facts[nid], r.route, wk, wk + pd.Timedelta(days=6), rise, cfg.magnitude_tolerance_pts)
        if not valid:
            bad.append((r.route, r.week_of, nid))
    return bad


def main():
    cfg = Config()
    df = run(cfg)
    ok, total, fails, absent = score(df)
    bad = fabrication_audit(df, cfg)
    print(f"Labeled rows correct: {ok}/{total}")
    for f in fails: print("  MISMATCH", f)
    print(f"Decoys wrongly present: {absent or 'none'}")
    print(f"Fabricated 'justified' rows: {bad or 'none'}")
    return 0 if ok == total and not absent and not bad else 1


if __name__ == "__main__":
    sys.exit(main())
