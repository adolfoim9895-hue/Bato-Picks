"""Conectores de datos. Las claves permanecen en el servidor (Streamlit secrets)."""
from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta
from urllib.parse import urlparse

import requests
import streamlit as st

API = "https://v3.football.api-sports.io"
TIMEOUT = 18


class APIError(Exception):
    pass


@st.cache_data(ttl=900, show_spinner=False)
def api_football(endpoint: str, args: tuple[tuple[str, str], ...], key: str) -> list[dict]:
    if not key:
        raise APIError("Falta la clave API_FOOTBALL_KEY")
    try:
        resp = requests.get(f"{API}/{endpoint.lstrip('/')}",
                            params=dict(args), headers={"x-apisports-key": key}, timeout=TIMEOUT)
        if resp.status_code == 429:
            raise APIError("Límite de solicitudes de API-Football. No repetir inmediatamente.")
        resp.raise_for_status()
        doc = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise APIError(f"No se pudo consultar API-Football: {str(exc)[:180]}") from exc
    if doc.get("errors"):
        raise APIError(f"API-Football: {str(doc['errors'])[:240]}")
    return doc.get("response") or []


def football(endpoint: str, key: str, **kwargs) -> list[dict]:
    args = tuple(sorted((k, str(v)) for k, v in kwargs.items() if v is not None))
    return api_football(endpoint, args, key)


    def recent_fixtures(team_id: int, kickoff: str, key: str, season: int) -> list:
    # Intervalo anterior a la fecha del partido: evita usar información del futuro.
    match_day = datetime.fromisoformat(kickoff.replace("Z", "+00:00")).date()
    return football("fixtures", key, team=team_id, season=season,
                    **{"from": (match_day - timedelta(days=240)).isoformat(),
                       "to": (match_day - timedelta(days=1)).isoformat()})


def fetch_standings(league_id: int, season: int, key: str) -> dict[int, int]:
    try:
        raw = football("standings", key, league=league_id, season=season)
        ranks = {}
        for league_obj in raw:
            for group in league_obj.get("league", {}).get("standings", []):
                for club in group:
                    tid = club.get("team", {}).get("id")
                    if tid and club.get("rank"):
                        ranks[tid] = club["rank"]
        return ranks
    except APIError:
        return {}


def optional_endpoint(endpoint: str, key: str, **kwargs) -> list[dict]:
    try:
        return football(endpoint, key, **kwargs)
    except APIError:
        return []


def get_lineup_history(team_id: int, past: list[dict], key: str, count: int = 3) -> list[list[dict]]:
    history = []
    for match in past[:count]:
        fid = match.get("fixture", {}).get("id")
        if fid:
            history.append(optional_endpoint("fixtures/lineups", key, fixture=fid))
    return history


GOOD_DOMAINS = (
    "uefa.com", "fifa.com", "concacaf.com", "cafonline.com", "the-afc.com",
    "premierleague.com", "bundesliga.com", "laliga.com", "ligamx.net", "ligafemenil.mx",
    "thefa.com", "efl.com", "rfef.es", "futbolperuano.com", "espn.com",
    "bbc.com", "skysports.com", "reuters.com", "apnews.com", "tudn.com",
    "record.com.mx", "as.com", "marca.com", "football-italia.net", "theguardian.com",
    "kicker.de", "transfermarkt.com", "transfermarkt.mx", "transfermarkt.es",
)


def trusted_domain(link: str) -> str | None:
    host = urlparse(link).netloc.lower().removeprefix("www.")
    if not host or not link.startswith("https://"):
        return None
    if any(host == d or host.endswith("." + d) for d in GOOD_DOMAINS):
        return host
    return None


@st.cache_data(ttl=3600, show_spinner=False)
def search_pre_match_sources(home: str, away: str, match_day: str, tavily_key: str) -> list[dict]:
    """Búsqueda opcional; devuelve enlaces con dominios conocidos, NO valida por sí sola una baja."""
    if not tavily_key:
        return []
    query = f'"{home}" "{away}" previa bajas lesionados alineaciones {match_day}'
    try:
        response = requests.post("https://api.tavily.com/search", json={
            "api_key": tavily_key, "query": query, "search_depth": "basic",
            "max_results": 8, "include_answer": False, "include_raw_content": False,
        }, timeout=TIMEOUT)
        response.raise_for_status()
        results = response.json().get("results", [])
    except (requests.RequestException, ValueError):
        return []
    good = []
    for item in results:
        url = item.get("url", "")
        domain = trusted_domain(url)
        if not domain:
            continue
        # Rechaza artículos inequívocamente posteriores al partido.
        published = str(item.get("published_date", ""))[:10]
        if published and published > match_day:
            continue
        good.append({"title": item.get("title", domain), "url": url,
                     "summary": item.get("content", "")[:280], "domain": domain,
                     "published": published or "Fecha sin verificar"})
    return good


def openai_responses(api_key: str, instructions: str, user_content: list, model: str) -> str:
    if not api_key:
        raise APIError("Falta OPENAI_API_KEY")
    request = {
        "model": model,
        "instructions": instructions,
        "input": [{"role": "user", "content": user_content}],
        "max_output_tokens": 1300,
    }
    try:
        response = requests.post("https://api.openai.com/v1/responses", json=request,
                                 headers={"Authorization": f"Bearer {api_key}",
                                          "Content-Type": "application/json"}, timeout=45)
        response.raise_for_status()
        doc = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise APIError(f"No se pudo completar el análisis con IA: {str(exc)[:250]}") from exc
    parts = []
    for o in doc.get("output", []):
        for c in o.get("content", []):
            if c.get("type") == "output_text":
                parts.append(c.get("text", ""))
    return "\n".join(parts).strip() or "La IA no devolvió texto."


def screenshot_matches(data: bytes, mime: str, key: str, model: str) -> list[str]:
    if len(data) > 4_000_000:
        raise APIError("La imagen supera el máximo de 4 MB de este prototipo.")
    if mime not in {"image/jpeg", "image/png", "image/webp"}:
        raise APIError("Se aceptan imágenes PNG, JPG o WEBP.")
    image_url = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    content = [
        {"type": "input_text", "text": "Extrae únicamente partidos de fútbol visibles. Devuelve SOLO JSON válido con forma {\"partidos\":[\"Local - Visitante\"]}. No inventes nombres ni partidos. Omite momios, fechas y marcadores."},
        {"type": "input_image", "image_url": image_url},
    ]
    response = openai_responses(key, "Extrae datos textuales de una captura; ante dudas omite, no completes nombres por intuición.", content, model)
    try:
        text = response.strip().removeprefix("```json").removesuffix("```").strip()
        data = json.loads(text)
        return [str(x).strip() for x in data.get("partidos", []) if " - " in str(x)][:40]
    except (json.JSONDecodeError, AttributeError):
        raise APIError("La IA no devolvió una lista de partidos en formato válido.")


def narrative(report: dict, key: str, model: str) -> str:
    essential = {
        "equipo_local": report["local"], "equipo_visitante": report["visitante"],
        "competicion": report["liga"], "estado_fuentes": report["estado"],
        "partidos_local": report["ultimos_local"],
        "partidos_visitante": report["ultimos_visitante"],
        "h2h": report["enfrentamientos"], "bajas_local": report["bajas_local"],
        "bajas_visitante": report["bajas_visitante"],
        "rotaciones": [report["rotacion_local"], report["rotacion_visitante"]],
        "estimaciones_modelo_no_calibrado": report["porcentajes"],
        "fuentes_externas": report["fuentes"],
    }
    prompt = (
        "Eres un analista deportivo crítico. Español claro. SOLO hechos presentes en el JSON y sus fuentes. "
        "Separar HECHOS de INTERPRETACIÓN. No consultar cuotas, no inventar lesiones, lesiones confirmadas "
        "solo si hay artículo verificable; si solo API, decir 'reportado por proveedor'. "
        "No presentar dos enlaces como confirmación de un dato si no lo respaldan. "
        "Distingue rivales fuertes cuando consta ranking, local/visita, historial. "
        "Pon 'ADVERTENCIA MUY IMPORTANTE' si hay titular reciente lesionado o >=3 rotaciones. "
        "Explica que la estimación es heurística no calibrada y no es consejo financiero. "
        "Si el estado es APARTADO, no inventes porcentaje. Respuesta máximo 450 palabras."
    )
    return openai_responses(key, prompt, [{"type": "input_text", "text": json.dumps(essential, ensure_ascii=False, default=str)}], model)
