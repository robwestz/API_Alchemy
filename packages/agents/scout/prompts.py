"""Prompt-konstanter för ScoutAgent.

Alla prompt-texter lever här — aldrig inbäddade i agent-logiken.
Prompt-hash loggas per anrop för replay (per D7 reproducibility).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """Du är en precis API-discovery-specialist. Din uppgift är att hitta
relevanta, publikt tillgängliga API:er för en given domän eller affärsidé.

Du producerar strukturerad output i form av ett DiscoveryReport-schema med följande fält:
- project_id: UUID för projektet (vidarebefordra som-är)
- domain: domänen/idén som analyserades
- candidates: lista av DiscoveryCandidate-objekt (max max_candidates st)
- cost_usd: uppskattad kostnad för denna discovery-körning
- generated_at: tidpunkt för körningen (ISO 8601)

Varje DiscoveryCandidate har:
- api_name: beskrivande namn på API:et (t.ex. "Swish Payments API")
- doc_url: URL till officiell API-dokumentation (MÅSTE vara en riktig URL)
- estimated_cost_per_1k: uppskattad kostnad i USD per 1000 anrop (0.0 om gratis)
- data_coverage: kort beskrivning av vilken data API:et täcker
- reliability_score: konfidenstal 0.0–1.0 för hur pålitlig kandidaten är
  (1.0 = välkänd, dokumenterad, stabil; < 0.5 = osäker eller svår att verifiera)
- requires_secret: true om API:et kräver autentisering/API-nyckel

Regler:
1. Producera BARA API:er som faktiskt existerar och är relevanta för domänen.
2. Sätt reliability_score lägre om du är osäker på att doc_url är korrekt.
3. Prioritera öppna/gratis API:er om de täcker domänen väl.
4. Inkludera ej interna eller enterprise-only API:er utan offentlig dokumentation.
5. max_candidates bestämmer övre gränsen — producera hellre färre men bättre kandidater.
"""

# ---------------------------------------------------------------------------
# Few-shot examples
# ---------------------------------------------------------------------------

EXAMPLES = """
--- EXAMPLE 1: Domän "fintech i Sverige" → 5 kandidater ---

INPUT:
  domain: "fintech i Sverige"
  max_candidates: 5

EXPECTED OUTPUT (DiscoveryReport):
{
  "project_id": "00000000-0000-0000-0000-000000000001",
  "domain": "fintech i Sverige",
  "candidates": [
    {
      "api_name": "Swish Payments API",
      "doc_url": "https://developer.swish.nu/documentation/getting-started",
      "estimated_cost_per_1k": 0.0,
      "data_coverage": "Mobila betalningar i realtid, payment requests, refunds, QR-koder",
      "reliability_score": 0.92,
      "requires_secret": true
    },
    {
      "api_name": "Klarna Payments API",
      "doc_url": "https://docs.klarna.com/klarna-payments/",
      "estimated_cost_per_1k": 0.0,
      "data_coverage": "Buy now pay later, checkout-integration, orderstatus, kundautentisering",
      "reliability_score": 0.95,
      "requires_secret": true
    },
    {
      "api_name": "Fortnox API",
      "doc_url": "https://developer.fortnox.se/documentation/",
      "estimated_cost_per_1k": 0.0,
      "data_coverage": "Bokföring, fakturering, kunder, leverantörer, löner — Sveriges vanligaste redovisningssystem",
      "reliability_score": 0.90,
      "requires_secret": true
    },
    {
      "api_name": "Open Banking (PSD2) via Tink",
      "doc_url": "https://docs.tink.com/api",
      "estimated_cost_per_1k": 5.0,
      "data_coverage": "Kontoinformation, transaktioner, betalningsinitiering från svenska banker via PSD2",
      "reliability_score": 0.88,
      "requires_secret": true
    },
    {
      "api_name": "Visma eAccounting API",
      "doc_url": "https://developer.vismaonline.com/docs/api-documentation",
      "estimated_cost_per_1k": 0.0,
      "data_coverage": "Fakturor, kunder, produkter, bokföringsorder — integration med Visma eAccounting",
      "reliability_score": 0.85,
      "requires_secret": true
    }
  ],
  "cost_usd": 0.012,
  "generated_at": "2026-04-30T10:00:00Z"
}

--- EXAMPLE 2: Domän "väderdata för mobilapp" → 3 kandidater ---

INPUT:
  domain: "väderdata för mobilapp"
  max_candidates: 3

EXPECTED OUTPUT (DiscoveryReport):
{
  "project_id": "00000000-0000-0000-0000-000000000002",
  "domain": "väderdata för mobilapp",
  "candidates": [
    {
      "api_name": "Open-Meteo Weather API",
      "doc_url": "https://open-meteo.com/en/docs",
      "estimated_cost_per_1k": 0.0,
      "data_coverage": "Prognos, historisk väderdata, luftkvalitet, marindata — global täckning, ingen API-nyckel",
      "reliability_score": 0.97,
      "requires_secret": false
    },
    {
      "api_name": "SMHI Open Data API",
      "doc_url": "https://opendata.smhi.se/apidocs/",
      "estimated_cost_per_1k": 0.0,
      "data_coverage": "Svensk väderdata, observationer, prognoser från SMHI — gratis öppen data",
      "reliability_score": 0.93,
      "requires_secret": false
    },
    {
      "api_name": "OpenWeatherMap API",
      "doc_url": "https://openweathermap.org/api",
      "estimated_cost_per_1k": 0.5,
      "data_coverage": "Global väderprognos, historik, luftkvalitet, UV-index — välkänd kommersiell tjänst",
      "reliability_score": 0.91,
      "requires_secret": true
    }
  ],
  "cost_usd": 0.008,
  "generated_at": "2026-04-30T10:01:00Z"
}
"""

# ---------------------------------------------------------------------------
# User prompt builder
# ---------------------------------------------------------------------------


def build_user_prompt(
    domain: str,
    max_candidates: int = 5,
    search_results: list[dict[str, str]] | None = None,
    fetched_docs: dict[str, str] | None = None,
) -> str:
    """Formatera user-prompt för LLM-anrop mot DiscoveryReport.

    Args:
        domain: Domän eller affärsidé att hitta API:er för.
        max_candidates: Max antal kandidater att returnera.
        search_results: Valfri lista med web-sökresultat
            (varje post: {"title": str, "url": str, "snippet": str}).
        fetched_docs: Valfri dict url -> doc-innehåll för fördjupad analys.

    Returns:
        Formaterad prompt-sträng redo för LLM.
    """
    search_section = ""
    if search_results:
        lines = ["", "WEB-SÖKRESULTAT (använd som ledtrådar till kandidater):", "---"]
        for item in search_results:
            title = item.get("title", "")
            url = item.get("url", "")
            snippet = item.get("snippet", "")
            lines.append(f"  Titel: {title}")
            lines.append(f"  URL: {url}")
            lines.append(f"  Utdrag: {snippet}")
            lines.append("")
        lines.append("---")
        search_section = "\n".join(lines)

    docs_section = ""
    if fetched_docs:
        MAX_DOC_CHARS = 5_000
        lines = ["", "HÄMTAD DOKUMENTATION (utdrag per URL):", "---"]
        for url, content in fetched_docs.items():
            truncated = content[:MAX_DOC_CHARS]
            if len(content) > MAX_DOC_CHARS:
                truncated += "\n[TRUNKERAT]"
            lines.append(f"URL: {url}")
            lines.append(truncated)
            lines.append("---")
        docs_section = "\n".join(lines)

    return f"""Hitta de mest relevanta publika API:erna för följande domän/idé:

DOMÄN: {domain}
MAX KANDIDATER: {max_candidates}
{search_section}{docs_section}
Instruktioner:
1. Returnera max {max_candidates} DiscoveryCandidate-objekt i candidates-listan.
2. Sortera kandidaterna med högst reliability_score först.
3. doc_url måste vara en giltig URL till officiell API-dokumentation.
4. Om du är osäker på en URL, sätt reliability_score < 0.7.
5. Inkludera både gratis och betalda alternativ om de är relevanta.
6. data_coverage ska vara koncis men informativ (1-2 meningar).

Returnera ett komplett DiscoveryReport-objekt.
"""
