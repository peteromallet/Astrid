"""Coordinator-side worker boundary admission for timeline evaluations.

The native launcher must call this with a host supervisor that executes probes
inside the exact worker boundary used for the model. A JSON isolation claim or
an agent-written result cannot implement this protocol. No default supervisor
or local-process fallback is supplied.
"""

from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass
from typing import Literal, Protocol


class BoundaryUnavailable(RuntimeError):
    """The evaluated worker has no independently proven access boundary."""


@dataclass(frozen=True)
class BoundaryRequirements:
    case_id: str
    worker_id: str
    model_boundary_id: str
    selected_case_path: str
    disposable_credential_path: str
    skill_path: str
    skill_sha256: str
    public_package_digest: str
    disposable_endpoint: str
    disposable_realm_id: str
    canonical_endpoint: str
    canonical_paths: tuple[str, ...]
    private_paths: tuple[str, ...]
    sibling_paths: tuple[str, ...]
    denied_endpoints: tuple[str, ...]
    skill_reference_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkerAttestation:
    """Host-supervisor observation, not a field from the evaluated worker."""

    worker_id: str
    boundary_id: str
    enforcement: Literal["container", "vm", "os_sandbox"]
    policy_digest: str
    selected_case_path: str
    public_package_digest: str


@dataclass(frozen=True)
class AccessProbe:
    probe_id: str
    kind: Literal["read_path", "write_path", "sha256_path", "runtime_handshake", "http_get"]
    target: str
    expected: Literal["allow", "deny"]
    expected_sha256: str | None = None
    expected_realm_id: str | None = None


@dataclass(frozen=True)
class ProbeObservation:
    worker_id: str
    boundary_id: str
    challenge: str
    probe_id: str
    observed: Literal["allow", "deny", "error"]
    sha256: str | None = None
    realm_id: str | None = None
    # A failed connection or missing file alone does not prove policy denial.
    denial_source: Literal["filesystem_policy", "not_mounted", "network_policy", "not_routable"] | None = None


@dataclass(frozen=True)
class BoundaryReceipt:
    case_id: str
    worker_id: str
    boundary_id: str
    challenge: str
    policy_digest: str
    public_package_digest: str
    probes: tuple[ProbeObservation, ...]
    status: Literal["pass"] = "pass"

    def as_dict(self) -> dict[str, object]:
        """Redacted coordinator evidence; never contains credential bytes."""
        return asdict(self)


class BoundarySupervisor(Protocol):
    """Trusted host adapter for the same worker later used by model launch."""

    def inspect_worker(self, worker_id: str) -> WorkerAttestation: ...

    def run_access_probe(
        self, worker_id: str, challenge: str, probe: AccessProbe,
    ) -> ProbeObservation: ...


def _required(value: str, field: str) -> None:
    if not isinstance(value, str) or not value:
        raise BoundaryUnavailable(f"boundary requirements omitted {field}")


def _probe_plan(requirements: BoundaryRequirements) -> tuple[AccessProbe, ...]:
    for field in (
        "case_id", "worker_id", "model_boundary_id", "selected_case_path",
        "disposable_credential_path", "skill_path", "skill_sha256",
        "public_package_digest", "disposable_endpoint", "disposable_realm_id",
        "canonical_endpoint",
    ):
        _required(getattr(requirements, field), field)
    if not requirements.canonical_paths or not requirements.private_paths or not requirements.sibling_paths:
        raise BoundaryUnavailable("boundary requires canonical, private, and sibling denial targets")
    if not requirements.denied_endpoints:
        raise BoundaryUnavailable("boundary requires unrelated endpoint denial targets")
    if requirements.disposable_endpoint == requirements.canonical_endpoint:
        raise BoundaryUnavailable("disposable and canonical endpoints must differ")
    if requirements.canonical_endpoint in requirements.denied_endpoints:
        raise BoundaryUnavailable("canonical endpoint must use its dedicated denial probe")
    probes = [
        AccessProbe("selected-case-read", "read_path", requirements.selected_case_path, "allow"),
        AccessProbe("selected-case-write", "write_path", requirements.selected_case_path, "allow"),
        AccessProbe("disposable-credential-read", "read_path", requirements.disposable_credential_path, "allow"),
        AccessProbe("skill-sha256", "sha256_path", requirements.skill_path, "allow", expected_sha256=requirements.skill_sha256),
        AccessProbe("disposable-runtime", "runtime_handshake", requirements.disposable_endpoint, "allow", expected_realm_id=requirements.disposable_realm_id),
        AccessProbe("canonical-runtime-denied", "http_get", requirements.canonical_endpoint, "deny"),
    ]
    for index, path in enumerate(requirements.skill_reference_paths):
        _required(path, f"skill_reference_paths[{index}]")
        probes.append(AccessProbe(f"skill-reference-{index}-read", "read_path", path, "allow"))
    for label, values in (
        ("canonical", requirements.canonical_paths),
        ("private", requirements.private_paths),
        ("sibling", requirements.sibling_paths),
    ):
        for index, path in enumerate(values):
            _required(path, f"{label}_paths[{index}]")
            probes.append(AccessProbe(f"{label}-{index}-denied", "read_path", path, "deny"))
    for index, endpoint in enumerate(requirements.denied_endpoints):
        _required(endpoint, f"denied_endpoints[{index}]")
        if endpoint == requirements.disposable_endpoint:
            raise BoundaryUnavailable("disposable endpoint cannot also be a denied endpoint")
        probes.append(AccessProbe(f"other-endpoint-{index}-denied", "http_get", endpoint, "deny"))
    return tuple(probes)


def prove_worker_boundary(
    supervisor: BoundarySupervisor | None, requirements: BoundaryRequirements,
) -> BoundaryReceipt:
    """Actively probe the exact host boundary before any evaluated model call.

    The caller must use the same `model_boundary_id` when launching the model.
    This helper validates observations from a coordinator-trusted supervisor;
    it does not create a container or certify an arbitrary JSON descriptor.
    """
    if supervisor is None:
        raise BoundaryUnavailable("no host worker supervisor is available; model launch is denied")
    probes = _probe_plan(requirements)
    attestation = supervisor.inspect_worker(requirements.worker_id)
    if not isinstance(attestation, WorkerAttestation):
        raise BoundaryUnavailable("host supervisor returned no typed worker attestation")
    if (
        attestation.worker_id != requirements.worker_id
        or attestation.boundary_id != requirements.model_boundary_id
        or attestation.enforcement not in {"container", "vm", "os_sandbox"}
        or not attestation.policy_digest
        or attestation.selected_case_path != requirements.selected_case_path
        or attestation.public_package_digest != requirements.public_package_digest
    ):
        raise BoundaryUnavailable("host worker attestation does not match selected case and model boundary")
    challenge = secrets.token_hex(16)
    observations: list[ProbeObservation] = []
    for probe in probes:
        observed = supervisor.run_access_probe(requirements.worker_id, challenge, probe)
        if not isinstance(observed, ProbeObservation):
            raise BoundaryUnavailable(f"worker probe {probe.probe_id} returned no typed observation")
        if (
            observed.worker_id != requirements.worker_id
            or observed.boundary_id != attestation.boundary_id
            or observed.challenge != challenge
            or observed.probe_id != probe.probe_id
        ):
            raise BoundaryUnavailable(f"worker probe {probe.probe_id} ran in a different boundary or challenge")
        if observed.observed != probe.expected:
            raise BoundaryUnavailable(f"worker probe {probe.probe_id} observed {observed.observed}, expected {probe.expected}")
        if probe.expected == "deny":
            permitted_denials = (
                {"filesystem_policy", "not_mounted"}
                if probe.kind == "read_path" else {"network_policy", "not_routable"}
            )
            if observed.denial_source not in permitted_denials:
                raise BoundaryUnavailable(f"worker probe {probe.probe_id} lacks policy-backed denial evidence")
        elif observed.denial_source is not None:
            raise BoundaryUnavailable(f"allowed worker probe {probe.probe_id} contains denial evidence")
        if probe.expected_sha256 and observed.sha256 != probe.expected_sha256:
            raise BoundaryUnavailable("worker skill hash differs inside the selected boundary")
        if probe.expected_realm_id and observed.realm_id != probe.expected_realm_id:
            raise BoundaryUnavailable("disposable Runtime handshake has the wrong realm")
        observations.append(observed)
    return BoundaryReceipt(
        case_id=requirements.case_id,
        worker_id=requirements.worker_id,
        boundary_id=attestation.boundary_id,
        challenge=challenge,
        policy_digest=attestation.policy_digest,
        public_package_digest=attestation.public_package_digest,
        probes=tuple(observations),
    )


__all__ = [
    "AccessProbe", "BoundaryReceipt", "BoundaryRequirements", "BoundarySupervisor",
    "BoundaryUnavailable", "ProbeObservation", "WorkerAttestation", "prove_worker_boundary",
]
