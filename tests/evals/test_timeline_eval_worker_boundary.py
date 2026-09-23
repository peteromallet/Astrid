from __future__ import annotations

from dataclasses import replace

import pytest

from evals.timeline.worker_boundary import (
    BoundaryRequirements,
    BoundaryUnavailable,
    ProbeObservation,
    WorkerAttestation,
    prove_worker_boundary,
)


def _requirements():
    return BoundaryRequirements(
        case_id="A01",
        worker_id="worker-a01",
        model_boundary_id="container-immutable-identity",
        selected_case_path="/case/A01",
        disposable_credential_path="/case/A01/runtime-credential.json",
        skill_path="/case/A01/public-skill/SKILL.md",
        skill_sha256="1" * 64,
        public_package_digest="sha256:" + "2" * 64,
        disposable_endpoint="http://disposable:9000",
        disposable_realm_id="disposable-realm",
        canonical_endpoint="http://canonical:9000",
        canonical_paths=("/workspace/canonical",),
        private_paths=("/host/private/checks.json",),
        sibling_paths=("/case/A02",),
        denied_endpoints=("http://127.0.0.1:63541",),
        skill_reference_paths=("/case/A01/public-skill/REFERENCES.md",),
    )


class Supervisor:
    def __init__(self, requirements):
        self.requirements = requirements
        self.probes = []
        self.override = None

    def inspect_worker(self, worker_id):
        r = self.requirements
        return WorkerAttestation(
            worker_id=worker_id, boundary_id=r.model_boundary_id,
            enforcement="container", policy_digest="sha256:" + "3" * 64,
            selected_case_path=r.selected_case_path,
            public_package_digest=r.public_package_digest,
        )

    def run_access_probe(self, worker_id, challenge, probe):
        self.probes.append(probe)
        value = ProbeObservation(
            worker_id=worker_id, boundary_id=self.requirements.model_boundary_id,
            challenge=challenge, probe_id=probe.probe_id, observed=probe.expected,
            sha256=probe.expected_sha256, realm_id=probe.expected_realm_id,
            denial_source=(
                "not_mounted" if probe.expected == "deny" and probe.kind == "read_path"
                else "network_policy" if probe.expected == "deny" else None
            ),
        )
        return self.override(probe, value) if self.override else value


def test_active_worker_probes_bind_skill_runtime_denials_and_model_boundary():
    requirements = _requirements()
    supervisor = Supervisor(requirements)
    receipt = prove_worker_boundary(supervisor, requirements)
    assert receipt.status == "pass"
    assert receipt.boundary_id == requirements.model_boundary_id
    assert {probe.probe_id for probe in receipt.probes} == {
        "selected-case-read", "selected-case-write", "disposable-credential-read",
        "skill-sha256", "disposable-runtime", "canonical-runtime-denied",
        "skill-reference-0-read", "canonical-0-denied", "private-0-denied",
        "sibling-0-denied", "other-endpoint-0-denied",
    }
    assert receipt.probes[2].probe_id == "disposable-credential-read"
    assert "token" not in str(receipt.as_dict())


def test_no_host_supervisor_or_incomplete_denial_targets_fail_closed():
    requirements = _requirements()
    with pytest.raises(BoundaryUnavailable, match="no host worker supervisor"):
        prove_worker_boundary(None, requirements)
    with pytest.raises(BoundaryUnavailable, match="canonical, private, and sibling"):
        prove_worker_boundary(Supervisor(requirements), replace(requirements, private_paths=()))


@pytest.mark.parametrize(
    ("probe_id", "change", "message"),
    [
        ("canonical-runtime-denied", {"observed": "allow", "denial_source": None}, "observed allow"),
        ("private-0-denied", {"denial_source": None}, "policy-backed denial"),
        ("skill-sha256", {"sha256": "0" * 64}, "skill hash differs"),
        ("disposable-runtime", {"realm_id": "canonical-realm"}, "wrong realm"),
        ("sibling-0-denied", {"boundary_id": "other-container"}, "different boundary"),
    ],
)
def test_worker_boundary_rejects_false_denials_wrong_skill_realm_and_identity(probe_id, change, message):
    requirements = _requirements()
    supervisor = Supervisor(requirements)
    supervisor.override = lambda probe, value: replace(value, **change) if probe.probe_id == probe_id else value
    with pytest.raises(BoundaryUnavailable, match=message):
        prove_worker_boundary(supervisor, requirements)


def test_attestation_must_name_exact_model_launch_boundary():
    requirements = _requirements()

    class WrongWorker(Supervisor):
        def inspect_worker(self, worker_id):
            return replace(super().inspect_worker(worker_id), boundary_id="preflight-container-only")

    with pytest.raises(BoundaryUnavailable, match="does not match selected case and model boundary"):
        prove_worker_boundary(WrongWorker(requirements), requirements)
