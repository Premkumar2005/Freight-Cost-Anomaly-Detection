"""Stretch goal: answer plain-English questions using ONLY the rows in output.csv.

Deterministic keyword parsing (route names, month, year). No LLM, so answers are
always traceable to a row; if nothing matches it says so instead of guessing.
"""
import re

import pandas as pd

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}


def answer(question: str, results_path) -> str:
    try:
        df = pd.read_csv(results_path, dtype=str).fillna("")
    except FileNotFoundError:
        return f"No results file at {results_path}. Run `python -m costwatch.cli run` first."
    q = question.lower()
    dates = pd.to_datetime(df["week_of"])
    mask = pd.Series(True, index=df.index)
    scope = []

    routes = [r for r in df["route"].unique()
              if r.lower() in q or all(part.lower() in q for part in r.split("-"))]
    mentioned = re.findall(r"\b[a-z]+-[a-z]+\b", q)  # route-like tokens, e.g. mumbai-delhi
    if routes:
        mask &= df["route"].isin(routes)
        scope.append(", ".join(routes))
    elif mentioned:  # user named a route we have no findings for: never fall back to other routes
        return (f"I have no flagged or justified cost rise for {', '.join(mentioned)} in my results. "
                "That means no week met the flagging rule, not that costs were unchanged.")
    month = next((n for m, n in MONTHS.items() if re.search(rf"\b{m}\b", q)), None)
    if month:
        mask &= dates.dt.month == month
        scope.append(f"month {month}")
    year = re.search(r"\b(20\d{2})\b", q)
    if year:
        mask &= dates.dt.year == int(year.group(1))
        scope.append(year.group(1))
    if not routes and not month and not year:
        return ("Please mention a route (e.g. Mumbai-Pune), a month, or a year. "
                f"Known routes with findings: {', '.join(sorted(df['route'].unique()))}.")

    hits = df[mask]
    label = " / ".join(scope)
    if hits.empty:
        return (f"I found no flagged or justified cost rise for {label} in my results. "
                "That means no week met the flagging rule, not that costs were unchanged.")
    lines = [f"Findings for {label}:"]
    for r in hits.itertuples():
        cite = f" [note {r.matched_note_id}]" if r.matched_note_id else " [no supporting note]"
        lines.append(f"- {r.route}, week of {r.week_of}: {r.cost_per_tonne_km} per tonne-km, "
                     f"{r.vs_own_history}. Verdict: {r.flagged}.{cite} {r.reason}")
    return "\n".join(lines)
