"""LocalProcessSandboxRunner — kör adapter-kod som lokal subprocess.

VARNING: Ingen nätverksisolering. Kräver explicit unsafe_acknowledged=True.
Används ALDRIG i CI eller produktion — endast för offline-dev.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

from loguru import logger

from packages.interfaces import SandboxResult, SandboxRunner


class LocalProcessSandboxRunner(SandboxRunner):
    """Kör adapter-testkod som lokal subprocess i temporär katalog.

    SÄKERHETSVARNING: Ingen nätverksisolering, ingen container-isolering.
    Subprocess ärver operatörens miljö (minus injicerade secrets).
    Kräver explicit ``unsafe_acknowledged=True`` — annars RuntimeError.

    Användning::

        runner = LocalProcessSandboxRunner(unsafe_acknowledged=True)
        result = await runner.run(code="print('PASS')", secrets={})
    """

    def __init__(self, unsafe_acknowledged: bool = False) -> None:
        if not unsafe_acknowledged:
            raise RuntimeError(
                "LocalProcessSandboxRunner is unsafe — only use for offline dev. "
                "Pass unsafe_acknowledged=True to confirm."
            )
        logger.warning(
            "LocalProcessSandboxRunner initierad. "
            "INGEN nätverksisolering. UNSAFE_LOCAL_EXECUTION=true. "
            "Använd ALDRIG i CI eller produktion."
        )
        self._unsafe_acknowledged = unsafe_acknowledged

    async def run(
        self,
        code: str,
        secrets: dict[str, str],
        network_policy: str = "none",
        timeout_ms: int = 30_000,
    ) -> SandboxResult:
        """Kör ``code`` som subprocess i temporär katalog.

        Args:
            code: Python-kod att exekvera.
            secrets: Dict med secrets att injicera som env-vars i subprocess.
            network_policy: Ignoreras — subprocess har ingen nätverksisolering.
                            Loggar WARNING om network_policy="none" begärs.
            timeout_ms: Timeout i millisekunder.

        Returns:
            SandboxResult med stdout, stderr, exit_code och duration_ms.
        """
        import os
        import time

        if network_policy == "none":
            logger.warning(
                "LocalProcessSandboxRunner: network_policy='none' begärd men kan "
                "INTE enforcea nätverksisolering utan extra setup (iptables/WSL). "
                "Subprocess har full nätverksåtkomst. UNSAFE_LOCAL_EXECUTION=true."
            )

        t_start = time.monotonic()

        with tempfile.TemporaryDirectory(prefix="alchemy_sandbox_") as tmpdir:
            code_path = Path(tmpdir) / "adapter_test.py"
            code_path.write_text(code, encoding="utf-8")

            # Bygg env: ärv OS-miljö, lägg till injicerade secrets
            env = dict(os.environ)
            env.update(secrets)
            # Markera tydligt att detta är en unsafe local-körning
            env["UNSAFE_LOCAL_EXECUTION"] = "true"

            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable,
                    str(code_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=tmpdir,
                    env=env,
                )

                try:
                    stdout_bytes, stderr_bytes = await asyncio.wait_for(
                        proc.communicate(),
                        timeout=timeout_ms / 1000.0,
                    )
                    exit_code = proc.returncode if proc.returncode is not None else -1
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.communicate()
                    stdout_bytes = b""
                    stderr_bytes = f"TIMEOUT after {timeout_ms}ms".encode()
                    exit_code = -1
                    logger.warning(
                        f"LocalProcessSandboxRunner: timeout efter {timeout_ms}ms"
                    )

            except Exception as exc:
                duration_ms = int((time.monotonic() - t_start) * 1000)
                logger.error(f"LocalProcessSandboxRunner subprocess error: {exc}")
                return SandboxResult(
                    success=False,
                    stdout="",
                    stderr=str(exc),
                    exit_code=-1,
                    duration_ms=duration_ms,
                    network_calls=[],
                )

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        duration_ms = int((time.monotonic() - t_start) * 1000)

        # success = process exited cleanly. Caller inspects stdout for assertions.
        success = exit_code == 0

        logger.info(
            f"LocalProcessSandboxRunner: exit_code={exit_code} "
            f"success={success} duration_ms={duration_ms}"
        )

        return SandboxResult(
            success=success,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=duration_ms,
            # Kan inte detektera nätverksanrop utan extra setup
            network_calls=[],
        )
