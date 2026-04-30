"""LocalTomlResolver — hämtar secrets från lokal TOML-fil.

TOML-format:
    [global]
    ANTHROPIC_API_KEY = "sk-ant-..."

    [project.00000000-0000-0000-0000-000000000001]
    STRIPE_SECRET_KEY = "sk-live-..."

Project-specifika secrets prioriteras över global-sektionen.
Filen skyddas med fil-permission-varning om world-readable.
"""

from __future__ import annotations

import stat
import tomllib
from pathlib import Path
from uuid import UUID

from loguru import logger


class LocalTomlResolver:
    """Läser secrets från TOML-fil med per-projekt-isolering.

    Project-specifik sektion läses FÖRE global-sektion (projekt vinner).
    Raise ``KeyError`` om nyckeln saknas i båda sektionerna.

    Args:
        toml_path: Absolut sökväg till secrets.toml-filen.

    Raises:
        FileNotFoundError: Om filen inte finns.
        tomllib.TOMLDecodeError: Om TOML-syntaxfel.
    """

    def __init__(self, toml_path: Path) -> None:
        self._toml_path = toml_path
        self._data = self._load(toml_path)

    def _load(self, path: Path) -> dict[str, object]:
        """Ladda och parsa TOML-filen. Varnar om world-readable."""
        if not path.exists():
            raise FileNotFoundError(f"Secrets-fil saknas: {path}")

        # Fil-permission-skydd: varna om world-readable (mode & 0o004 != 0)
        try:
            file_stat = path.stat()
            if file_stat.st_mode & stat.S_IROTH:
                logger.warning(
                    f"SÄKERHETSVARNING: {path} är world-readable (mode="
                    f"{oct(file_stat.st_mode)}). "
                    "Kör: chmod 600 {path}"
                )
        except Exception as exc:
            logger.debug(f"Kunde inte kontrollera fil-permissions för {path}: {exc}")

        with path.open("rb") as fh:
            data = tomllib.load(fh)

        logger.debug(f"LocalTomlResolver: laddade {path}")
        return data

    async def get(self, project_id: UUID, key: str) -> str:
        """Hämta en enskild secret.

        Söker i ordning: [project.<project_id>] → [global].

        Args:
            project_id: Projektets UUID.
            key: Nyckelnamn (t.ex. "STRIPE_SECRET_KEY").

        Returns:
            Secret-värdet som sträng.

        Raises:
            KeyError: Om nyckeln saknas i både projekt- och global-sektion.
        """
        project_section_key = str(project_id)

        # 1. Försök projekt-specifik sektion
        project_data = (
            self._data.get("project", {})  # type: ignore[union-attr]
            .get(project_section_key, {})  # type: ignore[union-attr]
        )
        if key in project_data:
            value = project_data[key]
            logger.debug(
                f"LocalTomlResolver: hittade {key!r} i projekt-sektion {project_section_key}"
            )
            return str(value)

        # 2. Försök global-sektion
        global_data = self._data.get("global", {})
        if key in global_data:  # type: ignore[operator]
            value = global_data[key]  # type: ignore[index]
            logger.debug(f"LocalTomlResolver: hittade {key!r} i global-sektion")
            return str(value)

        raise KeyError(
            f"Secret {key!r} saknas i både projekt-sektion "
            f"{project_section_key!r} och [global] i {self._toml_path}"
        )

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
                f"Följande secrets saknas för projekt {project_id}: {missing}"
            )

        return result
