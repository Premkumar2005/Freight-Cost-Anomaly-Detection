"""Load and validate the input CSVs. Bad rows are dropped and counted, never silently."""
import logging
import pandas as pd

log = logging.getLogger(__name__)

SHIPMENT_COLUMNS = ["shipment_id", "origin", "destination", "route_type", "quantity_tonnes",
                    "distance_km", "freight_cost_inr", "shipment_date"]
NOTE_COLUMNS = ["note_id", "date", "applies_to", "note"]
VALID_ROUTE_TYPES = {"Short", "Medium", "Long"}


def _read_csv(path, required):
    try:
        df = pd.read_csv(path)
    except FileNotFoundError:
        raise SystemExit(f"Input file not found: {path}")
    except pd.errors.EmptyDataError:
        raise SystemExit(f"Input file is empty: {path}")
    df.columns = [c.strip() for c in df.columns]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"{path} is missing required columns: {missing}")
    return df


def load_shipments(path) -> pd.DataFrame:
    df = _read_csv(path, SHIPMENT_COLUMNS)
    n0 = len(df)
    for col in ("origin", "destination", "route_type"):
        df[col] = df[col].astype(str).str.strip()
    for col in ("quantity_tonnes", "distance_km", "freight_cost_inr"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["shipment_date"] = pd.to_datetime(df["shipment_date"], errors="coerce")

    bad = (
        df[["quantity_tonnes", "distance_km", "freight_cost_inr", "shipment_date"]].isna().any(axis=1)
        | (df["quantity_tonnes"] <= 0) | (df["distance_km"] <= 0) | (df["freight_cost_inr"] <= 0)
        | ~df["route_type"].isin(VALID_ROUTE_TYPES)
        | df["origin"].isin(["", "nan"]) | df["destination"].isin(["", "nan"])
    )
    if bad.any():
        log.warning("Dropping %d invalid shipment rows (missing/non-positive values or bad route_type)", bad.sum())
    df = df[~bad]
    dup = df.duplicated("shipment_id")
    if dup.any():
        log.warning("Dropping %d duplicate shipment_ids", dup.sum())
        df = df[~dup]
    if df.empty:
        raise SystemExit("No valid shipment rows to analyse.")
    log.info("Loaded %d/%d valid shipment rows", len(df), n0)
    df = df.copy()
    df["route"] = df["origin"] + "-" + df["destination"]
    return df


def load_notes(path) -> pd.DataFrame:
    df = _read_csv(path, NOTE_COLUMNS)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["note_id", "date", "note"]).reset_index(drop=True)
    log.info("Loaded %d notes", len(df))
    return df
