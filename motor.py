"""Motor explicable de análisis deportivo. No hace promesas de rentabilidad."""
from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timezone
from typing import Any

FINAL = {"FT", "AET", "PEN", "AWD"}
AMISTOSOS = ("friendly", "friendlies", "amistos")
COPAS = ("cup", "copa", "coupe", "pokal", "coppa", "taça", "taca", "trophy")


def parse_date(raw: str) -> datetime:
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def is_before_match(fixture: dict, target: datetime) -> bool:
    dt = parse_date(fixture.get("fixture", {}).get("date", ""))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    return dt < target


def completed_before(fixtures: list[dict], kickoff: str, limit: int = 10) -> list[dict]:
    target = parse_date(kickoff)
    cleaned = [
        f for f in fixtures
        if f.get("fixture", {}).get("status", {}).get("short") in FINAL
        and is_before_match(f, target)
        and f.get("goals", {}).get("home") is not None
        and f.get("goals", {}).get("away") is not None
    ]
    return sorted(cleaned, key=lambda f: parse_date(f["fixture"]["date"]), reverse=True)[:limit]


def previous_lineup_counts(lineup_responses: list[list[dict]], team_id: int) -> tuple[Counter, int, dict]:
    starters = Counter()
    names: dict[int, dict] = {}
    n = 0
    for responses in lineup_responses:
        match_lineup = next((x for x in responses if x.get("team", {}).get("id") == team_id), None)
        if not match_lineup or not match_lineup.get("startXI"):
            continue
        n += 1
        for entry in match_lineup["startXI"]:
            player = entry.get("player", {})
            pid = player.get("id")
            if pid is not None:
                starters[pid] += 1
                names[pid] = {"nombre": player.get("name", ""), "pos": player.get("pos", "")}
    return starters, n, names


def classify_competition(league: dict) -> str:
    league_name = str(league.get("name", "")).lower()
    if any(token in league_name for token in AMISTOSOS):
        return "AMISTOSO"
    # Torneos oficiales de selecciones no son equivalentes a copas de clubes con rotaciones.
    international_official = ("nations league", "world cup", "qualif", "clasific", "africa cup",
                              "asian cup", "european championship", "euro qualification", "gold cup")
    if any(token in league_name for token in international_official):
        return "SELECCIÓN OFICIAL"
    if any(token in league_name for token in COPAS) or str(league.get("type", "")).lower() == "cup":
        return "COPA / TORNEO"
    return "LIGA"


def recent_rows(fixtures: list[dict], team_id: int, ranks: dict[int, int] | None = None) -> list[dict]:
    rows = []
    ranks = ranks or {}
    for f in fixtures:
        home = f.get("teams", {}).get("home", {})
        away = f.get("teams", {}).get("away", {})
        if team_id not in (home.get("id"), away.get("id")):
            continue
        is_home = home.get("id") == team_id
        own, rival = (home, away) if is_home else (away, home)
        own_goals = f["goals"]["home" if is_home else "away"]
        opp_goals = f["goals"]["away" if is_home else "home"]
        outcome = "V" if own_goals > opp_goals else "D" if own_goals < opp_goals else "E"
        rows.append({
            "Fecha": f.get("fixture", {}).get("date", "")[:10],
            "Rival": rival.get("name", "?"),
            "Sede": "Local" if is_home else "Visita",
            "Resultado": f"{own_goals}-{opp_goals}",
            "V/E/D": outcome,
            "Ranking rival": ranks.get(rival.get("id")),
            "Goles a favor": int(own_goals),
            "Goles en contra": int(opp_goals),
        })
    return rows


def summarize(rows: list[dict]) -> dict:
    return {
        "n": len(rows),
        "victorias": sum(r["V/E/D"] == "V" for r in rows),
        "empates": sum(r["V/E/D"] == "E" for r in rows),
        "derrotas": sum(r["V/E/D"] == "D" for r in rows),
        "gf": sum(r["Goles a favor"] for r in rows),
        "gc": sum(r["Goles en contra"] for r in rows),
        "rivales_top": sum(isinstance(r.get("Ranking rival"), int) and r["Ranking rival"] <= 6 for r in rows),
    }


def avg(values: list[float], default: float) -> float:
    return sum(values) / len(values) if values else default


def goals_estimate(home_rows: list[dict], away_rows: list[dict]) -> tuple[float, float]:
    """Heurística transparente, ajustada a tamaño de muestra y sede; NO calibrada."""
    if len(home_rows) < 3 or len(away_rows) < 3:
        raise ValueError("Se requieren al menos 3 partidos anteriores por equipo")
    home_only = [r for r in home_rows if r["Sede"] == "Local"]
    away_only = [r for r in away_rows if r["Sede"] == "Visita"]
    # Promedios globales de 8 partidos y submuestras de sede, con menor peso si hay pocos.
    h_gf = avg([r["Goles a favor"] for r in home_rows], 1.30)
    h_gc = avg([r["Goles en contra"] for r in home_rows], 1.20)
    a_gf = avg([r["Goles a favor"] for r in away_rows], 1.15)
    a_gc = avg([r["Goles en contra"] for r in away_rows], 1.35)
    wh = min(len(home_only) / 6, 0.45)
    wa = min(len(away_only) / 6, 0.45)
    h_gf = (1 - wh) * h_gf + wh * avg([r["Goles a favor"] for r in home_only], h_gf)
    h_gc = (1 - wh) * h_gc + wh * avg([r["Goles en contra"] for r in home_only], h_gc)
    a_gf = (1 - wa) * a_gf + wa * avg([r["Goles a favor"] for r in away_only], a_gf)
    a_gc = (1 - wa) * a_gc + wa * avg([r["Goles en contra"] for r in away_only], a_gc)
    shrink = min(min(len(home_rows), len(away_rows)) / 9, 1.0)
    goal_h = shrink * (0.55 * h_gf + 0.45 * a_gc + 0.16) + (1 - shrink) * 1.45
    goal_a = shrink * (0.55 * a_gf + 0.45 * h_gc - 0.08) + (1 - shrink) * 1.16
    return max(0.35, min(goal_h, 3.5)), max(0.35, min(goal_a, 3.5))


def prob_poisson(mu: float, goals: int) -> float:
    return math.exp(-mu) * mu**goals / math.factorial(goals)


def predict_1x2(mu_home: float, mu_away: float) -> dict:
    # Distribución hasta 12 goles por lado; normalizamos residual numérico.
    result = {"Local": 0.0, "Empate": 0.0, "Visitante": 0.0}
    for a in range(13):
        for b in range(13):
            p = prob_poisson(mu_home, a) * prob_poisson(mu_away, b)
            outcome = "Local" if a > b else "Empate" if a == b else "Visitante"
            result[outcome] += p
    total = sum(result.values())
    return {k: round(v / total * 100, 1) for k, v in result.items()}


def important_absences(injuries: list[dict], team_id: int, starts: Counter, n: int, names: dict) -> list[dict]:
    # API injuries refiere información del proveedor, no prueba que la ausencia sea oficial.
    result = []
    seen = set()
    for entry in injuries:
        team = entry.get("team") or {}
        if team.get("id") != team_id:
            continue
        player = entry.get("player") or {}
        pid = player.get("id")
        if pid in seen:
            continue
        seen.add(pid)
        appearances = starts.get(pid, 0)
        # 2 de 3 => evidencia de titularidad habitual, 1=> titular reciente, 0=> sin prueba.
        doubt = any(t in str(player.get("type", "")).lower() for t in ("question", "doubt", "uncertain"))
        priority = "MUY IMPORTANTE (EN DUDA)" if doubt and n >= 2 and appearances >= 2 else (
            "MUY IMPORTANTE" if n >= 2 and appearances >= 2 else "REVISAR")
        result.append({
            "Jugador": player.get("name", "Sin nombre"),
            "Motivo reportado": player.get("reason") or entry.get("fixture", {}).get("status", {}).get("long") or "No especificado",
            "Tipo": player.get("type", "Baja reportada"),
            "Inicios observados": f"{appearances}/{n}" if n else "Sin historial",
            "Posición": names.get(pid, {}).get("pos", "No verificada"),
            "Nivel": priority,
            "titular_reciente": bool(not doubt and n >= 2 and appearances >= 2),
            "id": pid,
        })
    return result


def rotation_report(current_lineups: list[dict], team_id: int, historical: Counter, sample_n: int) -> dict:
    lineup = next((l for l in current_lineups if l.get("team", {}).get("id") == team_id), None)
    if not lineup or not lineup.get("startXI"):
        return {"disponible": False, "texto": "Once oficial todavía no publicado por el proveedor"}
    current_ids = {x.get("player", {}).get("id") for x in lineup["startXI"]}
    habitual = {pid for pid, c in historical.items() if sample_n >= 2 and c >= 2}
    missing = habitual - current_ids
    return {
        "disponible": True,
        "jugadores_once": len(current_ids),
        "habituales_identificados": len(habitual),
        "habituales_fuera_once": len(missing),
        "ids_fuera": missing,
        "texto": f"{len(missing)} habituales fuera de los 11 (comparado con {sample_n} partidos previos)",
    }


def injury_adjustment(mu_home: float, mu_away: float, h_abs: list, a_abs: list) -> tuple[float, float, list[str]]:
    """Penalización conservadora SOLO para bajas que jugaron >=2/3 partidos previos.
    No se penalizan otra vez lesiones antiguas ausentes de esas alineaciones.
    """
    adjustments = []
    for absences, own in [(h_abs, "local"), (a_abs, "visitante")]:
        own_effect = 0.0
        opp_effect = 0.0
        for player in absences:
            if not player["titular_reciente"]:
                continue
            pos = player.get("Posición")
            if pos == "F":
                own_effect += 0.12
            elif pos == "M":
                own_effect += 0.07
                opp_effect += 0.03
            elif pos in {"G", "D"}:
                opp_effect += 0.10
            else:
                own_effect += 0.05
        own_effect = min(own_effect, 0.35)
        opp_effect = min(opp_effect, 0.30)
        if own == "local":
            mu_home -= own_effect
            mu_away += opp_effect
        else:
            mu_away -= own_effect
            mu_home += opp_effect
        if own_effect or opp_effect:
            adjustments.append(f"{own.capitalize()}: ataque -{own_effect:.2f}, rival +{opp_effect:.2f} goles esperados por bajas recientes (supuesto heurístico)")
    return max(mu_home, 0.3), max(mu_away, 0.3), adjustments


def evidence_status(h_rows: list, a_rows: list, source_links: list, h_lineups_n: int, a_lineups_n: int) -> tuple[str, str]:
    if min(len(h_rows), len(a_rows)) < 3:
        return "APARTADO", "Menos de 3 partidos anteriores por equipo: base insuficiente"
    domains = {x.get("domain") for x in source_links if x.get("domain")}
    if min(len(h_rows), len(a_rows)) >= 5 and len(domains) >= 2 and min(h_lineups_n, a_lineups_n) >= 2:
        return "VERIFICADO", "Resultados + historial de titulares + dos fuentes externas identificadas"
    return "PARCIAL", "Estadísticas disponibles, pero falta corroboración independiente y/o historial suficiente de alineaciones"


def analyze_fixture(fixture: dict, home_raw: list, away_raw: list, h2h_raw: list,
                    injuries: list, current_lineups: list, home_history_lineups: list,
                    away_history_lineups: list, ranks: dict[int, int] | None = None,
                    sources: list | None = None) -> dict:
    info = fixture.get("fixture", {})
    kickoff = info.get("date", "")
    teams = fixture["teams"]
    hid, aid = teams["home"]["id"], teams["away"]["id"]
    hfix = completed_before(home_raw, kickoff, limit=9)
    afix = completed_before(away_raw, kickoff, limit=9)
    hrows, arows = recent_rows(hfix, hid, ranks), recent_rows(afix, aid, ranks)
    hstart, hn, hnames = previous_lineup_counts(home_history_lineups, hid)
    astart, an, anames = previous_lineup_counts(away_history_lineups, aid)
    h_abs = important_absences(injuries, hid, hstart, hn, hnames)
    a_abs = important_absences(injuries, aid, astart, an, anames)
    hrot = rotation_report(current_lineups, hid, hstart, hn)
    arot = rotation_report(current_lineups, aid, astart, an)
    sources = sources or []
    status, reason = evidence_status(hrows, arows, sources, hn, an)
    h2h = [x for x in completed_before(h2h_raw, kickoff, limit=5)]
    pred, adjustments = None, []
    if status != "APARTADO":
        mu_h, mu_a = goals_estimate(hrows, arows)
        mu_h, mu_a, adjustments = injury_adjustment(mu_h, mu_a, h_abs, a_abs)
        pred = predict_1x2(mu_h, mu_a)
        pred["goles_esperados_local"] = round(mu_h, 2)
        pred["goles_esperados_visitante"] = round(mu_a, 2)
    warnings = []
    for team_name, lst, rot in [(teams["home"]["name"], h_abs, hrot), (teams["away"]["name"], a_abs, arot)]:
        major = [i["Jugador"] + (" (en duda)" if "EN DUDA" in i["Nivel"] else "")
                 for i in lst if i["Nivel"].startswith("MUY IMPORTANTE")]
        if major:
            warnings.append(f"ADVERTENCIA MUY IMPORTANTE — {team_name}: bajas reportadas de titulares recientes ({', '.join(major)})")
        if rot.get("disponible") and rot.get("habituales_fuera_once", 0) >= 3:
            warnings.append(f"ADVERTENCIA MUY IMPORTANTE — {team_name}: {rot['habituales_fuera_once']} titulares habituales fuera del once")
    comp_type = classify_competition(fixture.get("league", {}))
    if comp_type in {"AMISTOSO", "COPA / TORNEO"}:
        warnings.append(f"ADVERTENCIA — Tipo de competición: {comp_type}; revisar motivación y posibles rotaciones")
    if not current_lineups:
        warnings.append("Alineación oficial no disponible: las rotaciones aún no están verificadas")
    return {
        "id": info.get("id"), "fecha": kickoff,
        "local": teams["home"]["name"], "visitante": teams["away"]["name"],
        "liga": fixture.get("league", {}).get("name", ""), "tipo": comp_type,
        "estado": status, "razon_estado": reason,
        "ultimos_local": hrows, "ultimos_visitante": arows,
        "resumen_local": summarize(hrows), "resumen_visitante": summarize(arows),
        "enfrentamientos": recent_rows(h2h, hid),
        "bajas_local": h_abs, "bajas_visitante": a_abs,
        "rotacion_local": hrot, "rotacion_visitante": arot,
        "alertas": warnings, "porcentajes": pred,
        "ajustes_modelo": adjustments,
        "fuentes": sources,
    }
