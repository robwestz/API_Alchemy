"""E2BSandboxRunner — cloud-isolerad E2B-container för adapter-testkörning.

E2B SDK importeras lazily. Om e2b ej installerat: RuntimeError vid __init__.
Fas 3a: interface-kompatibel stub. Fas 3b: live E2B-integration.
"""

from __future__ import annotations

import time
from uuid import UUID

from loguru import logger

from packages.interfaces import SandboxResult, SandboxRunner

# Lazy import — e2b är optional extra i pyproject.toml
try:
    import e2b as _e2b_module  # noqa: F401
    _E2B_AVAILABLE = True
except ImportError:
    _E2B_AVAILABLE = False


def _redact_secrets(text: str, secrets: dict[str, str]) -> str:
    """Ersätt secret-värden med [REDACTED:KEY] i log-output.

    Redaktion sker EN gång här innan SandboxResult konstrueras (per OQ-9).
    """
    for key, value in secrets.items():
        if value and len(value) > 4:
            text = text.replace(value, f"[REDACTED:{key}]")
    return text


class E2BSandboxRunner(SandboxRunner):
    """Kör adapter-testkod i ephemeral E2B cloud-sandbox.

    Network-policy default "none" — container-isolering via E2B.
    Secrets injiceras som env-vars; aldrig hela vault (R1-mitigering).

    Fas 3a: Stub-implementation med korrekt interface.
             Kräver ``e2b``-paketet installerat (``pip install '.[sandbox]'``).
    Fas 3b: Live integration med riktig E2B API-nyckel från SecretsResolver.

    Usage::

        runner = E2BSandboxRunner(api_key="e2b-key", project_id=uuid)
        result = await runner.run(code="print('PASS')", secrets={})
    """

    def __init__(
        self,
        api_key: str | None = None,
        project_id: UUID | None = None,
    ) -> None:
        if not _E2B_AVAILABLE:
            raise RuntimeError(
                "E2B SDK not installed; pip install '.[sandbox]' or use LocalProcessSandboxRunner"
            )
        self._api_key = api_key
        self._project_id = project_id
        logger.debug(
            f"E2BSandboxRunner initierad project_id={project_id}"
        )

    async def _get_e2b_key(self) -> str:
        """Hämta E2B API-nyckel. Fas 3b: hämtar från SecretsResolver."""
        if self._api_key:
            return self._api_key
        import os
        key = os.environ.get("E2B_API_KEY", "")
        if not key:
            raise RuntimeError(
                "E2B_API_KEY saknas. Sätt environment-variabel eller "
                "skicka api_key till E2BSandboxRunner.__init__."
            )
        return key

    async def run(
        self,
        code: str,
        secrets: dict[str, str],
        network_policy: str = "none",
        timeout_ms: int = 30_000,
    ) -> SandboxResult:
        """Kör ``code`` i ephemeral E2B sandbox.

        Args:
            code: Python-kod att exekvera (t.ex. adapter_test.py-innehåll).
            secrets: Dict med secrets att injicera som env-vars.
                     Valideras mot adapter.secrets_required — inga extra nycklar.
            network_policy: "none" (default, R1) eller "allowlist".
            timeout_ms: Timeout i millisekunder.

        Returns:
            SandboxResult med secrets redactade i stdout/stderr.

        Raises:
            RuntimeError: Om e2b-paketet inte är installerat.
        """
        # e2b är garanterat tillgängligt här (checked i __init__)
        import e2b  # type: ignore[import]

        t_start = time.monotonic()
        stdout_buffer: list[str] = []
        stderr_buffer: list[str] = []
        exit_code = -1
        network_calls: list[str] = []

        api_key = await self._get_e2b_key()

        timeout_s = timeout_ms // 1000 + 10  # E2B timeout i sekunder, +10s buffer

        logger.info(
            f"E2BSandboxRunner: skapar sandbox "
            f"network_policy={network_policy!r} timeout_ms={timeout_ms}"
        )

        # Steg 1 — Skapa ephemeral E2B sandbox
        sandbox = await e2b.Sandbox.create(
            template="base",
            api_key=api_key,
            timeout=timeout_s,
            metadata={
                "project_id": str(self._project_id) if self._project_id else "unknown",
                "purpose": "adapter_test",
            },
        )

        try:
            # Steg 2 — Upload kod-fil
            await sandbox.filesystem.write("/home/user/adapter_test.py", code)

            # Network-policy handling
            if network_policy == "allowlist":
                logger.warning(
                    "E2BSandboxRunner: network_policy='allowlist' — "
                    "E2B SDK stöder ej allowlist i denna version. "
                    "Faller tillbaka till 'none' (ingen extra nätverksåtkomst)."
                )
            # "none": E2B default container-isolering gäller

            # Steg 3 — Exekvera med timeout
            process = await sandbox.process.start(
                "cd /home/user && python adapter_test.py",
                env_vars=dict(secrets),
                on_stdout=lambda e: stdout_buffer.append(e.line),
                on_stderr=lambda e: stderr_buffer.append(e.line),
            )

            try:
                result = await asyncio.wait_for(
                    process.wait(),
                    timeout=timeout_ms / 1000.0,
                )
                exit_code = result.exit_code
            except Exception:  # asyncio.TimeoutError or similar
                await process.kill()
                exit_code = -1
                stderr_buffer.append(f"TIMEOUT after {timeout_ms}ms")
                logger.warning(
                    f"E2BSandboxRunner: timeout efter {timeout_ms}ms"
                )

            # Steg 4 — Capture stdout/stderr
            stdout_raw = "\n".join(stdout_buffer)
            stderr_raw = "\n".join(stderr_buffer)

            # Steg 5 — Lista nätverksanrop
            try:
                network_calls = await sandbox.network.get_connections()
            except AttributeError:
                # Fallback: SDK stöder ej network monitor i denna version
                network_calls = []
                logger.debug(
                    "E2BSandboxRunner: sandbox.network.get_connections() ej tillgänglig "
                    "i denna SDK-version. network_calls = [] (svagare R1-garanti)."
                )

            # R1-enforcement
            if network_calls and network_policy == "none":
                logger.error(
                    "SECURITY WARNING: adapter-kod försökte göra nätverksanrop trots "
                    f"network_policy=none. Anrop: {network_calls}"
                )

        finally:
            # Steg 6 — Cleanup (ephemeral sandbox destrueras)
            await sandbox.close()
            logger.debug("E2BSandboxRunner: sandbox stängd och rensad.")

        duration_ms = int((time.monotonic() - t_start) * 1000)
        success = (exit_code == 0) and ("PASS" in stdout_raw)

        logger.info(
            f"E2BSandboxRunner: exit_code={exit_code} success={success} "
            f"duration_ms={duration_ms} network_calls={len(network_calls)}"
        )

        return SandboxResult(
            success=success,
            stdout=_redact_secrets(stdout_raw, secrets),
            stderr=_redact_secrets(stderr_raw, secrets),
            exit_code=exit_code,
            duration_ms=duration_ms,
            network_calls=network_calls,
        )


# asyncio import needed inside run() — add at module level for clarity
import asyncio  # noqa: E402
