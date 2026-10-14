"""All tunable settings in one place (no magic numbers elsewhere)."""
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    shipments_path: Path = ROOT / "data" / "shipment_records.csv"
    notes_path: Path = ROOT / "data" / "context_notes.csv"
    note_facts_path: Path = ROOT / "data" / "note_facts.json"
    output_path: Path = ROOT / "outputs" / "output.csv"
    cost_log_path: Path = ROOT / "outputs" / "cost_log.json"

    # Baselines (fixed by the case study brief)
    history_weeks: int = 8

    # Flagging policy (OUR choice - the brief leaves it open; see README)
    min_history_weeks: int = 4        # need at least this many prior weeks to judge
    min_rise_vs_own_pct: float = 5.0  # "cost is rising" vs own trailing average
    strong_rise_vs_own_pct: float = 15.0  # big jump: suspicious on its own
    min_premium_vs_peers_pct: float = 15.0  # or: rising AND well above same-length peers

    # Retrieval
    top_k_notes: int = 5
    # A note that quotes a % range explains a rise only up to its max + this slack
    magnitude_tolerance_pts: float = 3.0
