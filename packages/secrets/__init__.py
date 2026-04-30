"""Secrets resolvers — hämtar API-nycklar utan att exponera hela vault.

Implementations:
  - LocalTomlResolver: läser från lokal TOML-fil (offline-fallback)
  - DopplerResolver: hämtar från Doppler vault (online primary)

Båda implementerar SecretsResolver-protokollet från packages.interfaces.
"""

from packages.secrets.local_toml import LocalTomlResolver
from packages.secrets.doppler import DopplerResolver

__all__ = ["LocalTomlResolver", "DopplerResolver"]
