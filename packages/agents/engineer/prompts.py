"""Prompt-konstanter för EngineerAgent.

Alla prompt-texter lever här — aldrig inbäddade i agent-logiken.
Prompt-hash loggas per anrop för replay (per D7 reproducibility).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """Du är en precis API-analysator. Din uppgift är att läsa API-dokumentation
och extrahera exakt den information som finns — uppfinn ingenting.

Du producerar strukturerad output i form av ett AdapterDraft-schema med följande fält:
- api_name: slug-namn (snake_case, t.ex. "open_meteo_forecast")
- base_url: bas-URL utan path (t.ex. "https://api.example.com")
- endpoints: lista av endpoint-specifikationer
- secrets_required: EXAKTA env-var-namn som API:et kräver (inga wildcards, inga antaganden)
- rate_limit_hint: om dokumentationen anger rate-limit, annars null
- doc_url: URL:en du analyserade
- llm_confidence: ditt konfidenstal 0.0–1.0 för extraheringen

Regler:
1. secrets_required: lista BARA nycklar som dokumentationen EXPLICIT nämner. Inga wildcards.
2. Om ett API inte kräver autentisering: secrets_required = []
3. response_fields: mappar fältnamn till Python-typnamn (str, int, float, bool, list, dict)
4. Trunkera inte fältnamn — extrahera exakt det dokumentationen visar.
5. llm_confidence: 1.0 = dokumentationen är komplett och entydig. < 0.6 = osäker extraktion.
"""

# ---------------------------------------------------------------------------
# Few-shot examples
# ---------------------------------------------------------------------------

EXAMPLES = """
--- EXAMPLE 1: Open-Meteo (gratis, ingen autentisering) ---

DOC_URL: https://open-meteo.com/en/docs
DOC_CONTENT (utdrag):
  Open-Meteo offers free weather forecast APIs.
  Base URL: https://api.open-meteo.com/v1/forecast
  Parameters: latitude (required), longitude (required), current (optional)
  Response: {"latitude": 52.52, "longitude": 13.4, "current": {"temperature_2m": 15.3,
             "relative_humidity_2m": 65, "wind_speed_10m": 12.5}}
  No API key required.

EXPECTED OUTPUT (AdapterDraft):
{
  "api_name": "open_meteo_forecast",
  "base_url": "https://api.open-meteo.com",
  "endpoints": [
    {
      "path": "/v1/forecast",
      "method": "GET",
      "query_params": ["latitude", "longitude", "current", "hourly"],
      "response_fields": {
        "latitude": "float",
        "longitude": "float",
        "current.temperature_2m": "float",
        "current.relative_humidity_2m": "int",
        "current.wind_speed_10m": "float"
      },
      "requires_auth": false,
      "auth_header": null
    }
  ],
  "secrets_required": [],
  "rate_limit_hint": null,
  "doc_url": "https://open-meteo.com/en/docs",
  "llm_confidence": 0.95
}

--- EXAMPLE 2: Stripe (kräver API-nyckel) ---

DOC_URL: https://stripe.com/docs/api/charges/list
DOC_CONTENT (utdrag):
  GET https://api.stripe.com/v1/charges
  Authentication: Bearer token via Authorization header.
  Set your API key as: Authorization: Bearer sk_live_...
  Environment variable: STRIPE_SECRET_KEY
  Response: {"data": [{"id": "ch_xxx", "amount": 1000, "currency": "usd", "status": "succeeded"}]}
  Rate limit: 100 req/s in live mode.

EXPECTED OUTPUT (AdapterDraft):
{
  "api_name": "stripe_charges",
  "base_url": "https://api.stripe.com",
  "endpoints": [
    {
      "path": "/v1/charges",
      "method": "GET",
      "query_params": ["limit", "starting_after", "ending_before"],
      "response_fields": {
        "id": "str",
        "amount": "int",
        "currency": "str",
        "status": "str"
      },
      "requires_auth": true,
      "auth_header": "Authorization: Bearer {STRIPE_SECRET_KEY}"
    }
  ],
  "secrets_required": ["STRIPE_SECRET_KEY"],
  "rate_limit_hint": "100 req/s",
  "doc_url": "https://stripe.com/docs/api/charges/list",
  "llm_confidence": 0.92
}
"""

# ---------------------------------------------------------------------------
# User prompt builder
# ---------------------------------------------------------------------------


def build_user_prompt(doc_content: str, doc_url: str) -> str:
    """Formatera user-prompt för LLM-anrop mot AdapterDraft.

    Args:
        doc_content: Extraherad text från API-dokumentationssidan.
        doc_url: URL som dokumentationen hämtades från.

    Returns:
        Formaterad prompt-sträng redo för LLM.
    """
    # Trunkera till ~40 000 tecken (~30 000 tokens) om dokumentet är längre
    MAX_DOC_CHARS = 40_000
    truncated = len(doc_content) > MAX_DOC_CHARS
    if truncated:
        doc_content = doc_content[:MAX_DOC_CHARS] + "\n\n[TRUNKERAT — dokumentet är längre]"

    truncation_note = "\nOBS: Dokumentet trunkerades. Extrahera vad som finns — flagga lägre llm_confidence.\n" if truncated else ""

    return f"""Analysera följande API-dokumentation och extrahera ett AdapterDraft.

DOC_URL: {doc_url}
{truncation_note}
DOKUMENTATION:
---
{doc_content}
---

Instruktioner:
1. Extrahera EXAKT de secrets_required som dokumentationen nämner. Inga wildcards.
2. Om API:et är gratis/öppet: sätt secrets_required = [].
3. Sätt llm_confidence baserat på dokumentationens tydlighet (1.0 = komplett, 0.0 = otillräcklig).
4. api_name ska vara snake_case och beskrivande (t.ex. "open_meteo_forecast", inte bara "weather").
5. base_url ska INTE inkludera path — bara schema + host (t.ex. "https://api.example.com").

Returnera ett komplett AdapterDraft-objekt.
"""
