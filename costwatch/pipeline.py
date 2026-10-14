"""End-to-end run: load -> weekly metrics -> candidates -> retrieve -> verdict -> CSV."""
import json
import logging

import pandas as pd

from .config import Config
from .loader import load_notes, load_shipments
from .metrics import add_baselines, is_candidate, weekly_costs
from .retrieval import NoteRetriever, build_query
from .verdict import decide, load_note_facts

log = logging.getLogger(__name__)

OUTPUT_COLUMNS = ["route", "week_of", "cost_per_tonne_km", "vs_own_history", "vs_similar_routes",
                  "flagged", "matched_note_id", "reason"]


def _fmt_own(v):
    return f"{v:+.1f}% vs this route's past average"


def _fmt_peers(v):
    return "n/a (no peer routes this week)" if pd.isna(v) else f"{v:+.1f}% vs similar-length routes this week"


def run(cfg: Config = Config()) -> pd.DataFrame:
    shipments = load_shipments(cfg.shipments_path)
    notes = load_notes(cfg.notes_path)
    facts = load_note_facts(cfg.note_facts_path, notes)
    retriever = NoteRetriever(notes)

    table = add_baselines(weekly_costs(shipments), cfg.history_weeks)
    short = table[table["history_weeks_used"] < cfg.history_weeks]
    log.info("%d route-weeks used fewer than %d prior weeks of history", len(short), cfg.history_weeks)

    rows = []
    for rec in table.to_dict("records"):
        if not is_candidate(rec, cfg):
            continue
        ranked = [nid for nid, _ in retriever.search(build_query(rec["route"]), cfg.top_k_notes)]
        note_id, flagged, reason = decide(rec["route"], rec["week_of"], rec["vs_own_pct"], ranked,
                                          facts, notes, cfg.magnitude_tolerance_pts)
        rows.append({
            "route": rec["route"],
            "week_of": rec["week_of"].strftime("%Y-%m-%d"),
            "cost_per_tonne_km": f"{rec['cost_per_tonne_km']:.2f}",
            "vs_own_history": _fmt_own(rec["vs_own_pct"]),
            "vs_similar_routes": _fmt_peers(rec["vs_peers_pct"]),
            "flagged": "Yes" if flagged else "No (justified)",
            "matched_note_id": note_id or "",
            "reason": reason,
        })
    out = pd.DataFrame(rows, columns=OUTPUT_COLUMNS).sort_values(["week_of", "route"]).reset_index(drop=True)
    return out


def write_outputs(df: pd.DataFrame, cfg: Config = Config()):
    cfg.output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cfg.output_path, index=False, lineterminator="\n")
    # No LLM is called anywhere in this pipeline, so the cost log is honestly zero.
    with open(cfg.cost_log_path, "w") as f:
        json.dump({"llm_calls": 0, "input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": 0.0,
                   "note": "Retrieval is local TF-IDF; verdicts and explanations are rule/template based."},
                  f, indent=2)
    log.info("Wrote %d rows to %s", len(df), cfg.output_path)
