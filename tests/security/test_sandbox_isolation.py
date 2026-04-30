"""Sakerhets-tester for sandbox-isolering.

Testar att sandbox-kontrakten enforce:as: LocalProcess kraver explicit
unsafe-acknowledgement, E2B-runner failar gracefully om SDK saknas,
SandboxResult valideras pa bade success och fail-paths.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from packages.interfaces import SandboxResult
from packages.sandbox.local_runner import LocalProcessSandboxRunner


def test_local_runner_rejected_without_unsafe_ack() -> None:
    """LocalProcessSandboxRunner KRAVER unsafe_acknowledged=True."""
    with pytest.raises(RuntimeError, match="unsafe"):
        LocalProcessSandboxRunner()


def test_local_runner_accepts_with_unsafe_ack() -> None:
    """unsafe_acknowledged=True initialiserar utan fel."""
    runner = LocalProcessSandboxRunner(unsafe_acknowledged=True)
    assert runner._unsafe_acknowledged is True


@pytest.mark.asyncio
async def test_local_runner_subprocess_capture() -> None:
    """LocalProcess kor en trivial Python-snippet och returnerar SandboxResult."""
    runner = LocalProcessSandboxRunner(unsafe_acknowledged=True)
    code = "print('hello sandbox')"
    result = await runner.run(code=code, secrets={}, timeout_ms=10_000)

    assert isinstance(result, SandboxResult)
    assert result.success is True
    assert "hello sandbox" in result.stdout
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_local_runner_captures_failure() -> None:
    """SyntaxError -> success=False, exit_code != 0."""
    runner = LocalProcessSandboxRunner(unsafe_acknowledged=True)
    code = "this is not valid python ::"
    result = await runner.run(code=code, secrets={}, timeout_ms=10_000)

    assert result.success is False
    assert result.exit_code != 0
    assert result.stderr  # innehaller SyntaxError eller liknande


def test_e2b_runner_fails_gracefully_without_sdk() -> None:
    """E2BSandboxRunner ska raise:a tydligt fel om e2b SDK saknas.

    Skip:as om e2b ar installerat i test-env.
    """
    try:
        import e2b  # noqa: F401, PLC0415

        pytest.skip("e2b SDK is installed; cannot test missing-SDK fallback")
    except ImportError:
        pass

    from packages.sandbox.e2b_runner import E2BSandboxRunner  # noqa: PLC0415

    with pytest.raises((RuntimeError, ImportError)):
        E2BSandboxRunner()


def test_sandbox_result_schema_pass() -> None:
    """SandboxResult ska accepta giltiga falt."""
    result = SandboxResult(
        success=True,
        stdout="ok",
        stderr="",
        exit_code=0,
        duration_ms=42,
        network_calls=[],
    )
    assert result.success is True
    assert result.duration_ms == 42
    assert result.network_calls == []


def test_sandbox_result_schema_rejects_bad_types() -> None:
    """Pydantic ska reject:a icke-bool 'success'."""
    with pytest.raises(Exception):  # noqa: BLE001
        SandboxResult(  # type: ignore[arg-type]
            success="yes",  # type: ignore[arg-type]
            stdout="",
            stderr="",
            exit_code=0,
            duration_ms=0,
        )


@pytest.mark.asyncio
async def test_local_runner_network_policy_warning() -> None:
    """LocalProcess loggar warning nar network_policy='none' anvands."""
    runner = LocalProcessSandboxRunner(unsafe_acknowledged=True)
    code = "print('x')"
    with patch("packages.sandbox.local_runner.logger") as mock_logger:
        await runner.run(
            code=code, secrets={}, network_policy="none", timeout_ms=5_000
        )
        # Minst en warning ska ha loggats kring network-isolation
        warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
        assert any(
            "network" in c.lower() or "isolat" in c.lower() or "unsafe" in c.lower()
            for c in warning_calls
        )


@pytest.mark.asyncio
async def test_local_runner_timeout() -> None:
    """Lang-korande snippet timeout:as enligt timeout_ms."""
    runner = LocalProcessSandboxRunner(unsafe_acknowledged=True)
    code = "import time; time.sleep(5)"
    result = await runner.run(code=code, secrets={}, timeout_ms=500)

    # Timeout -> ej riktigt 5s
    assert result.duration_ms < 4_000
    assert result.success is False or bool(result.stderr)
