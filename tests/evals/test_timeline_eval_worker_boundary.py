from dataclasses import replace

import pytest

from evals.timeline.worker_boundary import (
    BoundaryRequirements,
    BoundaryUnavailable,
    HostFinalCapture,
    HostPathObservation,
    ProbeObservation,
    ProtectedPath,
    WorkerAttestation,
    WorkerLaunchObservation,
    WorkerLaunchRequest,
    host_final_capture_digest,
    launch_in_proven_boundary,
    pin_worker_boundary,
    prove_worker_boundary,
)


def _protected(path_id: str, category: str) -> ProtectedPath:
    return ProtectedPath(
        path_id=path_id,
        host_path=f"/host/{category}/{path_id}",
        worker_path=f"/forbidden/{category}/{path_id}",
    )


def _requirements() -> BoundaryRequirements:
    return BoundaryRequirements(
        case_id="A01",
        worker_id="worker-a01",
        execution_mode="runtime_edit",
        model_boundary_id="container-immutable-identity",
        host_selected_case_path="/host/attempt/cases/A01",
        selected_case_path="/case/A01",
        disposable_credential_path="/case/A01/runtime-credential.json",
        skill_path="/opt/astrid-public/astrid/packs/video_editing/skill/SKILL.md",
        skill_sha256="1" * 64,
        public_package_path="/opt/astrid-public",
        public_package_digest="sha256:" + "2" * 64,
        disposable_endpoint="https://disposable-runtime.example/v1",
        disposable_realm_id="disposable-realm",
        disposable_runtime_receipt_id="runtime-realm-receipt-1",
        canonical_endpoint="https://canonical-runtime.example/v1",
        coordinator_paths=(_protected("coordinator-evidence", "coordinator"),),
        source_paths=(_protected("source-checkout", "source"),),
        sibling_paths=(_protected("sibling-a02", "sibling"),),
        agent_case_paths=(_protected("prior-attempt", "agent-case"),),
        denied_endpoints=("http://127.0.0.1:63541",),
        skill_reference_paths=("/case/A01/public-skill/REFERENCES.md",),
    )


class Supervisor:
    def __init__(self, requirements: BoundaryRequirements):
        self.requirements = requirements
        self.probes = []
        self.override = None
        self.host_override = None
        self.launch_override = None

    def inspect_worker(self, worker_id):
        r = self.requirements
        return WorkerAttestation(
            worker_id=worker_id,
            execution_mode=r.execution_mode,
            boundary_id=r.model_boundary_id,
            supervisor_boundary_id="agentbox-host-supervisor",
            isolation_scope="cross_boundary",
            enforcement="container",
            runtime_receipt_id="container-runtime-receipt-1",
            policy_digest="sha256:" + "3" * 64,
            mount_policy_digest="sha256:" + "4" * 64,
            network_policy_digest="sha256:" + "5" * 64,
            selected_case_path=r.selected_case_path,
            public_package_path=r.public_package_path,
            public_package_digest=r.public_package_digest,
            disposable_realm_id=r.disposable_realm_id,
            disposable_runtime_receipt_id=r.disposable_runtime_receipt_id,
        )

    def inspect_host_path(self, worker_id, challenge, path):
        value = HostPathObservation(
            worker_id=worker_id,
            supervisor_boundary_id="agentbox-host-supervisor",
            challenge=challenge,
            path_id=path.path_id,
            host_path=path.host_path,
            observed="directory",
            identity_digest="sha256:" + "6" * 64,
            mount_policy_digest="sha256:" + "4" * 64,
        )
        return self.host_override(path, value) if self.host_override else value

    def run_access_probe(self, worker_id, challenge, probe):
        self.probes.append(probe)
        value = ProbeObservation(
            worker_id=worker_id,
            boundary_id=self.requirements.model_boundary_id,
            runtime_receipt_id="container-runtime-receipt-1",
            challenge=challenge,
            probe_id=probe.probe_id,
            observed=probe.expected,
            sha256=probe.expected_sha256,
            realm_id=probe.expected_realm_id,
            disposable_runtime_receipt_id=probe.expected_runtime_receipt_id,
            resolved_path=(
                "/opt/astrid-public/astrid/sdk/__init__.py"
                if probe.kind == "python_import"
                else "/opt/astrid-public/astrid/__init__.py"
                if probe.kind == "python_module_help" else None
            ),
            denial_source=(
                "not_mounted" if probe.expected == "deny" and probe.kind == "read_path"
                else "network_policy" if probe.expected == "deny" else None
            ),
        )
        return self.override(probe, value) if self.override else value

    def launch_worker(self, request):
        target = request.final_capture_target or {}
        timeline_id = str(target.get("timeline_id", "timeline-test"))
        head = "head-after"
        capture = HostFinalCapture(
            case_id=request.case_id,
            worker_id=request.worker_id,
            execution_mode=request.execution_mode,
            boundary_id=request.boundary_id,
            runtime_receipt_id=request.runtime_receipt_id,
            challenge=request.challenge,
            status="captured",
            worker_stopped=True,
            descendants_stopped=True,
            disposable_realm_id=self.requirements.disposable_realm_id,
            disposable_runtime_receipt_id=self.requirements.disposable_runtime_receipt_id,
            target_project_id=target.get("project_id", "project-test"),
            target_timeline_id=timeline_id,
            head_revision_id=head,
            timeline_heads={timeline_id: head},
            closures={timeline_id: {"head_revision_id": head}},
            case_tree_digest=None,
            capture_sha256="",
            realm_retired=True,
            write_denied=True,
        )
        capture = replace(capture, capture_sha256=host_final_capture_digest(capture))
        value = WorkerLaunchObservation(
            worker_id=request.worker_id,
            boundary_id=request.boundary_id,
            runtime_receipt_id=request.runtime_receipt_id,
            challenge=request.challenge,
            status="completed",
            returncode=0,
            elapsed_seconds=0.2,
            stdout='{"event":"done"}\n',
            worker_stopped=True,
            descendants_stopped=True,
            final_capture=capture,
        )
        return self.launch_override(request, value) if self.launch_override else value


def test_cross_boundary_probes_bind_real_host_paths_runtime_and_model_boundary():
    requirements = _requirements()
    supervisor = Supervisor(requirements)
    receipt = prove_worker_boundary(supervisor, requirements)
    assert receipt.status == "pass"
    assert receipt.isolation_scope == "cross_boundary"
    assert receipt.boundary_id == requirements.model_boundary_id
    assert {probe.probe_id for probe in receipt.probes} == {
        "selected-case-read", "selected-case-write", "disposable-credential-read",
        "skill-sha256", "astrid-cli-help", "astrid-sdk-import",
        "disposable-runtime", "canonical-runtime-denied",
        "skill-reference-0-read", "coordinator-coordinator-evidence-denied",
        "source-source-checkout-denied", "sibling-sibling-a02-denied",
        "agent-case-prior-attempt-denied", "other-endpoint-0-denied",
    }
    assert {row.path_id for row in receipt.protected_paths} == {
        "coordinator-evidence", "source-checkout", "sibling-a02", "prior-attempt",
    }
    assert "secret-credential-bytes" not in str(receipt.as_dict())


def test_offline_boundary_has_no_runtime_credential_or_handshake_and_captures_after_stop():
    requirements = replace(
        _requirements(), case_id="L01", execution_mode="offline",
        disposable_credential_path=None, disposable_endpoint=None,
        disposable_realm_id=None, disposable_runtime_receipt_id=None,
    )
    supervisor = Supervisor(requirements)
    receipt = prove_worker_boundary(supervisor, requirements)
    probe_ids = {probe.probe_id for probe in receipt.probes}
    assert "disposable-credential-read" not in probe_ids
    assert "disposable-runtime" not in probe_ids
    assert "canonical-runtime-denied" in probe_ids
    request = WorkerLaunchRequest(
        case_id="L01", worker_id=requirements.worker_id, execution_mode="offline",
        boundary_id=receipt.boundary_id, runtime_receipt_id=receipt.runtime_receipt_id,
        challenge=receipt.challenge, public_package_path=receipt.public_package_path,
        public_package_digest=receipt.public_package_digest,
        argv=("omp", "--cwd", requirements.selected_case_path, "--no-session"),
        cwd=requirements.selected_case_path, environment={}, timeout_seconds=10,
    )
    def offline_capture(_request, value):
        capture = replace(
            value.final_capture,
            case_id="L01", execution_mode="offline", status="offline_captured",
            disposable_realm_id=None, disposable_runtime_receipt_id=None,
            target_project_id=None, target_timeline_id=None, head_revision_id=None,
            timeline_heads={}, closures={}, case_tree_digest="sha256:case-tree",
            realm_retired=None, capture_sha256="",
        )
        return replace(value, final_capture=replace(
            capture, capture_sha256=host_final_capture_digest(capture),
        ))

    supervisor.launch_override = offline_capture
    observed = launch_in_proven_boundary(supervisor, receipt, request)
    assert observed.final_capture.status == "offline_captured"


def test_offline_boundary_rejects_any_runtime_authority():
    requirements = replace(
        _requirements(), execution_mode="offline", disposable_endpoint=None,
        disposable_realm_id=None, disposable_runtime_receipt_id=None,
    )
    with pytest.raises(BoundaryUnavailable, match="offline boundary must omit Runtime"):
        prove_worker_boundary(Supervisor(requirements), requirements)


def test_no_host_supervisor_or_incomplete_protected_targets_fail_closed():
    requirements = _requirements()
    with pytest.raises(BoundaryUnavailable, match="no host worker supervisor"):
        prove_worker_boundary(None, requirements)
    with pytest.raises(BoundaryUnavailable, match="coordinator, source, sibling, and agent-case"):
        prove_worker_boundary(Supervisor(requirements), replace(requirements, source_paths=()))


def test_missing_placeholder_host_path_cannot_count_as_not_mounted_isolation():
    requirements = _requirements()
    supervisor = Supervisor(requirements)
    supervisor.host_override = lambda _path, value: replace(
        value, observed="missing", identity_digest=None,
    )
    with pytest.raises(BoundaryUnavailable, match="missing or has no identity witness"):
        prove_worker_boundary(supervisor, requirements)


def test_protected_tree_cannot_hide_inside_selected_case_workspace():
    requirements = _requirements()
    overlapping = ProtectedPath(
        "coordinator-overlap", "/host/coordinator", "/case/A01/coordinator",
    )
    requirements = replace(requirements, coordinator_paths=(overlapping,))
    with pytest.raises(BoundaryUnavailable, match="overlaps the selected case workspace"):
        prove_worker_boundary(Supervisor(requirements), requirements)


def test_refused_connection_without_network_policy_witness_is_not_a_denial():
    requirements = _requirements()
    supervisor = Supervisor(requirements)
    supervisor.override = lambda probe, value: replace(
        value, denial_source="not_routable",
    ) if probe.probe_id == "canonical-runtime-denied" else value
    with pytest.raises(BoundaryUnavailable, match="policy-backed denial"):
        prove_worker_boundary(supervisor, requirements)


@pytest.mark.parametrize("failure", ["connection_error", "timeout"])
def test_connection_errors_and_timeouts_are_errors_not_denial_evidence(failure):
    requirements = _requirements()
    supervisor = Supervisor(requirements)
    supervisor.override = lambda probe, value: replace(
        value, observed="error", denial_source=None,
    ) if probe.probe_id == "canonical-runtime-denied" else value
    with pytest.raises(BoundaryUnavailable, match="observed error, expected deny"):
        prove_worker_boundary(supervisor, requirements)


def test_same_container_evidence_is_labelled_non_isolated_and_rejected():
    requirements = _requirements()

    class SameContainer(Supervisor):
        def inspect_worker(self, worker_id):
            return replace(
                super().inspect_worker(worker_id),
                isolation_scope="same_container",
                supervisor_boundary_id=requirements.model_boundary_id,
            )

    with pytest.raises(BoundaryUnavailable, match="same_container, not cross-boundary"):
        prove_worker_boundary(SameContainer(requirements), requirements)


def test_loopback_runtime_is_admitted_only_with_a_pinned_host_receipt():
    requirements = replace(
        _requirements(),
        disposable_endpoint="http://127.0.0.1:18787",
        disposable_runtime_receipt_id="",
    )
    with pytest.raises(BoundaryUnavailable, match="disposable_runtime_receipt_id"):
        prove_worker_boundary(Supervisor(requirements), requirements)

    requirements = replace(
        _requirements(),
        disposable_endpoint="http://127.0.0.1:18787",
    )
    receipt = prove_worker_boundary(Supervisor(requirements), requirements)
    assert receipt.status == "pass"


@pytest.mark.parametrize(
    ("probe_id", "change", "message"),
    [
        ("canonical-runtime-denied", {"observed": "allow", "denial_source": None}, "observed allow"),
        ("source-source-checkout-denied", {"denial_source": None}, "policy-backed denial"),
        ("skill-sha256", {"sha256": "0" * 64}, "skill hash differs"),
        ("disposable-runtime", {"realm_id": "canonical-realm"}, "wrong realm"),
        ("disposable-runtime", {"disposable_runtime_receipt_id": "synthetic"}, "pinned host receipt"),
        ("sibling-sibling-a02-denied", {"boundary_id": "other-container"}, "different boundary"),
        ("astrid-sdk-import", {"resolved_path": "/case/A01/fake/astrid/sdk/__init__.py"}, "outside the public package"),
    ],
)
def test_worker_boundary_rejects_false_denials_wrong_runtime_and_identity(probe_id, change, message):
    requirements = _requirements()
    supervisor = Supervisor(requirements)
    supervisor.override = lambda probe, value: replace(value, **change) if probe.probe_id == probe_id else value
    with pytest.raises(BoundaryUnavailable, match=message):
        prove_worker_boundary(supervisor, requirements)


def test_model_launch_must_use_same_supervisor_challenge_and_runtime_receipt():
    requirements = _requirements()
    supervisor = Supervisor(requirements)
    receipt = prove_worker_boundary(supervisor, requirements)
    request = WorkerLaunchRequest(
        case_id=requirements.case_id,
        worker_id=requirements.worker_id,
        execution_mode=requirements.execution_mode,
        boundary_id=receipt.boundary_id,
        runtime_receipt_id=receipt.runtime_receipt_id,
        challenge=receipt.challenge,
        public_package_path=receipt.public_package_path,
        public_package_digest=receipt.public_package_digest,
        argv=("omp", "--cwd", requirements.selected_case_path, "--no-session"),
        cwd=requirements.selected_case_path,
        environment={},
        timeout_seconds=10,
        final_capture_target={"project_id": "project-test", "timeline_id": "timeline-test"},
    )
    assert launch_in_proven_boundary(supervisor, receipt, request).status == "completed"
    supervisor.launch_override = lambda _request, value: replace(value, challenge="stale")
    with pytest.raises(BoundaryUnavailable, match="outside the proven worker boundary"):
        launch_in_proven_boundary(supervisor, receipt, request)


def test_private_grading_requires_worker_and_descendants_stopped():
    requirements = _requirements()
    supervisor = Supervisor(requirements)
    receipt = prove_worker_boundary(supervisor, requirements)
    request = WorkerLaunchRequest(
        case_id=requirements.case_id,
        worker_id=requirements.worker_id,
        execution_mode=requirements.execution_mode,
        boundary_id=receipt.boundary_id,
        runtime_receipt_id=receipt.runtime_receipt_id,
        challenge=receipt.challenge,
        public_package_path=receipt.public_package_path,
        public_package_digest=receipt.public_package_digest,
        argv=("omp", "--cwd", requirements.selected_case_path, "--no-session"),
        cwd=requirements.selected_case_path,
        environment={},
        timeout_seconds=10,
        final_capture_target={"project_id": "project-test", "timeline_id": "timeline-test"},
    )
    supervisor.launch_override = lambda _request, value: replace(
        value, worker_stopped=False, descendants_stopped=False,
    )
    with pytest.raises(BoundaryUnavailable, match="descendants were not stopped"):
        launch_in_proven_boundary(supervisor, receipt, request)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"disposable_realm_id": "wrong-realm"}, "selected Runtime realm"),
        ({"target_timeline_id": "wrong-target"}, "selected Runtime realm"),
        ({"realm_retired": False}, "selected Runtime realm"),
        ({"write_denied": False}, "write-denial witness"),
    ],
)
def test_runtime_final_capture_must_match_target_realm_and_retirement(change, message):
    requirements = _requirements()
    supervisor = Supervisor(requirements)
    receipt = prove_worker_boundary(supervisor, requirements)
    request = WorkerLaunchRequest(
        case_id=requirements.case_id, worker_id=requirements.worker_id,
        execution_mode=requirements.execution_mode, boundary_id=receipt.boundary_id,
        runtime_receipt_id=receipt.runtime_receipt_id, challenge=receipt.challenge,
        public_package_path=receipt.public_package_path,
        public_package_digest=receipt.public_package_digest,
        argv=("omp", "--cwd", requirements.selected_case_path, "--no-session"),
        cwd=requirements.selected_case_path, environment={}, timeout_seconds=10,
        final_capture_target={"project_id": "project-test", "timeline_id": "timeline-test"},
    )
    def wrong_capture(_request, value):
        capture = replace(value.final_capture, **change, capture_sha256="")
        return replace(value, final_capture=replace(
            capture, capture_sha256=host_final_capture_digest(capture),
        ))

    supervisor.launch_override = wrong_capture
    with pytest.raises(BoundaryUnavailable, match=message):
        launch_in_proven_boundary(supervisor, receipt, request)


def test_attestation_must_name_exact_model_launch_boundary():
    requirements = _requirements()

    class WrongWorker(Supervisor):
        def inspect_worker(self, worker_id):
            return replace(super().inspect_worker(worker_id), boundary_id="preflight-container-only")

    with pytest.raises(BoundaryUnavailable, match="does not match selected case and model boundary"):
        prove_worker_boundary(WrongWorker(requirements), requirements)


def test_host_created_values_are_pinned_before_proof():
    requirements = replace(
        _requirements(),
        model_boundary_id=None,
        public_package_digest=None,
        disposable_realm_id=None,
        disposable_runtime_receipt_id=None,
    )

    class HostCreatedSupervisor(Supervisor):
        def inspect_worker(self, worker_id):
            return replace(
                super().inspect_worker(worker_id),
                boundary_id="docker:actual-worker",
                public_package_digest="sha256:actual-package",
                disposable_realm_id="actual-realm",
                disposable_runtime_receipt_id="runtime:actual-receipt",
            )

    supervisor = HostCreatedSupervisor(requirements)
    pinned = pin_worker_boundary(supervisor, requirements)
    assert pinned.model_boundary_id == "docker:actual-worker"
    assert pinned.public_package_digest == "sha256:actual-package"
    assert pinned.disposable_realm_id == "actual-realm"
    assert pinned.disposable_runtime_receipt_id == "runtime:actual-receipt"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"public_package_path": "/opt/stale-package"}, "public_package_path"),
        ({"public_package_digest": "sha256:stale-package"}, "public_package_digest"),
    ],
)
def test_pinning_rejects_stale_public_package_identity(change, message):
    actual = _requirements()
    requested = replace(actual, **change)
    with pytest.raises(BoundaryUnavailable, match=message):
        pin_worker_boundary(Supervisor(actual), requested)


@pytest.mark.parametrize(
    "change",
    [
        {"public_package_path": "/opt/stale-package"},
        {"public_package_digest": "sha256:stale-package"},
    ],
)
def test_launch_rejects_stale_public_package_identity(change):
    requirements = _requirements()
    supervisor = Supervisor(requirements)
    receipt = prove_worker_boundary(supervisor, requirements)
    request = WorkerLaunchRequest(
        case_id=requirements.case_id,
        worker_id=requirements.worker_id,
        execution_mode=requirements.execution_mode,
        boundary_id=receipt.boundary_id,
        runtime_receipt_id=receipt.runtime_receipt_id,
        challenge=receipt.challenge,
        public_package_path=receipt.public_package_path,
        public_package_digest=receipt.public_package_digest,
        argv=("omp", "--cwd", requirements.selected_case_path, "--no-session"),
        cwd=requirements.selected_case_path,
        environment={},
        timeout_seconds=10,
        final_capture_target={"project_id": "project-test", "timeline_id": "timeline-test"},
    )
    with pytest.raises(BoundaryUnavailable, match="does not match the proven receipt"):
        launch_in_proven_boundary(supervisor, receipt, replace(request, **change))
