"""DopplerResolver — hämtar secrets från Doppler vault.

Fas 3a: Stub-implementation.
- Försöker importera doppler-SDK (om installerat).
- Faller tillbaka till subprocess `doppler secrets get <key> --plain`.
- Om varken SDK eller CLI finns: tydligt RuntimeError.

Samma interface som LocalTomlResolver (SecretsResolver-protokollet).
"""

from __future__ import annotations

import asyncio
import shutil
from uuid import UUID

from loguru import logger

# Lazy import av Doppler SDK — kan saknas i operatörens env
try:
    import doppler as _doppler_module  # type: ignore[import]
    _DOPPLER_SDK_AVAILABLE = True
except ImportError:
    _DOPPLER_SDK_AVAILABLE = False

# Kontrollera om Doppler CLI finns i PATH
_DOPPLER_CLI_AVAILABLE = shutil.which("doppler") is not None


def _check_doppler_available() -> None:
    """Raise tydligt fel om varken Doppler SDK eller CLI finns."""
    if not _DOPPLER_SDK_AVAILABLE and not _DOPPLER_CLI_AVAILABLE:
        raise RuntimeError(
            "DopplerResolver kräver antingen Doppler Python SDK "
            "(pip install doppler-sdk) eller Doppler CLI (https://docs.doppler.com/docs/cli). "
            "Alternativ: använd LocalTomlResolver för offline-dev."
        )


class DopplerResolver:
    """Hämtar secrets från Doppler vault via SDK eller CLI-subprocess.

    Fas 3a stub: interface-kompatibel. Live Doppler-integration i Fas 5.

    Args:
        token: Doppler service token. Om None läses DOPPLER_TOKEN env-var.
        project: Doppler-projektnamn (används med CLI-fallback).
        config: Doppler-config (t.ex. "prd", "dev").

    Raises:
        RuntimeError: Om varken Doppler SDK eller CLI är tillgängligt.
    """

    def __init__(
        self,
        token: str | None = None,
        project: str | None = None,
        config: str | None = None,
    ) -> None:
        _check_doppler_available()
        self._token = token
        self._project = project
        self._config = config
        logger.debug(
            f"DopplerResolver initierad "
            f"sdk={_DOPPLER_SDK_AVAILABLE} cli={_DOPPLER_CLI_AVAILABLE} "
            f"project={project!r} config={config!r}"
        )

    async def get(self, project_id: UUID, key: str) -> str:
        """Hämta en enskild secret från Doppler.

        Försöker SDK först, sedan CLI subprocess.

        Args:
            project_id: Projektets UUID (används för loggning/audit).
            key: Nyckelnamn (t.ex. "STRIPE_SECRET_KEY").

        Returns:
            Secret-värdet som sträng.

        Raises:
            KeyError: Om nyckeln inte finns i Doppler.
            RuntimeError: Om Doppler är otillgänglig.
        """
        if _DOPPLER_SDK_AVAILABLE:
            return await self._get_via_sdk(project_id, key)
        return await self._get_via_cli(key)

    async def _get_via_sdk(self, project_id: UUID, key: str) -> str:
        """Hämta via Doppler Python SDK (Fas 3a stub)."""
        # Fas 3a: SDK-anrop är stubbart — implementeras fullt i Fas 5
        # SDK-interface kan variera med version; detta är defensiv stub
        try:
            import doppler  # type: ignore[import]
            import os

            token = self._token or os.environ.get("DOPPLER_TOKEN", "")
            if not token:
                raise RuntimeError(
                    "DOPPLER_TOKEN saknas. Sätt environment-variabel eller "
                    "skicka token till DopplerResolver.__init__."
                )

            # Fas 3a: direktanrop mot SDK (Fas 5 lägger till full error-handling)
            client = doppler.DopplerSDK(access_token=token)
            response = client.secrets.get(
                project=self._project,
                config=self._config,
                name=key,
            )
            value = response.secret.value.raw if response.secret else None
            if value is None:
                raise KeyError(f"Secret {key!r} saknas i Doppler.")
            logger.debug(f"DopplerResolver (SDK): hittade {key!r}")
            return str(value)
        except KeyError:
            raise
        except Exception as exc:
            logger.warning(
                f"DopplerResolver SDK-fel för {key!r}: {exc}. "
                "Försöker CLI-fallback."
            )
            if _DOPPLER_CLI_AVAILABLE:
                return await self._get_via_cli(key)
            raise

    async def _get_via_cli(self, key: str) -> str:
        """Hämta via `doppler secrets get <key> --plain` subprocess."""
        import os

        cmd = ["doppler", "secrets", "get", key, "--plain"]
        if self._project:
            cmd.extend(["--project", self._project])
        if self._config:
            cmd.extend(["--config", self._config])

        env = dict(os.environ)
        if self._token:
            env["DOPPLER_TOKEN"] = self._token

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=10.0
            )
            exit_code = proc.returncode if proc.returncode is not None else -1
        except asyncio.TimeoutError:
            raise RuntimeError(f"Doppler CLI timeout vid hämtning av {key!r}.")
        except Exception as exc:
            raise RuntimeError(f"Doppler CLI subprocess-fel: {exc}") from exc

        if exit_code != 0:
            stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
            if "not found" in stderr.lower() or "does not exist" in stderr.lower():
                raise KeyError(f"Secret {key!r} saknas i Doppler (CLI): {stderr}")
            raise RuntimeError(
                f"Doppler CLI returnerade exit_code={exit_code} för {key!r}: {stderr}"
            )

        value = stdout_bytes.decode("utf-8", errors="replace").strip()
        logger.debug(f"DopplerResolver (CLI): hittade {key!r}")
        return value

    async def get_many(
        self, project_id: UUID, keys: list[str]
    ) -> dict[str, str]:
        """Hämta flera secrets på en gång.

        Args:
            project_id: Projektets UUID.
            keys: Lista med nyckelnamn.

        Returns:
            Dict med nyckel → värde för alla begärda nycklar.

        Raises:
            KeyError: Om någon nyckel saknas.
        """
        result: dict[str, str] = {}
        missing: list[str] = []

        for key in keys:
            try:
                result[key] = await self.get(project_id, key)
            except KeyError:
                missing.append(key)

        if missing:
            raise KeyError(
                f"Följande secrets saknas för projekt {project_id} i Doppler: {missing}"
            )

        return result
