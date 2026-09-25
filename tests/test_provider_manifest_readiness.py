"""Set-wide provider admission checks for the host-managed TCP broker contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from astrid.core.execution.generic_host import GenericPackHost
from astrid.core.execution.executor.schema import load_executor_manifest


ROOT = Path(__file__).resolve().parents[1]
PACKS = ROOT / "astrid" / "packs"
MATRIX = ROOT / "config" / "astrid-beta-capabilities.json"


def _provider_host(*, credentials: dict[str, str]) -> GenericPackHost:
    host = GenericPackHost(
        pack_roots=[PACKS],
        capability_matrix=MATRIX,
        credential_source=credentials,
    )
    host.discover()
    host.preflight()
    return host


def _fixture_credentials(host: GenericPackHost) -> dict[str, str]:
    names = {
        str(name)
        for record in host.capabilities.values()
        if record.adapter.family == "provider"
        for name in (record.matrix.get("required_env") or ())
    }
    return {name: "provider-manifest-fixture-secret" for name in names}


def test_every_tcp_provider_manifest_declares_an_enforceable_host_broker():
    host = _provider_host(credentials={})
    providers = [record for record in host.capabilities.values() if record.adapter.family == "provider"]

    assert len(providers) == 26
    for record in providers:
        policy = record.definition.metadata["network_policy"]
        protocols = {str(value).lower() for value in policy["allowed_protocols"]}
        broker = policy.get("broker")
        if protocols & {"udp", "quic"}:
            assert not record.ready
            continue
        assert isinstance(broker, dict)
        assert broker["host_managed"] is True
        assert broker["kind"] == "broker"
        assert broker["enforced"] is True
        assert broker["observable"] is True
        assert broker["route"]
        assert broker["wrapper"]
        descendant = policy.get("descendant_enforcement")
        assert isinstance(descendant, dict)
        assert descendant["kind"] == "broker"
        assert descendant["validated"] is True
        assert descendant["observable"] is True
        assert descendant["route"]
        assert descendant["wrapper"]


def test_all_supported_provider_routes_are_ready_and_grantable_with_declared_inputs():
    probe = _provider_host(credentials={})
    host = _provider_host(credentials=_fixture_credentials(probe))
    providers = [record for record in host.capabilities.values() if record.adapter.family == "provider"]
    tcp_providers = []
    for record in providers:
        protocols = {str(value).lower() for value in record.definition.metadata["network_policy"]["allowed_protocols"]}
        if not protocols & {"udp", "quic"}:
            tcp_providers.append(record)
            if record.id == "editorial.script_pipeline" and not record.ready:
                assert record.preflight["sandbox"]["reason"] == (
                    "host-managed provider broker requires an OS network sandbox"
                )
                pytest.skip(
                    "LINUX_SANDBOX: editorial.script_pipeline requires "
                    "darwin sandbox-exec for its host-managed broker"
                )
            if not record.ready and record.matrix.get("disposition") == "optional":
                # Optional provider routes remain truthfully unavailable when
                # this host lacks a declared local binary; that is a valid
                # readiness result, not a broker-contract failure.
                assert record.preflight["binaries"]["ok"] is False
                continue
            assert record.ready, (record.id, record.preflight)

    assert len(tcp_providers) == 26
    for record in tcp_providers:
        if not record.ready:
            assert record.matrix.get("disposition") == "optional"
            continue
        policy = record.definition.metadata["network_policy"]
        dynamic_inputs = {
            str(value)
            for key in ("dynamic_tcp_inputs", "dynamic_url_inputs")
            for value in (policy.get(key) or ())
        }
        if dynamic_inputs:
            declared_inputs = {str(item.name) for item in record.definition.inputs}
            assert dynamic_inputs <= declared_inputs
            # Dynamic routes cannot be granted from an empty synthetic task:
            # the resolver must inspect the caller-supplied route artifact.
            continue
        task = {
            "task": {
                "id": f"manifest-grant-{record.id}",
                "capability": record.id,
                "spec": {"inputs": {}},
            }
        }
        token = host.request_provider_route_grant(task)
        assert token.startswith("provider-route-grant-v1.")


def test_runpod_session_dynamic_routes_match_declared_manifest_and_cli_inputs(tmp_path: Path):
    """Keep the one-shot session's host route and public CLI contracts aligned."""
    from astrid.packs.runpod.executors._common import build_parser

    definition = load_executor_manifest(
        PACKS / "runpod" / "executors" / "session" / "executor.yaml"
    )
    policy = definition.metadata["network_policy"]
    dynamic_inputs = {
        str(value)
        for key in ("dynamic_tcp_inputs", "dynamic_url_inputs")
        for value in (policy.get(key) or ())
    }
    declared_inputs = {str(item.name) for item in definition.inputs}

    assert dynamic_inputs <= declared_inputs
    # session provisions its own pod; pod_handle is an internal breadcrumb,
    # not a public session input or CLI option.
    assert not dynamic_inputs

    assert definition.command is not None
    command_inputs = {str(item.input) for item in definition.command.input_args}
    assert command_inputs == declared_inputs

    argv = ["session", "--produces-dir", str(tmp_path)]
    for item in definition.command.input_args:
        port = next(port for port in definition.inputs if port.name == item.input)
        if port.type == "integer":
            value = "1"
        elif item.input == "upload_mode":
            value = "sftp_walk"
        elif port.type in {"path", "file"}:
            value = str(tmp_path)
        else:
            value = "fixture"
        argv.extend([str(item.flag), value])

    parsed = build_parser().parse_args(argv)
    assert parsed.command == "session"
    assert all(hasattr(parsed, name) for name in command_inputs)


def test_required_provider_routes_report_truthful_availability_without_credentials():
    host = _provider_host(credentials={})
    required = [
        record
        for record in host.capabilities.values()
        if record.adapter.family == "provider" and record.matrix.get("disposition") == "required"
    ]
    assert len(required) == 14
    for record in required:
        if record.ready:
            # A locally authenticated binary-backed route may be ready without
            # environment credentials; do not manufacture an unavailable
            # result merely because this probe deliberately supplied none.
            assert not record.preflight["credentials"]["missing"]
            assert not (record.matrix.get("required_env") or ())
            assert record.preflight["binaries"]["ok"] is True
        else:
            assert (
                record.preflight["credentials"]["missing"]
                or record.preflight["binaries"]["missing"]
            )
