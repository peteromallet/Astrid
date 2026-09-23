"""Host-enforced worker boundary admission for timeline evaluations.

The coordinator may trust only a supervisor which lives outside the evaluated
worker, probes the exact runtime that will execute the model, and launches the
model through that same runtime. Missing files and refused ports observed in
the coordinator's own container are not isolation evidence.
"""

from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass, replace
from pathlib import PurePosixPath
from typing import Literal, Mapping, Protocol


class BoundaryUnavailable(RuntimeError):
    """The evaluated worker has no independently proven access boundary."""


@dataclass(frozen=True)
class ProtectedPath:
    """A real host path which must be absent or policy-denied in the worker."""

    path_id: str
    host_path: str
    worker_path: str


@dataclass(frozen=True)
class BoundaryRequirements:
    case_id: str
    worker_id: str
    model_boundary_id: str | None
    host_selected_case_path: str
    selected_case_path: str
    disposable_credential_path: str
    skill_path: str
    skill_sha256: str
    public_package_path: str
    public_package_digest: str | None
    disposable_endpoint: str
    disposable_realm_id: str | None
    disposable_runtime_receipt_id: str | None
    canonical_endpoint: str
    coordinator_paths: tuple[ProtectedPath, ...]
    source_paths: tuple[ProtectedPath, ...]
    sibling_paths: tuple[ProtectedPath, ...]
    agent_case_paths: tuple[ProtectedPath, ...]
    denied_endpoints: tuple[str, ...]
    skill_reference_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkerAttestation:
    """Observation issued by a host supervisor outside the worker runtime."""

    worker_id: str
    boundary_id: str
    supervisor_boundary_id: str
    isolation_scope: Literal["cross_boundary", "same_container", "same_process"]
    enforcement: Literal["container", "vm", "os_sandbox"]
    runtime_receipt_id: str
    policy_digest: str
    mount_policy_digest: str
    network_policy_digest: str
    selected_case_path: str
    public_package_path: str
    public_package_digest: str
    disposable_realm_id: str
    disposable_runtime_receipt_id: str


@dataclass(frozen=True)
class AccessProbe:
    probe_id: str
    kind: Literal[
        "read_path", "write_path", "sha256_path", "runtime_handshake", "http_get",
        "python_module_help", "python_import",
    ]
    target: str
    expected: Literal["allow", "deny"]
    expected_sha256: str | None = None
    expected_realm_id: str | None = None
    expected_runtime_receipt_id: str | None = None


@dataclass(frozen=True)
class ProbeObservation:
    worker_id: str
    boundary_id: str
    runtime_receipt_id: str
    challenge: str
    probe_id: str
    observed: Literal["allow", "deny", "error"]
    sha256: str | None = None
    realm_id: str | None = None
    disposable_runtime_receipt_id: str | None = None
    resolved_path: str | None = None
    denial_source: Literal["filesystem_policy", "not_mounted", "network_policy", "not_routable"] | None = None


@dataclass(frozen=True)
class HostPathObservation:
    worker_id: str
    supervisor_boundary_id: str
    challenge: str
    path_id: str
    host_path: str
    observed: Literal["file", "directory", "missing", "error"]
    identity_digest: str | None = None
    mount_policy_digest: str | None = None


@dataclass(frozen=True)
class BoundaryReceipt:
    case_id: str
    worker_id: str
    boundary_id: str
    supervisor_boundary_id: str
    isolation_scope: Literal["cross_boundary"]
    runtime_receipt_id: str
    challenge: str
    selected_case_path: str
    policy_digest: str
    mount_policy_digest: str
    network_policy_digest: str
    public_package_path: str
    public_package_digest: str
    disposable_runtime_receipt_id: str
    protected_paths: tuple[HostPathObservation, ...]
    probes: tuple[ProbeObservation, ...]
    status: Literal["pass"] = "pass"

    def as_dict(self) -> dict[str, object]:
        """Redacted coordinator evidence; never contains credential bytes."""
        return asdict(self)


@dataclass(frozen=True)
class WorkerLaunchRequest:
    worker_id: str
    boundary_id: str
    runtime_receipt_id: str
    challenge: str
    public_package_path: str
    public_package_digest: str
    argv: tuple[str, ...]
    cwd: str
    environment: Mapping[str, str]
    timeout_seconds: float


@dataclass(frozen=True)
class WorkerLaunchObservation:
    worker_id: str
    boundary_id: str
    runtime_receipt_id: str
    challenge: str
    status: Literal["completed", "failed", "timeout", "unavailable"]
    returncode: int | None
    elapsed_seconds: float
    stdout: str = ""
    stderr: str = ""


class BoundarySupervisor(Protocol):
    """Trusted host adapter for both probes and the evaluated model launch."""

    def inspect_worker(self, worker_id: str) -> WorkerAttestation: ...

    def inspect_host_path(
        self, worker_id: str, challenge: str, path: ProtectedPath,
    ) -> HostPathObservation: ...

    def run_access_probe(
        self, worker_id: str, challenge: str, probe: AccessProbe,
    ) -> ProbeObservation: ...

    def launch_worker(self, request: WorkerLaunchRequest) -> WorkerLaunchObservation: ...


def pin_worker_boundary(
    supervisor: BoundarySupervisor | None, requirements: BoundaryRequirements,
) -> BoundaryRequirements:
    """Resolve host-created identities, then require exact values thereafter.

    Container IDs and disposable Runtime receipts do not exist when the static
    coordinator manifest is authored. The trusted host may supply them once;
    ``prove_worker_boundary`` then performs only exact comparisons, and the
    launch request rechecks the resulting receipt.
    """
    if supervisor is None:
        raise BoundaryUnavailable("no host worker supervisor is available; model launch is denied")
    attestation = supervisor.inspect_worker(requirements.worker_id)
    if not isinstance(attestation, WorkerAttestation):
        raise BoundaryUnavailable("host supervisor returned no typed worker attestation")
    expected = (
        ("model_boundary_id", requirements.model_boundary_id, attestation.boundary_id),
        ("public_package_digest", requirements.public_package_digest, attestation.public_package_digest),
        ("disposable_realm_id", requirements.disposable_realm_id, attestation.disposable_realm_id),
        (
            "disposable_runtime_receipt_id",
            requirements.disposable_runtime_receipt_id,
            attestation.disposable_runtime_receipt_id,
        ),
    )
    for field, requested, observed in expected:
        if requested is not None and requested != observed:
            raise BoundaryUnavailable(f"host worker attestation changed requested {field}")
        _required(observed, f"host attestation {field}")
    if attestation.public_package_path != requirements.public_package_path:
        raise BoundaryUnavailable("host worker attestation changed requested public_package_path")
    return replace(
        requirements,
        model_boundary_id=attestation.boundary_id,
        public_package_digest=attestation.public_package_digest,
        disposable_realm_id=attestation.disposable_realm_id,
        disposable_runtime_receipt_id=attestation.disposable_runtime_receipt_id,
    )


def _required(value: str | None, field: str) -> None:
    if not isinstance(value, str) or not value:
        raise BoundaryUnavailable(f"boundary requirements omitted {field}")


def _protected_paths(requirements: BoundaryRequirements) -> tuple[tuple[str, ProtectedPath], ...]:
    groups = (
        ("coordinator", requirements.coordinator_paths),
        ("source", requirements.source_paths),
        ("sibling", requirements.sibling_paths),
        ("agent-case", requirements.agent_case_paths),
    )
    if any(not values for _label, values in groups):
        raise BoundaryUnavailable(
            "boundary requires coordinator, source, sibling, and agent-case protected paths"
        )
    flattened: list[tuple[str, ProtectedPath]] = []
    seen_ids: set[str] = set()
    seen_worker_paths: set[str] = set()
    selected_path = PurePosixPath(requirements.selected_case_path)
    for label, values in groups:
        for index, path in enumerate(values):
            if not isinstance(path, ProtectedPath):
                raise BoundaryUnavailable(f"{label}_paths[{index}] is not a typed protected path")
            for field in ("path_id", "host_path", "worker_path"):
                _required(getattr(path, field), f"{label}_paths[{index}].{field}")
            if path.path_id in seen_ids:
                raise BoundaryUnavailable(f"duplicate protected path id: {path.path_id}")
            worker_path = PurePosixPath(path.worker_path)
            if path.worker_path in seen_worker_paths:
                raise BoundaryUnavailable(f"duplicate protected worker path: {path.worker_path}")
            if worker_path == selected_path or selected_path in worker_path.parents:
                raise BoundaryUnavailable(
                    f"protected path {path.path_id} overlaps the selected case workspace"
                )
            seen_ids.add(path.path_id)
            seen_worker_paths.add(path.worker_path)
            flattened.append((label, path))
    return tuple(flattened)


def _probe_plan(requirements: BoundaryRequirements) -> tuple[tuple[AccessProbe, ProtectedPath | None], ...]:
    for field in (
        "case_id", "worker_id", "model_boundary_id", "host_selected_case_path",
        "selected_case_path", "disposable_credential_path", "skill_path", "skill_sha256",
        "public_package_path", "public_package_digest", "disposable_endpoint", "disposable_realm_id",
        "disposable_runtime_receipt_id", "canonical_endpoint",
    ):
        _required(getattr(requirements, field), field)
    # The Runtime SDK and the supported RuntimeDaemon intentionally expose a
    # loopback URL.  Loopback by itself is not isolation evidence, but it is
    # valid when the host supervisor has separately proven the Runtime process
    # and worker network namespace (and the authenticated realm/receipt below).
    # Same-container synthetic health endpoints are rejected by the attested
    # worker/runtime identity and handshake probes, not by URL spelling.
    if not requirements.denied_endpoints:
        raise BoundaryUnavailable("boundary requires unrelated endpoint denial targets")
    if requirements.disposable_endpoint == requirements.canonical_endpoint:
        raise BoundaryUnavailable("disposable and canonical endpoints must differ")
    if requirements.canonical_endpoint in requirements.denied_endpoints:
        raise BoundaryUnavailable("canonical endpoint must use its dedicated denial probe")
    package_root = PurePosixPath(requirements.public_package_path)
    skill_path = PurePosixPath(requirements.skill_path)
    if package_root not in skill_path.parents:
        raise BoundaryUnavailable("rendering skill must come from the bounded public Astrid package")
    probes: list[tuple[AccessProbe, ProtectedPath | None]] = [
        (AccessProbe("selected-case-read", "read_path", requirements.selected_case_path, "allow"), None),
        (AccessProbe("selected-case-write", "write_path", requirements.selected_case_path, "allow"), None),
        (AccessProbe("disposable-credential-read", "read_path", requirements.disposable_credential_path, "allow"), None),
        (AccessProbe("skill-sha256", "sha256_path", requirements.skill_path, "allow", expected_sha256=requirements.skill_sha256), None),
        (AccessProbe("astrid-cli-help", "python_module_help", "astrid", "allow"), None),
        (AccessProbe("astrid-sdk-import", "python_import", "astrid.sdk", "allow"), None),
        (AccessProbe(
            "disposable-runtime", "runtime_handshake", requirements.disposable_endpoint, "allow",
            expected_realm_id=requirements.disposable_realm_id,
            expected_runtime_receipt_id=requirements.disposable_runtime_receipt_id,
        ), None),
        (AccessProbe("canonical-runtime-denied", "http_get", requirements.canonical_endpoint, "deny"), None),
    ]
    for index, path in enumerate(requirements.skill_reference_paths):
        _required(path, f"skill_reference_paths[{index}]")
        probes.append((AccessProbe(f"skill-reference-{index}-read", "read_path", path, "allow"), None))
    for label, path in _protected_paths(requirements):
        probes.append((AccessProbe(f"{label}-{path.path_id}-denied", "read_path", path.worker_path, "deny"), path))
    for index, endpoint in enumerate(requirements.denied_endpoints):
        _required(endpoint, f"denied_endpoints[{index}]")
        if endpoint == requirements.disposable_endpoint:
            raise BoundaryUnavailable("disposable endpoint cannot also be a denied endpoint")
        probes.append((AccessProbe(f"other-endpoint-{index}-denied", "http_get", endpoint, "deny"), None))
    return tuple(probes)


def prove_worker_boundary(
    supervisor: BoundarySupervisor | None, requirements: BoundaryRequirements,
) -> BoundaryReceipt:
    """Actively probe the exact cross-boundary runtime used for model launch."""
    if supervisor is None:
        raise BoundaryUnavailable("no host worker supervisor is available; model launch is denied")
    probes = _probe_plan(requirements)
    attestation = supervisor.inspect_worker(requirements.worker_id)
    if not isinstance(attestation, WorkerAttestation):
        raise BoundaryUnavailable("host supervisor returned no typed worker attestation")
    if attestation.isolation_scope != "cross_boundary":
        raise BoundaryUnavailable(
            f"worker evidence is {attestation.isolation_scope}, not cross-boundary isolation"
        )
    if attestation.supervisor_boundary_id == attestation.boundary_id:
        raise BoundaryUnavailable("host supervisor and worker report the same boundary identity")
    if (
        attestation.worker_id != requirements.worker_id
        or attestation.boundary_id != requirements.model_boundary_id
        or attestation.enforcement not in {"container", "vm", "os_sandbox"}
        or not attestation.supervisor_boundary_id
        or not attestation.runtime_receipt_id
        or not attestation.policy_digest
        or not attestation.mount_policy_digest
        or not attestation.network_policy_digest
        or attestation.selected_case_path != requirements.selected_case_path
        or attestation.public_package_path != requirements.public_package_path
        or attestation.public_package_digest != requirements.public_package_digest
        or attestation.disposable_realm_id != requirements.disposable_realm_id
        or attestation.disposable_runtime_receipt_id != requirements.disposable_runtime_receipt_id
    ):
        raise BoundaryUnavailable("host worker attestation does not match selected case and model boundary")
    challenge = secrets.token_hex(16)
    host_observations: list[HostPathObservation] = []
    observations: list[ProbeObservation] = []
    for probe, protected in probes:
        if protected is not None:
            host_observed = supervisor.inspect_host_path(requirements.worker_id, challenge, protected)
            if not isinstance(host_observed, HostPathObservation):
                raise BoundaryUnavailable(f"protected path {protected.path_id} has no typed host observation")
            if (
                host_observed.worker_id != requirements.worker_id
                or host_observed.supervisor_boundary_id != attestation.supervisor_boundary_id
                or host_observed.challenge != challenge
                or host_observed.path_id != protected.path_id
                or host_observed.host_path != protected.host_path
                or host_observed.mount_policy_digest != attestation.mount_policy_digest
            ):
                raise BoundaryUnavailable(f"protected path {protected.path_id} was inspected by the wrong host boundary")
            if host_observed.observed not in {"file", "directory"} or not host_observed.identity_digest:
                raise BoundaryUnavailable(
                    f"protected host path {protected.path_id} is missing or has no identity witness"
                )
            host_observations.append(host_observed)
        observed = supervisor.run_access_probe(requirements.worker_id, challenge, probe)
        if not isinstance(observed, ProbeObservation):
            raise BoundaryUnavailable(f"worker probe {probe.probe_id} returned no typed observation")
        if (
            observed.worker_id != requirements.worker_id
            or observed.boundary_id != attestation.boundary_id
            or observed.runtime_receipt_id != attestation.runtime_receipt_id
            or observed.challenge != challenge
            or observed.probe_id != probe.probe_id
        ):
            raise BoundaryUnavailable(f"worker probe {probe.probe_id} ran in a different boundary or challenge")
        if observed.observed != probe.expected:
            raise BoundaryUnavailable(f"worker probe {probe.probe_id} observed {observed.observed}, expected {probe.expected}")
        if probe.expected == "deny":
            permitted_denials = (
                {"filesystem_policy", "not_mounted"}
                if probe.kind == "read_path" else {"network_policy"}
            )
            if observed.denial_source not in permitted_denials:
                raise BoundaryUnavailable(f"worker probe {probe.probe_id} lacks policy-backed denial evidence")
        elif observed.denial_source is not None:
            raise BoundaryUnavailable(f"allowed worker probe {probe.probe_id} contains denial evidence")
        if probe.expected_sha256 and observed.sha256 != probe.expected_sha256:
            raise BoundaryUnavailable("worker skill hash differs inside the selected boundary")
        if probe.kind in {"python_module_help", "python_import"}:
            if not observed.resolved_path:
                raise BoundaryUnavailable(f"worker probe {probe.probe_id} did not resolve the public package")
            resolved = PurePosixPath(observed.resolved_path)
            public_root = PurePosixPath(attestation.public_package_path)
            if public_root not in resolved.parents:
                raise BoundaryUnavailable(
                    f"worker probe {probe.probe_id} resolved outside the public package"
                )
        if probe.expected_realm_id and observed.realm_id != probe.expected_realm_id:
            raise BoundaryUnavailable("disposable Runtime handshake has the wrong realm")
        if (
            probe.expected_runtime_receipt_id
            and observed.disposable_runtime_receipt_id != probe.expected_runtime_receipt_id
        ):
            raise BoundaryUnavailable("disposable Runtime handshake lacks the pinned host receipt")
        observations.append(observed)
    return BoundaryReceipt(
        case_id=requirements.case_id,
        worker_id=requirements.worker_id,
        boundary_id=attestation.boundary_id,
        supervisor_boundary_id=attestation.supervisor_boundary_id,
        isolation_scope="cross_boundary",
        runtime_receipt_id=attestation.runtime_receipt_id,
        challenge=challenge,
        selected_case_path=attestation.selected_case_path,
        policy_digest=attestation.policy_digest,
        mount_policy_digest=attestation.mount_policy_digest,
        network_policy_digest=attestation.network_policy_digest,
        public_package_path=attestation.public_package_path,
        public_package_digest=attestation.public_package_digest,
        disposable_runtime_receipt_id=attestation.disposable_runtime_receipt_id,
        protected_paths=tuple(host_observations),
        probes=tuple(observations),
    )


def launch_in_proven_boundary(
    supervisor: BoundarySupervisor | None,
    receipt: BoundaryReceipt,
    request: WorkerLaunchRequest,
) -> WorkerLaunchObservation:
    """Launch via the same host supervisor/runtime proven by ``receipt``."""
    if supervisor is None:
        raise BoundaryUnavailable("no host worker supervisor is available for model launch")
    if (
        request.worker_id != receipt.worker_id
        or request.boundary_id != receipt.boundary_id
        or request.runtime_receipt_id != receipt.runtime_receipt_id
        or request.challenge != receipt.challenge
        or request.public_package_path != receipt.public_package_path
        or request.public_package_digest != receipt.public_package_digest
        or request.cwd != receipt.selected_case_path
        or not request.argv
    ):
        raise BoundaryUnavailable(
            "model launch request is not bound to the proven worker boundary; "
            "request does not match the proven receipt"
        )
    cwd_indices = [index for index, value in enumerate(request.argv) if value == "--cwd"]
    if (
        len(cwd_indices) != 1
        or cwd_indices[0] + 1 >= len(request.argv)
        or request.argv[cwd_indices[0] + 1] != receipt.selected_case_path
    ):
        raise BoundaryUnavailable("model argv is not bound to the selected worker case path")
    observed = supervisor.launch_worker(request)
    if not isinstance(observed, WorkerLaunchObservation):
        raise BoundaryUnavailable("host supervisor returned no typed model launch observation")
    if (
        observed.worker_id != receipt.worker_id
        or observed.boundary_id != receipt.boundary_id
        or observed.runtime_receipt_id != receipt.runtime_receipt_id
        or observed.challenge != receipt.challenge
    ):
        raise BoundaryUnavailable("model launch ran outside the proven worker boundary")
    return observed


__all__ = [
    "AccessProbe", "BoundaryReceipt", "BoundaryRequirements", "BoundarySupervisor",
    "BoundaryUnavailable", "HostPathObservation", "ProbeObservation", "ProtectedPath",
    "WorkerAttestation", "WorkerLaunchObservation", "WorkerLaunchRequest",
    "launch_in_proven_boundary", "pin_worker_boundary", "prove_worker_boundary",
]
