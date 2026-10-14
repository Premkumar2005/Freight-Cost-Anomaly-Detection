"""Verdict gate: decides 'justified' vs 'unexplained' using ONLY structured facts about notes.

A note justifies a rise only if ALL hold:
  1. it applies to this route (named route or 'All Routes'),
  2. its effect window overlaps the flagged week,
  3. it says costs went UP (notes that say 'no effect' never justify),
  4. if it quotes a % range, the observed rise is not far above that range.
Otherwise: unexplained. Nothing is guessed.
"""
import json
from dataclasses import dataclass
from typing import Optional

import pandas as pd

UNEXPLAINED_DEFAULT = ("No matching note found for this route or date range. "
                       "Cost rise looks unexplained and worth a human review.")


@dataclass
class NoteFact:
    note_id: str
    routes: list
    effect: str
    window_start: pd.Timestamp
    window_end: Optional[pd.Timestamp]
    persistence_weeks: Optional[int]
    magnitude_pct: Optional[list]
    explanation: str

    def effective_end(self) -> pd.Timestamp:
        if self.window_end is not None:
            return self.window_end
        if self.persistence_weeks:
            return self.window_start + pd.Timedelta(weeks=self.persistence_weeks) - pd.Timedelta(days=1)
        return self.window_start + pd.Timedelta(days=6)  # single dated week

    def covers_route(self, route: str) -> bool:
        return "*" in self.routes or route in self.routes


def load_note_facts(path, notes_df) -> dict:
    """Load curated facts and cross-check them against the raw notes file."""
    with open(path) as f:
        raw = json.load(f)
    note_dates = dict(zip(notes_df["note_id"], notes_df["date"]))
    facts = {}
    for r in raw:
        if r["note_id"] not in note_dates:
            raise SystemExit(f"note_facts.json references unknown note {r['note_id']}")
        facts[r["note_id"]] = NoteFact(
            r["note_id"], r["routes"], r["effect"], pd.Timestamp(r["window_start"]),
            pd.Timestamp(r["window_end"]) if r["window_end"] else None,
            r["persistence_weeks"], r["magnitude_pct"], r["explanation"])
    missing = set(note_dates) - set(facts)
    if missing:
        raise SystemExit(f"No structured facts for notes: {sorted(missing)}")
    return facts


def check_note(fact: NoteFact, route, wk_start, wk_end, rise, tolerance_pts):
    """Does this note justify a rise of `rise`% on `route` in the given week?

    Returns (True, None) or (False, short_reason_why_not).
    """
    if not fact.covers_route(route):
        return False, "it is about a different route or does not affect this dataset"
    if fact.effect != "raises_cost":
        return False, "it states there was no cost impact"
    if wk_end < fact.window_start or wk_start > fact.effective_end():
        return False, (f"its effect window ({fact.window_start.date()} to "
                       f"{fact.effective_end().date()}) does not include this week")
    if fact.magnitude_pct and rise > fact.magnitude_pct[1] + tolerance_pts:
        return False, (f"it explains only about {fact.magnitude_pct[0]:g}-{fact.magnitude_pct[1]:g}% "
                       f"but the observed rise is {rise:+.1f}%")
    return True, None


def decide(route, week_of, vs_own_pct, ranked_ids, facts, notes_df, tolerance_pts):
    """Return (matched_note_id or None, flagged: bool, reason text).

    ranked_ids: retrieved note ids, best first. The first note that passes the gate wins.
    """
    wk_start = pd.Timestamp(week_of)
    wk_end = wk_start + pd.Timedelta(days=6)
    note_date = dict(zip(notes_df["note_id"], notes_df["date"]))
    rejected = []  # notes that talk about this route but fail the gate

    for nid in ranked_ids:
        fact = facts[nid]
        ok, why = check_note(fact, route, wk_start, wk_end, vs_own_pct, tolerance_pts)
        if ok:
            return nid, False, (f"Matches note {nid} dated {note_date[nid].date()}: {fact.explanation}. "
                                f"The cost rise has a clear explanation.")
        if fact.covers_route(route):  # only mention notes that are about this route / all routes
            rejected.append((nid, why))

    if rejected:
        nid, why = rejected[0]
        return None, True, (f"The closest note ({nid}, {note_date[nid].date()}) says {facts[nid].explanation}; "
                            f"it does not justify this rise because {why}. "
                            f"No genuine justification found; flagged for review.")
    return None, True, UNEXPLAINED_DEFAULT
