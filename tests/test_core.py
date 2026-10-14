import pandas as pd
import pytest

from costwatch.config import Config
from costwatch.loader import load_shipments
from costwatch.metrics import add_baselines, weekly_costs
from costwatch.pipeline import OUTPUT_COLUMNS, run
from costwatch.retrieval import NoteRetriever, build_query
from costwatch.verdict import NoteFact, check_note, decide
from costwatch.evaluation import fabrication_audit, score
from costwatch.ask import answer


def _ship(rows):
    cols = ["shipment_id", "origin", "destination", "route_type", "quantity_tonnes", "distance_km",
            "freight_cost_inr", "shipment_date"]
    return pd.DataFrame(rows, columns=cols)


def _write(tmp_path, rows):
    p = tmp_path / "s.csv"
    _ship(rows).to_csv(p, index=False)
    return p


def test_week_boundaries_monday_to_sunday(tmp_path):
    p = _write(tmp_path, [
        ["a", "A", "B", "Short", 10, 100, 1000, "2024-01-01"],   # Monday
        ["b", "A", "B", "Short", 10, 100, 1000, "2024-01-07"],   # Sunday, same week
        ["c", "A", "B", "Short", 10, 100, 3000, "2024-01-08"],   # next Monday
    ])
    w = weekly_costs(load_shipments(p))
    assert list(w["week_of"].dt.strftime("%Y-%m-%d")) == ["2024-01-01", "2024-01-08"]
    assert w.loc[0, "cost_per_tonne_km"] == pytest.approx(2000 / 2000)
    assert w.loc[1, "cost_per_tonne_km"] == pytest.approx(3000 / 1000)


def test_baselines_exclude_current_week_and_self():
    rows = []
    for i, v in enumerate([1, 1, 1, 1, 1, 1, 1, 1, 2]):          # route X, 9 weeks
        rows.append(["X-Y", "Short", pd.Timestamp("2024-01-01") + pd.Timedelta(weeks=i), v, 1, 1, 1])
    for i in range(9):                                            # peer route, constant 3
        rows.append(["P-Q", "Short", pd.Timestamp("2024-01-01") + pd.Timedelta(weeks=i), 3, 1, 1, 1])
    w = pd.DataFrame(rows, columns=["route", "route_type", "week_of", "cost_per_tonne_km", "total_cost", "tonne_km", "n_shipments"])
    out = add_baselines(w, 8)
    last = out[(out.route == "X-Y") & (out.week_of == pd.Timestamp("2024-02-26"))].iloc[0]
    assert last["own_history_avg"] == pytest.approx(1.0)          # no look-ahead, current week excluded
    assert last["peer_avg"] == pytest.approx(3.0)                 # only the other route
    assert last["vs_own_pct"] == pytest.approx(100.0)
    first = out[(out.route == "X-Y")].iloc[0]
    assert pd.isna(first["own_history_avg"])                      # nothing before week 1


def test_fewer_than_8_weeks_uses_all_available():
    w = pd.DataFrame({"route": ["X-Y"] * 3, "route_type": ["Short"] * 3,
                      "week_of": pd.to_datetime(["2024-01-01", "2024-01-08", "2024-01-15"]),
                      "cost_per_tonne_km": [1.0, 3.0, 5.0], "total_cost": 1, "tonne_km": 1, "n_shipments": 1})
    out = add_baselines(w, 8)
    assert out.loc[2, "own_history_avg"] == pytest.approx(2.0) and out.loc[2, "history_weeks_used"] == 2


def test_invalid_rows_dropped(tmp_path):
    p = _write(tmp_path, [
        ["a", "A", "B", "Short", 10, 100, 1000, "2024-01-01"],
        ["b", "A", "B", "Short", 0, 100, 1000, "2024-01-01"],        # zero quantity
        ["c", "A", "B", "Short", 10, 100, 1000, "not-a-date"],       # bad date
        ["d", "A", "B", "Bogus", 10, 100, 1000, "2024-01-01"],       # bad route_type
        ["a", "A", "B", "Short", 10, 100, 1000, "2024-01-01"],       # duplicate id
    ])
    assert len(load_shipments(p)) == 1


def test_missing_file_and_missing_columns(tmp_path):
    with pytest.raises(SystemExit):
        load_shipments(tmp_path / "nope.csv")
    bad = tmp_path / "bad.csv"; bad.write_text("x,y\n1,2\n")
    with pytest.raises(SystemExit):
        load_shipments(bad)


def _fact(**kw):
    d = dict(note_id="N9", routes=["A-B"], effect="raises_cost", window_start=pd.Timestamp("2025-01-20"),
             window_end=pd.Timestamp("2025-01-26"), persistence_weeks=None, magnitude_pct=None, explanation="x")
    d.update(kw)
    return NoteFact(**d)


def test_gate_rejects_wrong_route_window_and_no_effect():
    wk = pd.Timestamp("2025-01-20"); end = wk + pd.Timedelta(days=6)
    assert check_note(_fact(), "A-B", wk, end, 20, 3)[0]
    assert not check_note(_fact(), "C-D", wk, end, 20, 3)[0]                       # wrong route
    later = pd.Timestamp("2025-02-10")
    assert not check_note(_fact(), "A-B", later, later + pd.Timedelta(days=6), 20, 3)[0]  # wrong window
    assert not check_note(_fact(effect="no_cost_effect"), "A-B", wk, end, 20, 3)[0]        # says no effect
    assert not check_note(_fact(magnitude_pct=[5, 7]), "A-B", wk, end, 25, 3)[0]           # rise too big
    assert check_note(_fact(magnitude_pct=[5, 7]), "A-B", wk, end, 8, 3)[0]


def test_retrieval_is_deterministic_and_relevant():
    notes = pd.read_csv(Config().notes_path)
    r = NoteRetriever(notes)
    a = r.search(build_query("Chennai-Bangalore"), 3)
    assert a == r.search(build_query("Chennai-Bangalore"), 3)
    assert a[0][0] in {"N001", "N009"}


@pytest.fixture(scope="module")
def result():
    return run(Config())


def test_output_contract(result):
    header = (Config().notes_path.parent / "sample_output_format_v2.csv").read_text().splitlines()[0].split(",")
    assert list(result.columns) == header == OUTPUT_COLUMNS
    assert set(result.flagged) <= {"Yes", "No (justified)"}
    assert (result[result.flagged == "Yes"].matched_note_id == "").all()
    assert (result[result.flagged != "Yes"].matched_note_id != "").all()


def test_sample_rows_reproduced(result):
    s = result[(result.route == "Mumbai-Pune") & (result.week_of == "2025-09-15")].iloc[0]
    assert s.cost_per_tonne_km == "3.98" and s.vs_own_history.startswith("+9.2%") and s.vs_similar_routes.startswith("+23.6%")
    s = result[(result.route == "Delhi-Jaipur") & (result.week_of == "2024-11-11")].iloc[0]
    assert s.cost_per_tonne_km == "4.17" and s.vs_own_history.startswith("+35.5%") and s.vs_similar_routes.startswith("+21.0%")


def test_eval_and_no_fabrication(result):
    ok, total, fails, absent = score(result)
    assert ok == total and not absent
    assert fabrication_audit(result, Config()) == []


def test_ask_answers_from_results_only(tmp_path):
    out = tmp_path / "o.csv"
    run(Config()).to_csv(out, index=False)
    assert "N001" in answer("why did Chennai-Bangalore get pricier in March 2025?", out)
    assert "no flagged" in answer("what happened on Mumbai-Delhi in 2024?", out).lower()
    assert "Please mention" in answer("hello", out)
