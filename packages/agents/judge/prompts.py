"""Judge agent — LLM prompts for DX-score evaluation.

DX = Developer eXperience. The LLM rates 0.0–1.0 based on:
  - docs quality (clarity, completeness, examples)
  - error messages (descriptiveness, actionability)
  - response structure (consistency, nested depth, field naming)
  - latency consistency (p50 vs p95 spread)
"""

from __future__ import annotations

import json

__all__ = ["DX_EXAMPLES", "DX_SYSTEM_PROMPT", "build_dx_prompt"]

DX_SYSTEM_PROMPT = """\
You are an API quality evaluator specialising in Developer eXperience (DX).

Your task: given metadata about an API adapter, rate its DX on a scale from 0.0 to 1.0.

## Scoring dimensions (equal weight)
1. **Documentation quality** — Are endpoints clearly described? Are request/response \
examples provided? Is authentication explained?
2. **Error messages** — When the API fails, are error payloads descriptive and \
actionable? Do they include error codes, human-readable messages, and hints?
3. **Response structure** — Is the JSON response consistent across calls? Are field \
names predictable (snake_case or camelCase consistently)? Is nesting shallow and logical?
4. **Latency consistency** — How wide is the spread between p50 and p95 latency? \
A well-behaved API has p95 < 2x p50.

## Output format
Respond with ONLY a JSON object -- no prose, no markdown fences:
{"dx_score": <float 0.0-1.0>, "rationale": "<one sentence>"}

## Rules
- dx_score MUST be in [0.0, 1.0]. Never return a value outside this range.
- Be calibrated: a score of 0.9 means genuinely excellent DX; 0.5 is mediocre; \
0.2 is painful to use.
- Base your judgement strictly on the provided metadata, not on brand reputation.
"""

DX_EXAMPLES = """\
## Examples

### Example 1 -- open_meteo (high DX, expected score ~0.9)
adapter_name: open_meteo
sample_response: {"latitude": 59.33, "longitude": 18.07, "current": \
{"temperature_2m": 12.5, "relative_humidity_2m": 71, "wind_speed_10m": 4.2}, \
"current_units": {"temperature_2m": "C", "relative_humidity_2m": "%", \
"wind_speed_10m": "km/h"}}
latency_p50_ms: 120.0
error_messages: []
-> {"dx_score": 0.9, "rationale": "Clean flat structure with co-located units, \
no auth required, free, and consistently fast."}

### Example 2 -- hypothetical_bad_api (low DX, expected score ~0.3)
adapter_name: hypothetical_bad_api
sample_response: {"d": [{"v": 99, "t": 1714000000, "x": null}], "s": 1, "e": ""}
latency_p50_ms: 850.0
error_messages: ["ERR_001", "Internal error", "Contact support"]
-> {"dx_score": 0.3, "rationale": "Cryptic single-letter field names, opaque error \
codes without context, and high latency."}
"""


def build_dx_prompt(
    adapter_name: str,
    sample_response: dict[str, object],
    latency_p50_ms: float,
    error_messages: list[str],
) -> str:
    """Build the user-turn prompt for DX-score evaluation.

    Args:
        adapter_name: Identifier of the adapter being evaluated.
        sample_response: One representative response payload from the adapter.
        latency_p50_ms: Median latency across benchmark runs (milliseconds).
        error_messages: List of error strings observed during benchmark runs.
            Pass an empty list if no errors occurred.

    Returns:
        Formatted user-turn string ready to be passed as the ``"user"`` message
        in the LLM call.
    """
    response_json = json.dumps(sample_response, ensure_ascii=False, indent=2)
    errors_repr = json.dumps(error_messages, ensure_ascii=False)
    return (
        f"adapter_name: {adapter_name}\n"
        f"sample_response:\n{response_json}\n"
        f"latency_p50_ms: {latency_p50_ms:.1f}\n"
        f"error_messages: {errors_repr}\n\n"
        "Rate the DX of this adapter."
    )
