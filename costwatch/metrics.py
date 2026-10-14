"""Weekly cost per tonne-km and the two baselines defined in the case study."""
import numpy as np
import pandas as pd


def weekly_costs(shipments: pd.DataFrame) -> pd.DataFrame:
    """One row per (route, route_type, week_of). week_of = Monday of the shipment's week.

    cost_per_tonne_km = sum(cost) / sum(tonnes * km)  (volume-weighted, i.e. exactly
    'total freight cost / (quantity x distance)' for the week).
    """
    df = shipments.copy()
    df["week_of"] = df["shipment_date"].dt.normalize() - pd.to_timedelta(df["shipment_date"].dt.weekday, unit="D")
    df["tonne_km"] = df["quantity_tonnes"] * df["distance_km"]
    weekly = (df.groupby(["route", "route_type", "week_of"], as_index=False)
                .agg(total_cost=("freight_cost_inr", "sum"), tonne_km=("tonne_km", "sum"),
                     n_shipments=("shipment_id", "count")))
    weekly["cost_per_tonne_km"] = weekly["total_cost"] / weekly["tonne_km"]
    return weekly.sort_values(["route", "week_of"]).reset_index(drop=True)


def add_baselines(weekly: pd.DataFrame, history_weeks: int) -> pd.DataFrame:
    """Add own-history and peer baselines (no look-ahead, no padding)."""
    out = weekly.copy()
    out = out.sort_values(["route", "week_of"]).reset_index(drop=True)
    hist_avg, hist_n = [], []
    for _, grp in out.groupby("route", sort=True):
        series = grp.set_index("week_of")["cost_per_tonne_km"]
        for wk in grp["week_of"]:
            lo = wk - pd.Timedelta(weeks=history_weeks)
            prior = series[(series.index >= lo) & (series.index < wk)]  # strictly before this week
            hist_avg.append(prior.mean() if len(prior) else np.nan)
            hist_n.append(len(prior))
    out["own_history_avg"] = hist_avg
    out["history_weeks_used"] = hist_n

    # Peer average: other routes, same route_type, same week (self excluded)
    key = out.groupby(["route_type", "week_of"])["cost_per_tonne_km"].agg(["sum", "count"])
    s_sum = out.set_index(["route_type", "week_of"]).index.map(key["sum"])
    s_cnt = out.set_index(["route_type", "week_of"]).index.map(key["count"])
    peer_cnt = np.asarray(s_cnt) - 1
    with np.errstate(divide="ignore", invalid="ignore"):
        out["peer_avg"] = np.where(peer_cnt > 0, (np.asarray(s_sum) - out["cost_per_tonne_km"]) / peer_cnt, np.nan)

    out["vs_own_pct"] = (out["cost_per_tonne_km"] / out["own_history_avg"] - 1) * 100
    out["vs_peers_pct"] = (out["cost_per_tonne_km"] / out["peer_avg"] - 1) * 100
    return out


def is_candidate(row, cfg) -> bool:
    """Flagging policy: rising vs own history AND (a big jump OR well above similar routes)."""
    if row["history_weeks_used"] < cfg.min_history_weeks or np.isnan(row["vs_own_pct"]):
        return False
    if row["vs_own_pct"] < cfg.min_rise_vs_own_pct:
        return False
    big_jump = row["vs_own_pct"] >= cfg.strong_rise_vs_own_pct
    above_peers = (not np.isnan(row["vs_peers_pct"])) and row["vs_peers_pct"] >= cfg.min_premium_vs_peers_pct
    return bool(big_jump or above_peers)
