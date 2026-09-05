"""VibeComfyBackend — local generation via vibecomfy ready templates.

The backend drives the template's declared ``bind_input`` contract through
``wf.set_input()``.  Template graph inspection is intentionally not part of
the runtime API: a template that does not declare a requested input is an
invalid template, not an invitation to infer a node target.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from astrid.core.generation.backends.base import (
    BackendAdapter,
    GenerationResult,
    derive_frames_from_duration,
    parse_dimension_pair,
    split_feature_support,
)
from astrid.core.model_catalog.schema import BackendSpec, ModelEntry

logger = logging.getLogger(__name__)

# Explicit runtime adapter precedence.  The pip-installed embedded runtime is
# preferred; the checked-out managed server runtime remains the second choice.
ADAPTER_ORDER: tuple[str, ...] = ("pip_embedded", "checkout_server")

VIBECOMFY_ENGINE_REVISION = "dc8d962a8e330015bbb209080292fad248f1ceb3"
COMFYUI_VERSION = "0.26.0"
_PIP_EMBEDDED_PROFILE_SCHEMA = "astrid.vibecomfy.pip_embedded.v2"
_REQUEST_SCHEMA = "astrid.vibecomfy.request.v1"
_READY_SCHEMA = "astrid.vibecomfy.ready.v1"
_RESULT_SCHEMA = "astrid.vibecomfy.result.v1"
_PIP_EMBEDDED_SCRIPT = r"""
import hashlib,json,os,sys,time
from pathlib import Path
from vibecomfy.runtime.run import run_embedded_sync
from vibecomfy.runtime.session import SessionConfig
from vibecomfy.workflow import FORMAT_VERSION,VibeWorkflow
def pairs(items):
    result={}
    for key,value in items:
        if key in result: raise ValueError("duplicate JSON key")
        result[key]=value
    return result
def load(path):
    raw=Path(path).read_bytes()
    if len(raw)>16*1024*1024: raise ValueError("request too large")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("non-finite JSON")))
request=load(sys.argv[1])
if not isinstance(request,dict) or request.get("schema")!="astrid.vibecomfy.request.v1":
    raise SystemExit(2)
if set(request) != {"schema","nonce","task_identity","profile_digest","workflow","workflow_digest",
                    "config_digest","profile_readiness_digest","config","policy","request_digest"}:
    raise SystemExit(2)
if request.get("workflow",{}).get("vibecomfy_format_version")!=FORMAT_VERSION:
    raise SystemExit(2)
workflow=VibeWorkflow.from_envelope(request["workflow"])
def digest(value):
    return "sha256:"+hashlib.sha256(json.dumps(value,sort_keys=True,
        separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
if digest(request["workflow"]) != request.get("workflow_digest") or workflow.to_envelope()!=request["workflow"]:
    raise SystemExit(2)
for node in workflow.nodes.values():
    if node.class_type in {"vibecomfy.code","vibecomfy.loop"}:
        raise SystemExit(2)
config=request["config"]
ready={"schema":"astrid.vibecomfy.ready.v1","nonce":request["nonce"],
       "request_digest":request["request_digest"],"profile_digest":request["profile_digest"],
       "config_digest":request["config_digest"],"ok":True,
       "interpreter":{"executable":os.path.realpath(sys.executable),
                      "prefix":os.path.realpath(sys.prefix),
                      "version":".".join(str(x) for x in sys.version_info[:3])}}
Path(sys.argv[2]).write_text(json.dumps(ready,sort_keys=True,separators=(",",":")),encoding="utf-8")
deadline=time.monotonic()+float(request["policy"]["ready_seconds"])
while not Path(sys.argv[3]).exists():
    if time.monotonic() >= deadline: raise SystemExit(3)
    time.sleep(0.05)
cfg=SessionConfig(runtime_root=config["runtime_root"],cwd=config["cwd"],
    warm_policy="never",strict_drift=False,extra=config["extra"])
result=run_embedded_sync(workflow,config=cfg)
root=Path(config["extra"]["output_directory"])
outputs=[]
for raw in result.outputs:
    path=Path(raw)
    if not path.is_absolute() or path.is_symlink() or path.parent.resolve()!=root.resolve():
        raise RuntimeError("runtime output escaped owned output directory")
    info=path.stat()
    if not path.is_file() or info.st_nlink!=1:
        raise RuntimeError("runtime output is not a private regular file")
    outputs.append({"relative_path":path.name,"size_bytes":info.st_size,
                    "sha256":"sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()})
payload={"schema":"astrid.vibecomfy.result.v1","nonce":request["nonce"],
    "request_digest":request["request_digest"],"profile_digest":request["profile_digest"],
    "config_digest":request["config_digest"],"status":"succeeded",
    "run_id":result.run_id,"prompt_id":result.prompt_id,"outputs":outputs}
Path(sys.argv[4]).write_text(json.dumps(payload,sort_keys=True,separators=(",",":")),encoding="utf-8")
"""
_SECRET_KEY_WORDS = (
    "secret",
    "token",
    "password",
    "credential",
    "api_key",
    "private_key",
)
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")
_MAX_JSON_BYTES = 16 * 1024 * 1024
_MAX_RESULT_BYTES = 1024 * 1024
_MAX_OUTPUT_BYTES = 16 * 1024 * 1024 * 1024


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"pip_embedded {field} must be sha256:<64 lowercase hex")
    return value


def _strict_json_value(
    value: Any,
    *,
    path: str = "value",
    seen: set[int] | None = None,
    depth: int = 0,
) -> Any:
    if depth > 64:
        raise ValueError(f"{path} exceeds the JSON nesting limit")
    active = set() if seen is None else seen
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a non-finite number")
        return value
    marker = id(value)
    if marker in active:
        raise ValueError(f"{path} contains a cycle")
    active.add(marker)
    try:
        if isinstance(value, Mapping):
            result: dict[str, Any] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ValueError(f"{path} has a non-string key")
                result[key] = _strict_json_value(
                    item, path=f"{path}.{key}", seen=active, depth=depth + 1
                )
            return result
        if isinstance(value, (list, tuple)):
            return [
                _strict_json_value(item, path=f"{path}[{i}]", seen=active, depth=depth + 1)
                for i, item in enumerate(value)
            ]
    finally:
        active.discard(marker)
    raise ValueError(f"{path} contains an unsupported value")


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze_json(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(v) for v in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _thaw_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_json(v) for v in value]
    return value


def _strict_load_json(path: Path, *, limit: int) -> dict[str, Any]:
    if not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("pip_embedded requires no-follow file custody")
    flags = os.O_RDONLY | os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError("JSON transport document is not safely openable") from exc
    try:
        info = os.fstat(fd)
        if stat.S_IFMT(info.st_mode) != stat.S_IFREG or info.st_nlink != 1:
            raise ValueError("JSON transport document is not a private regular file")
        with os.fdopen(fd, "rb", closefd=True) as stream:
            fd = -1
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("JSON transport document is too large")
    finally:
        if fd >= 0:
            os.close(fd)

    def reject_constant(value: str) -> Any:
        raise ValueError(f"non-finite JSON constant {value}")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = item
        return result

    decoded = json.loads(
        raw.decode("utf-8"), object_pairs_hook=reject_duplicates, parse_constant=reject_constant
    )
    if not isinstance(decoded, dict):
        raise ValueError("JSON transport document must be an object")
    _strict_json_value(decoded)
    return decoded


def _require_absolute_path(value: str | Path, field: str, *, directory: bool = False) -> str:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"pip_embedded {field} must be an explicit absolute path")
    if path.is_symlink():
        raise ValueError(f"pip_embedded {field} must not be a symlink")
    resolved = path.resolve(strict=False)
    if directory:
        if path.exists() and not path.is_dir():
            raise ValueError(f"pip_embedded {field} must be a directory")
    elif path.exists() and not path.is_file():
        raise ValueError(f"pip_embedded {field} must be a file")
    return str(resolved)


def _assert_secret_free(value: Any, *, path: str = "profile") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if any(word in str(key).lower() for word in _SECRET_KEY_WORDS):
                raise ValueError(f"pip_embedded profile contains secret-shaped field {path}.{key}")
            _assert_secret_free(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_secret_free(item, path=f"{path}[{index}]")


def _profile_interpreters(raw: object) -> list[dict[str, str]]:
    if not isinstance(raw, str):
        raise ValueError("pip_embedded HC-03 interpreter fact must be a JSON list")
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("pip_embedded HC-03 interpreter fact is malformed") from exc
    if not isinstance(values, list) or not values:
        raise ValueError("pip_embedded HC-03 interpreter fact is incomplete")
    result = []
    for value in values:
        if not isinstance(value, dict) or set(value) != {"path", "version", "sha256"}:
            raise ValueError("pip_embedded HC-03 interpreter identity is invalid")
        if not isinstance(value["version"], str) or not value["version"].strip():
            raise ValueError("pip_embedded HC-03 interpreter version is invalid")
        result.append(
            {
                "path": _require_absolute_path(value["path"], "interpreter fact path"),
                "version": value["version"],
                "sha256": _require_digest(value["sha256"], "interpreter fact sha256"),
            }
        )
    return result


def _normalize_hc03_profile(value: Mapping[str, Any]) -> dict[str, Any]:
    raw = _strict_json_value(value)
    if not isinstance(raw, dict):
        raise ValueError("pip_embedded HC-03 readiness profile must be an object")
    if isinstance(raw, dict) and isinstance(raw.get("runtime"), Mapping):
        _assert_secret_free({key: item for key, item in raw.items() if key != "runtime"})
        _assert_secret_free(
            {
                "runtime": {
                    key: item
                    for key, item in raw["runtime"].items()
                    if key != "credential_reference"
                }
            }
        )
    else:
        _assert_secret_free(raw)
    if raw.get("schema_version") != "hc03-worker-readiness.v1" or raw.get("status") != "ready":
        raise ValueError("pip_embedded requires a ready HC-03 readiness profile")
    if set(raw) != {
        "schema_version",
        "status",
        "verified_facts",
        "verified_facts_digest",
        "runtime",
        "launch",
        "worker_actor",
        "worker_scopes",
    }:
        raise ValueError("pip_embedded HC-03 readiness schema is invalid")
    facts = raw["verified_facts"]
    if not isinstance(facts, Mapping) or set(facts) != {"exact", "minimum"}:
        raise ValueError("pip_embedded HC-03 verified facts are incomplete")
    exact, minimum = facts["exact"], facts["minimum"]
    expected_exact = {
        "interpreter",
        "runtime_lock",
        "engine_lock",
        "model_digest",
        "custom_node_digest",
        "driver",
        "root",
        "port",
    }
    if not isinstance(exact, Mapping) or set(exact) != expected_exact:
        raise ValueError("pip_embedded HC-03 verified facts have an invalid schema")
    if not isinstance(minimum, Mapping) or set(minimum) != {"vram_bytes", "scratch_bytes"}:
        raise ValueError("pip_embedded HC-03 verified minima have an invalid schema")
    if (
        isinstance(exact["port"], bool)
        or not isinstance(exact["port"], int)
        or not 1 <= exact["port"] <= 65535
    ):
        raise ValueError("pip_embedded HC-03 port is invalid")
    if any(
        not isinstance(exact[key], str) or not exact[key].strip()
        for key in expected_exact - {"port"}
    ):
        raise ValueError("pip_embedded HC-03 exact facts are invalid")
    if any(
        isinstance(v, bool) or not isinstance(v, int) or v < 0 or v > 2**53 - 1
        for v in minimum.values()
    ):
        raise ValueError("pip_embedded HC-03 minimum facts are invalid")
    interpreters = _profile_interpreters(exact["interpreter"])
    runtime = raw["runtime"]
    launch = raw["launch"]
    runtime_keys = {
        "endpoint",
        "port",
        "pid",
        "process_birth_id",
        "runtime_instance_id",
        "runtime_epoch",
        "schema_digest",
        "coordinator_epoch",
        "active_realm",
        "credential_reference",
        "discovery_digest",
    }
    launch_keys = {
        "host_interpreter",
        "source_checkout",
        "engine_interpreter",
        "output_root",
        "pack_root",
        "support_root",
        "ready_file",
        "state_file",
        "boot_manifest_path",
        "boot_manifest_hash",
    }
    if not isinstance(runtime, Mapping) or set(runtime) not in (
        runtime_keys,
        runtime_keys - {"credential_reference"},
    ):
        raise ValueError("pip_embedded HC-03 Runtime schema is invalid")
    if not isinstance(launch, Mapping) or set(launch) != launch_keys:
        raise ValueError("pip_embedded HC-03 launch schema is invalid")
    if any(
        not isinstance(runtime[key], str) or not runtime[key].strip()
        for key in set(runtime) - {"port", "pid", "runtime_epoch"}
    ):
        raise ValueError("pip_embedded HC-03 Runtime facts are invalid")
    if any(
        isinstance(runtime[key], bool) or not isinstance(runtime[key], int) or runtime[key] <= 0
        for key in ("port", "pid", "runtime_epoch")
    ):
        raise ValueError("pip_embedded HC-03 Runtime numeric facts are invalid")
    endpoint = urllib_parse.urlsplit(runtime["endpoint"])
    if (
        endpoint.scheme != "http"
        or endpoint.hostname not in {"127.0.0.1", "localhost", "::1"}
        or endpoint.path not in {"", "/"}
        or endpoint.query
        or endpoint.fragment
        or endpoint.username
        or endpoint.password
        or endpoint.port != runtime["port"]
        or runtime["port"] != exact["port"]
    ):
        raise ValueError("pip_embedded HC-03 endpoint/port mismatch")
    if any(not isinstance(launch[key], str) or not launch[key].strip() for key in launch_keys):
        raise ValueError("pip_embedded HC-03 launch facts are invalid")
    for key in (
        "host_interpreter",
        "engine_interpreter",
        "source_checkout",
        "pack_root",
        "support_root",
        "ready_file",
        "state_file",
        "boot_manifest_path",
        "output_root",
    ):
        if Path(launch[key]).expanduser().resolve(strict=False) != Path(launch[key]).expanduser():
            raise ValueError(f"pip_embedded HC-03 launch.{key} is not canonical")
    if not _SHA256_RE.fullmatch(runtime["schema_digest"]) or not _SHA256_RE.fullmatch(
        runtime["discovery_digest"]
    ):
        raise ValueError("pip_embedded HC-03 Runtime digest is invalid")
    if raw["worker_actor"] != "astrid-pack-host" or raw["worker_scopes"] != [
        "handshake",
        "worker:register",
        "worker:execute",
        "tasks:read",
        "objects:read",
        "objects:write",
    ]:
        raise ValueError("pip_embedded HC-03 worker identity is invalid")
    normalized_facts = {
        "exact": dict(sorted(exact.items())),
        "minimum": dict(sorted(minimum.items())),
    }
    if raw["verified_facts_digest"] != _digest(normalized_facts):
        raise ValueError("pip_embedded HC-03 verified facts digest is invalid")
    projection = {
        "schema_version": raw["schema_version"],
        "status": raw["status"],
        "verified_facts": normalized_facts,
        "verified_facts_digest": _digest(normalized_facts),
        "runtime": {
            key: runtime[key] for key in sorted(runtime_keys) if key != "credential_reference"
        },
        "launch": {key: launch[key] for key in sorted(launch_keys)},
        "worker_actor": raw["worker_actor"],
        "worker_scopes": list(raw["worker_scopes"]),
        "_interpreter_identities": interpreters,
    }
    # The locator is checked for shape but never retained in the child profile.
    _assert_secret_free({key: item for key, item in raw.items() if key != "runtime"})
    return projection


@dataclass(frozen=True, slots=True)
class PipEmbeddedTimeouts:
    preparation_seconds: float = 5.0
    ready_seconds: float = 30.0
    execution_seconds: float = 3600.0
    term_seconds: float = 2.0
    kill_seconds: float = 3.0
    reap_seconds: float = 2.0
    cleanup_seconds: float = 5.0
    control_seconds: float = 15.0

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"pip_embedded timeout {name} must be finite and positive")


@dataclass(frozen=True, slots=True)
class _ChildResult:
    nonce: str
    run_id: str
    prompt_id: str | None
    outputs: tuple[tuple[str, int, str], ...]
    published_outputs: tuple[Path, ...] = ()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _reject_symlink_ancestors(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            raise ValueError(f"pip_embedded path contains a symlink: {path}")


def _remove_tree(path: Path, *, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    if not path.exists() and not path.is_symlink():
        return
    for child in sorted(path.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if time.monotonic() >= deadline:
            raise TimeoutError("pip_embedded cleanup deadline exceeded")
        if child.is_symlink() or child.is_file():
            child.unlink()
        elif child.is_dir():
            child.rmdir()
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        path.rmdir()


def _validate_profile_evidence(
    profile: "PipEmbeddedProfile", evidence: Mapping[str, Any]
) -> dict[str, Any]:
    raw = _strict_json_value(evidence)
    _assert_secret_free(raw, path="installation_evidence")
    required = {
        "engine_lock_path",
        "vibecomfy_root",
        "vibecomfy_revision",
        "python_sha256",
        "python_version",
        "python_prefix",
        "root_map",
        "model_manifest",
        "custom_node_manifest",
    }
    if not isinstance(raw, dict) or set(raw) != required:
        raise ValueError("pip_embedded installation evidence schema is incomplete")
    lock = Path(raw["engine_lock_path"])
    if lock != lock.resolve(strict=False) or lock.is_symlink() or not lock.is_file():
        raise ValueError("pip_embedded engine lock evidence is not a regular file")
    if _hash_file(lock) != profile.package_lock_digest:
        raise ValueError("pip_embedded engine lock bytes do not match package lock")
    if Path(raw["vibecomfy_root"]).resolve(strict=False) != Path(profile.engine_root):
        raise ValueError("pip_embedded VibeComfy root does not match profile")
    if raw["vibecomfy_revision"] != profile.vibecomfy_revision:
        raise ValueError("pip_embedded installed revision does not match profile")
    _require_digest(raw["python_sha256"], "installation python_sha256")
    prefix = _require_absolute_path(
        raw["python_prefix"], "installation python_prefix", directory=True
    )
    if prefix != profile.python_environment:
        raise ValueError("pip_embedded Python prefix does not match environment")
    if not isinstance(raw["python_version"], str) or not raw["python_version"]:
        raise ValueError("pip_embedded installation Python version is invalid")
    root_map = raw["root_map"]
    if not isinstance(root_map, Mapping) or set(root_map) != {
        "source",
        "model",
        "custom_node",
        "scratch",
        "cas",
    }:
        raise ValueError("pip_embedded root evidence is incomplete")
    for name, path in (
        ("source", profile.astrid_source_root),
        ("model", profile.model_root),
        ("custom_node", profile.custom_nodes_root),
        ("scratch", profile.scratch_root),
        ("cas", profile.cas_root),
    ):
        if root_map[name] != _digest({"path": str(path)}):
            raise ValueError(f"pip_embedded {name} root evidence does not match profile")
    if profile.hc03_profile["verified_facts"]["exact"]["root"] != _digest(
        dict(sorted(root_map.items()))
    ):
        raise ValueError("pip_embedded HC-03 root fact does not match producer root map")
    for name in ("model_manifest", "custom_node_manifest"):
        descriptor = raw[name]
        if not isinstance(descriptor, Mapping) or set(descriptor) != {"path", "digest", "sha256"}:
            raise ValueError(f"pip_embedded {name} evidence is incomplete")
        manifest = Path(descriptor["path"])
        if (
            manifest != manifest.resolve(strict=False)
            or manifest.is_symlink()
            or not manifest.is_file()
        ):
            raise ValueError(f"pip_embedded {name} manifest is not a regular file")
        if _hash_file(manifest) != descriptor["sha256"]:
            raise ValueError(f"pip_embedded {name} manifest bytes do not match evidence")
        _require_digest(descriptor["digest"], f"{name} digest")
    if (
        profile.hc03_profile["verified_facts"]["exact"]["model_digest"]
        != raw["model_manifest"]["digest"]
    ):
        raise ValueError("pip_embedded model manifest does not match HC-03")
    if (
        profile.hc03_profile["verified_facts"]["exact"]["custom_node_digest"]
        != raw["custom_node_manifest"]["digest"]
    ):
        raise ValueError("pip_embedded custom-node manifest does not match HC-03")
    return raw


@dataclass(frozen=True, slots=True)
class PipEmbeddedProfile:
    python_executable: str | Path
    python_environment: str | Path
    vibecomfy_revision: str
    package_lock_digest: str
    astrid_source_root: str | Path
    astrid_pack_root: str | Path
    engine_root: str | Path
    custom_nodes_root: str | Path
    model_root: str | Path
    output_root: str | Path
    scratch_root: str | Path
    cas_root: str | Path
    hc03_profile: Mapping[str, Any]
    installation_evidence: Mapping[str, Any] | None = None
    hc03_handoff_hash: str | None = None
    timeouts: PipEmbeddedTimeouts = PipEmbeddedTimeouts()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "python_executable",
            _require_absolute_path(self.python_executable, "python_executable"),
        )
        object.__setattr__(
            self,
            "python_environment",
            _require_absolute_path(self.python_environment, "python_environment", directory=True),
        )
        for field in (
            "astrid_source_root",
            "astrid_pack_root",
            "engine_root",
            "custom_nodes_root",
            "model_root",
            "output_root",
            "scratch_root",
            "cas_root",
        ):
            object.__setattr__(
                self, field, _require_absolute_path(getattr(self, field), field, directory=True)
            )
        for field in (
            "python_environment",
            "astrid_source_root",
            "astrid_pack_root",
            "engine_root",
            "custom_nodes_root",
            "model_root",
            "output_root",
            "scratch_root",
            "cas_root",
        ):
            root = Path(getattr(self, field))
            _reject_symlink_ancestors(root)
            if not root.is_dir():
                raise ValueError(f"pip_embedded {field} must be an existing directory")
        _reject_symlink_ancestors(Path(self.python_executable))
        if not Path(self.python_executable).is_file():
            raise ValueError("pip_embedded python_executable must be an existing file")
        if not isinstance(self.timeouts, PipEmbeddedTimeouts):
            raise TypeError("pip_embedded timeouts must be typed")
        if Path(self.python_environment) not in Path(self.python_executable).parents:
            raise ValueError("pip_embedded executable is not inside the pinned environment")
        if not isinstance(self.vibecomfy_revision, str) or not re.fullmatch(
            r"[0-9a-f]{40}", self.vibecomfy_revision
        ):
            raise ValueError("pip_embedded vibecomfy_revision must be a pinned commit")
        object.__setattr__(
            self,
            "package_lock_digest",
            _require_digest(self.package_lock_digest, "package_lock_digest"),
        )
        readiness = _normalize_hc03_profile(self.hc03_profile)
        identities = readiness.pop("_interpreter_identities")
        selected = next(
            (item for item in identities if item["path"] == self.python_executable), None
        )
        if selected is None:
            raise ValueError("pip_embedded selected interpreter is absent from HC-03 identity list")
        if not any(item["path"] == readiness["launch"]["host_interpreter"] for item in identities):
            raise ValueError("pip_embedded host interpreter is absent from HC-03 identity list")
        if readiness["launch"]["engine_interpreter"] != self.python_executable:
            raise ValueError("pip_embedded engine interpreter does not match HC-03 readiness")
        if (
            readiness["launch"]["source_checkout"] != self.astrid_source_root
            or readiness["launch"]["pack_root"] != self.astrid_pack_root
        ):
            raise ValueError("pip_embedded source/pack roots do not match HC-03 readiness")
        if readiness["launch"]["output_root"] != self.output_root:
            raise ValueError("pip_embedded output root does not match HC-03 readiness")
        if readiness["verified_facts"]["exact"]["engine_lock"] != self.package_lock_digest:
            raise ValueError("pip_embedded package lock does not match HC-03 readiness")
        if not isinstance(self.installation_evidence, Mapping):
            raise ValueError("pip_embedded installation evidence is required")
        evidence = _validate_profile_evidence(self, self.installation_evidence)
        if evidence["python_sha256"] != selected["sha256"]:
            raise ValueError("pip_embedded executable bytes do not match installation evidence")
        if self.hc03_handoff_hash is None:
            raise ValueError("pip_embedded external HC-03 handoff hash is required")
        _require_digest(self.hc03_handoff_hash, "hc03_handoff_hash")
        object.__setattr__(self, "hc03_profile", _freeze_json(readiness))
        object.__setattr__(self, "installation_evidence", _freeze_json(evidence))

    @classmethod
    def from_hc03(cls, **kwargs: Any) -> "PipEmbeddedProfile":
        return cls(**kwargs)

    @property
    def command(self) -> tuple[str, ...]:
        return (
            str(self.python_executable),
            "-I",
            "-B",
            "-c",
            _PIP_EMBEDDED_SCRIPT,
            "<request>",
            "<ready>",
            "<go>",
            "<result>",
        )

    @property
    def identity(self) -> dict[str, Any]:
        return {
            "schema": _PIP_EMBEDDED_PROFILE_SCHEMA,
            "profile": "pip_embedded",
            "python_executable": self.python_executable,
            "python_environment": self.python_environment,
            "vibecomfy_revision": self.vibecomfy_revision,
            "package_lock_digest": self.package_lock_digest,
            "astrid_source_root": self.astrid_source_root,
            "astrid_pack_root": self.astrid_pack_root,
            "engine_root": self.engine_root,
            "custom_nodes_root": self.custom_nodes_root,
            "model_root": self.model_root,
            "output_root": self.output_root,
            "scratch_root": self.scratch_root,
            "cas_root": self.cas_root,
            "hc03_handoff_hash": self.hc03_handoff_hash,
            "hc03": _thaw_json(self.hc03_profile),
            "installation_evidence": _thaw_json(self.installation_evidence),
        }

    @property
    def identity_digest(self) -> str:
        return _digest(self.identity)

    @property
    def command_digest(self) -> str:
        return _digest(
            {
                "argv": list(self.command),
                "cwd_policy": "private_runtime",
                "flags": ["-I", "-B"],
                "timeouts": {
                    name: getattr(self.timeouts, name)
                    for name in self.timeouts.__dataclass_fields__
                },
            }
        )

    @property
    def readiness_digest(self) -> str:
        return _digest(_thaw_json(self.hc03_profile))

    @property
    def profile_digest(self) -> str:
        return _digest(
            {
                "identity": self.identity,
                "command_digest": self.command_digest,
                "readiness_digest": self.readiness_digest,
                "policy": {
                    "execution": "isolated_cold",
                    "warm_reuse": False,
                    "timeouts": self.timeouts.__dict__
                    if hasattr(self.timeouts, "__dict__")
                    else {
                        name: getattr(self.timeouts, name)
                        for name in self.timeouts.__dataclass_fields__
                    },
                },
            }
        )

    def to_dict(self) -> dict[str, Any]:
        value = {
            "schema": _PIP_EMBEDDED_PROFILE_SCHEMA,
            "profile": "pip_embedded",
            "identity": self.identity,
            "command": {"argv": list(self.command), "cwd_policy": "private_runtime"},
            "readiness": _thaw_json(self.hc03_profile),
            "policy": {"execution": "isolated_cold", "warm_reuse": False},
            "digests": {
                "identity": self.identity_digest,
                "command": self.command_digest,
                "readiness": self.readiness_digest,
                "profile": self.profile_digest,
            },
        }
        _assert_secret_free(value)
        return value


class PipEmbeddedExecution(Protocol):
    def start(self) -> None: ...
    def wait_ready(self, timeout: float) -> None: ...
    def go(self) -> None: ...
    def run(self, timeout: float, cancel_event: threading.Event | None = None) -> _ChildResult: ...
    def terminate(self, term_seconds: float, kill_seconds: float, reap_seconds: float) -> None: ...
    def cleanup(self) -> None: ...


class _SubprocessEmbeddedExecution:
    def __init__(
        self, profile: PipEmbeddedProfile, request: Mapping[str, Any], staging: Path
    ) -> None:
        self.profile, self.request, self.staging = profile, dict(request), staging
        self.runtime_dir = staging / "runtime"
        self.input_dir = staging / "input"
        self.output_dir = staging / "engine-output"
        self.temp_dir = staging / "temp"
        for path in (self.runtime_dir, self.input_dir, self.output_dir, self.temp_dir):
            path.mkdir()
        self.request_path, self.ready_path = staging / "request.json", staging / "ready.json"
        self.go_path, self.result_path, self.log_path = (
            staging / "GO",
            staging / "result.json",
            staging / "embedded.log",
        )
        config = {
            "runtime_root": str(self.runtime_dir),
            "cwd": str(self.runtime_dir),
            "extra": {
                "input_directory": str(self.input_dir),
                "output_directory": str(self.output_dir),
                "temp_directory": str(self.temp_dir),
                "extra_model_paths_config": [str(staging / "paths.yaml")],
            },
        }
        self.request["config"] = config
        self.request["config_digest"] = _digest(config)
        self.request["request_digest"] = _digest(
            {key: value for key, value in self.request.items() if key != "request_digest"}
        )
        self.request_path.write_bytes(_canonical_json(self.request).encode())
        self._process: subprocess.Popen[bytes] | None = None
        self._log_handle: Any = None

    def start(self) -> None:
        from astrid.core.execution.process_group import popen_owned_group

        argv = [
            str(self.profile.python_executable),
            "-I",
            "-B",
            "-c",
            _PIP_EMBEDDED_SCRIPT,
            str(self.request_path),
            str(self.ready_path),
            str(self.go_path),
            str(self.result_path),
        ]
        environment = {
            "PATH": str(Path(self.profile.python_executable).parent),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "VIRTUAL_ENV": str(self.profile.python_environment),
            "VIBECOMFY_WATCHDOG": "0",
        }
        self._log_handle = self.log_path.open("wb")
        try:
            self._process = popen_owned_group(
                argv,
                cwd=str(self.runtime_dir),
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=self._log_handle,
                stderr=subprocess.STDOUT,
                close_fds=True,
            )
        except BaseException:
            self._log_handle.close()
            self._log_handle = None
            raise

    def wait_ready(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.ready_path.is_file():
                ready = _strict_load_json(self.ready_path, limit=_MAX_RESULT_BYTES)
                if ready.get("ok") is not True:
                    raise RuntimeError(str(ready.get("error") or "embedded child rejected request"))
                interpreter = ready.get("interpreter")
                expected_interpreter = self.profile.installation_evidence
                if (
                    not isinstance(interpreter, Mapping)
                    or interpreter.get("executable") != str(self.profile.python_executable)
                    or interpreter.get("prefix") != str(self.profile.python_environment)
                    or interpreter.get("version") != expected_interpreter["python_version"]
                ):
                    raise RuntimeError("embedded READY interpreter identity mismatch")
                expected = {
                    "nonce": self.request["nonce"],
                    "request_digest": self.request["request_digest"],
                    "profile_digest": self.request["profile_digest"],
                    "config_digest": self.request["config_digest"],
                }
                if any(ready.get(key) != value for key, value in expected.items()):
                    raise RuntimeError("embedded READY identity mismatch")
                return
            if self._process is None or self._process.returncode is not None:
                raise RuntimeError("embedded child exited before READY")
            time.sleep(0.05)
        raise TimeoutError("embedded child READY deadline exceeded")

    def go(self) -> None:
        self.go_path.write_bytes(b"go\n")

    def run(self, timeout: float, cancel_event: threading.Event | None = None) -> _ChildResult:
        if self._process is None:
            raise RuntimeError("embedded process was not started")
        deadline = time.monotonic() + timeout
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("embedded run cancelled")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("embedded execution deadline exceeded")
            try:
                self._process.wait(timeout=min(0.05, remaining))
                break
            except subprocess.TimeoutExpired:
                continue
        if self._process.returncode != 0:
            raise RuntimeError(f"embedded execution exited with status {self._process.returncode}")
        from astrid.core.execution.process_group import _group_id, _process_snapshot

        snapshot = _process_snapshot()
        if not snapshot and self._process.returncode is None:
            raise RuntimeError("embedded process-group census unavailable")
        if any(info.pgid == _group_id(self._process) for info in snapshot.values()):
            raise RuntimeError("embedded descendants remain live after child exit")
        value = _strict_load_json(self.result_path, limit=_MAX_RESULT_BYTES)
        if set(value) != {
            "schema",
            "nonce",
            "request_digest",
            "profile_digest",
            "config_digest",
            "status",
            "run_id",
            "prompt_id",
            "outputs",
        }:
            raise ValueError("embedded result schema is invalid")
        if (
            value["schema"] != _RESULT_SCHEMA
            or value["nonce"] != self.request["nonce"]
            or value["request_digest"] != self.request["request_digest"]
            or value["profile_digest"] != self.request["profile_digest"]
            or value["config_digest"] != self.request["config_digest"]
            or value["status"] != "succeeded"
        ):
            raise ValueError("embedded result identity/status is invalid")
        if (
            not isinstance(value["run_id"], str)
            or not value["run_id"]
            or (value["prompt_id"] is not None and not isinstance(value["prompt_id"], str))
        ):
            raise ValueError("embedded result identifiers are invalid")
        outputs: list[tuple[str, int, str]] = []
        if not isinstance(value["outputs"], list) or len(value["outputs"]) > 64:
            raise ValueError("embedded result outputs are invalid")
        total_size = 0
        seen_names: set[str] = set()
        for item in value["outputs"]:
            if not isinstance(item, dict) or set(item) != {"relative_path", "size_bytes", "sha256"}:
                raise ValueError("embedded output descriptor is invalid")
            name = item["relative_path"]
            if (
                not isinstance(name, str)
                or not name
                or Path(name).name != name
                or name in {".", ".."}
                or "/" in name
                or "\\" in name
                or "\x00" in name
            ):
                raise ValueError("embedded output path is invalid")
            if name in seen_names:
                raise ValueError("embedded result contains duplicate outputs")
            seen_names.add(name)
            if (
                isinstance(item["size_bytes"], bool)
                or not isinstance(item["size_bytes"], int)
                or item["size_bytes"] < 0
            ):
                raise ValueError("embedded output size is invalid")
            total_size += item["size_bytes"]
            if total_size > _MAX_OUTPUT_BYTES:
                raise ValueError("embedded result outputs exceed the configured bound")
            outputs.append(
                (name, item["size_bytes"], _require_digest(item["sha256"], "output sha256"))
            )
        return _ChildResult(value["nonce"], value["run_id"], value["prompt_id"], tuple(outputs))

    def terminate(self, term_seconds: float, kill_seconds: float, reap_seconds: float) -> None:
        process = self._process
        if process is None:
            return
        from astrid.core.execution.process_group import signal_group

        signal_group(process, signal.SIGTERM)
        self._bounded_group_wait(process, term_seconds, signal_group, signal.SIGTERM)
        if process.returncode is None:
            signal_group(process, signal.SIGKILL)
            self._bounded_group_wait(process, kill_seconds, signal_group, signal.SIGKILL)
        try:
            process.wait(timeout=reap_seconds)
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError("embedded child reap deadline exceeded") from exc
        from astrid.core.execution.process_group import _group_id, _process_snapshot

        if any(info.pgid == _group_id(process) for info in _process_snapshot().values()):
            raise TimeoutError("embedded descendants remain live after reap")

    @staticmethod
    def _bounded_group_wait(
        process: subprocess.Popen[bytes], seconds: float, sender: Any, sig: int
    ) -> None:
        from astrid.core.execution.process_group import _group_id, _process_snapshot

        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            snapshot = _process_snapshot()
            if not snapshot and process.returncode is None:
                raise TimeoutError("embedded process-group census unavailable")
            members = [info for info in snapshot.values() if info.pgid == _group_id(process)]
            if not members:
                return
            sender(process, sig)
            time.sleep(min(0.05, max(0.001, deadline - time.monotonic())))
        raise TimeoutError("embedded process group containment deadline exceeded")

    def cleanup(self) -> None:
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None


ExecutionFactory = Callable[[PipEmbeddedProfile, Mapping[str, Any], Path], PipEmbeddedExecution]


class PipEmbeddedSession:
    def __init__(
        self,
        profile: PipEmbeddedProfile,
        *,
        execution_factory: ExecutionFactory | None = None,
        timeouts: PipEmbeddedTimeouts | None = None,
    ) -> None:
        if not isinstance(profile, PipEmbeddedProfile):
            raise TypeError("pip_embedded requires a PipEmbeddedProfile")
        self.profile = profile
        self.timeouts = timeouts or profile.timeouts
        self._execution_factory = execution_factory or (
            lambda selected_profile, request, staging: _SubprocessEmbeddedExecution(
                selected_profile, request, staging
            )
        )
        self._lock = threading.RLock()
        self._record: dict[str, Any] | None = None
        self._poisoned = False
        self._disposed: dict[str, Any] | None = None
        self.last_lifecycle, self.last_warm_reused = "cold", False

    @property
    def warm(self) -> bool:
        return False

    @property
    def poisoned(self) -> bool:
        return self._poisoned

    @property
    def fence_pending(self) -> bool:
        return self._poisoned

    def _reserve(self, identity: str) -> dict[str, Any]:
        with self._lock:
            if self._poisoned:
                raise RuntimeError("pip_embedded session is poisoned; create a new cold instance")
            if self._record is not None:
                raise RuntimeError("pip_embedded execution is already in progress")
            self._disposed = None
            record = {
                "nonce": uuid.uuid4().hex,
                "identity": identity,
                "phase": "PREPARING",
                "stop": None,
                "cancel_event": threading.Event(),
                "handle": None,
                "done": threading.Event(),
                "outcome": None,
                "staging": None,
                "outputs": None,
            }
            self._record = record
            return record

    @staticmethod
    def _task_identity(value: str | None) -> str:
        if value is None:
            return "task-unspecified"
        if not isinstance(value, str) or not value.strip():
            raise ValueError("pip_embedded task identity must be non-empty")
        return value

    def _finalize(
        self, record: dict[str, Any], outcome: dict[str, Any], *, poison: bool = False
    ) -> None:
        with self._lock:
            if record["outcome"] is not None:
                return
            record["outcome"] = outcome
            if poison:
                self._poisoned = True
            if record["stop"] is not None:
                self._disposed = {
                    "ok": outcome.get("reaped") is True,
                    "status": record["stop"],
                    "transition": record["stop"],
                    "terminated": outcome.get("reaped") is True,
                    "reaped": outcome.get("reaped") is True,
                }
            self._record = None
            record["done"].set()

    def run(
        self, workflow: Any, *, task_identity: str | None = None, out_dir: Path | None = None
    ) -> Any:
        identity = self._task_identity(task_identity)
        record = self._reserve(identity)

        handle: PipEmbeddedExecution | None = None
        staging: Path | None = None
        published: list[Path] = []
        cleaned = False
        try:
            if out_dir is None:
                raise ValueError("pip_embedded requires an explicit output directory")
            destination = self.validate_output_dir(out_dir)
            destination.mkdir(parents=True, exist_ok=True)
            from vibecomfy.workflow import VibeWorkflow

            if type(workflow) is not VibeWorkflow:
                raise ValueError("unsupported_workflow: expected pinned VibeWorkflow")
            envelope = _strict_json_value(workflow.to_envelope(), path="workflow")
            if envelope.get("vibecomfy_format_version") is None:
                raise ValueError("unsupported_workflow: missing VibeComfy format stamp")
            request = {
                "schema": _REQUEST_SCHEMA,
                "nonce": record["nonce"],
                "task_identity": identity,
                "profile_digest": self.profile.profile_digest,
                "workflow": envelope,
                "workflow_digest": _digest(envelope),
                "config_digest": None,
                "profile_readiness_digest": self.profile.readiness_digest,
                "policy": {
                    "ready_seconds": self.timeouts.ready_seconds,
                    "execution_seconds": self.timeouts.execution_seconds,
                },
            }
            staging = Path(tempfile.mkdtemp(dir=self.profile.scratch_root, prefix="pip-embedded-"))
            record["staging"] = staging
            (staging / "paths.yaml").write_text(
                "vibecomfy:\n"
                f"  base_path: {self.profile.model_root}\n"
                "  checkpoints: checkpoints\n"
                "  clip: clip\n"
                "  clip_vision: clip_vision\n"
                "  configs: configs\n"
                "  controlnet: controlnet\n"
                "  diffusion_models: diffusion_models\n"
                "  embeddings: embeddings\n"
                "  loras: loras\n"
                "  style_models: style_models\n"
                "  unet: unet\n"
                "  upscale_models: upscale_models\n"
                "  vae: vae\n"
                "  vae_approx: vae_approx\n"
                "  text_encoders: text_encoders\n"
                "  audio_encoders: audio_encoders\n"
                f"  custom_nodes: {self.profile.custom_nodes_root}\n",
                encoding="utf-8",
            )
            with self._lock:
                if record["stop"] is not None:
                    raise RuntimeError("pip_embedded run cancelled before spawn")
                record["phase"] = "SPAWNING"
            handle = self._execution_factory(self.profile, request, staging)
            with self._lock:
                record["handle"] = handle
                if record["stop"] is not None:
                    raise RuntimeError("pip_embedded run cancelled during factory")
                record["phase"] = "PREFLIGHT"
            handle.start()
            with self._lock:
                if record["stop"] is not None:
                    raise RuntimeError("pip_embedded run cancelled before GO")
            handle.wait_ready(self.timeouts.ready_seconds)
            with self._lock:
                if record["stop"] is not None:
                    raise RuntimeError("pip_embedded run cancelled before GO")
                record["phase"] = "RUNNING"
            handle.go()
            try:
                result = handle.run(self.timeouts.execution_seconds, record["cancel_event"])
            except TypeError as exc:
                if "positional" not in str(exc) and "argument" not in str(exc):
                    raise
                result = handle.run(self.timeouts.execution_seconds)
            if not isinstance(result, _ChildResult) or result.nonce != record["nonce"]:
                raise ValueError("embedded result nonce/type mismatch")
            with self._lock:
                if record["stop"] is not None:
                    raise RuntimeError("pip_embedded run cancelled during execution")
                record["phase"] = "COLLECTING"
            published = self._collect_outputs(handle, result, destination)
            result = _ChildResult(
                result.nonce, result.run_id, result.prompt_id, result.outputs, tuple(published)
            )
            with self._lock:
                if record["stop"] is not None:
                    raise RuntimeError("pip_embedded run cancelled during output collection")
            cleaned = True
            handle.cleanup()
            _remove_tree(staging, timeout=self.timeouts.cleanup_seconds)
            staging = None
            with self._lock:
                if record["stop"] is not None:
                    raise RuntimeError("pip_embedded run cancelled during finalization")
                self._finalize(
                    record, {"ok": True, "result": result, "outputs": published, "reaped": True}
                )
            return result
        except BaseException as exc:
            poison = not (isinstance(exc, RuntimeError) and "cancelled" in str(exc))
            reaped = False
            if handle is not None:
                try:
                    if not cleaned:
                        handle.terminate(
                            self.timeouts.term_seconds,
                            self.timeouts.kill_seconds,
                            self.timeouts.reap_seconds,
                        )
                    reaped = True
                except BaseException:
                    poison = True
                try:
                    if not cleaned:
                        cleaned = True
                        handle.cleanup()
                except BaseException:
                    poison = True
            if published:
                try:
                    _remove_tree(published[0].parent, timeout=self.timeouts.cleanup_seconds)
                except BaseException:
                    poison = True
            if staging is not None and not poison:
                try:
                    _remove_tree(staging, timeout=self.timeouts.cleanup_seconds)
                except BaseException:
                    poison = True
            self._finalize(
                record, {"ok": False, "error": str(exc), "reaped": reaped}, poison=poison
            )
            raise

    def _collect_outputs(
        self, handle: PipEmbeddedExecution, result: _ChildResult, destination: Path
    ) -> list[Path]:
        source = getattr(handle, "output_dir", None)
        if not isinstance(source, Path):
            raise RuntimeError("embedded output custody is unavailable")
        _reject_symlink_ancestors(source)
        _reject_symlink_ancestors(destination)
        publication = destination / f".pip-embedded-{uuid.uuid4().hex}"
        publication.mkdir(mode=0o700)
        created: list[Path] = []
        deadline = time.monotonic() + self.timeouts.cleanup_seconds
        try:
            names: set[str] = set()
            total_size = 0
            for name, size, expected in result.outputs:
                if time.monotonic() >= deadline:
                    raise TimeoutError("embedded output collection deadline exceeded")
                if name in names or name in {".", ".."} or Path(name).name != name:
                    raise ValueError("duplicate or invalid embedded output")
                names.add(name)
                total_size += size
                if total_size > _MAX_OUTPUT_BYTES:
                    raise ValueError("embedded output set exceeds configured bound")
                src, dst = source / name, publication / name
                if src.is_symlink() or not src.is_file() or dst.exists() or dst.is_symlink():
                    raise ValueError("embedded output custody rejected path")
                source_fd = os.open(src, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                destination_fd: int | None = None
                try:
                    before = os.fstat(source_fd)
                    if (
                        stat.S_IFMT(before.st_mode) != stat.S_IFREG
                        or before.st_nlink != 1
                        or before.st_size != size
                    ):
                        raise ValueError("embedded output custody rejected file")
                    destination_fd = os.open(
                        dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
                    )
                    with (
                        os.fdopen(source_fd, "rb", closefd=True) as reader,
                        os.fdopen(destination_fd, "wb", closefd=True) as writer,
                    ):
                        source_fd, destination_fd = -1, -1
                        digest = hashlib.sha256()
                        while chunk := reader.read(1024 * 1024):
                            if time.monotonic() >= deadline:
                                raise TimeoutError("embedded output collection deadline exceeded")
                            digest.update(chunk)
                            writer.write(chunk)
                        writer.flush()
                        os.fsync(writer.fileno())
                finally:
                    if source_fd >= 0:
                        os.close(source_fd)
                    if destination_fd is not None and destination_fd >= 0:
                        os.close(destination_fd)
                after = os.stat(src, follow_symlinks=False)
                if (
                    after.st_dev,
                    after.st_ino,
                    after.st_nlink,
                    after.st_size,
                    after.st_mtime_ns,
                ) != (
                    before.st_dev,
                    before.st_ino,
                    before.st_nlink,
                    before.st_size,
                    before.st_mtime_ns,
                ):
                    raise ValueError("embedded output mutated during custody")
                if "sha256:" + digest.hexdigest() != expected:
                    raise ValueError("embedded output digest mismatch")
                created.append(dst)
            published = destination / f"pip-embedded-{uuid.uuid4().hex}"
            if published.exists() or published.is_symlink():
                raise FileExistsError("embedded publication name occupied")
            os.rename(publication, published)
            directory_fd = os.open(destination, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return [published / path.name for path in created]
        except BaseException:
            _remove_tree(publication, timeout=self.timeouts.cleanup_seconds)
            raise

    def _control(self, reason: str, task_identity: str | None) -> dict[str, Any]:
        identity = self._task_identity(task_identity)
        with self._lock:
            record = self._record
            if record is None:
                if self._disposed is None:
                    self._disposed = {
                        "ok": True,
                        "status": "cold",
                        "transition": reason,
                        "terminated": False,
                        "reaped": True,
                    }
                return dict(self._disposed)
            if record["identity"] != identity:
                self._poisoned = True
                record["stop"] = "identity-mismatch"
                raise RuntimeError("pip_embedded active handle identity mismatch")
            if record["stop"] is None:
                record["stop"] = reason
            record["cancel_event"].set()
            event = record["done"]
        if not event.wait(timeout=self.timeouts.control_seconds):
            self._poisoned = True
            raise RuntimeError("pip_embedded pending containment")
        outcome = record["outcome"] or {
            "ok": False,
            "error": "missing terminal outcome",
            "reaped": False,
        }
        return {
            "ok": outcome.get("ok") is True,
            "status": reason,
            "transition": reason,
            "terminated": outcome.get("reaped") is True,
            "reaped": outcome.get("reaped") is True,
        }

    def cancel(self, *, task_identity: str | None = None) -> dict[str, Any]:
        return self._control("cancelled", task_identity)

    def release(self, *, task_identity: str | None = None) -> dict[str, Any]:
        return self._control("released", task_identity)

    def validate_output_dir(self, out_dir: Path) -> Path:
        candidate = Path(out_dir).expanduser()
        if not candidate.is_absolute():
            raise ValueError("pip_embedded output directory must be explicit and absolute")
        _reject_symlink_ancestors(candidate)
        resolved = candidate.resolve(strict=False)
        root = Path(self.profile.output_root)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                "pip_embedded output directory is outside the profile output root"
            ) from exc
        return resolved


class _NoRedirectHandler(urllib_request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> Any:
        raise ValueError("checkout_server remote request redirected unexpectedly")


def _open_checkout_http(request: urllib_request.Request, *, timeout: float) -> Any:
    """Open one checkout-server request without following redirects."""
    return urllib_request.build_opener(_NoRedirectHandler).open(request, timeout=timeout)


def _validate_checkout_server_url(server_url: str) -> str:
    """Return a canonical, origin-only HTTP(S) endpoint."""
    if not isinstance(server_url, str) or not server_url:
        raise ValueError("checkout_server requires an explicit server_url")
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in server_url):
        raise ValueError(
            "checkout_server server_url must not contain whitespace or control characters"
        )
    if "\\" in server_url:
        raise ValueError("checkout_server server_url must not contain backslashes")
    if "?" in server_url or "#" in server_url:
        raise ValueError("checkout_server server_url must not contain query or fragment")
    parsed = urllib_parse.urlsplit(server_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("checkout_server server_url must be an HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("checkout_server server_url must not contain credentials")
    if parsed.netloc.endswith(":"):
        raise ValueError("checkout_server server_url has an invalid port")
    if parsed.query or parsed.fragment:
        raise ValueError("checkout_server server_url must not contain query or fragment")
    if parsed.path not in {"", "/"}:
        raise ValueError("checkout_server server_url must contain only an origin")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("checkout_server server_url has an invalid port") from exc
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("checkout_server server_url has an invalid port")

    host = parsed.hostname
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in host):
        raise ValueError("checkout_server server_url has an invalid host")
    if ":" in host:
        # IPv6 literals must use the bracketed URL spelling.
        try:
            import ipaddress

            ipaddress.IPv6Address(host)
        except ValueError as exc:
            raise ValueError("checkout_server server_url has an invalid host") from exc
        host_part = f"[{host.lower()}]"
    else:
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", host):
            raise ValueError("checkout_server server_url has an invalid host")
        if ".." in host or any(
            not label or label.startswith("-") or label.endswith("-") for label in host.split(".")
        ):
            raise ValueError("checkout_server server_url has an invalid host")
        host_part = host.lower()
    return f"{parsed.scheme}://{host_part}{f':{port}' if port is not None else ''}"


def _validate_output_field(
    value: object,
    *,
    field: str,
    allow_empty: bool = False,
    reject_slash: bool = False,
) -> str:
    if not isinstance(value, str) or (not value and not allow_empty):
        raise ValueError(f"checkout_server output descriptor has invalid {field}")
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 or char == "\\" for char in value):
        raise ValueError(f"checkout_server output descriptor has unsafe {field}")
    if value.startswith("/") or value.startswith("~") or urllib_parse.urlsplit(value).scheme:
        raise ValueError(f"checkout_server output descriptor has unsafe {field}")
    if ".." in value or (reject_slash and "/" in value):
        raise ValueError(f"checkout_server output descriptor has unsafe {field}")
    if not allow_empty and not value:
        raise ValueError(f"checkout_server output descriptor has invalid {field}")
    return value


def _validate_output_descriptor(descriptor: object) -> tuple[str, str, str]:
    if not isinstance(descriptor, dict):
        raise ValueError("checkout_server output descriptor must be an object")
    if set(descriptor) != {"filename", "subfolder", "type"}:
        raise ValueError("checkout_server output descriptor has an invalid schema")
    filename = _validate_output_field(
        descriptor.get("filename"), field="filename", reject_slash=True
    )
    subfolder = _validate_output_field(
        descriptor.get("subfolder"), field="subfolder", allow_empty=True
    )
    output_type = _validate_output_field(descriptor.get("type"), field="type")
    if output_type not in {"output", "temp"}:
        raise ValueError("checkout_server output descriptor has invalid type")
    return filename, subfolder, output_type


def _extract_output_descriptors(value: object) -> list[object]:
    "Find Comfy output descriptors nested in node/output containers."
    if isinstance(value, list):
        descriptors: list[object] = []
        for item in value:
            descriptors.extend(_extract_output_descriptors(item))
        return descriptors
    if isinstance(value, dict):
        if set(value) == {"filename", "subfolder", "type"}:
            return [value]
        descriptors = []
        for item in value.values():
            descriptors.extend(_extract_output_descriptors(item))
        return descriptors
    return []


# ---------------------------------------------------------------------------
# Size / resolution parsing helpers
# ---------------------------------------------------------------------------


def _parse_size(size: str) -> tuple[int, int]:
    """Parse ``WxH``, ``W*H``, ``W,H``, or a single integer into ``(width, height)``.

    Returns ``(1024, 1024)`` if *size* is empty or unparseable.
    """
    return parse_dimension_pair(size, allow_single=True) or (1024, 1024)


def _parse_resolution(res: str) -> tuple[int, int] | None:
    """Parse a resolution string like ``"1280x720"`` into ``(width, height)``.

    Accepted separators: ``x``, ``X``, ``*``, ``,``.  Returns ``None`` if
    *res* is empty or unparseable.
    """
    return parse_dimension_pair(res)


# ---------------------------------------------------------------------------
# VibeComfyBackend
# ---------------------------------------------------------------------------


class VibeComfyBackend(BackendAdapter):
    """Local generation backend via pinned VibeComfy ready templates.

    The base adapter has no transport endpoint.  ``CheckoutServerAdapter`` is
    the explicit remote-only subclass and owns all remote HTTP behavior.
    """

    def __init__(
        self,
        *,
        profile: PipEmbeddedProfile | None = None,
        execution_factory: ExecutionFactory | None = None,
    ) -> None:
        self._pip_embedded_profile = profile
        self._pip_embedded_session = (
            PipEmbeddedSession(profile, execution_factory=execution_factory)
            if profile is not None
            else None
        )

    def _run_workflow(self, workflow: Any) -> Any:
        session = getattr(self, "_pip_embedded_session", None)
        if session is None:
            raise ValueError(
                "pip_embedded requires an explicit PipEmbeddedProfile; "
                "ambient interpreter/package discovery is disabled"
            )
        raise ValueError(
            "pip_embedded direct workflow execution requires an explicit output directory"
        )

    def _collect_outputs(self, result: Any, out_dir: Path) -> list[Path]:
        # Kept for the checkout-server subclass; pip_embedded collection is
        # performed by PipEmbeddedSession while it still owns the source FD.
        session = getattr(self, "_pip_embedded_session", None)
        if session is not None:
            raise ValueError("pip_embedded output custody must be collected by its session")
        image_paths: list[Path] = []
        for output_path_str in result.outputs:
            src = Path(output_path_str)
            if not src.is_file():
                logger.warning("VibeComfy output not found: %s", src)
                continue
            dst = out_dir / src.name
            if dst.exists():
                stem, suffix, counter = src.stem, src.suffix, 1
                while dst.exists():
                    dst = out_dir / f"{stem}_{counter}{suffix}"
                    counter += 1
            shutil.copy2(src, dst)
            image_paths.append(dst)
        return image_paths

    #: Default canonical→template parameter name mapping per mode.
    #: Used as a fallback when ``BackendSpec.param_map`` is empty.
    #: Size and resolution are handled specially in :meth:`generate` so
    #: their entries here are nominal; the adapter splits width/height.
    DEFAULT_PARAM_MAP: dict[str, dict[str, str]] = {
        # ── Image modes ────────────────────────────────────────────────
        "t2i": {
            "prompt": "prompt",
            "negative_prompt": "negative_prompt",
            "seed": "seed",
            "count": "count",
            "size": "size",
            "guidance_scale": "guidance",
            "steps": "steps",
        },
        "i2i": {
            "prompt": "prompt",
            "seed": "seed",
            "image_ref": "image_ref",
            "size": "size",
            "strength": "denoise",
            "guidance_scale": "guidance",
            "steps": "steps",
        },
        "edit": {
            "prompt": "prompt",
            "seed": "seed",
            "count": "count",
            "image_ref": "image",
            "size": "size",
            "guidance_scale": "guidance",
            "steps": "steps",
        },
        # ── Video modes ────────────────────────────────────────────────
        "t2v": {
            "prompt": "prompt",
            "negative_prompt": "negative_prompt",
            "seed": "seed",
            "resolution": "resolution",
            "frames": "frames",
            "fps": "fps",
        },
        "i2v": {
            "prompt": "prompt",
            "negative_prompt": "negative_prompt",
            "seed": "seed",
            "image_ref": "image",
            "resolution": "resolution",
            "frames": "frames",
            "fps": "fps",
        },
        "flf": {
            "prompt": "prompt",
            "negative_prompt": "negative_prompt",
            "seed": "seed",
            "image_ref": "start_image",
            "image_end_ref": "end_image",
            "resolution": "resolution",
            "frames": "frames",
            "fps": "fps",
        },
    }

    def generate(
        self,
        entry: ModelEntry,
        mode: str,
        params: dict[str, Any],
        out_dir: Path,
    ) -> GenerationResult:
        if type(self) is VibeComfyBackend and self._pip_embedded_session is None:
            raise ValueError(
                "pip_embedded requires an explicit PipEmbeddedProfile; "
                "ambient interpreter/package discovery is disabled"
            )
        pip_session = getattr(self, "_pip_embedded_session", None)
        if pip_session is not None:
            out_dir = pip_session.validate_output_dir(out_dir)
        # Lazy-import VibeComfy (SD-009), and snapshot only its repository
        # template corpus.  Dynamic/user template discovery is forbidden.
        import vibecomfy  # noqa: F401
        from vibecomfy.registry.ready import (
            repo_ready_template_discovery,
            resolve_ready_template,
            workflow_from_ready,
        )

        mode_spec = entry.modes[mode]
        backend_spec: BackendSpec = mode_spec.backends["local"]
        template_id = backend_spec.template

        # --- resolve seed (or generate one) ----------------------------------
        seed_used: int = params.get("seed", 0)

        # --- build param map: canonical → template parameter name ------------
        param_map: dict[str, str] = dict(backend_spec.param_map)
        if not param_map:
            param_map = dict(self.DEFAULT_PARAM_MAP.get(mode, {}))

        # --- derive frame count deterministically ----------------------------
        # If duration is supplied without frames, and fps is known, derive frames
        computed_frames = derive_frames_from_duration(params)
        if computed_frames is not None:
            logger.debug("Computed frames=%d from duration * fps", computed_frames)

        # --- compute applied / dropped feature lists -------------------------
        applied_features, dropped_features = split_feature_support(params, mode_spec.supports)
        discovery = repo_ready_template_discovery()
        record = resolve_ready_template(template_id, discovery)

        # The catalog value and resolved record must both be canonical
        # ``category/template_id`` identifiers from the repository corpus.
        requested_id = str(template_id)
        requested_parts = requested_id.split("/")
        canonical_id = str(getattr(record, "template_id", ""))
        id_parts = canonical_id.split("/")
        if (
            requested_id != canonical_id
            or len(requested_parts) != 2
            or len(id_parts) != 2
            or any(not part or part in {".", ".."} for part in requested_parts)
            or any(not part or part in {".", ".."} for part in id_parts)
            or getattr(record, "source_scope", None) != "repo"
        ):
            raise ValueError(f"VibeComfy template {template_id!r} is not a canonical repo template")
        template_path = Path(getattr(record, "path", ""))
        template_root = Path(getattr(record, "root", ""))
        try:
            template_path_resolved = template_path.resolve(strict=True)
            template_root_resolved = template_root.resolve(strict=True)
            template_path_resolved.relative_to(template_root_resolved)
        except (OSError, ValueError) as exc:
            raise ValueError(
                f"VibeComfy template {canonical_id!r} is outside its repo root"
            ) from exc
        expected_hash = str(backend_spec.template_hash)
        if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", expected_hash):
            raise ValueError(f"VibeComfy template {canonical_id!r} has no valid sha256 pin")
        actual_hash = hashlib.sha256(template_path_resolved.read_bytes()).hexdigest()
        if actual_hash.lower() != expected_hash[7:].lower():
            raise ValueError(f"VibeComfy template {canonical_id!r} failed its sha256 pin")
        t0 = time.monotonic()
        wf = workflow_from_ready(canonical_id, _discovery=discovery)
        # Features whose param_map key is in the feature list get mapped.
        # Count is not set on the workflow — the caller loops externally.
        for canon, tmpl_param in param_map.items():
            if canon == "count":
                continue  # count is managed by the executor loop
            if canon == "size":
                w, h = _parse_size(params.get("size", ""))
                # Try set_input for width/height individually
                wf.set_input("width", w)
                wf.set_input("height", h)
                continue
            if canon == "resolution":
                res_str = str(params.get("resolution", ""))
                parsed = _parse_resolution(res_str)
                if parsed:
                    w, h = parsed
                    wf.set_input("width", w)
                    wf.set_input("height", h)
                continue
            if canon not in params:
                continue
            value = params[canon]
            if value is None:
                continue
            wf.set_input(tmpl_param, value)

        unbound_inputs = getattr(wf, "metadata", {}).get("unbound_inputs", {})
        if isinstance(unbound_inputs, dict):
            requested_unbound = sorted(
                tmpl_param
                for canon, tmpl_param in param_map.items()
                if canon not in {"count", "size", "resolution"}
                and canon in params
                and params[canon] is not None
                and tmpl_param in unbound_inputs
            )
            if requested_unbound:
                raise ValueError(
                    f"VibeComfy template {template_id!r} does not declare inputs: "
                    + ", ".join(requested_unbound)
                )

        if pip_session is not None:
            result = pip_session.run(wf, out_dir=out_dir, task_identity=params.get("task_identity"))
            duration_ms = int((time.monotonic() - t0) * 1000)
            image_paths = list(result.published_outputs)
        else:
            result = self._run_workflow(wf)
            duration_ms = int((time.monotonic() - t0) * 1000)
            out_dir = out_dir.resolve()
            out_dir.mkdir(parents=True, exist_ok=True)
            image_paths = self._collect_outputs(result, out_dir)

        return GenerationResult(
            image_paths=image_paths,
            seed_used=seed_used,
            model_actual=template_id,
            cost_usd=None,  # local backends have no cost
            duration_ms=duration_ms,
            applied_features=applied_features,
            dropped_features=dropped_features,
            error=None,
        )


class VibeComfyEngine:
    """Lifecycle wrapper around a host-owned ComfyUI runtime.

    Warmth is disposable.  Every lifecycle transition is serialized by a
    lock, while native containment fences prepare/run callers before making
    its HTTP requests.  A failed containment operation poisons the lifecycle
    until the complete interrupt + queue-clear + ``/api/free`` sequence
    succeeds.
    """

    def __init__(self, server_url: str) -> None:
        self._origin = _validate_checkout_server_url(server_url)
        self._lock = threading.RLock()
        self._operation: str | None = None
        self._running = False
        self._poisoned = False
        self._fence_pending = False
        self._cold_reset_verified = False
        self._warm = False
        self._fingerprint: str | None = None
        self._warmth_identity: str | None = None
        self._model_bytes_digest: str | None = None
        self._runtime_instance_id: str | None = None
        self._prepared_fingerprint: str | None = None
        self._prepared_warmth_identity: str | None = None
        self._prepared_model_bytes_digest: str | None = None
        self._prepared_runtime_instance_id: str | None = None
        self._lifecycle_generation = 0
        self.last_lifecycle = "cold"
        self.last_warm_reused = False

    @property
    def warm(self) -> bool:
        return self._warm

    @property
    def fingerprint(self) -> str | None:
        return self._fingerprint or self._prepared_fingerprint

    @property
    def warmth_identity(self) -> str | None:
        return self._warmth_identity or self._prepared_warmth_identity

    @property
    def model_bytes_digest(self) -> str | None:
        return self._model_bytes_digest or self._prepared_model_bytes_digest

    @property
    def prepared_fingerprint(self) -> str | None:
        return self._prepared_fingerprint

    @property
    def prepared_model_bytes_digest(self) -> str | None:
        return self._prepared_model_bytes_digest

    @property
    def prepared_runtime_instance_id(self) -> str | None:
        return self._prepared_runtime_instance_id

    @property
    def prepared_warmth_identity(self) -> str | None:
        return self._prepared_warmth_identity

    @property
    def runtime_instance_id(self) -> str | None:
        return self._runtime_instance_id or self._prepared_runtime_instance_id

    @property
    def poisoned(self) -> bool:
        return self._poisoned

    @property
    def fence_pending(self) -> bool:
        return self._fence_pending

    @staticmethod
    def _identity(value: object, field: str) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError(f"checkout_server {field} must be a non-empty string")
        return value

    @staticmethod
    def _runtime_identity(value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                "checkout_server runtime_instance_id must come from canonical health/bootstrap"
            )
        # Reject synthetic digests and probe tags.
        if value.startswith("probe:"):
            raise ValueError(
                "checkout_server runtime_instance_id must come from canonical health/bootstrap"
            )
        try:
            parsed = uuid.UUID(value)
        except ValueError as exc:
            raise ValueError(
                "checkout_server runtime_instance_id must be a valid UUID from canonical health/bootstrap"
            ) from exc
        return str(parsed)

    @staticmethod
    def _validate_model_bytes_digest(*values: str | None) -> str:
        candidates = [value for value in values if value is not None]
        if not candidates:
            raise ValueError("checkout_server requires model_bytes_digest for production warmth")
        normalized: list[str] = []
        for value in candidates:
            if not isinstance(value, str) or not re.fullmatch(
                r"(?:sha256:)?[0-9a-fA-F]{64}", value
            ):
                raise ValueError(
                    "checkout_server model_bytes_digest must be sha256:<64hex> or raw 64hex"
                )
            normalized.append("sha256:" + value.removeprefix("sha256:").lower())
        if len(set(normalized)) != 1:
            raise ValueError("checkout_server model digest aliases do not match")
        return normalized[0]

    def _clear_prepared(self) -> None:
        self._prepared_fingerprint = None
        self._prepared_warmth_identity = None
        self._prepared_model_bytes_digest = None
        self._prepared_runtime_instance_id = None

    def _clear_warm(self) -> None:
        self._warm = False
        self._fingerprint = None
        self._warmth_identity = None
        self._model_bytes_digest = None
        self._runtime_instance_id = None
        self.last_lifecycle = "cold"
        self.last_warm_reused = False

    def _warm_is_compatible(
        self,
        fingerprint: str,
        warmth_identity: str | None,
        model_bytes_digest: str,
        runtime_instance_id: str,
    ) -> bool:
        return (
            self._warm
            and self._fingerprint == fingerprint
            and self._model_bytes_digest == model_bytes_digest
            and (warmth_identity is None or self._warmth_identity in {None, warmth_identity})
            and self._runtime_instance_id == runtime_instance_id
        )

    def _abort_preparation(self) -> None:
        """Discard both pending and previously published warmth."""
        with self._lock:
            self._clear_warm()
            self._clear_prepared()
            self._lifecycle_generation += 1

    def _poison(self, *, cold_reset_verified: bool = False) -> None:
        self._clear_warm()
        self._clear_prepared()
        self._poisoned = True
        self._fence_pending = True
        self._cold_reset_verified = cold_reset_verified
        self._lifecycle_generation += 1

    def _reset_after_free(self) -> None:
        self._clear_warm()
        self._clear_prepared()
        self._poisoned = False
        self._fence_pending = False
        self._cold_reset_verified = False
        self._lifecycle_generation += 1

    def _cold_free(self) -> None:
        """Prove a cold reset with complete native containment."""
        result = self._contain(
            "reset",
            (
                ("/interrupt", {}, "interrupt"),
                ("/queue", {"clear": True}, "queue_clear"),
                ("/api/free", {"unload_models": True, "free_memory": True}, "free"),
            ),
        )
        if not result.get("ok", False):
            raise RuntimeError("checkout_server could not prove complete cold reset")

    def _contain(
        self,
        operation: str,
        paths: tuple[tuple[str, dict[str, Any], str], ...],
        *,
        preflight: Any | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            if self._operation is not None:
                raise RuntimeError(f"checkout_server {self._operation} is already in progress")
            if (self._poisoned or self._fence_pending) and (
                not paths or paths[0][0] != "/interrupt"
            ):
                paths = (
                    ("/interrupt", {}, "interrupt"),
                    *paths,
                )
            self._operation = operation
            # Set the fence and discard old warmth before any probe/request.
            self._fence_pending = True
            self._clear_warm()
            self._clear_prepared()
            self._lifecycle_generation += 1
        errors: list[str] = []
        results: dict[str, Any] = {}
        try:
            if preflight is not None:
                try:
                    preflight()
                except Exception as exc:
                    errors.append(str(exc))
            for path, payload, key in paths:
                try:
                    results[key] = self._post(path, payload)
                except Exception as exc:
                    errors.append(str(exc))
            with self._lock:
                if errors:
                    # Any failed step keeps the fence.  A successful free
                    # alone is not evidence that interrupt and queue state
                    # were contained.
                    self._poison(cold_reset_verified=False)
                    return {
                        "ok": False,
                        "status": "requires_fence",
                        "contained": False,
                        "cancelled": False,
                        "released": False,
                        "error": "; ".join(errors),
                        "results": results,
                    }
                self._reset_after_free()
                return {
                    "ok": True,
                    "status": "cancelled" if operation == "cancel" else "cold",
                    "contained": True,
                    "cancelled": operation == "cancel",
                    "released": operation == "release",
                    "results": results,
                }
        finally:
            with self._lock:
                self._operation = None

    def _prepare_for_warm_session(self) -> bool:
        """Fence warmth while the adapter probes the host."""
        with self._lock:
            if self._operation is not None:
                raise RuntimeError(f"checkout_server {self._operation} is already in progress")
            if self._running:
                raise RuntimeError("checkout_server run is already in progress")
            requires_cold_reset = (
                self._poisoned
                or self._fence_pending
                or self._warm
                or self._prepared_fingerprint is not None
            )
            self._fence_pending = True
            # Published warmth remains a candidate until the probe succeeds;
            # _poison() clears it if the probe fails.
            self._clear_prepared()
            self._lifecycle_generation += 1
            return requires_cold_reset

    def prepare_session(
        self,
        fingerprint: str,
        warmth_identity: str | None = None,
        *,
        runtime_instance_id: str | None = None,
        model_bytes_digest: str | None = None,
        model_digest: str | None = None,
        artifact_sha256: str | None = None,
        cold: bool = False,
    ) -> dict[str, Any]:
        """Fence incompatible warmth and report the lifecycle decision."""
        fingerprint = self._identity(fingerprint, "fingerprint")
        if warmth_identity is not None:
            warmth_identity = self._identity(warmth_identity, "warmth_identity")
        model_bytes = self._validate_model_bytes_digest(
            model_bytes_digest, model_digest, artifact_sha256
        )
        if runtime_instance_id is None:
            raise ValueError(
                "checkout_server runtime_instance_id is required from canonical health/bootstrap"
            )
        runtime_instance_id = self._runtime_identity(runtime_instance_id)
        with self._lock:
            if self._operation is not None:
                raise RuntimeError(f"checkout_server {self._operation} is already in progress")
            if self._running:
                raise RuntimeError("checkout_server run is already in progress")
            if self._fence_pending or self._poisoned:
                if not cold:
                    raise RuntimeError(
                        "checkout_server lifecycle is poisoned or fence-pending; "
                        "a proven cold reset is required"
                    )
                self._cold_free()
            compatible = self._warm_is_compatible(
                fingerprint,
                warmth_identity,
                model_bytes,
                runtime_instance_id,
            )
            if self._warm and not compatible:
                released = self.release(reason="incompatible fingerprint")
                if not released.get("ok", False):
                    raise ValueError("checkout_server could not release incompatible warmth")
            self._prepared_fingerprint = fingerprint
            self._prepared_warmth_identity = warmth_identity
            self._prepared_model_bytes_digest = model_bytes
            self._prepared_runtime_instance_id = runtime_instance_id
            self.last_lifecycle = "warm" if compatible else "cold"
            self.last_warm_reused = compatible
            return {
                "status": self.last_lifecycle,
                "lifecycle": self.last_lifecycle,
                "warm_reused": compatible,
                "fingerprint": fingerprint,
                "fingerprint_stored": fingerprint,
                "warmth_identity": warmth_identity,
                "model_bytes_digest": model_bytes,
                "runtime_instance_id": runtime_instance_id,
                "poisoned": self._poisoned,
                "fence_pending": self._fence_pending,
            }

    def warm_session(
        self,
        fingerprint: str,
        warmth_identity: str | None = None,
        *,
        runtime_instance_id: str | None = None,
        model_bytes_digest: str | None = None,
        model_digest: str | None = None,
        artifact_sha256: str | None = None,
        cold: bool = False,
    ) -> dict[str, Any]:
        """M2 host-ABI spelling for :meth:`prepare_session`."""
        return self.prepare_session(
            fingerprint,
            warmth_identity,
            runtime_instance_id=runtime_instance_id,
            model_bytes_digest=model_bytes_digest,
            model_digest=model_digest,
            artifact_sha256=artifact_sha256,
            cold=cold,
        )

    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        request = urllib_request.Request(
            f"{self._origin}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with _open_checkout_http(request, timeout=10.0) as response:
                status = getattr(response, "status", 200)
                if not 200 <= status < 300:
                    raise ValueError(f"checkout_server {path} returned a non-2xx status")
                raw = response.read(64 * 1024 + 1)
                if len(raw) > 64 * 1024:
                    raise ValueError(f"checkout_server {path} response is too large")
                if not raw:
                    return {}
                try:
                    return json.loads(raw.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    return {"acknowledged": True}
        except (OSError, urllib_error.URLError) as exc:
            raise ValueError(f"checkout_server {path} request failed") from exc

    def run(self, workflow: Any, *, runtime_instance_id: str | None = None) -> Any:
        """Run one workflow without allowing poisoned lifecycle reuse."""
        with self._lock:
            if self._operation is not None:
                raise RuntimeError(f"checkout_server {self._operation} is already in progress")
            if self._running:
                raise RuntimeError("checkout_server run is already in progress")
            if self._poisoned or self._fence_pending:
                raise RuntimeError(
                    "checkout_server lifecycle is poisoned or fence-pending; "
                    "a proven cold reset is required"
                )
            if runtime_instance_id is None:
                raise ValueError(
                    "checkout_server runtime_instance_id is required from canonical health/bootstrap"
                )
            runtime_instance_id = self._runtime_identity(runtime_instance_id)
            if self._prepared_runtime_instance_id != runtime_instance_id:
                self._poison()
                raise RuntimeError("checkout_server runtime instance changed")
            run_generation = self._lifecycle_generation
            self._running = True

        try:
            from vibecomfy.runtime.run import run_sync

            result = run_sync(workflow, server_url=self._origin)
            with self._lock:
                # A containment transition may have superseded this run.
                if self._lifecycle_generation == run_generation:
                    self._warm = True
                    self._fingerprint = self._prepared_fingerprint
                    self._warmth_identity = self._prepared_warmth_identity
                    self._model_bytes_digest = self._prepared_model_bytes_digest
                    self._runtime_instance_id = self._prepared_runtime_instance_id
                    self._clear_prepared()
            return result
        except BaseException:
            with self._lock:
                self._running = False
                # A containment/reset transition may have superseded this
                # run.  Its completion must not alter newer fence state.
                if self._lifecycle_generation == run_generation:
                    self._poison()
            raise
        finally:
            with self._lock:
                self._running = False

    def cancel(
        self,
        frame: object | None = None,
        *,
        preflight: Any | None = None,
    ) -> dict[str, Any]:
        """Interrupt execution and clear pending ComfyUI work."""
        del frame
        return self._contain(
            "cancel",
            (
                ("/interrupt", {}, "interrupt"),
                ("/queue", {"clear": True}, "queue_clear"),
                ("/api/free", {"unload_models": True, "free_memory": True}, "free"),
            ),
            preflight=preflight,
        )

    def release(
        self,
        frame: object | None = None,
        *,
        reason: str = "requested",
        preflight: Any | None = None,
    ) -> dict[str, Any]:
        """Clear queued work and unload ComfyUI models/VAE state."""
        del frame, reason
        return self._contain(
            "release",
            (
                ("/queue", {"clear": True}, "queue_clear"),
                ("/api/free", {"unload_models": True, "free_memory": True}, "free"),
            ),
            preflight=preflight,
        )


class CheckoutServerAdapter(VibeComfyBackend):
    """Submit pinned workflows to an already-running host-owned server."""

    def __init__(
        self,
        server_url: str,
        *,
        environment_fingerprint: str = "checkout_server",
    ) -> None:
        # Keep the validated origin private; the base class has no remote path.
        self._origin = _validate_checkout_server_url(server_url)
        self._environment_fingerprint = VibeComfyEngine._identity(
            environment_fingerprint, "environment_fingerprint"
        )
        self._engine = VibeComfyEngine(self._origin)
        self._system_stats_verified = False
        self._runtime_instance_id: str | None = None
        self._startup_probe_digest: str | None = None

    @property
    def runtime_instance_id(self) -> str | None:
        """Canonical instance identity supplied by M2 health/bootstrap."""
        return self._engine.runtime_instance_id or self._engine.prepared_runtime_instance_id

    @property
    def poisoned(self) -> bool:
        return self._engine.poisoned

    @property
    def fence_pending(self) -> bool:
        return self._engine.fence_pending

    def _probe_system_stats(self) -> None:
        """Verify the pinned ComfyUI version only.

        Runtime instance identity is supplied by canonical M2
        health/bootstrap; a system-stats digest is never an identity fence.
        """
        self._system_stats_verified = False
        request = urllib_request.Request(f"{self._origin}/system_stats", method="GET")
        try:
            with _open_checkout_http(request, timeout=5.0) as response:
                status = getattr(response, "status", 200)
                if status != 200:
                    raise ValueError("checkout_server /system_stats returned a non-200 status")
                body = response.read(64 * 1024 + 1)
                if len(body) > 64 * 1024:
                    raise ValueError("checkout_server /system_stats response is too large")
                payload = json.loads(body.decode("utf-8"))
        except (OSError, urllib_error.URLError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("checkout_server /system_stats probe failed") from exc
        if not isinstance(payload, dict):
            raise ValueError("checkout_server /system_stats response is not an object")
        system = payload.get("system")
        if not isinstance(system, dict) or system.get("comfyui_version") != COMFYUI_VERSION:
            raise ValueError(
                f"checkout_server requires ComfyUI {COMFYUI_VERSION} according to /system_stats"
            )
        self._startup_probe_digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        self._system_stats_verified = True

    @staticmethod
    def session_fingerprint(
        *,
        model_fingerprint: str,
        model_bytes_digest: str,
        environment_fingerprint: str,
        server_url: str,
        runtime_instance_id: str,
    ) -> str:
        """Derive a fingerprint bound to model bytes and runtime instance."""
        payload = {
            "schema": "astrid.vibecomfy.session.v2",
            "engine_revision": VIBECOMFY_ENGINE_REVISION,
            "comfyui_version": COMFYUI_VERSION,
            "model": VibeComfyEngine._identity(model_fingerprint, "model_fingerprint"),
            "model_bytes": VibeComfyEngine._validate_model_bytes_digest(model_bytes_digest),
            "environment": VibeComfyEngine._identity(
                environment_fingerprint, "environment_fingerprint"
            ),
            "server": _validate_checkout_server_url(server_url),
            "runtime_instance": VibeComfyEngine._runtime_identity(runtime_instance_id),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def warm_session(
        self,
        fingerprint: str,
        warmth_identity: str | None = None,
        *,
        runtime_instance_id: str | None = None,
        model_bytes_digest: str | None = None,
        model_digest: str | None = None,
        artifact_sha256: str | None = None,
        cold: bool = False,
    ) -> dict[str, Any]:
        """Fence warmth before probing caller-provided health and identity."""
        fingerprint = VibeComfyEngine._identity(fingerprint, "fingerprint")
        if warmth_identity is not None:
            warmth_identity = VibeComfyEngine._identity(warmth_identity, "warmth_identity")
        model_bytes = VibeComfyEngine._validate_model_bytes_digest(
            model_bytes_digest, model_digest, artifact_sha256
        )
        if runtime_instance_id is None:
            raise ValueError(
                "checkout_server runtime_instance_id is required from canonical health/bootstrap"
            )
        instance_id = VibeComfyEngine._runtime_identity(runtime_instance_id)
        with self._engine._lock:
            was_blocked = self._engine._poisoned or self._engine._fence_pending
            requires_cold_reset = self._engine._prepare_for_warm_session()
            try:
                self._probe_system_stats()
            except BaseException:
                self._engine._poison(cold_reset_verified=False)
                raise
            compatible = self._engine._warm_is_compatible(
                fingerprint,
                warmth_identity,
                model_bytes,
                instance_id,
            )
            if compatible and not cold and not was_blocked:
                # Only the probe fence is transient; retain the published
                # snapshot so prepare_session can report warm reuse.
                requires_cold_reset = False
            if not requires_cold_reset:
                self._engine._fence_pending = False
            return self._engine.prepare_session(
                fingerprint,
                warmth_identity,
                runtime_instance_id=instance_id,
                model_bytes_digest=model_bytes,
                cold=cold or requires_cold_reset,
            )

    @staticmethod
    def _model_bytes_digest(
        backend_spec: BackendSpec,
        *supplied: str | None,
    ) -> str:
        """Resolve an exact model artifact digest; fail closed when undeclared."""
        caller_values = [value for value in supplied if value is not None]
        if caller_values:
            return VibeComfyEngine._validate_model_bytes_digest(*caller_values)
        hints = backend_spec.hints
        if isinstance(hints, dict):
            hint_values = [
                hints[key]
                for key in ("model_bytes_digest", "model_digest", "artifact_sha256")
                if key in hints
            ]
            if hint_values:
                return VibeComfyEngine._validate_model_bytes_digest(*hint_values)
        return VibeComfyEngine._validate_model_bytes_digest(None)

    def generate(
        self,
        entry: ModelEntry,
        mode: str,
        params: dict[str, Any],
        out_dir: Path,
        *,
        fingerprint: str | None = None,
        warmth_identity: str | None = None,
        environment_fingerprint: str | None = None,
        model_bytes_digest: str | None = None,
        model_digest: str | None = None,
        artifact_sha256: str | None = None,
        runtime_instance_id: str | None = None,
    ) -> GenerationResult:
        """Generate with disposable warm reuse and host-compatible identities."""
        backend_spec = entry.modes[mode].backends["local"]
        model_fingerprint = f"{entry.id}:{backend_spec.template}"
        model_bytes = self._model_bytes_digest(
            backend_spec, model_bytes_digest, model_digest, artifact_sha256
        )
        if runtime_instance_id is None:
            raise ValueError(
                "checkout_server runtime_instance_id is required from canonical health/bootstrap"
            )
        instance_id = VibeComfyEngine._runtime_identity(runtime_instance_id)
        environment = (
            self._environment_fingerprint
            if environment_fingerprint is None
            else VibeComfyEngine._identity(environment_fingerprint, "environment_fingerprint")
        )
        canonical_fingerprint = self.session_fingerprint(
            model_fingerprint=model_fingerprint,
            model_bytes_digest=model_bytes,
            environment_fingerprint=environment,
            server_url=self._origin,
            runtime_instance_id=instance_id,
        )
        if fingerprint is not None and fingerprint != canonical_fingerprint:
            raise ValueError("checkout_server fingerprint must equal canonical session fingerprint")
        effective_fingerprint = canonical_fingerprint
        if warmth_identity is None:
            warmth_identity = f"{model_fingerprint}:{model_bytes}:{environment}"
        try:
            self.warm_session(
                effective_fingerprint,
                warmth_identity,
                runtime_instance_id=instance_id,
                model_bytes_digest=model_bytes,
            )
            return super().generate(entry, mode, params, out_dir)
        except BaseException:
            self._engine._abort_preparation()
            raise

    def cancel(self, frame: object | None = None) -> dict[str, Any]:
        """Fence native work before probing or settling host cancellation."""
        return self._engine.cancel(frame, preflight=self._probe_system_stats)

    def release(self, frame: object | None = None, *, reason: str = "requested") -> dict[str, Any]:
        """Fence native state before probing and mark the adapter cold."""
        return self._engine.release(
            frame,
            reason=reason,
            preflight=self._probe_system_stats,
        )

    def _run_workflow(self, workflow: Any) -> Any:
        """Probe version and submit with the canonical runtime identity."""
        self._origin = _validate_checkout_server_url(self._origin)
        self._probe_system_stats()
        instance_id = self._engine.prepared_runtime_instance_id
        if instance_id is None:
            instance_id = self._engine.runtime_instance_id
        if instance_id is None:
            raise ValueError(
                "checkout_server runtime_instance_id is required from canonical health/bootstrap"
            )
        return self._engine.run(workflow, runtime_instance_id=instance_id)

    def _collect_outputs(self, result: Any, out_dir: Path) -> list[Path]:
        """Custody remote outputs through validated Comfy ``/view`` downloads."""
        metadata_path = getattr(result, "metadata_path", None)
        if not isinstance(metadata_path, (str, Path)) or not str(metadata_path):
            raise ValueError("checkout_server result has no metadata_path")
        try:
            metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("checkout_server result metadata is unreadable") from exc
        outputs = metadata.get("comfy_outputs") if isinstance(metadata, dict) else None
        descriptors = _extract_output_descriptors(outputs)
        if not descriptors:
            raise ValueError("checkout_server result metadata has no comfy_outputs")

        image_paths: list[Path] = []
        for descriptor in descriptors:
            filename, subfolder, output_type = _validate_output_descriptor(descriptor)
            query = urllib_parse.urlencode(
                {"filename": filename, "subfolder": subfolder, "type": output_type}
            )
            request = urllib_request.Request(f"{self._origin}/view?{query}", method="GET")
            destination = out_dir / filename
            if destination.exists():
                stem = destination.stem
                suffix = destination.suffix
                counter = 1
                while destination.exists():
                    destination = out_dir / f"{stem}_{counter}{suffix}"
                    counter += 1
            temporary_path: Path | None = None
            try:
                with _open_checkout_http(request, timeout=30.0) as response:
                    status = getattr(response, "status", 200)
                    if status != 200:
                        raise ValueError("checkout_server /view returned a non-200 status")
                    with tempfile.NamedTemporaryFile(
                        mode="wb",
                        dir=out_dir,
                        prefix=".checkout-download-",
                        delete=False,
                    ) as temporary:
                        temporary_path = Path(temporary.name)
                        shutil.copyfileobj(response, temporary)
                        temporary.flush()
                        os.fsync(temporary.fileno())
                os.replace(temporary_path, destination)
                temporary_path = None
            except (OSError, urllib_error.URLError) as exc:
                raise ValueError(f"checkout_server could not download output {filename!r}") from exc
            finally:
                if temporary_path is not None:
                    try:
                        temporary_path.unlink()
                    except FileNotFoundError:
                        pass
            image_paths.append(destination)
        return image_paths
