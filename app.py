"""Bato Picks Analyzer — aplicación Streamlit lista para GitHub/Streamlit Cloud."""
from __future__ import annotations

import csv
import io
import json
import os
import re
import unicodedata
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from motor import analyze_fixture, completed_before
from proveedores import (
    APIError, football, optional_endpoint, fetch_standings,
    get_lineup_history, recent_fixtures, search_pre_match_sources,
    screenshot_matches, narrative,
)

st.set_page_config(page_title="Bato Picks Analyzer", page_icon="⚽", layout="wide")
st.markdown("""
<style>
    .block-container { max-width: 1250px; padding-top: 1.5rem; }
    .hero { padding: 1.5rem; border-radius: 15px; color:#eefcff;
            background: linear-gradient(125deg,#102935,#147b78); margin-bottom: 1.0rem; }
    .hero h1 {margin: 0 0 0.3rem 0; color: white; font-size: 2rem;}
    .hero p {color: #d4f3ef; margin-bottom:0;}
    .warn {padding: .8rem 1rem; border-left: 5px solid #e64f50;
           background: rgba(230,79,80,.12); border-radius: 6px; margin: .4rem 0;}
    .quiet {font-size:.9rem; opacity:.8;}
</style>""", unsafe_allow_html=True)


def secret(key: str) -> str:
    env = os.environ.get(key, "")
    if env:
        return env
    try:
        return str(st.secrets.get(key, ""))
    except Exception:
        return ""


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(x for x in text if not unicodedata.combining(x))
    text = re.sub(r"\b(fc|cf|afc|sc|cd|club|united|football|futbol)\b", " ", text.lower())
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def label_match(game: dict) -> str:
    from motor import parse_date
    start = parse_date(game["fixture"].get("date", "")).astimezone(ZoneInfo("America/Tijuana"))
    return (f"{game['teams']['home']['name']} — {game['teams']['away']['name']}"
            f"   · {game['league']['name']}   · {start.strftime('%H:%M')} Tijuana")


def auto_match(text: str, fixture_pool: list[dict]) -> tuple[int | None, float]:
    chunks = re.split(r"\s+-\s+|\s+vs\.?\s+", text, maxsplit=1, flags=re.IGNORECASE)
    if len(chunks) != 2:
        return None, 0.0
    h, a = [norm(x) for x in chunks]
    if not h or not a:
        return None, 0.0
    best_id, best_score = None, 0.0
    for fixture in fixture_pool:
        x = norm(fixture["teams"]["home"]["name"])
        y = norm(fixture["teams"]["away"]["name"])
        score = 0.5 * SequenceMatcher(None, x, h).ratio() + 0.5 * SequenceMatcher(None, y, a).ratio()
        if score > best_score:
            best_id, best_score = fixture["fixture"]["id"], score
    return (best_id, best_score) if best_score >= 0.73 else (None, best_score)


def demo_report() -> dict:
    """Demostración ficticia y rotulada explícitamente; nunca información deportiva real."""
    anchor = datetime.now(ZoneInfo("America/Tijuana")) + timedelta(days=4)
    kickoff = anchor.isoformat()
    team_h = {"id": 101, "name": "Atlético Ejemplo"}
    team_a = {"id": 202, "name": "Deportivo Ficticio"}
    fixture = {"fixture": {"id": 0, "date": kickoff, "status": {"short": "NS"}},
               "teams": {"home": team_h, "away": team_a},
               "league": {"name": "Liga Ficticia (demostración)", "type": "League"}}

    def past(team: dict, gf_list: list[int], ga_list: list[int], own_home: bool) -> list:
        result = []
        for i, (gf, ga) in enumerate(zip(gf_list, ga_list)):
            rival = {"id": 400 + i, "name": f"Rival inventado {i+1}"}
            home, away = (team, rival) if (i % 2 == 0) == own_home else (rival, team)
            own_is_home = home["id"] == team["id"]
            result.append({"fixture": {"id": 1000 + team["id"] * 10 + i,
                                           "date": (anchor - timedelta(days=(i + 1) * 7)).isoformat(),
                                           "status": {"short": "FT"}},
                           "teams": {"home": home, "away": away},
                           "goals": {"home": gf if own_is_home else ga,
                                     "away": ga if own_is_home else gf}})
        return result

    h_recent = past(team_h, [3, 2, 1, 2, 3, 1, 4, 2], [0, 1, 0, 1, 2, 1, 0, 0], True)
    a_recent = past(team_a, [0, 1, 1, 0, 2, 1, 0, 1], [2, 3, 1, 2, 3, 2, 1, 2], False)
    lineup_hist = []
    for _ in range(3):
        lineup_hist.append([{"team": team_h, "startXI": [
            {"player": {"id": 100 + i, "name": f"Titular ficticio {i+1}", "pos": "F" if i == 9 else "M"}}
            for i in range(11)]}])
    injuries = [{"team": team_h, "player": {"id": 109, "name": "Titular ficticio 10",
                                                  "type": "Injury", "reason": "Ejemplo inventado"}}]
    report = analyze_fixture(fixture, h_recent, a_recent, [], injuries, [], lineup_hist, [], {}, [])
    report["ejemplo"] = True
    return report


def run_analysis(game: dict, sports_key: str, search_key: str, history_count: int, news: bool) -> dict:
    fid = game["fixture"]["id"]
    hid = game["teams"]["home"]["id"]
    aid = game["teams"]["away"]["id"]
    kickoff = game["fixture"]["date"]
    season = game["league"]["season"]
home = recent_fixtures(hid, kickoff, sports_key, season)
away = recent_fixtures(aid, kickoff, sports_key, season)
h2h = optional_endpoint("fixtures/headtohead", sports_key, h2h=f"{hid}-{aid}", last=10)
    injured = optional_endpoint("injuries", sports_key, fixture=fid)
    lineups = optional_endpoint("fixtures/lineups", sports_key, fixture=fid)
    history_home = get_lineup_history(hid, completed_before(home, kickoff, 4), sports_key, count=history_count)
    history_away = get_lineup_history(aid, completed_before(away, kickoff, 4), sports_key, count=history_count)
    league = game.get("league", {})
    ranks = fetch_standings(league.get("id", 0), league.get("season", 2026), sports_key)
    sources = search_pre_match_sources(game["teams"]["home"]["name"],
                                       game["teams"]["away"]["name"],
                                       kickoff[:10], search_key) if news else []
    report = analyze_fixture(game, home, away, h2h, injured, lineups,
                             history_home, history_away, ranks, sources)
    report["ejemplo"] = False
    return report


def render_report(r: dict, ai_key: str, model: str) -> None:
    st.subheader(f"{r['local']}  vs  {r['visitante']}")
    st.caption(f"{r['liga']} · {r['fecha'][:16]} · análisis previo")
    if r.get("ejemplo"):
        st.error("MODO PRUEBA: todos los equipos, resultados, lesiones y cálculos de este ejemplo son FICTICIOS.")
    state_color = {"VERIFICADO": "green", "PARCIAL": "orange", "APARTADO": "red"}
    st.markdown(f":{state_color.get(r['estado'], 'gray')}[**{r['estado']}**] — {r['razon_estado']}")
    for warning in r["alertas"]:
        st.markdown(f'<div class="warn"><strong>{warning}</strong></div>', unsafe_allow_html=True)
    pred = r["porcentajes"]
    if not pred:
        st.warning("✳ APARTADO: sin muestra suficiente. No se calcula ningún porcentaje.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Gana local", f"{pred['Local']:.1f}%")
        c2.metric("Empate", f"{pred['Empate']:.1f}%")
        c3.metric("Gana visita", f"{pred['Visitante']:.1f}%")
        st.progress(max(0.0, min(1.0, pred["Local"] / 100)), text="Estimación heurística de victoria local")
        st.caption(f"Goles esperados estimados: {pred['goles_esperados_local']} – {pred['goles_esperados_visitante']}. "
                   "Modelo Poisson simplificado, NO entrenado ni calibrado; no son probabilidades garantizadas.")
        if r["ajustes_modelo"]:
            st.info("Ajustes transparentes por ausencias de titulares recientes: " + " · ".join(r["ajustes_modelo"]))
    col_a, col_b = st.columns(2)
    for col, title, rows, summary, injuries, rotation in [
        (col_a, r["local"], r["ultimos_local"], r["resumen_local"], r["bajas_local"], r["rotacion_local"]),
        (col_b, r["visitante"], r["ultimos_visitante"], r["resumen_visitante"], r["bajas_visitante"], r["rotacion_visitante"]),
    ]:
        with col:
            st.markdown(f"**{title} — últimos {summary['n']} partidos**")
            st.write(f"{summary['victorias']} victorias · {summary['empates']} empates · {summary['derrotas']} derrotas")
            st.write(f"Goles: {summary['gf']} a favor / {summary['gc']} en contra")
            if rows:
                cols = ["Fecha", "Rival", "Sede", "Resultado", "V/E/D", "Ranking rival"]
                st.dataframe(pd.DataFrame(rows)[cols], hide_index=True, use_container_width=True)
            if injuries:
                st.markdown("**Lesiones / suspensiones reportadas por proveedor**")
                st.dataframe(pd.DataFrame(injuries)[["Jugador", "Tipo", "Motivo reportado", "Inicios observados", "Nivel"]],
                             hide_index=True, use_container_width=True)
            else:
                st.caption("Sin registros de bajas del proveedor; NO garantiza plantel completo.")
            st.caption(rotation.get("texto", "Rotación pendiente"))
    with st.expander("Enfrentamientos directos anteriores y fuentes"):
        if r["enfrentamientos"]:
            st.dataframe(pd.DataFrame(r["enfrentamientos"]), hide_index=True, use_container_width=True)
        else:
            st.write("No se encontraron enfrentamientos anteriores confiables antes de la fecha.")
        st.write("Datos deportivos: API-Football (API-Sports). Las fuentes de noticias no sustituyen los partes oficiales.")
        for item in r["fuentes"]:
            st.markdown(f"- [{item['title']}]({item['url']}) — {item['domain']} — {item['published']}")
        if not r["fuentes"]:
            st.caption("Sin enlaces externos corroborados; activar Tavily para buscar prensa y federaciones.")
    if ai_key and not r.get("ejemplo"):
        if st.button("✍️ Redactar análisis narrativo con IA", key=f"ai-{r['id']}"):
            with st.spinner("Redactando con base en los datos obtenidos..."):
                try:
                    st.markdown(narrative(r, ai_key, model))
                except APIError as exc:
                    st.error(str(exc))
    st.divider()


st.markdown('''<div class="hero"><h1>⚽ Bato Picks Analyzer</h1>
<p>Datos verificables · rivales recientes · titulares · alertas · pronósticos orientativos</p></div>''',
            unsafe_allow_html=True)
st.caption("La información del proveedor puede tener cobertura incompleta. Nunca confundir ausencia de noticias con ausencia de lesiones.")

sports_key = secret("API_FOOTBALL_KEY")
search_key = secret("TAVILY_API_KEY")
ai_key = secret("OPENAI_API_KEY")

with st.sidebar:
    st.header("Configuración")
    st.write("API-Football:", "✅ Conectada" if sports_key else "❌ Sin clave")
    st.write("Noticias Tavily:", "✅ Conectado" if search_key else "⚪ Opcional")
    st.write("OpenAI (capturas y redacción):", "✅ Conectado" if ai_key else "⚪ Opcional")
    model = st.text_input("Modelo OpenAI", value="gpt-4.1-mini")
    hcount = st.slider("Partidos previos para comparar titulares", 0, 3, 2,
                       help="Más partidos = mejores alertas, pero más llamadas a la API")
    news = st.checkbox("Buscar noticias de fuentes fiables", value=bool(search_key), disabled=not search_key)
    exclude_cups = st.checkbox("Ocultar copas y amistosos (no excluye selecciones oficiales)", value=True)
    st.info("Con el plan gratuito de API-Football suele haber 100 solicitudes al día; analiza máximo cinco encuentros por tanda para administrar el límite.")
    st.caption("No subir claves a GitHub. Añadirlas en los secretos de Streamlit Cloud.")

mode = st.radio("Modo", ["Partidos reales", "Demostración ficticia"], horizontal=True)
if mode == "Demostración ficticia":
    render_report(demo_report(), "", model)
    st.stop()

if not sports_key:
    st.warning("Para consultar partidos reales falta configurar API_FOOTBALL_KEY. Puedes probar primero «Demostración ficticia».")
    with st.expander("¿Dónde se configura?"):
        st.code('API_FOOTBALL_KEY = "TU_CLAVE"\n# Opcionales:\nTAVILY_API_KEY = "TU_CLAVE"\nOPENAI_API_KEY = "TU_CLAVE"', language="toml")
    st.stop()

current = datetime.now(ZoneInfo("America/Tijuana")).date()
choice_day = st.date_input("Fecha de los partidos (hora de Tijuana)", value=current,
                           min_value=current - timedelta(days=365),
                           max_value=current + timedelta(days=180))
if choice_day < current:
    st.warning("Fecha pasada: el análisis usa únicamente partidos anteriores a cada encuentro, pero los partes de lesiones actuales podrían no representar el pasado. No usar como evaluación retrospectiva exacta.")

st.markdown("#### 1. Buscar partidos")
if st.button("🔎 Cargar partidos de la fecha", type="primary"):
    with st.spinner("Consultando calendario..."):
        try:
            items = football("fixtures", sports_key, date=choice_day.isoformat(), timezone="America/Tijuana")
            st.session_state["fixtures_day"] = items
            st.session_state["loaded_day"] = choice_day.isoformat()
        except APIError as exc:
            st.error(str(exc))

pool = st.session_state.get("fixtures_day", []) if st.session_state.get("loaded_day") == choice_day.isoformat() else []
if pool:
    st.caption(f"{len(pool)} partidos disponibles en el proveedor para la fecha.")
    if exclude_cups:
        from motor import classify_competition
        pool = [f for f in pool if classify_competition(f.get("league", {})) in {"LIGA", "SELECCIÓN OFICIAL"}]
    uploaded = st.file_uploader("Opcional: captura de tus partidos (JPG/PNG, requiere OpenAI)", type=["png", "jpg", "jpeg", "webp"])
    if uploaded is not None:
        if not ai_key:
            st.info("Para leer automáticamente la captura configura OPENAI_API_KEY. También puedes escribir los partidos abajo.")
        elif st.button("📷 Extraer partidos de la captura con IA"):
            try:
                st.session_state["extracted"] = screenshot_matches(uploaded.getvalue(),
                                                                     uploaded.type, ai_key, model)
            except APIError as exc:
                st.error(str(exc))
    lines = st.text_area("Opcional: uno por línea, en formato 'Local - Visitante'",
                         value="\n".join(st.session_state.get("extracted", [])), height=95)
    preliminary = []
    unmatched = []
    for line in [x.strip() for x in lines.splitlines() if x.strip()]:
        fid, match_score = auto_match(line, pool)
        if fid:
            preliminary.append(fid)
        else:
            unmatched.append(f"{line} (coincidencia insuficiente)")
    if unmatched:
        st.warning("✳ Sin coincidencia exacta en el calendario: " + "; ".join(unmatched))
    q = norm(st.text_input("Filtrar lista por equipo o liga"))
    filtered = [p for p in pool if not q or q in norm(label_match(p))]
    filtered = filtered[:400]
    lookup = {f["fixture"]["id"]: f for f in pool}
    options = [p["fixture"]["id"] for p in filtered]
    for fid in preliminary:
        if fid in lookup and fid not in options:
            options.insert(0, fid)
    default = [x for x in preliminary if x in options]
    selected = st.multiselect("Elige partidos (máximo 5 por tanda)", options, default=default,
                              format_func=lambda x: label_match(lookup[x]),
                              max_selections=5)
    if st.button("📊 Analizar seleccionados", type="primary", disabled=not selected):
        result = []
        for index, fid in enumerate(selected, 1):
            with st.spinner(f"Analizando {index}/{len(selected)}: {label_match(lookup[fid])}..."):
                try:
                    report = run_analysis(lookup[fid], sports_key, search_key, hcount, news)
                    result.append(report)
                except APIError as exc:
                    st.error(f"{label_match(lookup[fid])}: {exc}")
        st.session_state["reports"] = result
        st.session_state["report_day"] = choice_day.isoformat()

reports = st.session_state.get("reports", []) if st.session_state.get("report_day") == choice_day.isoformat() else []
if reports:
    st.markdown("---")
    st.header("2. Resultados de los análisis")
    brief = []
    for r in reports:
        p = r["porcentajes"] or {}
        brief.append({"Partido": f"{r['local']} - {r['visitante']}",
                      "Estado": r["estado"], "Local %": p.get("Local"),
                      "Empate %": p.get("Empate"), "Visita %": p.get("Visitante"),
                      "Alertas importantes": sum("MUY IMPORTANTE" in w for w in r["alertas"])})
    st.dataframe(pd.DataFrame(brief), hide_index=True, use_container_width=True)
    a, b = st.columns(2)
    a.download_button("⬇ Descargar resumen CSV", pd.DataFrame(brief).to_csv(index=False).encode("utf-8-sig"),
                      file_name="bato_picks_resumen.csv", mime="text/csv")
    b.download_button("⬇ Descargar análisis JSON", json.dumps(reports, ensure_ascii=False, indent=2, default=str),
                      file_name="bato_picks_analisis.json", mime="application/json")
    st.markdown("**APARTADOS:**")
    excluded = [r for r in reports if r["estado"] == "APARTADO"]
    st.write(", ".join(f"✳ {r['local']} - {r['visitante']}" for r in excluded) if excluded else "Ninguno por falta de datos mínimos.")
    for report in reports:
        render_report(report, ai_key, model)

st.caption("Herramienta de exploración deportiva. No garantiza aciertos, no automatiza apuestas y no usa cuotas para sus estimaciones.")
