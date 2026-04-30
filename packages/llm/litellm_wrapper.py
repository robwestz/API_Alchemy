"""LiteLLM wrapper — enda platsen i systemet som gör LLM-anrop.

Arkitekturell princip: INGA andra filer får importera litellm eller
anropa ett LLM direkt. Alla anrop sker via `complete()` här.

Cost-callback skriver automatiskt till cost_ledger via LakeRepository.
Modellnamnet skickas in som argument — aldrig hårdkodat.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import litellm
from loguru import logger
from pydantic import BaseModel

from packages.lake.repository import LakeRepository


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class CompletionResult(BaseModel):
    """Output från ett LLM-anrop via complete()."""

    content: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    model: str


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def complete(
    *,
    project_id: UUID,
    agent_id: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.7,
    repo: LakeRepository | None = None,
    **kwargs: Any,
) -> CompletionResult:
    """Kör ett LLM-anrop och logga kostnad till cost_ledger.

    Args:
        project_id:  Projekt som betalas för anropet.
        agent_id:    Agentens identitet (ex. "scout", "engineer").
        model:       LiteLLM-modellsträng (ex. "openai/gpt-4o").
        messages:    OpenAI-format meddelandelista.
        temperature: Sampling-temperatur (0-2).
        repo:        LakeRepository-instans för cost-logging. Om None loggas
                     kosten bara via loguru (används i tester utan DB).
        **kwargs:    Vidarebefordras till litellm.acompletion().

    Returns:
        CompletionResult med innehåll, token-räkning och kostnad.
    """
    logger.debug(
        f"LLM call model={model!r} agent={agent_id!r} "
        f"msgs={len(messages)} temp={temperature}"
    )

    response = await litellm.acompletion(
        model=model,
        messages=messages,
        temperature=temperature,
        **kwargs,
    )

    # Extrahera innehåll
    content: str = ""
    choice = response.choices[0] if response.choices else None
    if choice is not None and choice.message is not None:
        content = choice.message.content or ""

    # Token-räkning
    usage = response.usage
    tokens_in: int = int(usage.prompt_tokens) if usage and usage.prompt_tokens else 0
    tokens_out: int = int(usage.completion_tokens) if usage and usage.completion_tokens else 0

    # Kostnad via litellm completion_cost
    cost_usd: float = 0.0
    try:
        cost_usd = float(litellm.completion_cost(completion_response=response))
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Could not compute cost for model={model!r}: {exc}")

    result = CompletionResult(
        content=content,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
        model=model,
    )

    logger.info(
        f"LLM done model={model!r} tokens_in={tokens_in} "
        f"tokens_out={tokens_out} cost_usd={cost_usd:.6f}"
    )

    # Skriv till cost_ledger om repo finns
    if repo is not None:
        await repo.record_cost(
            project_id=project_id,
            agent_id=agent_id,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
        )

    return result
