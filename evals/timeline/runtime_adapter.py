"""Explicit Runtime setup and readback for isolated timeline evaluations.

The adapter binds one caller-supplied disposable realm, seeds targets using
server-assigned identities, and reads the committed closure back by the actual
parent head after an edit. It never falls back to the canonical Runtime or to a
mutable child projection.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .fixture import Baseline, CaseIdentities, DisposableEndpoint, FixtureError, MediaRequirement

ISOLATION_CONTRACT_KIND = "astrid.timeline-eval-isolation.v1"
ISOLATION_MARKER_NAME = ".astrid-timeline-eval-isolated.json"
REQUIRED_SCOPES = frozenset({"projects:read", "projects:write", "objects:read", "objects:write"})


def _remap_known_item_references_fallback(
    value: Any, item_ids: Mapping[str, str], *, key: str | None = None,
) -> Any:
    """Remap schema-known item references without importing the full core stack.

    Trusted fixture-preparation containers intentionally carry only the public
    Astrid source and runtime client.  The core authoring module also imports
    optional validation dependencies (for example ``jsonschema``), so keep the
    narrow identity rewrite available when those dependencies are absent.
    """
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for child_key, child in value.items():
            if not isinstance(child_key, str):
                result[child_key] = copy.deepcopy(child)
            elif isinstance(child, str) and (
                child_key in {"item_id", "source_item_id", "selected_item_id", "parent_item_id"}
                or child_key.endswith("_item_id")
            ):
                result[child_key] = item_ids.get(child, child)
            elif isinstance(child, list) and child_key.endswith("_item_ids"):
                result[child_key] = [
                    item_ids.get(item, item) if isinstance(item, str) else copy.deepcopy(item)
                    for item in child
                ]
            else:
                result[child_key] = _remap_known_item_references_fallback(child, item_ids, key=child_key)
        return result
    if isinstance(value, list):
        return [_remap_known_item_references_fallback(item, item_ids, key=key) for item in value]
    return copy.deepcopy(value)


class RuntimeAdapterError(FixtureError):
    """Runtime preflight or adapter contract failure."""


@dataclass(frozen=True)
class VerifiedIsolation:
    endpoint: str
    realm_id: str
    credential_file: Path
    realm_root: Path
    canonical_endpoint: str
    canonical_realm_id: str
    canonical_root: Path
    contract_path: Path

    def fixture_endpoint(self) -> DisposableEndpoint:
        return DisposableEndpoint(
            url=self.endpoint,
            realm_id=self.realm_id,
            credential_ref=str(self.credential_file),
            purpose="timeline-eval-disposable-realm",
        )


def _regular_non_symlink(path: Path, label: str) -> Path:
    absolute = path.expanduser().absolute()
    current = absolute
    while True:
        if current.is_symlink():
            raise RuntimeAdapterError(f"{label} path must not traverse a symlink")
        if current == current.parent:
            break
        current = current.parent
    return absolute


def _load_json(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeAdapterError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise RuntimeAdapterError(f"{label} must be a JSON object")
    return value


def verify_isolation_contract(
    *,
    endpoint: str | None,
    credential_file: str | Path | None,
    contract_path: str | Path | None,
) -> VerifiedIsolation:
    """Validate explicit connection inputs and on-disk realm separation.

    There is no environment lookup and no default/canonical endpoint fallback.
    The signed-in Runtime handshake is checked separately by
    :func:`connect_isolated_runtime`.
    """
    if not endpoint or not credential_file or not contract_path:
        raise RuntimeAdapterError(
            "explicit disposable endpoint, credential file, and isolation contract are required; refusing canonical/default fallback"
        )

    from astrid.sdk.workspace_client import validate_runtime_endpoint

    try:
        normalized_endpoint = validate_runtime_endpoint(endpoint)
    except Exception as exc:  # Runtime client owns URL validation details.
        raise RuntimeAdapterError(f"invalid explicit Runtime endpoint: {exc}") from exc

    credential = _regular_non_symlink(Path(credential_file), "credential")
    contract_file = _regular_non_symlink(Path(contract_path), "isolation contract")
    if not credential.is_file():
        raise RuntimeAdapterError("explicit disposable credential file does not exist")
    if not contract_file.is_file():
        raise RuntimeAdapterError("explicit isolation contract file does not exist")
    # Validate that the credential is usable without exposing its token.
    try:
        from astrid.sdk.workspace_client import resolve_runtime_connection

        resolve_runtime_connection(normalized_endpoint, credential)
    except Exception as exc:
        raise RuntimeAdapterError(f"explicit disposable credential is invalid: {exc}") from exc

    contract = _load_json(contract_file, "isolation contract")
    required = {
        "kind", "purpose", "isolated", "endpoint", "realm_id", "realm_root",
        "credential_file", "canonical_endpoint", "canonical_realm_id", "canonical_root",
    }
    missing = sorted(required - set(contract))
    if missing:
        raise RuntimeAdapterError("isolation contract is missing: " + ", ".join(missing))
    if contract.get("kind") != ISOLATION_CONTRACT_KIND:
        raise RuntimeAdapterError(f"isolation contract kind must be {ISOLATION_CONTRACT_KIND}")
    if contract.get("purpose") != "timeline-eval-disposable-realm" or contract.get("isolated") is not True:
        raise RuntimeAdapterError("isolation contract must assert the disposable timeline-eval realm purpose")
    if contract.get("endpoint") != normalized_endpoint:
        raise RuntimeAdapterError("isolation contract endpoint does not match the requested endpoint")
    if Path(str(contract.get("credential_file"))).expanduser().absolute() != credential:
        raise RuntimeAdapterError("isolation contract credential_file does not match the supplied credential")
    if contract.get("canonical_endpoint") == normalized_endpoint:
        raise RuntimeAdapterError("disposable endpoint must differ from the canonical endpoint")
    realm_id = contract.get("realm_id")
    canonical_realm_id = contract.get("canonical_realm_id")
    if not isinstance(realm_id, str) or not realm_id or realm_id == canonical_realm_id:
        raise RuntimeAdapterError("disposable realm_id must be explicit and differ from the canonical realm")
    realm_root = _regular_non_symlink(Path(str(contract["realm_root"])), "disposable realm root").resolve()
    canonical_root = _regular_non_symlink(Path(str(contract["canonical_root"])), "canonical realm root").resolve()
    if not realm_root.is_dir() or not canonical_root.is_dir():
        raise RuntimeAdapterError("disposable and canonical realm roots must both exist as directories")
    if realm_root == canonical_root:
        raise RuntimeAdapterError("disposable realm root equals canonical realm root")
    try:
        realm_root.relative_to(canonical_root)
    except ValueError:
        pass
    else:
        raise RuntimeAdapterError("disposable realm root must not be inside the canonical realm root")
    try:
        canonical_root.relative_to(realm_root)
    except ValueError:
        pass
    else:
        raise RuntimeAdapterError("canonical realm root must not be inside the disposable realm root")

    marker_path = realm_root / ISOLATION_MARKER_NAME
    marker = _load_json(marker_path, "disposable realm marker")
    if marker.get("kind") != ISOLATION_CONTRACT_KIND or marker.get("realm_id") != realm_id:
        raise RuntimeAdapterError("disposable realm marker does not match the isolation contract")
    if marker.get("purpose") != "timeline-eval-disposable-realm":
        raise RuntimeAdapterError("disposable realm marker has the wrong purpose")

    return VerifiedIsolation(
        endpoint=normalized_endpoint,
        realm_id=realm_id,
        credential_file=credential,
        realm_root=realm_root,
        canonical_endpoint=str(contract["canonical_endpoint"]),
        canonical_realm_id=str(canonical_realm_id),
        canonical_root=canonical_root,
        contract_path=contract_file,
    )


@dataclass(frozen=True)
class RuntimeConnectionProof:
    endpoint: str
    realm_id: str
    actor_id: str
    runtime_epoch: int
    scopes: tuple[str, ...]
    contract_path: str


class RuntimeFixtureAdapter:
    """Explicit connection to one proven disposable Runtime realm.

    Project/timeline creation, media ownership, publication, and exact
    coordinator-side readback all remain scoped to the supplied realm.
    """

    def __init__(self, isolation: VerifiedIsolation, workspace: Any, proof: RuntimeConnectionProof):
        self.isolation = isolation
        self.workspace = workspace
        self.proof = proof
        self.endpoint = isolation.fixture_endpoint()
        self._case_state: dict[tuple[str, str], tuple[Baseline, CaseIdentities]] = {}

    @classmethod
    def connect(
        cls,
        *,
        endpoint: str | None,
        credential_file: str | Path | None,
        contract_path: str | Path | None,
        client_factory: Callable[..., Any] | None = None,
    ) -> "RuntimeFixtureAdapter":
        isolation = verify_isolation_contract(
            endpoint=endpoint,
            credential_file=credential_file,
            contract_path=contract_path,
        )
        if client_factory is None:
            from astrid.sdk.workspace_client import WorkspaceClient

            client_factory = WorkspaceClient
        workspace = client_factory(isolation.endpoint, isolation.credential_file)
        health = workspace.health()
        if not isinstance(health, Mapping) or health.get("status") != "ok":
            raise RuntimeAdapterError("disposable Runtime health check failed")
        # Work only with the explicitly supplied credential and requested
        # scopes. The handshake realm is the server's independently observed
        # identity, not the contract's assertion alone.
        handshake = workspace.handshake(
            "astrid-timeline-eval", "1", sorted(REQUIRED_SCOPES)
        )
        if not isinstance(handshake, Mapping):
            raise RuntimeAdapterError("disposable Runtime handshake is not an object")
        if handshake.get("realm_id") != isolation.realm_id:
            raise RuntimeAdapterError("Runtime handshake realm_id differs from the isolated contract")
        scopes = handshake.get("scopes")
        if not isinstance(scopes, (list, tuple)) or not REQUIRED_SCOPES.issubset(set(scopes)):
            raise RuntimeAdapterError("disposable credential lacks required project/object read-write scopes")
        epoch = health.get("runtime_epoch")
        if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 1:
            raise RuntimeAdapterError("disposable Runtime health has invalid runtime_epoch")
        actor_id = handshake.get("actor_id")
        if not isinstance(actor_id, str) or not actor_id:
            raise RuntimeAdapterError("disposable Runtime handshake has no actor_id")
        if not callable(getattr(getattr(workspace, "_generated", None), "publish_parent_composition", None)):
            raise RuntimeAdapterError("installed generated Runtime client lacks publish_parent_composition")
        proof = RuntimeConnectionProof(
            endpoint=isolation.endpoint,
            realm_id=isolation.realm_id,
            actor_id=actor_id,
            runtime_epoch=epoch,
            scopes=tuple(sorted(scopes)),
            contract_path=str(isolation.contract_path),
        )
        return cls(isolation, workspace, proof)

    @staticmethod
    def _plain(value: Any) -> Any:
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return RuntimeFixtureAdapter._plain(dataclasses.asdict(value))
        if isinstance(value, Mapping):
            return {str(key): RuntimeFixtureAdapter._plain(child) for key, child in value.items()}
        if isinstance(value, (list, tuple)):
            return [RuntimeFixtureAdapter._plain(child) for child in value]
        return value

    @classmethod
    def _data(cls, value: Any, field: str) -> Mapping[str, Any]:
        plain = cls._plain(value)
        data = plain.get("data", plain) if isinstance(plain, Mapping) else None
        if not isinstance(data, Mapping):
            raise RuntimeAdapterError(f"Runtime {field} response has no data record")
        return data

    @staticmethod
    def _digest(value: Any) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _remap_item_payload(payload: Mapping[str, Any], item_ids: Mapping[str, str]) -> dict[str, Any]:
        # Reuse the author's schema-aware item-reference walker. `id` is
        # changed only on direct records in the known `items` array.
        try:
            from astrid.core.timeline.authoring_bundle import _remap_known_item_references
        except (ImportError, ModuleNotFoundError):
            # The trusted prep image does not need the full authoring validator;
            # preserve the exact narrow remapping semantics when optional core
            # dependencies are unavailable.
            _remap_known_item_references = _remap_known_item_references_fallback

        result = _remap_known_item_references(dict(payload), item_ids)
        items = result.get("items")
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                source = item.get("item_id", item.get("id"))
                target = item_ids.get(source) if isinstance(source, str) else None
                if target:
                    if "item_id" in item:
                        item["item_id"] = target
                    else:
                        item["id"] = target
        return result

    @staticmethod
    def _remap_parent_payload(payload: Mapping[str, Any], identities: CaseIdentities) -> dict[str, Any]:
        result = copy.deepcopy(dict(payload))
        occurrences = result.get("occurrences")
        if not isinstance(occurrences, list):
            raise RuntimeAdapterError("source parent payload has no occurrence list")
        for index, occurrence in enumerate(occurrences):
            if not isinstance(occurrence, dict):
                raise RuntimeAdapterError(f"parent occurrence {index} is not an object")
            for field, mapping in (
                ("occurrence_id", identities.occurrence_ids),
                ("shot_id", identities.shot_ids),
                ("shot_revision_id", identities.shot_revision_ids),
            ):
                source = occurrence.get(field)
                if not isinstance(source, str) or source not in mapping:
                    raise RuntimeAdapterError(f"parent occurrence {index} has unresolved {field}")
                occurrence[field] = mapping[source]
        return result

    def create_suite_project(self, project_alias: str, *, idempotency_key: str) -> Mapping[str, Any]:
        metadata = {
            "timeline_eval_suite": "astrid-timeline-navigation-and-actions",
            "purpose": "timeline-eval-disposable-realm",
            "project_alias": project_alias,
        }
        # E02 uses a case-scoped idempotency key for the shared suite project.
        # Reuse only an exact suite project within this already-verified realm.
        page = self._plain(self.workspace.list_projects(limit=100))
        while True:
            if isinstance(page, Mapping):
                rows = page.get("items", [])
                cursor = page.get("next_cursor")
            elif isinstance(page, (list, tuple)) and len(page) == 2:
                rows, cursor = page
            else:
                rows, cursor = [], None
            for row in rows if isinstance(rows, (list, tuple)) else ():
                if not isinstance(row, Mapping) or row.get("slug") != project_alias:
                    continue
                if row.get("metadata") != metadata:
                    raise RuntimeAdapterError("disposable project slug exists with different metadata")
                project_id = row.get("project_id", row.get("id"))
                return {"project_id": project_id, "slug": project_alias, "reused": True}
            if not cursor:
                break
            page = self._plain(self.workspace.list_projects(cursor=cursor, limit=100))
        created = self._data(self.workspace.create_project(
            "Timeline Eval Suite",
            slug=project_alias,
            metadata=metadata,
            idempotency_key=idempotency_key,
        ), "create_project")
        project_id = created.get("project_id", created.get("id"))
        if not isinstance(project_id, str) or not project_id:
            raise RuntimeAdapterError("Runtime create_project omitted its server-assigned ID")
        return {"project_id": project_id, "slug": project_alias, "reused": False}

    def create_case_timeline(self, project_id: str, timeline_alias: str, *, idempotency_key: str) -> Mapping[str, Any]:
        created = self._data(self.workspace.create_timeline(
            project_id, timeline_alias, idempotency_key=idempotency_key,
        ), "create_timeline")
        timeline_id = created.get("timeline_id", created.get("id", timeline_alias))
        if not isinstance(timeline_id, str) or not timeline_id:
            raise RuntimeAdapterError("Runtime create_timeline omitted the timeline ID")
        if timeline_id != timeline_alias:
            raise RuntimeAdapterError("Runtime returned a timeline ID different from the requested deterministic alias")
        return {"timeline_id": timeline_id, "slug": timeline_alias}

    def ensure_media_owned(self, project_id: str, requirement: MediaRequirement, media_bytes: bytes) -> Mapping[str, Any]:
        digest = requirement.digest.removeprefix("sha256:")
        actual = hashlib.sha256(media_bytes).hexdigest()
        if actual != digest:
            raise RuntimeAdapterError(f"attempt-local media bytes fail digest verification for {requirement.digest}")
        # Runtime idempotency is request-sensitive. Include every argument that
        # affects the ingest payload, so a retry after metadata correction gets
        # a fresh key instead of reusing the key with conflicting input.
        ingest_request = {
            "project_id": project_id,
            "digest": requirement.digest,
            "media_type": requirement.media_type,
            "filename": Path(requirement.source_handle).name,
        }
        key = "eval-media-" + hashlib.sha256(
            json.dumps(ingest_request, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        result = self._data(self.workspace.ingest_project_object(
            project_id,
            media_bytes,
            media_type=ingest_request["media_type"],
            filename=ingest_request["filename"],
            idempotency_key=key,
        ), "ingest_project_object")
        object_id = result.get("object_id", result.get("digest"))
        if not isinstance(object_id, str) or object_id.removeprefix("sha256:") != digest:
            raise RuntimeAdapterError("Runtime ingest returned a different media digest")
        # Project-scoped location only resolves if the object is owned by this
        # project; verify that invariant after the ingest receipt.
        location = self._data(self.workspace.get_project_object_location(project_id, object_id), "get_project_object_location")
        if location.get("verified") is not True or location.get("digest", object_id).removeprefix("sha256:") != digest:
            raise RuntimeAdapterError("Runtime did not verify the ingested bytes as project-owned media")
        return {"project_id": project_id, "digest": requirement.digest, "object_id": object_id}

    def _publication(
        self, project_id: str, identities: CaseIdentities, baseline: Baseline,
        *, expected_head: str | None, parent_revision_id: str | None = None,
        owned_media: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        closure = baseline.closure
        source_parent = closure["parent_revision"]["payload"]
        parent_payload = self._remap_parent_payload(source_parent, identities)
        source_shots = list(closure["shot_revisions"])
        source_internal = list(closure["internal_timeline_revisions"])
        shot_revisions: list[dict[str, Any]] = []
        internal_revisions: list[dict[str, Any]] = []
        shot_manifest: list[dict[str, Any]] = []
        internal_manifest: list[dict[str, Any]] = []
        source_shot_to_target = identities.shot_ids
        source_revision_to_internal_revision = identities.internal_revision_ids

        for row in source_internal:
            source_timeline_id = str(row["timeline_id"])
            source_revision_id = str(row["revision_id"])
            target_timeline_id = identities.internal_timeline_ids.get(source_timeline_id)
            target_revision_id = source_revision_to_internal_revision.get(source_revision_id)
            if not target_timeline_id or not target_revision_id:
                raise RuntimeAdapterError(f"internal timeline identity mapping missing for {source_revision_id}")
            # Runtime stores immutable shot-local timeline revisions under an
            # existing project timeline identity. Fixture seeding creates one
            # case timeline, so each internal revision belongs to that timeline;
            # synthetic per-shot timeline IDs have no Runtime row to resolve.
            target_timeline_id = identities.timeline_id
            payload = copy.deepcopy(dict(row["payload"]))
            internal_revisions.append({
                "timeline_id": target_timeline_id,
                "revision_id": target_revision_id,
                "payload": payload,
                "content_digest": self._digest(payload),
            })
            internal_manifest.append({
                "timeline_id": target_timeline_id,
                "revision_id": target_revision_id,
                "content_digest": self._digest(payload),
            })

        for row in source_shots:
            source_shot_id = str(row["shot_id"])
            source_revision_id = str(row["revision_id"])
            source_internal_revision_id = str(row.get("internal_timeline_revision_id") or row["payload"].get("internal_timeline_revision_id"))
            target_shot_id = source_shot_to_target.get(source_shot_id)
            target_revision_id = identities.shot_revision_ids.get(source_revision_id)
            target_internal_revision_id = source_revision_to_internal_revision.get(source_internal_revision_id)
            if not target_shot_id or not target_revision_id or not target_internal_revision_id:
                raise RuntimeAdapterError(f"shot identity mapping missing for {source_revision_id}")
            payload = self._remap_item_payload(row["payload"], identities.item_ids)
            payload["internal_timeline_revision_id"] = target_internal_revision_id
            digest = self._digest(payload)
            shot_revisions.append({
                "shot_id": target_shot_id,
                "revision_id": target_revision_id,
                "internal_timeline_revision_id": target_internal_revision_id,
                "payload": payload,
                "content_digest": digest,
            })
            shot_manifest.append({
                "shot_id": target_shot_id,
                "revision_id": target_revision_id,
                "internal_timeline_revision_id": target_internal_revision_id,
                "content_digest": digest,
            })

        # Runtime accepts only SHA-256 content-addressed dependencies and also
        # checks per-project ownership. Content IDs remain stable across realms.
        media_manifest = [
            {"media_id": "sha256:" + item.digest.removeprefix("sha256:"),
             "content_digest": "sha256:" + item.digest.removeprefix("sha256:")}
            for item in baseline.media
        ]
        expected_parent_digest = self._digest(parent_payload)
        return {
            "project_id": project_id,
            "timeline_id": identities.timeline_id,
            "expected_head": expected_head,
            "parent_revision_id": parent_revision_id or identities.parent_revision_id,
            "content_digest": expected_parent_digest,
            "parent_composition": parent_payload,
            "internal_timeline_revisions": internal_revisions,
            "shot_revisions": shot_revisions,
            "dependency_manifest": {
                "shots": shot_manifest,
                "internal_timelines": internal_manifest,
                "media": media_manifest,
            },
        }

    def publish_parent_composition(self, project_id: str, timeline_id: str, publication: Mapping[str, Any], *, idempotency_key: str) -> Mapping[str, Any]:
        generated = getattr(self.workspace, "_generated", None)
        publish = getattr(generated, "publish_parent_composition", None)
        if not callable(publish):
            raise RuntimeAdapterError("generated Runtime client lacks publish_parent_composition")
        value = publish(project_id, timeline_id, dict(publication), idempotency_key=idempotency_key)
        return self._plain(value)

    def publish_authoring_candidate_route(
        self,
        target: Mapping[str, Any],
        candidate: Mapping[str, Any],
        *,
        idempotency_key: str,
    ) -> Mapping[str, Any]:
        """Validate and commit one host-built candidate in the disposable target.

        This is the shared case-scoped edit route for future action fixtures.
        It intentionally accepts a complete authoring-bundle candidate rather
        than inventing per-case request shapes.  The candidate is bound to the
        public target's server-assigned project/timeline and exact expected
        head; every selected dependency is checked as destination-owned before
        the existing atomic Runtime publication port is called.
        """
        if not isinstance(target, Mapping) or not isinstance(candidate, Mapping):
            raise RuntimeAdapterError("authoring candidate route requires target and candidate objects")
        if target.get("kind") != "astrid.timeline-eval.public-target.v1":
            raise RuntimeAdapterError("authoring candidate route requires a versioned public target receipt")
        if target.get("scope") != "selected-case-only":
            raise RuntimeAdapterError("authoring candidate route requires a selected-case-only target scope")
        if target.get("read_only") is True:
            raise RuntimeAdapterError("authoring candidate route cannot edit a read-only target")
        target_endpoint = target.get("endpoint")
        # ``self.endpoint`` is the verified DisposableEndpoint descriptor;
        # compare the pinned URL, never the descriptor object itself.
        if not isinstance(target_endpoint, str) or target_endpoint != self.endpoint.url:
            raise RuntimeAdapterError("public target endpoint is not the connected disposable endpoint")
        project_id = target.get("project_id")
        timeline_id = target.get("timeline_id")
        expected_head = target.get("head_revision_id")
        if not all(isinstance(value, str) and value for value in (project_id, timeline_id, expected_head)):
            raise RuntimeAdapterError("public target is missing disposable project, timeline, or expected head")
        locator = target.get("target_locator")
        if not isinstance(locator, Mapping):
            raise RuntimeAdapterError("public target has no case-scoped target locator")
        capabilities = target.get("capabilities")
        edit = capabilities.get("edit") if isinstance(capabilities, Mapping) else None
        if not isinstance(edit, Mapping) or edit.get("status") != "available":
            raise RuntimeAdapterError("public target does not expose an available edit capability")
        route = edit.get("route")
        if route != "authoring-bundle validate/commit":
            raise RuntimeAdapterError(f"unsupported public edit route: {route!r}")
        if candidate.get("project_id") != project_id or candidate.get("timeline_id") != timeline_id:
            raise RuntimeAdapterError("authoring candidate project/timeline differs from public target")
        base_parent = candidate.get("base_parent")
        if not isinstance(base_parent, Mapping) or base_parent.get("revision_id") != expected_head:
            raise RuntimeAdapterError("authoring candidate base parent is not the public target expected head")
        if self.current_head(project_id, timeline_id) != expected_head:
            raise RuntimeAdapterError("public target expected head is stale before candidate commit")
        try:
            from astrid.core.timeline.authoring_bundle import compile_authoring_candidate, publish_authoring_candidate
            compilation = compile_authoring_candidate(candidate)
        except Exception as exc:  # adapter boundary converts compiler details to one typed error
            raise RuntimeAdapterError(f"authoring candidate validation failed: {exc}") from exc
        publication = compilation.publication
        dependency_manifest = publication.get("dependency_manifest", {})
        if not isinstance(dependency_manifest, Mapping):
            raise RuntimeAdapterError("compiled candidate dependency manifest is malformed")
        dependencies = dependency_manifest.get("media", [])
        if not isinstance(dependencies, list):
            raise RuntimeAdapterError("compiled candidate dependency manifest has no media list")
        for index, dependency in enumerate(dependencies):
            if not isinstance(dependency, Mapping):
                raise RuntimeAdapterError(f"compiled candidate media dependency {index} is malformed")
            media_id = dependency.get("media_id", dependency.get("content_digest"))
            if not isinstance(media_id, str) or not media_id:
                raise RuntimeAdapterError(f"compiled candidate media dependency {index} has no media ID")
            location = self._data(
                self.workspace.get_project_object_location(
                    project_id, media_id.removeprefix("sha256:"),
                ),
                "get_project_object_location",
            )
            if location.get("verified") is not True:
                raise RuntimeAdapterError(f"candidate media is not destination-owned: {media_id}")
            observed = location.get("digest", media_id)
            if isinstance(observed, str) and observed.removeprefix("sha256:") != media_id.removeprefix("sha256:"):
                raise RuntimeAdapterError(f"destination-owned media digest differs for {media_id}")
        try:
            result = publish_authoring_candidate(
                candidate, self, idempotency_key=idempotency_key,
            )
        except Exception as exc:
            raise RuntimeAdapterError(f"authoring candidate commit failed: {exc}") from exc
        return {
            "kind": "astrid.timeline-eval.disposable-authoring-publication.v1",
            "route": "authoring-bundle validate/commit",
            "case_id": target.get("case_id"),
            "project_id": project_id,
            "timeline_id": timeline_id,
            "expected_head": expected_head,
            "candidate_digest": compilation.candidate_digest,
            "identity_mapping": result.get("identity_mapping"),
            "publication": result.get("publication"),
        }

    def seed_case(self, project_id: str, identities: CaseIdentities, baseline: Baseline, owned_media: Mapping[str, str], *, idempotency_key: str) -> Mapping[str, Any]:
        if project_id != identities.project_id:
            raise RuntimeAdapterError("seed project does not match Runtime-assigned CaseIdentities.project_id")
        publication = self._publication(project_id, identities, baseline, expected_head=None, owned_media=owned_media)
        result = self._data(self.publish_parent_composition(
            project_id, identities.timeline_id, publication, idempotency_key=idempotency_key,
        ), "publish_parent_composition")
        new_head = result.get("new_head", result.get("parent_revision_id", result.get("revision_id")))
        if new_head != identities.parent_revision_id:
            raise RuntimeAdapterError("Runtime seed receipt head differs from the planned parent revision")
        self._case_state[(project_id, identities.timeline_id)] = (baseline, identities)
        semantic = self.read_case_semantic_digest(project_id, identities.timeline_id)
        if semantic != baseline.semantic_digest:
            raise RuntimeAdapterError("seed exact readback differs from pinned baseline semantics")
        return {
            "project_id": project_id,
            "timeline_id": identities.timeline_id,
            "new_head": new_head,
            "semantic_digest": semantic,
            "runtime_receipt": dict(result),
        }

    def current_head(self, project_id: str, timeline_id: str) -> str:
        timeline = self._data(self.workspace.get_timeline(timeline_id, project_id=project_id), "get_timeline")
        head = timeline.get("head_revision_id")
        return str(head) if isinstance(head, str) else ""

    def list_project_timeline_heads(self, project_id: str) -> dict[str, str | None]:
        """Inventory every timeline head in the disposable case project.

        The independent grader captures this before and after an agent run so
        a mutation to a sibling timeline, including a newly created timeline,
        cannot be hidden by a correct target readback.
        """
        heads: dict[str, str | None] = {}
        cursor: str | None = None
        seen_cursors: set[str] = set()
        while True:
            page = self._plain(self.workspace.list_timelines(project_id, cursor=cursor, limit=100))
            if isinstance(page, Mapping):
                rows, next_cursor = page.get("items", []), page.get("next_cursor")
            elif isinstance(page, (list, tuple)) and len(page) == 2:
                rows, next_cursor = page
            else:
                raise RuntimeAdapterError("Runtime list_timelines returned an invalid page")
            if not isinstance(rows, (list, tuple)):
                raise RuntimeAdapterError("Runtime list_timelines omitted its items")
            for row in rows:
                if not isinstance(row, Mapping):
                    raise RuntimeAdapterError("Runtime list_timelines contains a malformed timeline")
                timeline_id = row.get("timeline_id", row.get("id"))
                if not isinstance(timeline_id, str) or not timeline_id or timeline_id in heads:
                    raise RuntimeAdapterError("Runtime list_timelines contains a missing or duplicate timeline ID")
                head = row.get("head_revision_id")
                if head is not None and (not isinstance(head, str) or not head):
                    raise RuntimeAdapterError("Runtime list_timelines contains an invalid head")
                heads[timeline_id] = head
            if not next_cursor:
                return heads
            if not isinstance(next_cursor, str) or next_cursor in seen_cursors:
                raise RuntimeAdapterError("Runtime list_timelines has an invalid pagination cursor")
            seen_cursors.add(next_cursor)
            cursor = next_cursor

    def read_current_closure(
        self, project_id: str, timeline_id: str, *, head: str | None = None,
    ) -> dict[str, Any]:
        """Read the exact committed parent/shot/internal closure at ``head``.

        This is deliberately independent of the seed identity map. Agents may
        create, duplicate, replace, or remove shots, so post-edit grading must
        follow the current parent's pinned dependency IDs rather than assume
        that every returned child still has a seed ID.
        """
        parent_revision_id = head or self.current_head(project_id, timeline_id)
        if not parent_revision_id:
            raise RuntimeAdapterError("case timeline has no committed parent head")
        parent = self._data(
            self.workspace.get_project_parent_composition_revision(
                project_id, timeline_id, parent_revision_id,
            ),
            "get_parent_revision",
        )
        if parent.get("revision_id") != parent_revision_id:
            raise RuntimeAdapterError("Runtime returned a different parent composition revision")
        payload = parent.get("payload")
        occurrences = payload.get("occurrences") if isinstance(payload, Mapping) else None
        if not isinstance(occurrences, list):
            raise RuntimeAdapterError("current parent payload has no occurrence list")

        shots: list[Mapping[str, Any]] = []
        shot_by_key: dict[tuple[str, str], Mapping[str, Any]] = {}
        internals: list[Mapping[str, Any]] = []
        seen_shots: set[tuple[str, str]] = set()
        seen_internals: set[str] = set()
        for index, occurrence in enumerate(occurrences):
            if not isinstance(occurrence, Mapping):
                raise RuntimeAdapterError(f"current parent occurrence {index} is not an object")
            shot_id = occurrence.get("shot_id")
            shot_revision_id = occurrence.get("shot_revision_id", occurrence.get("revision_id"))
            if not isinstance(shot_id, str) or not isinstance(shot_revision_id, str):
                raise RuntimeAdapterError(f"current parent occurrence {index} does not pin a shot revision")
            shot_key = (shot_id, shot_revision_id)
            if shot_key not in seen_shots:
                shot = self._data(
                    self.workspace.get_project_shot_revision(
                        project_id, shot_id, shot_revision_id,
                    ),
                    f"shot_revision {shot_id}/{shot_revision_id}",
                )
                if shot.get("shot_id") != shot_id or shot.get("revision_id") != shot_revision_id:
                    raise RuntimeAdapterError("Runtime returned a different pinned shot revision")
                shots.append(shot)
                shot_by_key[shot_key] = shot
                seen_shots.add(shot_key)
            shot = shot_by_key[shot_key]
            internal_revision_id = shot.get("internal_timeline_revision_id")
            if not isinstance(internal_revision_id, str) or not internal_revision_id:
                raise RuntimeAdapterError(f"shot revision {shot_revision_id!r} has no internal timeline pin")
            if internal_revision_id not in seen_internals:
                internal = self._data(
                    self.workspace.get_project_timeline_revision(
                        project_id, timeline_id, internal_revision_id,
                    ),
                    f"internal_timeline_revision {internal_revision_id}",
                )
                if internal.get("revision_id") != internal_revision_id:
                    raise RuntimeAdapterError("Runtime returned a different pinned internal timeline revision")
                internals.append(internal)
                seen_internals.add(internal_revision_id)
        return {
            "project_id": project_id,
            "timeline_id": timeline_id,
            "parent_revision": parent,
            "shot_revisions": shots,
            "internal_timeline_revisions": internals,
            "head_revision_id": parent_revision_id,
        }

    def read_current_semantic_digest(self, project_id: str, timeline_id: str) -> str:
        """Digest the exact current closure without assuming seeded identities."""
        closure = self.read_current_closure(project_id, timeline_id)
        semantic = {
            "parent": closure["parent_revision"].get("payload"),
            "shots": [row.get("payload") for row in closure["shot_revisions"]],
            "internal_timelines": [row.get("payload") for row in closure["internal_timeline_revisions"]],
        }
        return self._digest(semantic)

    def read_case_semantic_digest(self, project_id: str, timeline_id: str) -> str:
        state = self._case_state.get((project_id, timeline_id))
        if state is None:
            raise RuntimeAdapterError("case has not been seeded through this adapter")
        baseline, identities = state
        head = self.current_head(project_id, timeline_id)
        if not head:
            raise RuntimeAdapterError("case timeline has no committed parent head")
        parent = self._data(self.workspace.get_project_parent_composition_revision(project_id, timeline_id, head), "get_parent_revision")
        payload = copy.deepcopy(dict(parent.get("payload", {})))
        inverse_occurrences = {target: source for source, target in identities.occurrence_ids.items()}
        inverse_shots = {target: source for source, target in identities.shot_ids.items()}
        inverse_shot_revisions = {target: source for source, target in identities.shot_revision_ids.items()}
        for occurrence in payload.get("occurrences", []):
            if not isinstance(occurrence, dict):
                raise RuntimeAdapterError("readback parent has malformed occurrence")
            for field, mapping in (("occurrence_id", inverse_occurrences), ("shot_id", inverse_shots), ("shot_revision_id", inverse_shot_revisions)):
                value = occurrence.get(field)
                if value not in mapping:
                    raise RuntimeAdapterError(f"readback parent has unresolved mapped {field}")
                occurrence[field] = mapping[value]

        # The ordinary parent-revision read API returns the immutable parent
        # payload, not its publication dependency manifest. Read back each
        # dependency by its exact server-assigned identity below and reconstruct
        # semantics from those returned payloads; never require an unavailable
        # response field or infer candidate success from the submit receipt.
        shot_records: dict[str, Mapping[str, Any]] = {}
        for source in baseline.closure["shot_revisions"]:
            source_id = str(source["revision_id"])
            target_shot = identities.shot_ids[str(source["shot_id"])]
            target_revision = identities.shot_revision_ids[source_id]
            read = self._data(self.workspace.get_project_shot_revision(project_id, target_shot, target_revision), "get_shot_revision")
            shot_payload = self._remap_item_payload(read["payload"], {target: original for original, target in identities.item_ids.items()})
            internal_revision = str(source.get("internal_timeline_revision_id") or source["payload"].get("internal_timeline_revision_id"))
            shot_payload["internal_timeline_revision_id"] = internal_revision
            shot_records[source_id] = shot_payload

        internal_records: dict[str, Mapping[str, Any]] = {}
        for source in baseline.closure["internal_timeline_revisions"]:
            source_revision = str(source["revision_id"])
            target_timeline = identities.timeline_id
            target_revision = identities.internal_revision_ids[source_revision]
            read = self._data(self.workspace.get_project_timeline_revision(project_id, target_timeline, target_revision), "get_internal_revision")
            internal_records[source_revision] = read["payload"]

        semantic = {
            "parent": payload,
            "shots": [shot_records[str(row["revision_id"])] for row in baseline.closure["shot_revisions"]],
            "internal_timelines": [internal_records[str(row["revision_id"])] for row in baseline.closure["internal_timeline_revisions"]],
        }
        return self._digest(semantic)

    def publish_baseline(self, project_id: str, timeline_id: str, baseline: Baseline, *, expected_head: str, idempotency_key: str) -> Mapping[str, Any]:
        state = self._case_state.get((project_id, timeline_id))
        if state is None:
            raise RuntimeAdapterError("cannot reset a case that this adapter has not seeded")
        _prior_baseline, identities = state
        parent_revision_id = "eval-reset-" + hashlib.sha256(f"{identities.parent_revision_id}\0{expected_head}\0{baseline.semantic_digest}".encode()).hexdigest()[:32]
        publication = self._publication(
            project_id, identities, baseline,
            expected_head=expected_head,
            parent_revision_id=parent_revision_id,
        )
        result = self._data(self.publish_parent_composition(
            project_id, timeline_id, publication, idempotency_key=idempotency_key,
        ), "publish_baseline")
        self._case_state[(project_id, timeline_id)] = (baseline, identities)
        return {"new_head": result.get("new_head", result.get("parent_revision_id", parent_revision_id))}


class WorkspaceClosureReader:
    """Read-only exact-closure view over any coordinator-owned Runtime client.

    This delegates to the fixture adapter's existing resolver. A source client
    can therefore supply canonical preservation evidence without being bound
    as the disposable writer or introducing another closure implementation.
    """

    def __init__(self, workspace: Any):
        self.workspace = workspace

    @staticmethod
    def _plain(value: Any) -> Any:
        return RuntimeFixtureAdapter._plain(value)

    @staticmethod
    def _data(value: Any, field: str) -> Mapping[str, Any]:
        return RuntimeFixtureAdapter._data(value, field)

    def current_head(self, project_id: str, timeline_id: str) -> str:
        return RuntimeFixtureAdapter.current_head(self, project_id, timeline_id)

    def read_current_closure(
        self, project_id: str, timeline_id: str, *, head: str | None = None,
    ) -> dict[str, Any]:
        return RuntimeFixtureAdapter.read_current_closure(self, project_id, timeline_id, head=head)

    def list_project_timeline_heads(self, project_id: str) -> dict[str, str | None]:
        return RuntimeFixtureAdapter.list_project_timeline_heads(self, project_id)


def isolation_contract_template(
    *, endpoint: str, realm_id: str, credential_file: str | Path,
    realm_root: str | Path, canonical_endpoint: str, canonical_realm_id: str,
    canonical_root: str | Path,
) -> dict[str, Any]:
    """Build a contract mapping for an operator who has created a fresh realm.

    This helper does not start a daemon or create any files.
    """
    return {
        "kind": ISOLATION_CONTRACT_KIND,
        "purpose": "timeline-eval-disposable-realm",
        "isolated": True,
        "endpoint": endpoint,
        "realm_id": realm_id,
        "credential_file": str(Path(credential_file).expanduser().absolute()),
        "realm_root": str(Path(realm_root).expanduser().absolute()),
        "canonical_endpoint": canonical_endpoint,
        "canonical_realm_id": canonical_realm_id,
        "canonical_root": str(Path(canonical_root).expanduser().absolute()),
        # The launcher admission check requires this explicit negative claim;
        # it is only a declarative preflight input, not process isolation.
        "canonical_source_access": False,
        "source_access_available_to_agent": False,
    }


def prepare_local_disposable_project(
    seed_dir: str | Path,
    case_dir: str | Path,
    *,
    case_id: str,
    runtime_project_id: str | None = None,
    runtime: Any | None = None,
    project_creator: Callable[..., Any] | None = None,
) -> Any:
    """Prepare a local case project through the existing adapter surface.

    The implementation is kept in a standalone filesystem seam so callers can
    use it without starting the HTTP Runtime daemon; an existing Runtime
    ``create_project`` client may still be supplied for server-assigned IDs.
    """
    from .local_project_adapter import prepare_local_project

    return prepare_local_project(
        seed_dir,
        case_dir,
        case_id=case_id,
        runtime_project_id=runtime_project_id,
        runtime=runtime,
        project_creator=project_creator,
    )


__all__ = [
    "ISOLATION_CONTRACT_KIND", "ISOLATION_MARKER_NAME", "REQUIRED_SCOPES",
    "RuntimeAdapterError", "RuntimeConnectionProof", "RuntimeFixtureAdapter",
    "VerifiedIsolation", "WorkspaceClosureReader", "isolation_contract_template", "verify_isolation_contract",
    "prepare_local_disposable_project",
]
