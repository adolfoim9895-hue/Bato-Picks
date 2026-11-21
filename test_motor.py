import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from motor import (
    analyze_fixture, classify_competition, completed_before, evidence_status,
    goals_estimate, important_absences, predict_1x2, previous_lineup_counts,
)


def fixture(fid, day, home_id, away_id, a, b, status="FT"):
    return {"fixture": {"id": fid, "date": day, "status": {"short": status}},
            "teams": {"home": {"id": home_id, "name": f"Equipo {home_id}"},
                      "away": {"id": away_id, "name": f"Equipo {away_id}"}},
            "goals": {"home": a, "away": b}, "league": {"name": "Prueba", "type": "League"}}


def test_no_future_leakage():
    before = fixture(1, "2026-11-01T16:00:00+00:00", 1, 2, 2, 0)
    after = fixture(2, "2026-12-01T16:00:00+00:00", 1, 3, 2, 1)
    result = completed_before([after, before], "2026-11-15T16:00:00+00:00")
    assert [x["fixture"]["id"] for x in result] == [1]


def test_probabilities_sum_100():
    p = predict_1x2(1.6, 1.1)
    assert abs(sum(p.values()) - 100) <= 0.15
    assert p["Local"] > p["Visitante"]


def test_status_insufficient():
    status, reason = evidence_status([{}, {}], [{}, {}], [], 0, 0)
    assert status == "APARTADO"


def test_injured_recent_starter_major():
    lineups = [[{"team": {"id": 10}, "startXI": [{"player": {"id": 42, "name": "El 9", "pos": "F"}}]}]
               for _ in range(3)]
    starts, n, names = previous_lineup_counts(lineups, 10)
    injuries = [{"team": {"id": 10}, "player": {"id": 42, "name": "El 9", "type": "Injury"}}]
    result = important_absences(injuries, 10, starts, n, names)
    assert result[0]["Nivel"] == "MUY IMPORTANTE"


def test_old_injury_not_penalized():
    lineups = [[{"team": {"id": 10}, "startXI": [{"player": {"id": 5, "name": "Otro", "pos": "M"}}]}]
               for _ in range(3)]
    starts, n, names = previous_lineup_counts(lineups, 10)
    injuries = [{"team": {"id": 10}, "player": {"id": 42, "name": "El 9", "type": "Injury"}}]
    result = important_absences(injuries, 10, starts, n, names)
    assert result[0]["Nivel"] == "REVISAR"


def test_cup_filter():
    assert classify_competition({"name": "Cup of Nations", "type": "Cup"}) == "COPA / TORNEO"
    assert classify_competition({"name": "Premier League", "type": "League"}) == "LIGA"
    assert classify_competition({"name": "UEFA Nations League", "type": "Cup"}) == "SELECCIÓN OFICIAL"


def test_analyze_full_flow_without_network():
    match = fixture(999, "2026-11-25T16:00:00+00:00", 1, 2, None, None, status="NS")
    games_h = [fixture(x, f"2026-11-{20-x:02d}T16:00:00+00:00", 1, 100+x, 2, 1) for x in range(8)]
    games_a = [fixture(x+100, f"2026-11-{20-x:02d}T16:00:00+00:00", 200+x, 2, 1, 0) for x in range(8)]
    report = analyze_fixture(match, games_h, games_a, [], [], [], [], [])
    assert report["estado"] == "PARCIAL"
    assert report["porcentajes"] is not None
    assert abs(sum(report["porcentajes"][k] for k in ("Local", "Empate", "Visitante")) - 100) < .2
