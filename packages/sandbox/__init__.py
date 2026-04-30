"""Sandbox runners — isolerad exekvering av auto-genererad adapter-kod.

Implementations:
  - E2BSandboxRunner: cloud-isolerad E2B-container (default)
  - LocalProcessSandboxRunner: lokal subprocess (kräver --unsafe-local-flag)

Val av backend sker via get_sandbox_runner() factory eller direkt instansiering.
"""

from packages.sandbox.e2b_runner import E2BSandboxRunner
from packages.sandbox.local_runner import LocalProcessSandboxRunner

__all__ = ["E2BSandboxRunner", "LocalProcessSandboxRunner"]
