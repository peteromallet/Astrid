"""VibeComfyBackend — local generation via vibecomfy ready templates.

The backend drives the template's declared ``bind_input`` contract through
``wf.set_input()``.  Template graph inspection is intentionally not part of
the runtime API: a template that does not declare a requested input is an
invalid template, not an invitation to infer a node target.
"""

from __future__ import annotations

import ctypes
import errno
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
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from dataclasses import replace as dataclass_replace
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
import hashlib,json,os,select,sys,time
from pathlib import Path
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
                    "config_digest","profile_readiness_digest","config","policy","request_digest",
                    "launch_digest","package_facts","resolver_facts"}:
    raise SystemExit(2)
def publish(value, directory_fd, name="ready.json"):
    encoded=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()
    if len(encoded)>1024*1024: raise ValueError("bootstrap response too large")
    temp=".ready-"+request["nonce"]
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory_fd)
    try:
        os.write(fd,encoded); os.fsync(fd)
    finally: os.close(fd)
    try:
        os.link(temp,name,src_dir_fd=directory_fd,dst_dir_fd=directory_fd,follow_symlinks=False)
    finally:
        try: os.unlink(temp,dir_fd=directory_fd)
        except FileNotFoundError: pass
def fail(code,reason):
    publish({"schema":"astrid.vibecomfy.ready.v1","nonce":request["nonce"],
        "request_digest":request["request_digest"],"profile_digest":request["profile_digest"],
        "config_digest":request["config_digest"],"launch_digest":request["launch_digest"],
        "ok":False,"error":{"code":code,"reason":reason}},int(sys.argv[5]))
try:
    staging_fd=int(sys.argv[5]); os.fstat(staging_fd)
except Exception:
    raise SystemExit(2)
def digest(value):
    return "sha256:"+hashlib.sha256(json.dumps(value,sort_keys=True,
        separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
if digest({key:value for key,value in request.items() if key!="request_digest"}) != request["request_digest"]:
    raise SystemExit(2)
if request["config_digest"] != digest(request["config"]):
    raise SystemExit(2)
try:
    from vibecomfy.runtime.run import run_embedded_sync
    from vibecomfy.runtime.session import SessionConfig
    from vibecomfy.workflow import FORMAT_VERSION,VibeWorkflow
except Exception:
    fail("not_ready","effective_resolver_unproven")
    raise SystemExit(4)
if request.get("workflow",{}).get("vibecomfy_format_version")!=FORMAT_VERSION:
    raise SystemExit(2)
workflow=VibeWorkflow.from_envelope(request["workflow"])
if digest(request["workflow"]) != request.get("workflow_digest") or workflow.to_envelope()!=request["workflow"]:
    raise SystemExit(2)
for node in workflow.nodes.values():
    if node.class_type in {"vibecomfy.code","vibecomfy.loop"}:
        raise SystemExit(2)
config=request["config"]
def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return "sha256:"+h.hexdigest()
package_files=[]
for item in request["package_facts"]["files"]:
    measured={"path":item["path"],"sha256":sha(item["path"])}
    if measured["sha256"] != item["sha256"]: raise SystemExit(4)
    package_files.append(measured)
package={"revision":request["package_facts"]["revision"],"digest":digest(package_files),"files":package_files}
try:
    # A requested root list is not an observation.  Only the fixed pinned
    # runtime's own resolver machinery can establish effective paths.
    import importlib.util
    comfy_spec=importlib.util.find_spec("comfy")
    if comfy_spec is None or not comfy_spec.origin:
        raise RuntimeError("comfy resolver unavailable")
    raise RuntimeError("effective resolver equivalence is not proven")
except Exception:
    fail("not_ready","effective_resolver_unproven")
    raise SystemExit(4)
ready={"schema":"astrid.vibecomfy.ready.v1","nonce":request["nonce"],
       "request_digest":request["request_digest"],"profile_digest":request["profile_digest"],
       "config_digest":request["config_digest"],"launch_digest":request["launch_digest"],"ok":True,
       "interpreter":{"executable":os.path.realpath(sys.executable),
                      "prefix":os.path.realpath(sys.prefix),
                      "version":".".join(str(x) for x in sys.version_info[:3])},
       "package":package,"resolver":resolver}
publish(ready,staging_fd)
go_fd=int(sys.argv[3]); os.set_blocking(go_fd,False)
deadline=time.monotonic()+float(request["policy"]["ready_seconds"])
frame=None
while frame is None:
    if time.monotonic() >= deadline: raise SystemExit(3)
    readable,_,_=select.select([go_fd],[],[],max(0.001,deadline-time.monotonic()))
    if readable:
        frame=os.read(go_fd,4096)
        break
if frame is None or len(frame)>4096: raise SystemExit(2)
try: go=json.loads(frame.decode("utf-8"),object_pairs_hook=pairs)
except Exception: raise SystemExit(2)
if go != {"nonce":request["nonce"],"request_digest":request["request_digest"],"launch_digest":request["launch_digest"]}:
    raise SystemExit(2)
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
fd=os.open(sys.argv[4],os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
try:
    encoded=json.dumps(payload,sort_keys=True,separators=(",",":")).encode()
    os.write(fd,encoded); os.fsync(fd)
finally: os.close(fd)
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


class _PipEmbeddedError(RuntimeError):
    """Typed, fail-closed boundary for the cold embedded adapter."""

    def __init__(
        self,
        code: str,
        reason: str,
        *,
        phase: str = "admission",
        nonce: str | None = None,
        go_sent: bool = False,
        outcome: Mapping[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.reason = reason
        self.phase = phase
        self.nonce = nonce
        self.go_sent = go_sent
        self.outcome = _thaw_json(outcome) if outcome is not None else None
        super().__init__(f"{code}:{reason}")


def _unavailable(reason: str, *, phase: str = "admission") -> _PipEmbeddedError:
    return _PipEmbeddedError("not_ready", reason, phase=phase)


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
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
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
    if not isinstance(values, list) or not values or len(values) > 16:
        raise ValueError("pip_embedded HC-03 interpreter fact is incomplete")
    result = []
    seen: set[str] = set()
    for encoded in values:
        # The Worker producer emits a JSON list of JSON strings, not a list of
        # already-decoded objects.  Accepting the latter would silently change
        # the producer contract and its fact digest.
        if not isinstance(encoded, str) or len(encoded) > 4096:
            raise ValueError("pip_embedded HC-03 interpreter identity is not producer-shaped")
        try:
            value = json.loads(encoded, object_pairs_hook=lambda pairs: dict(pairs))
        except json.JSONDecodeError as exc:
            raise ValueError("pip_embedded HC-03 interpreter identity is malformed") from exc
        if not isinstance(value, dict) or set(value) != {"path", "version", "sha256"}:
            raise ValueError("pip_embedded HC-03 interpreter identity is invalid")
        if not isinstance(value["version"], str) or not value["version"].strip():
            raise ValueError("pip_embedded HC-03 interpreter version is invalid")
        path = _require_absolute_path(value["path"], "interpreter fact path")
        if path in seen:
            raise ValueError("pip_embedded HC-03 interpreter identity is duplicated")
        seen.add(path)
        result.append(
            {
                "path": path,
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
    collection_seconds: float = 120.0

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


@dataclass(frozen=True, slots=True)
class _InvocationBinding:
    """Immutable identity captured when one invocation is admitted."""

    nonce: str
    identity: str
    profile_digest: str


@dataclass(frozen=True, slots=True)
class _OutputCustody:
    """Admission-owned descriptors for the one source tree we may collect."""

    binding: _InvocationBinding
    scratch_fd: int
    scratch_identity: tuple[int, int]
    staging_fd: int
    staging_identity: tuple[int, int]
    staging_name: str
    staging_path: Path
    source_fd: int
    source_identity: tuple[int, int]
    source_name: str
    source_path: Path
    destination_fd: int
    destination_identity: tuple[int, int]
    destination_path: Path


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


def _remove_tree_at(parent_fd: int, name: str, *, timeout: float, expected: tuple[int, int] | None = None) -> None:
    """Remove one directory owned by this invocation, relative to its parent FD."""
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ValueError("pip_embedded cleanup name is invalid")
    deadline = time.monotonic() + timeout
    child_fd = os.open(name, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW, dir_fd=parent_fd)
    try:
        info = os.fstat(child_fd)
        if expected is not None and (info.st_dev, info.st_ino) != expected:
            raise ValueError("pip_embedded cleanup custody changed")
        for entry in os.listdir(child_fd):
            if time.monotonic() >= deadline:
                raise TimeoutError("pip_embedded cleanup deadline exceeded")
            if entry in {".", ".."} or Path(entry).name != entry:
                raise ValueError("pip_embedded cleanup entry is invalid")
            try:
                leaf = os.open(entry, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=child_fd)
            except OSError as exc:
                raise ValueError("pip_embedded cleanup custody unavailable") from exc
            try:
                leaf_info = os.fstat(leaf)
                mode = stat.S_IFMT(leaf_info.st_mode)
                if mode == stat.S_IFDIR:
                    _remove_tree_at(child_fd, entry, timeout=max(0.001, deadline - time.monotonic()))
                elif mode == stat.S_IFREG and leaf_info.st_nlink == 1:
                    os.unlink(entry, dir_fd=child_fd)
                else:
                    raise ValueError("pip_embedded cleanup encountered unowned entry")
            finally:
                os.close(leaf)
        os.fsync(child_fd)
    finally:
        os.close(child_fd)
    os.rmdir(name, dir_fd=parent_fd)
    os.fsync(parent_fd)


@dataclass(frozen=True, slots=True)
class _GroupCensus:
    known: bool
    members: tuple[tuple[int, int, int, str], ...] = ()
    reason: str | None = None
    leader_birth: str | None = None

    @property
    def live(self) -> tuple[tuple[int, int, int, str], ...]:
        return tuple(item for item in self.members if "Z" not in item[3].upper())


@dataclass(frozen=True, slots=True)
class _ProcessOwnership:
    pid: int
    pgid: int
    birth: str
    dev: int | None = None
    ino: int | None = None
    pre_reap_quiescent: bool = False
    reaped: bool = False


def _census_owned_group(
    process: subprocess.Popen[bytes], deadline: float, *, reaped: bool = False,
    ownership: _ProcessOwnership | None = None,
) -> _GroupCensus:
    """Bounded, state-bearing census; empty output is never positive proof."""
    if process.pid <= 0:
        return _GroupCensus(False, reason="invalid-leader")
    owned = ownership or getattr(process, "_astrid_ownership", None)
    if owned is not None:
        if owned.pid != process.pid or owned.pgid <= 0 or not owned.birth:
            return _GroupCensus(False, reason="ownership-mismatch")
        pgid = owned.pgid
    else:
        try:
            pgid = os.getpgid(process.pid)
        except OSError as exc:
            return _GroupCensus(False, reason=f"leader-ownership:{exc.errno}")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return _GroupCensus(False, reason="deadline")
    ps = "/bin/ps" if Path("/bin/ps").exists() else "/usr/bin/ps"
    if not Path(ps).is_file():
        return _GroupCensus(False, reason="ps-unavailable")
    try:
        completed = subprocess.run(
            [ps, "-axo", "pid=,ppid=,pgid=,stat=,lstart="],
            check=False,
            capture_output=True,
            text=True,
            env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
            timeout=max(0.001, remaining),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _GroupCensus(False, reason=f"census-failed:{type(exc).__name__}")
    if completed.returncode != 0 or not completed.stdout or len(completed.stdout) > 4 * 1024 * 1024:
        return _GroupCensus(False, reason="census-empty-or-failed")
    rows: list[tuple[int, int, int, str]] = []
    observer_seen = False
    leader_seen = False
    leader_birth: str | None = None
    try:
        for line in completed.stdout.splitlines():
            fields = line.split()
            if len(fields) < 9:
                return _GroupCensus(False, reason="malformed-census-row")
            pid, ppid, row_pgid = (int(fields[0]), int(fields[1]), int(fields[2]))
            state = fields[3]
            birth = " ".join(fields[4:])
            if pid == os.getpid():
                observer_seen = True
            if pid == process.pid:
                leader_seen = True
                leader_birth = birth
            if row_pgid == pgid:
                rows.append((pid, ppid, row_pgid, state))
    except (TypeError, ValueError):
        return _GroupCensus(False, reason="malformed-census-row")
    if not observer_seen:
        return _GroupCensus(False, reason="census-lost-owner")
    if owned is not None and leader_seen and leader_birth != owned.birth:
        return _GroupCensus(False, reason="leader-birth-mismatch")
    if not leader_seen and not (reaped and owned is not None and owned.reaped):
        return _GroupCensus(False, reason="census-lost-owner")
    if reaped and owned is not None and owned.reaped and rows:
        # A post-reap group with any remaining member is not attributable to
        # the old leader without an independent birth proof.
        if not leader_seen:
            return _GroupCensus(False, reason="post-reap-group-ambiguous")
    return _GroupCensus(True, tuple(rows), None, leader_birth)


def _publish_directory_noreplace(
    source_parent_fd: int, source_name: str, destination_parent_fd: int, destination_name: str
) -> None:
    if (
        not source_name
        or not destination_name
        or Path(source_name).name != source_name
        or Path(destination_name).name != destination_name
        or source_name in {".", ".."}
        or destination_name in {".", ".."}
    ):
        raise ValueError("pip_embedded publication names must be single components")
    encoded_source, encoded_destination = os.fsencode(source_name), os.fsencode(destination_name)
    if sys.platform == "darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        try:
            rename = libc.renameatx_np
        except AttributeError as exc:
            raise _unavailable("atomic_publication_unavailable") from exc
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        flags = 0x00000004
    else:
        libc = ctypes.CDLL(None, use_errno=True)
        try:
            rename = libc.renameat2
        except AttributeError as exc:
            raise _unavailable("atomic_publication_unavailable") from exc
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        flags = 1
    result = rename(
        source_parent_fd,
        encoded_source,
        destination_parent_fd,
        encoded_destination,
        flags,
    )
    if result != 0:
        error = ctypes.get_errno()
        if error == errno.EEXIST:
            raise FileExistsError(error, "publication destination already exists")
        if error in {errno.ENOSYS, errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EXDEV}:
            raise _unavailable("atomic_publication_unavailable")
        raise OSError(error, os.strerror(error))


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
        "producer_source_root",
        "model_manifest",
        "custom_node_manifest",
        "package_inventory",
        "resolver_roots",
        "resolver_digest",
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
    producer_source = Path(raw["producer_source_root"])
    if (
        not producer_source.is_absolute()
        or producer_source.resolve(strict=False) != producer_source
        or not producer_source.is_dir()
    ):
        raise ValueError("pip_embedded producer source root is not a stable directory")
    for name, path in (
        ("source", producer_source),
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
        try:
            manifest_value = _strict_load_json(manifest, limit=_MAX_JSON_BYTES)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"pip_embedded {name} manifest is not strict JSON") from exc
        if not isinstance(manifest_value.get("files"), list) or len(manifest_value) != 1:
            raise ValueError(f"pip_embedded {name} manifest inventory is invalid")
        actual_files: list[dict[str, str]] = []
        for item in manifest_value["files"]:
            if not isinstance(item, Mapping) or set(item) != {"path", "sha256"}:
                raise ValueError(f"pip_embedded {name} manifest entry is invalid")
            relative = item["path"]
            if (
                not isinstance(relative, str)
                or not relative
                or Path(relative).is_absolute()
                or any(part in {"", ".", ".."} for part in Path(relative).parts)
            ):
                raise ValueError(f"pip_embedded {name} manifest path is invalid")
            root = profile.model_root if name == "model_manifest" else profile.custom_nodes_root
            listed = root / relative
            if listed.is_symlink() or not listed.is_file():
                raise ValueError(f"pip_embedded {name} listed file is unavailable")
            measured = _hash_file(listed)
            if measured != item["sha256"]:
                raise ValueError(f"pip_embedded {name} listed file bytes do not match")
            actual_files.append({"path": relative, "sha256": measured})
        if _digest({"files": actual_files}) != descriptor["digest"]:
            raise ValueError(f"pip_embedded {name} inventory digest does not match bytes")
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
    inventory = raw["package_inventory"]
    if not isinstance(inventory, list) or not inventory:
        raise ValueError("pip_embedded package inventory is unavailable")
    for item in inventory:
        if not isinstance(item, Mapping) or set(item) != {"path", "sha256"}:
            raise ValueError("pip_embedded package inventory is invalid")
        path = Path(item["path"])
        if not path.is_absolute() or path.is_symlink() or not path.is_file():
            raise ValueError("pip_embedded package inventory path is unavailable")
        if _hash_file(path) != item["sha256"]:
            raise ValueError("pip_embedded package inventory bytes do not match")
    roots = raw["resolver_roots"]
    if not isinstance(roots, list) or not roots or any(
        not isinstance(path, str) or not Path(path).is_absolute() or Path(path).is_symlink()
        or not Path(path).is_dir()
        for path in roots
    ):
        raise ValueError("pip_embedded effective resolver roots are unavailable")
    if raw["resolver_digest"] != _digest({"roots": roots}):
        raise ValueError("pip_embedded effective resolver digest does not match roots")
    return raw


@dataclass(frozen=True, slots=True)
class _HC03AdmissionBinding:
    """A retained result of an external T03 validation, not a caller flag."""

    support_root: str
    handoff_name: str
    support_dev: int
    support_ino: int
    raw_hash: str
    facts_digest: str
    projection_digest: str
    expected_projection: Mapping[str, Any]
    support_fd: int = field(repr=False, compare=False)


def _retain_hc03_validation(
    expected_context: Mapping[str, Any], handoff_path: str | Path
) -> _HC03AdmissionBinding:
    """Retain independently supplied T03 facts and support-root custody.

    Production callers must pass the already validated host result.  This
    helper deliberately does not derive its expectation from a submitted
    ``PipEmbeddedProfile``; focused tests use it to model that external seam.
    """
    normalized = _normalize_hc03_profile(expected_context)
    expected_projection = {
        key: value for key, value in normalized.items() if key != "_interpreter_identities"
    }
    handoff = Path(handoff_path).expanduser()
    if not handoff.is_absolute() or handoff.name in {".", ".."} or Path(handoff.name).name != handoff.name:
        raise _unavailable("hc03_handoff_unavailable")
    support_root = Path(normalized["launch"]["support_root"])
    if handoff.parent != support_root or support_root.is_symlink() or not support_root.is_dir():
        raise _unavailable("hc03_support_custody_unavailable")
    _reject_symlink_ancestors(support_root)
    support_fd = os.open(support_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW)
    try:
        support_info = os.fstat(support_fd)
        fd = os.open(handoff.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=support_fd)
        try:
            info = os.fstat(fd)
            if stat.S_IFMT(info.st_mode) != stat.S_IFREG or info.st_nlink != 1:
                raise _unavailable("hc03_handoff_unavailable")
            raw = b""
            while len(raw) <= _MAX_JSON_BYTES:
                part = os.read(fd, _MAX_JSON_BYTES + 1 - len(raw))
                if not part:
                    break
                raw += part
            if len(raw) > _MAX_JSON_BYTES:
                raise _unavailable("hc03_handoff_too_large")
        finally:
            os.close(fd)
    except BaseException:
        os.close(support_fd)
        raise
    raw_hash = "sha256:" + hashlib.sha256(raw).hexdigest()
    # The independently retained bytes must themselves decode to the retained
    # facts; a hash/projection asserted after profile construction is not enough.
    try:
        decoded = json.loads(raw.decode("utf-8"), object_pairs_hook=lambda pairs: dict(pairs))
        observed = _normalize_hc03_profile(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        os.close(support_fd)
        raise _unavailable("hc03_handoff_malformed") from exc
    observed_projection = {key: value for key, value in observed.items() if key != "_interpreter_identities"}
    if observed_projection != expected_projection:
        os.close(support_fd)
        raise _PipEmbeddedError("readiness_mismatch", "hc03_independent_context", phase="admission")
    return _HC03AdmissionBinding(
        str(support_root), handoff.name, support_info.st_dev, support_info.st_ino,
        raw_hash, observed_projection["verified_facts_digest"], _digest(observed_projection),
        _freeze_json(expected_projection), support_fd,
    )


def _read_bound_handoff(
    binding: _HC03AdmissionBinding, expected_profile: Mapping[str, Any]
) -> tuple[str, str]:
    """Read exact bytes through retained support-root custody at each edge."""
    try:
        support_info = os.fstat(binding.support_fd)
        if (support_info.st_dev, support_info.st_ino) != (binding.support_dev, binding.support_ino):
            raise _unavailable("hc03_support_custody_changed")
        fd = os.open(binding.handoff_name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=binding.support_fd)
        try:
            info = os.fstat(fd)
            if stat.S_IFMT(info.st_mode) != stat.S_IFREG or info.st_nlink != 1:
                raise _unavailable("hc03_handoff_unavailable")
            raw = os.read(fd, _MAX_JSON_BYTES + 1)
        finally:
            os.close(fd)
    except OSError as exc:
        raise _unavailable("hc03_handoff_unavailable") from exc
    if len(raw) > _MAX_JSON_BYTES:
        raise _unavailable("hc03_handoff_too_large")
    actual_hash = "sha256:" + hashlib.sha256(raw).hexdigest()
    if actual_hash != binding.raw_hash:
        raise _PipEmbeddedError("readiness_mismatch", "hc03_handoff_hash", phase="admission")
    try:
        decoded = json.loads(raw.decode("utf-8"), object_pairs_hook=lambda pairs: dict(pairs))
        normalized = _normalize_hc03_profile(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise _unavailable("hc03_handoff_malformed") from exc
    public = {key: value for key, value in normalized.items() if key != "_interpreter_identities"}
    if public["verified_facts_digest"] != binding.facts_digest:
        raise _PipEmbeddedError("readiness_mismatch", "hc03_facts_digest", phase="admission")
    if _digest(public) != binding.projection_digest or public != _thaw_json(binding.expected_projection):
        raise _PipEmbeddedError("readiness_mismatch", "hc03_projection", phase="admission")
    expected = _strict_json_value(expected_profile)
    if expected != public:
        raise _PipEmbeddedError("readiness_mismatch", "hc03_profile", phase="admission")
    return actual_hash, binding.projection_digest


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
    hc03_handoff_path: str | Path | None = None
    hc03_trust: _HC03AdmissionBinding | None = None
    root_identities: Mapping[str, tuple[int, int]] | None = None
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
        if self.hc03_handoff_path is None or not isinstance(self.hc03_trust, _HC03AdmissionBinding):
            raise _unavailable("hc03_unbound")
        handoff_hash = _require_digest(self.hc03_handoff_hash, "hc03_handoff_hash")
        if self.hc03_trust.raw_hash != handoff_hash:
            raise _PipEmbeddedError("readiness_mismatch", "hc03_trust_hash")
        handoff_path = Path(self.hc03_handoff_path).expanduser().resolve(strict=False)
        requested_handoff = Path(self.hc03_handoff_path).expanduser()
        if requested_handoff.is_symlink() or handoff_path.parent != Path(self.hc03_trust.support_root) or handoff_path.name != self.hc03_trust.handoff_name:
            raise _PipEmbeddedError("readiness_mismatch", "hc03_handoff_custody")
        _read_bound_handoff(self.hc03_trust, readiness)
        root_identities = {
            name: (Path(path).stat().st_dev, Path(path).stat().st_ino)
            for name, path in {
                "environment": self.python_environment,
                "engine": self.engine_root,
                "custom_nodes": self.custom_nodes_root,
                "models": self.model_root,
                "output": self.output_root,
                "scratch": self.scratch_root,
                "cas": self.cas_root,
                "source": self.astrid_source_root,
                "pack": self.astrid_pack_root,
            }.items()
        }
        object.__setattr__(self, "hc03_profile", _freeze_json(readiness))
        object.__setattr__(self, "installation_evidence", _freeze_json(evidence))
        object.__setattr__(self, "hc03_handoff_hash", handoff_hash)
        object.__setattr__(self, "hc03_handoff_path", _require_absolute_path(self.hc03_handoff_path, "hc03_handoff_path"))
        object.__setattr__(self, "hc03_trust", self.hc03_trust)
        object.__setattr__(self, "root_identities", MappingProxyType(root_identities))

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
    def wait_completed(self, timeout: float, cancel_event: threading.Event | None = None) -> None: ...
    def read_result(self) -> _ChildResult: ...
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
            path.mkdir(exist_ok=True)
        self.request_path, self.ready_path = staging / "request.json", staging / "ready.json"
        self.result_path, self.log_path = staging / "result.json", staging / "embedded.log"
        self._go_read_fd, self._go_write_fd = os.pipe()
        os.set_blocking(self._go_write_fd, False)
        self._staging_fd = os.open(staging, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW)
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
        self.launch_spec = {
            "argv": [
                str(self.profile.python_executable), "-I", "-B", "-c", "<embedded-script>",
                str(self.request_path), str(self.ready_path), str(self._go_read_fd), str(self.result_path),
                str(self._staging_fd),
            ],
            "cwd": str(self.runtime_dir),
            "environment": {
                "PATH": str(Path(self.profile.python_executable).parent),
                "PYTHONNOUSERSITE": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "VIRTUAL_ENV": str(self.profile.python_environment),
                "VIBECOMFY_WATCHDOG": "0",
            },
            "script_digest": "sha256:" + hashlib.sha256(_PIP_EMBEDDED_SCRIPT.encode()).hexdigest(),
            "config_digest": self.request["config_digest"],
            "paths_digest": _hash_file(staging / "paths.yaml"),
            "handoff_hash": self.profile.hc03_handoff_hash,
            "readiness_digest": self.profile.readiness_digest,
            "package_inventory": _digest(_thaw_json(self.profile.installation_evidence["package_inventory"])),
            "timeouts": {
                name: getattr(self.profile.timeouts, name)
                for name in self.profile.timeouts.__dataclass_fields__
            },
        }
        self.request["launch_digest"] = _digest(self.launch_spec)
        self.request["package_facts"] = self._measured_package_facts()
        self.request["resolver_facts"] = {
            "roots": list(self.profile.installation_evidence["resolver_roots"]),
            "digest": self.profile.installation_evidence["resolver_digest"],
        }
        self.request["request_digest"] = _digest(
            {key: value for key, value in self.request.items() if key != "request_digest"}
        )
        self.request_path.write_bytes(_canonical_json(self.request).encode())
        self._process: subprocess.Popen[bytes] | None = None
        self._log_handle: Any = None
        self.measured_ready: dict[str, Any] | None = None
        self._completed = False
        self._observed_exit = False
        self._reaped = False
        self.ownership: _ProcessOwnership | None = None
        self._go_sent = False

    def start(self) -> None:
        argv = [
            str(self.profile.python_executable),
            "-I",
            "-B",
            "-c",
            _PIP_EMBEDDED_SCRIPT,
            str(self.request_path),
            str(self.ready_path),
            str(self._go_read_fd),
            str(self.result_path),
            str(self._staging_fd),
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
            process = subprocess.Popen(
                argv,
                cwd=str(self.runtime_dir),
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=self._log_handle,
                stderr=subprocess.STDOUT,
                close_fds=True,
                start_new_session=True,
                pass_fds=(self._go_read_fd, self._staging_fd),
            )
            # Publish custody immediately after OS creation.  A later
            # provenance failure must still be able to terminate this process.
            self._process = process
            deadline = time.monotonic() + self.profile.timeouts.preparation_seconds
            ownership = None
            while time.monotonic() < deadline:
                candidate = _census_owned_group(process, deadline)
                if candidate.known:
                    leaders = [row for row in candidate.members if row[0] == process.pid]
                    if leaders:
                        leader = leaders[0]
                        # lstart is captured by the census parser and is kept
                        # as immutable birth provenance by the process record.
                        ownership = _ProcessOwnership(process.pid, process.pid, candidate.leader_birth or "")
                        break
                time.sleep(0.01)
            if ownership is None:
                raise _PipEmbeddedError("containment_pending", "leader-provenance-unavailable", phase="spawn")
            self.ownership = ownership
            process._astrid_ownership = ownership  # type: ignore[attr-defined]
            os.close(self._go_read_fd)
            self._go_read_fd = -1
        except BaseException:
            if self._go_read_fd >= 0:
                os.close(self._go_read_fd)
            self._log_handle.close()
            self._log_handle = None
            raise

    def wait_ready(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                ready = _strict_load_json(self.ready_path, limit=_MAX_RESULT_BYTES)
            except ValueError:
                if os.path.lexists(self.ready_path):
                    raise
                ready = None
            if ready is not None:
                if set(ready) == {
                    "schema", "nonce", "request_digest", "profile_digest", "config_digest",
                    "launch_digest", "ok", "error",
                } and ready.get("ok") is False:
                    error = ready.get("error")
                    if (
                        isinstance(error, Mapping)
                        and set(error) == {"code", "reason"}
                        and error.get("code") in {"not_ready", "unsupported_installation"}
                        and isinstance(error.get("reason"), str)
                        and error.get("reason")
                    ):
                        raise _PipEmbeddedError("not_ready", str(error.get("reason") or "bootstrap_failed"), phase="ready")
                    raise _PipEmbeddedError("readiness_mismatch", "bootstrap_rejected", phase="ready")
                if set(ready) != {
                    "schema", "nonce", "request_digest", "profile_digest", "config_digest",
                    "launch_digest", "ok", "interpreter", "package", "resolver",
                } or ready.get("schema") != _READY_SCHEMA or ready.get("ok") is not True:
                    raise _PipEmbeddedError("readiness_mismatch", "ready_schema", phase="ready")
                interpreter = ready.get("interpreter")
                expected_interpreter = self.profile.installation_evidence
                if (
                    not isinstance(interpreter, Mapping)
                    or interpreter.get("executable") != str(self.profile.python_executable)
                    or interpreter.get("prefix") != str(self.profile.python_environment)
                    or interpreter.get("version") != expected_interpreter["python_version"]
                ):
                    raise _PipEmbeddedError("readiness_mismatch", "ready_interpreter", phase="ready")
                package = ready.get("package")
                resolver = ready.get("resolver")
                if not isinstance(package, Mapping) or not isinstance(resolver, Mapping):
                    raise _unavailable("ready_facts_unavailable", phase="ready")
                expected_package = self._measured_package_facts()
                expected_resolver = {
                    "roots": list(self.profile.installation_evidence["resolver_roots"]),
                    "digest": self.profile.installation_evidence["resolver_digest"],
                }
                if package != expected_package:
                    raise _PipEmbeddedError("readiness_mismatch", "package_facts", phase="ready")
                if resolver != expected_resolver:
                    raise _PipEmbeddedError("readiness_mismatch", "resolver_facts", phase="ready")
                expected = {
                    "nonce": self.request["nonce"],
                    "request_digest": self.request["request_digest"],
                    "profile_digest": self.request["profile_digest"],
                    "config_digest": self.request["config_digest"],
                    "launch_digest": self.request["launch_digest"],
                }
                if any(ready.get(key) != value for key, value in expected.items()):
                    raise _PipEmbeddedError("readiness_mismatch", "ready_identity", phase="ready")
                self.measured_ready = ready
                return
            if self._process is None or self._process.returncode is not None:
                raise _PipEmbeddedError("not_ready", "bootstrap_failed", phase="ready")
            time.sleep(0.05)
        raise _PipEmbeddedError("not_ready", "ready_deadline", phase="ready")

    def go(self) -> None:
        if self._go_sent or self._go_write_fd < 0:
            raise _PipEmbeddedError("go_failed", "go_already_sent", phase="go")
        frame = _canonical_json({
            "nonce": self.request["nonce"],
            "request_digest": self.request["request_digest"],
            "launch_digest": self.request["launch_digest"],
        }).encode("utf-8")
        try:
            written = os.write(self._go_write_fd, frame)
        except OSError as exc:
            reason = "go_pipe_full" if exc.errno in {errno.EAGAIN, errno.EWOULDBLOCK} else "go_pipe_closed"
            raise _PipEmbeddedError("go_failed", reason, phase="go") from exc
        finally:
            os.close(self._go_write_fd)
            self._go_write_fd = -1
        if written != len(frame):
            raise _PipEmbeddedError("go_failed", "go_pipe_short_write", phase="go")
        self._go_sent = True

    def wait_completed(self, timeout: float, cancel_event: threading.Event | None = None) -> None:
        if self._process is None:
            raise RuntimeError("embedded process was not started")
        deadline = time.monotonic() + timeout
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("embedded run cancelled")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("embedded execution deadline exceeded")
            census = _census_owned_group(self._process, deadline, ownership=self.ownership)
            if census.known:
                leader = next((row for row in census.members if row[0] == self._process.pid), None)
                if leader is not None and "Z" in leader[3].upper():
                    self._observed_exit = True
                    self._completed = True
                    return None
            time.sleep(min(0.05, remaining))
        raise TimeoutError("embedded execution deadline exceeded")

    def read_result(self) -> _ChildResult:
        if self._process is None:
            raise RuntimeError("embedded process was not started")
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

    def _measured_package_facts(self) -> dict[str, Any]:
        inventory = self.profile.installation_evidence["package_inventory"]
        return {
            "revision": self.profile.vibecomfy_revision,
            "digest": _digest(_thaw_json(inventory)),
            "files": _thaw_json(inventory),
        }

    def terminate(self, term_seconds: float, kill_seconds: float, reap_seconds: float) -> Mapping[str, Any]:
        process = self._process
        if process is None or self.ownership is None:
            raise _PipEmbeddedError("containment_pending", "process-provenance-unavailable", phase="containment")
        if self._reaped:
            return {"ok": True, "terminated": self._go_sent, "reaped": True, "group_quiescent": True}
        term_deadline = time.monotonic() + term_seconds
        census = _census_owned_group(process, term_deadline, ownership=self.ownership)
        if not census.known:
            raise _PipEmbeddedError("containment_pending", census.reason or "unknown-census", phase="containment")
        if census.live:
            try:
                os.killpg(self.ownership.pgid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        state = self._bounded_group_wait(process, term_deadline, signal.SIGTERM, ownership=self.ownership)
        if state != "QUIESCENT":
            kill_deadline = time.monotonic() + kill_seconds
            census = _census_owned_group(process, kill_deadline, ownership=self.ownership)
            if not census.known:
                raise _PipEmbeddedError("containment_pending", census.reason or "unknown-census", phase="containment")
            if census.live:
                try:
                    os.killpg(self.ownership.pgid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            state = self._bounded_group_wait(process, kill_deadline, signal.SIGKILL, ownership=self.ownership)
            if state != "QUIESCENT":
                raise _PipEmbeddedError("containment_pending", "group-live-at-deadline", phase="containment")
        try:
            process.wait(timeout=reap_seconds)
            self._reaped = True
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError("embedded child reap deadline exceeded") from exc
        ownership = dataclass_replace(self.ownership, pre_reap_quiescent=True, reaped=True)
        self.ownership = ownership
        final = _census_owned_group(process, time.monotonic() + reap_seconds, reaped=True, ownership=ownership)
        if not final.known:
            raise _PipEmbeddedError("containment_pending", final.reason or "unknown-census", phase="containment")
        if final.live:
            raise _PipEmbeddedError("containment_pending", "descendants-remain-live", phase="containment")
        return {"ok": True, "terminated": self._go_sent, "reaped": True, "group_quiescent": True}

    @staticmethod
    def _bounded_group_wait(
        process: subprocess.Popen[bytes], deadline: float, sig: int, *,
        ownership: _ProcessOwnership | None = None,
    ) -> str:
        while time.monotonic() < deadline:
            census = _census_owned_group(process, deadline, ownership=ownership)
            if not census.known:
                return "UNKNOWN"
            if not census.live:
                return "QUIESCENT"
            try:
                if ownership is None:
                    return "UNKNOWN"
                os.killpg(ownership.pgid, sig)
            except ProcessLookupError:
                pass
            time.sleep(min(0.05, max(0.001, deadline - time.monotonic())))
        return "LIVE_AT_DEADLINE"

    def cleanup(self) -> None:
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None
        for attr in ("_go_write_fd", "_go_read_fd", "_staging_fd"):
            fd = getattr(self, attr, -1)
            if isinstance(fd, int) and fd >= 0:
                os.close(fd)
                setattr(self, attr, -1)


def _measure_executable(profile: PipEmbeddedProfile) -> dict[str, Any]:
    path = Path(profile.python_executable)
    if path.is_symlink() or not path.is_file():
        raise _unavailable("interpreter_unavailable")
    before = path.stat()
    if stat.S_IFMT(before.st_mode) != stat.S_IFREG or not (before.st_mode & 0o111):
        raise _unavailable("interpreter_not_executable")
    measured = _hash_file(path)
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns
    ):
        raise _PipEmbeddedError("readiness_mismatch", "interpreter_changed")
    expected = profile.installation_evidence["python_sha256"]
    if measured != expected:
        raise _PipEmbeddedError("readiness_mismatch", "interpreter_bytes")
    return {
        "sha256": measured,
        "device": before.st_dev,
        "inode": before.st_ino,
        "size": before.st_size,
        "mtime_ns": before.st_mtime_ns,
        "ctime_ns": before.st_ctime_ns,
    }


def _revalidate_launch_evidence(profile: PipEmbeddedProfile) -> dict[str, Any]:
    """Re-measure mutable launch facts immediately before each admission edge."""
    executable = _measure_executable(profile)
    if not isinstance(profile.hc03_trust, _HC03AdmissionBinding):
        raise _unavailable("hc03_unbound")
    _read_bound_handoff(profile.hc03_trust, _thaw_json(profile.hc03_profile))
    evidence = _thaw_json(profile.installation_evidence)
    try:
        current_ids = {
            name: (Path(path).stat().st_dev, Path(path).stat().st_ino)
            for name, path in {
                "environment": profile.python_environment,
                "engine": profile.engine_root,
                "custom_nodes": profile.custom_nodes_root,
                "models": profile.model_root,
                "output": profile.output_root,
                "scratch": profile.scratch_root,
                "cas": profile.cas_root,
                "source": profile.astrid_source_root,
                "pack": profile.astrid_pack_root,
            }.items()
        }
    except OSError as exc:
        raise _unavailable("installation_custody_unproven") from exc
    if current_ids != dict(profile.root_identities or {}):
        raise _PipEmbeddedError("readiness_mismatch", "installation_root_identity")
    try:
        _validate_profile_evidence(profile, evidence)
    except (OSError, ValueError) as exc:
        message = str(exc)
        if "unavailable" in message or "required" in message:
            raise _unavailable("installation_custody_unproven") from exc
        raise _PipEmbeddedError("readiness_mismatch", "installation_inventory") from exc
    if not evidence.get("package_inventory") or not evidence.get("resolver_roots"):
        raise _unavailable("effective_resolver_unproven")
    return {
        "executable": executable,
        "package_inventory": _digest(evidence["package_inventory"]),
        "resolver_digest": evidence["resolver_digest"],
        "profile_digest": profile.profile_digest,
        "readiness_digest": profile.readiness_digest,
        "handoff_hash": profile.hc03_handoff_hash,
    }


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
        if timeouts is not None and timeouts != profile.timeouts:
            raise ValueError("pip_embedded timeout policy must match the immutable profile")
        self.timeouts = profile.timeouts
        self._execution_factory = execution_factory or (
            lambda selected_profile, request, staging: _SubprocessEmbeddedExecution(
                selected_profile, request, staging
            )
        )
        self._lock = threading.RLock()
        self._record: dict[str, Any] | None = None
        self._poisoned = False
        self._disposed: dict[str, Any] | None = None
        self._cached_outcome: Mapping[str, Any] | None = None
        self._cached_binding: _InvocationBinding | None = None
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
            if self._disposed is not None:
                raise _PipEmbeddedError("not_ready", "session_disposed", phase="admission")
            if self._poisoned:
                raise _PipEmbeddedError("containment_pending", "session_poisoned", phase="admission")
            if self._record is not None:
                raise RuntimeError("pip_embedded execution is already in progress")
            binding = _InvocationBinding(
                uuid.uuid4().hex, identity, self.profile.profile_digest
            )
            record = {
                "binding": binding,
                "nonce": binding.nonce,
                "identity": identity,
                "profile_digest": binding.profile_digest,
                "phase": "PREPARING",
                "stop_reason": None,
                "cancel_event": threading.Event(),
                "handle": None,
                "done": threading.Event(),
                "outcome": None,
                "staging": None,
                "outputs": None,
                "destination": None,
                "source_dir_fd": None,
                "destination_fd": None,
                "scratch_fd": None,
                "staging_fd": None,
                "staging_name": None,
                "staging_identity": None,
                "custody": None,
                "spawn_pending": False,
                "start_finished": False,
                "containment_state": "NOT_STARTED",
                "containment_done": threading.Event(),
                "containment_result": None,
                "owner_finished": False,
                "cleanup_state": "NOT_STARTED",
                "publication_state": None,
                "go_sent": False,
                "preparation_deadline": time.monotonic() + self.timeouts.preparation_seconds,
                "pre_go_deadline": time.monotonic() + self.timeouts.preparation_seconds + self.timeouts.ready_seconds,
                "ready_deadline": None,
                "failure": None,
                "control_fault": None,
            }
            self._record = record
            return record

    def active_invocation(self) -> dict[str, Any] | None:
        with self._lock:
            if self._record is None:
                return None
            return {
                "nonce": self._record["binding"].nonce,
                "identity": self._record["binding"].identity,
                "phase": self._record["phase"],
                "stop_reason": self._record["stop_reason"],
            }

    @staticmethod
    def _task_identity(value: str | None) -> str:
        if value is None:
            return "task-unspecified"
        if not isinstance(value, str) or not value.strip():
            raise ValueError("pip_embedded task identity must be non-empty")
        return value

    @staticmethod
    def _outcome_copy(outcome: Mapping[str, Any] | None) -> dict[str, Any]:
        return _thaw_json(outcome or {})

    def _finalize(
        self,
        record: dict[str, Any],
        outcome: dict[str, Any],
        *,
        poison: bool = False,
        error: BaseException | None = None,
    ) -> None:
        with self._lock:
            if record["outcome"] is not None:
                return
            binding: _InvocationBinding = record["binding"]
            frozen = dict(outcome)
            frozen.setdefault("nonce", binding.nonce)
            frozen.setdefault("identity", binding.identity)
            status = frozen.get("status")
            if not isinstance(status, str) or not status:
                status = record["stop_reason"]
            if not isinstance(status, str) or not status:
                status = getattr(error, "code", None) or ("succeeded" if frozen.get("ok") else "failed")
            if status == "succeeded" and frozen.get("ok") is not True:
                status = getattr(error, "code", None) or "failed"
            frozen["status"] = status
            frozen.setdefault("transition", frozen["status"])
            frozen.setdefault("terminated", frozen.get("termination_complete") is True)
            frozen.setdefault("reaped", frozen.get("direct_child_reaped") is True)
            frozen.setdefault("group_quiescent", frozen.get("group_quiescent") is True)
            frozen.setdefault("cleanup_complete", frozen.get("cleanup_complete") is True)
            frozen.setdefault("fence_pending", poison or frozen.get("fence_pending") is True)
            publication = record.get("publication_state")
            frozen.setdefault("phase", record.get("phase"))
            frozen.setdefault("publication", self._outcome_copy(publication) if publication else None)
            frozen.setdefault(
                "termination",
                {
                    "complete": frozen["terminated"],
                    "reaped": frozen["reaped"],
                    "group_quiescent": frozen["group_quiescent"],
                },
            )
            frozen.setdefault(
                "reap",
                {
                    "direct_child": frozen["reaped"],
                    "group_quiescent": frozen["group_quiescent"],
                },
            )
            frozen.setdefault(
                "cleanup",
                {
                    "complete": frozen["cleanup_complete"],
                    "state": record.get("cleanup_state"),
                },
            )
            frozen.setdefault("fence", {"pending": frozen["fence_pending"]})
            frozen = _freeze_json(frozen)
            record["outcome"] = frozen
            self._cached_outcome = frozen
            self._cached_binding = binding
            if poison or frozen["fence_pending"]:
                self._poisoned = True
            if record["stop_reason"] is not None:
                self._disposed = frozen
            record["owner_finished"] = True
            if not frozen["fence_pending"]:
                self._record = None
            record["done"].set()

    @staticmethod
    def _close_custody(record: dict[str, Any]) -> None:
        custody = record.get("custody")
        if isinstance(custody, _OutputCustody):
            fds = (custody.source_fd, custody.staging_fd, custody.scratch_fd, custody.destination_fd)
        else:
            fds = tuple(record.get(key) for key in ("source_dir_fd", "staging_fd", "scratch_fd", "destination_fd"))
        for fd in fds:
            if isinstance(fd, int) and fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass
        for key in ("source_dir_fd", "staging_fd", "scratch_fd", "destination_fd"):
            record[key] = None

    def _ensure_contained(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if record["containment_state"] == "DONE":
                return dict(record["containment_result"])
            if record["containment_state"] == "IN_PROGRESS":
                event = record["containment_done"]
                claimant = False
            else:
                record["containment_state"] = "IN_PROGRESS"
                event = record["containment_done"]
                claimant = True
                handle = record.get("handle")
                stop_reason = record.get("stop_reason")
        if not claimant:
            event.wait(timeout=self.timeouts.control_seconds)
            with self._lock:
                return dict(record.get("containment_result") or {
                    "ok": False, "terminated": False, "reaped": False,
                    "group_quiescent": False, "fence_pending": True,
                })
        result = {
            "ok": True,
            "terminated": False,
            "reaped": False,
            "group_quiescent": True,
            "cleanup_complete": False,
            "fence_pending": False,
            "error_code": None,
        }
        try:
            if record.get("spawn_pending") and handle is None:
                with self._lock:
                    record["containment_state"] = "NOT_STARTED"
                return {
                    "ok": False, "terminated": False, "reaped": False,
                    "group_quiescent": False, "cleanup_complete": False,
                    "fence_pending": True, "error_code": "containment_pending",
                }
            if handle is None:
                result["reaped"] = True
            if handle is not None:
                if stop_reason is not None or record.get("go_sent"):
                    containment = handle.terminate(
                        self.timeouts.term_seconds,
                        self.timeouts.kill_seconds,
                        self.timeouts.reap_seconds,
                    )
                    if not isinstance(containment, Mapping) or not containment.get("reaped"):
                        raise _PipEmbeddedError("containment_pending", "handle-did-not-prove-reap", phase="containment")
                    result.update(dict(containment))
                else:
                    # A normal completion still needs the process handle's
                    # containment proof.  The protocol's terminate operation
                    # performs only the bounded census/reap; it does not imply
                    # a cancellation transition.
                    containment = handle.terminate(
                        self.timeouts.term_seconds,
                        self.timeouts.kill_seconds,
                        self.timeouts.reap_seconds,
                    )
                    if not isinstance(containment, Mapping) or not containment.get("reaped"):
                        raise _PipEmbeddedError("containment_pending", "handle-did-not-prove-reap", phase="containment")
                    result.update(dict(containment))
            result["group_quiescent"] = result.get("group_quiescent") is True
        except BaseException as exc:
            result.update(
                ok=False,
                group_quiescent=False,
                fence_pending=True,
                error_code=getattr(exc, "code", "containment_pending"),
                error=str(exc),
            )
        with self._lock:
            record["containment_result"] = dict(result)
            record["containment_state"] = "DONE"
            record["containment_done"].set()
        return result

    def run(
        self, workflow: Any, *, task_identity: str | None = None, out_dir: Path | None = None
    ) -> Any:
        identity = self._task_identity(task_identity)
        record = self._reserve(identity)
        binding: _InvocationBinding = record["binding"]
        handle: PipEmbeddedExecution | None = None
        staging: Path | None = None
        published: list[Path] = []
        try:
            if time.monotonic() > record["preparation_deadline"]:
                raise _unavailable("preparation_deadline")
            if out_dir is None:
                raise ValueError("pip_embedded requires an explicit output directory")
            destination = self.validate_output_dir(out_dir)
            destination.mkdir(parents=True, exist_ok=True)
            destination_fd = os.open(
                destination, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
            )
            record["destination"] = destination
            record["destination_fd"] = destination_fd
            scratch = Path(self.profile.scratch_root)
            scratch_fd = os.open(scratch, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW)
            record["scratch_fd"] = scratch_fd
            scratch_info = os.fstat(scratch_fd)
            record["scratch_identity"] = (scratch_info.st_dev, scratch_info.st_ino)
            from vibecomfy.workflow import VibeWorkflow

            if type(workflow) is not VibeWorkflow:
                raise ValueError("unsupported_workflow: expected pinned VibeWorkflow")
            envelope = _strict_json_value(workflow.to_envelope(), path="workflow")
            if envelope.get("vibecomfy_format_version") is None:
                raise ValueError("unsupported_workflow: missing VibeComfy format stamp")
            request = {
                "schema": _REQUEST_SCHEMA,
                "nonce": binding.nonce,
                "task_identity": identity,
                "profile_digest": binding.profile_digest,
                "workflow": envelope,
                "workflow_digest": _digest(envelope),
                "config_digest": None,
                "profile_readiness_digest": self.profile.readiness_digest,
                "policy": {
                    "ready_seconds": self.timeouts.ready_seconds,
                    "execution_seconds": self.timeouts.execution_seconds,
                },
            }
            staging_name = f"pip-embedded-{uuid.uuid4().hex}"
            os.mkdir(staging_name, mode=0o700, dir_fd=scratch_fd)
            staging = scratch / staging_name
            record["staging"] = staging
            record["staging_name"] = staging_name
            staging_fd = os.open(staging_name, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW, dir_fd=scratch_fd)
            record["staging_fd"] = staging_fd
            staging_info = os.fstat(staging_fd)
            record["staging_identity"] = (staging_info.st_dev, staging_info.st_ino)
            engine_output = staging / "engine-output"
            os.mkdir("engine-output", mode=0o700, dir_fd=staging_fd)
            source_fd = os.open(
                "engine-output", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW,
                dir_fd=staging_fd,
            )
            record["source_dir_fd"] = source_fd
            record["source_identity"] = (
                os.fstat(source_fd).st_dev,
                os.fstat(source_fd).st_ino,
            )
            record["custody"] = _OutputCustody(
                binding=binding,
                scratch_fd=scratch_fd,
                scratch_identity=record["scratch_identity"],
                staging_fd=staging_fd,
                staging_identity=record["staging_identity"],
                staging_name=staging_name,
                staging_path=staging,
                source_fd=source_fd,
                source_identity=record["source_identity"],
                source_name="engine-output",
                source_path=engine_output,
                destination_fd=destination_fd,
                destination_identity=(
                    os.fstat(destination_fd).st_dev,
                    os.fstat(destination_fd).st_ino,
                ),
                destination_path=destination,
            )
            (staging / "paths.yaml").write_text(
                "vibecomfy:\n"
                f"  base_path: {json.dumps(self.profile.model_root)}\n"
                + "\n".join(
                    f"  {category}: {json.dumps(str(Path(self.profile.model_root) / category))}"
                    for category in (
                        "checkpoints", "clip", "clip_vision", "configs", "controlnet",
                        "diffusion_models", "embeddings", "loras", "style_models", "unet",
                        "upscale_models", "vae", "vae_approx", "text_encoders", "audio_encoders",
                    )
                )
                + f"\n  custom_nodes: {json.dumps(self.profile.custom_nodes_root)}\n",
                encoding="utf-8",
            )
            launch_facts = _revalidate_launch_evidence(self.profile)
            record["launch_facts"] = launch_facts
            with self._lock:
                if record["stop_reason"] is not None:
                    raise _PipEmbeddedError("cancelled", "before_spawn", nonce=binding.nonce)
                record["phase"] = "SPAWNING"
                record["spawn_pending"] = True
            handle = self._execution_factory(self.profile, request, staging)
            with self._lock:
                record["handle"] = handle
                record["spawn_pending"] = False
                if record["stop_reason"] is not None:
                    raise _PipEmbeddedError("cancelled", "before_start", nonce=binding.nonce)
                if time.monotonic() > record["pre_go_deadline"]:
                    raise _unavailable("pre_go_deadline", phase="spawn")
                record["phase"] = "PREFLIGHT"
            handle.start()
            with self._lock:
                record["start_finished"] = True
                if record["stop_reason"] is not None:
                    raise _PipEmbeddedError("cancelled", "before_ready", nonce=binding.nonce)
                record["ready_deadline"] = time.monotonic() + self.timeouts.ready_seconds
            handle.wait_ready(self.timeouts.ready_seconds)
            if time.monotonic() > record["pre_go_deadline"]:
                raise _unavailable("pre_go_deadline", phase="ready")
            _revalidate_launch_evidence(self.profile)
            with self._lock:
                if record["stop_reason"] is not None:
                    raise _PipEmbeddedError("cancelled", "before_go", nonce=binding.nonce)
                record["phase"] = "RUNNING"
                handle.go()
                record["go_sent"] = True
            handle.wait_completed(self.timeouts.execution_seconds, record["cancel_event"])
            containment = self._ensure_contained(record)
            if not containment.get("group_quiescent", False) or not containment.get("reaped", False):
                raise _PipEmbeddedError("containment_pending", "normal_completion", phase="containment")
            result = handle.read_result()
            if not isinstance(result, _ChildResult) or result.nonce != binding.nonce:
                raise ValueError("embedded result nonce/type mismatch")
            with self._lock:
                if record["stop_reason"] is not None:
                    raise _PipEmbeddedError("cancelled", "during_execution", nonce=binding.nonce)
                record["phase"] = "COLLECTING"
            published = self._collect_outputs(record, result, destination)
            result = _ChildResult(
                result.nonce, result.run_id, result.prompt_id, result.outputs, tuple(published)
            )
            with self._lock:
                if record["stop_reason"] is not None:
                    raise _PipEmbeddedError("cancelled", "during_collection", nonce=binding.nonce)
            record["cleanup_state"] = "IN_PROGRESS"
            handle.cleanup()
            custody = record.get("custody")
            cleanup_parent = custody.scratch_fd if isinstance(custody, _OutputCustody) else record["scratch_fd"]
            cleanup_name = custody.staging_name if isinstance(custody, _OutputCustody) else record["staging_name"]
            cleanup_identity = custody.staging_identity if isinstance(custody, _OutputCustody) else record["staging_identity"]
            _remove_tree_at(
                cleanup_parent, cleanup_name,
                timeout=self.timeouts.cleanup_seconds, expected=cleanup_identity,
            )
            record["cleanup_state"] = "DONE"
            self._close_custody(record)
            staging = None
            self._finalize(
                record,
                {
                    "ok": True,
                    "result": result,
                    "outputs": published,
                    "termination_complete": True,
                    "direct_child_reaped": True,
                    "group_quiescent": True,
                    "cleanup_complete": True,
                },
                error=None,
            )
            return result
        except BaseException as exc:
            containment = record.get("containment_result") or self._ensure_contained(record)
            poison = bool(containment.get("fence_pending")) or record.get("stop_reason") == "identity-mismatch" or bool(record.get("publication_fence"))
            cleanup_complete = False
            if handle is not None and record.get("cleanup_state") != "DONE":
                try:
                    record["cleanup_state"] = "IN_PROGRESS"
                    handle.cleanup()
                    record["cleanup_state"] = "DONE"
                except BaseException as cleanup_exc:
                    record["failure"] = str(cleanup_exc)
                    poison = True
            if staging is not None and not poison:
                try:
                    custody = record.get("custody")
                    cleanup_parent = custody.scratch_fd if isinstance(custody, _OutputCustody) else record.get("scratch_fd")
                    cleanup_name = custody.staging_name if isinstance(custody, _OutputCustody) else record.get("staging_name")
                    cleanup_identity = custody.staging_identity if isinstance(custody, _OutputCustody) else record.get("staging_identity")
                    if cleanup_parent is not None and cleanup_name:
                        _remove_tree_at(
                            cleanup_parent, cleanup_name,
                            timeout=self.timeouts.cleanup_seconds,
                            expected=cleanup_identity,
                        )
                    cleanup_complete = True
                except BaseException:
                    poison = True
            if not poison:
                self._close_custody(record)
            terminal_exc = exc if isinstance(exc, _PipEmbeddedError) else _PipEmbeddedError(
                "publication_failure" if record.get("publication_state") else "failed",
                str(exc) or type(exc).__name__,
                phase=record.get("phase", "admission"),
                nonce=binding.nonce,
            )
            self._finalize(
                record,
                {
                    "ok": False,
                    "error": str(terminal_exc),
                    "error_code": terminal_exc.code,
                    "termination_complete": containment.get("terminated", False),
                    "direct_child_reaped": containment.get("reaped", False),
                    "group_quiescent": containment.get("group_quiescent", False),
                    "cleanup_complete": cleanup_complete,
                    "fence_pending": poison,
                },
                poison=poison,
                error=terminal_exc,
            )
            terminal_exc.outcome = self._outcome_copy(record.get("outcome"))
            if terminal_exc is not exc:
                raise terminal_exc from exc
            raise

    def _collect_outputs(
        self, record: dict[str, Any], result: _ChildResult, destination: Path
    ) -> list[Path]:
        custody = record.get("custody")
        if record is not self._record or not isinstance(custody, _OutputCustody):
            raise ValueError("embedded output custody is not bound to this invocation")
        binding = custody.binding
        if (
            record.get("binding") != binding
            or record.get("nonce") != binding.nonce
            or record.get("identity") != binding.identity
            or record.get("profile_digest") != binding.profile_digest
            or result.nonce != binding.nonce
        ):
            raise ValueError("embedded output invocation identity changed")
        if record.get("phase") != "COLLECTING":
            raise ValueError("embedded output collection is outside the invocation phase")
        if Path(destination).expanduser().resolve(strict=False) != custody.destination_path:
            raise ValueError("embedded output destination is not the admitted directory")
        if (
            record.get("source_dir_fd") != custody.source_fd
            or record.get("source_identity") != custody.source_identity
            or record.get("staging_fd") != custody.staging_fd
            or record.get("staging_identity") != custody.staging_identity
            or record.get("scratch_fd") != custody.scratch_fd
            or record.get("scratch_identity") != custody.scratch_identity
            or record.get("destination_fd") != custody.destination_fd
            or record.get("destination") != custody.destination_path
            or record.get("staging") != custody.staging_path
            or record.get("staging_name") != custody.staging_name
        ):
            raise ValueError("embedded output admission custody was substituted")
        handle = record.get("handle")
        if handle is not None and getattr(handle, "output_dir", custody.source_path) != custody.source_path:
            raise ValueError("embedded output handle source was substituted")
        source_fd = custody.source_fd
        destination_fd = custody.destination_fd
        staging_fd = custody.staging_fd
        scratch_fd = custody.scratch_fd
        if not all(isinstance(fd, int) and fd >= 0 for fd in (source_fd, destination_fd, staging_fd, scratch_fd)):
            raise RuntimeError("embedded output custody is unavailable")
        _reject_symlink_ancestors(destination)
        try:
            source_info = os.fstat(source_fd)
            if stat.S_IFMT(source_info.st_mode) != stat.S_IFDIR or source_info.st_nlink < 1:
                raise ValueError("embedded output source custody is not a directory")
            if (source_info.st_dev, source_info.st_ino) != custody.source_identity:
                raise ValueError("embedded output source custody changed")
            staging_info = os.fstat(staging_fd)
            if stat.S_IFMT(staging_info.st_mode) != stat.S_IFDIR or (
                staging_info.st_dev, staging_info.st_ino
            ) != custody.staging_identity:
                raise ValueError("embedded output staging custody changed")
            scratch_info = os.fstat(scratch_fd)
            if stat.S_IFMT(scratch_info.st_mode) != stat.S_IFDIR or (
                scratch_info.st_dev, scratch_info.st_ino
            ) != custody.scratch_identity:
                raise ValueError("embedded output scratch custody changed")
            check_staging_fd = os.open(
                custody.staging_name, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW,
                dir_fd=scratch_fd,
            )
            try:
                if (os.fstat(check_staging_fd).st_dev, os.fstat(check_staging_fd).st_ino) != (
                    staging_info.st_dev, staging_info.st_ino
                ):
                    raise ValueError("embedded output staging custody changed")
            finally:
                os.close(check_staging_fd)
            check_source_fd = os.open(
                custody.source_name,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW,
                dir_fd=staging_fd,
            )
            try:
                if (os.fstat(check_source_fd).st_dev, os.fstat(check_source_fd).st_ino) != custody.source_identity:
                    raise ValueError("embedded output source relationship changed")
            finally:
                os.close(check_source_fd)
            destination_info = os.fstat(destination_fd)
            if stat.S_IFMT(destination_info.st_mode) != stat.S_IFDIR or (
                destination_info.st_dev, destination_info.st_ino
            ) != custody.destination_identity:
                raise ValueError("embedded output destination custody changed")
        except OSError as exc:
            raise ValueError("embedded output custody unavailable") from exc
        publication_name = f".pip-embedded-staging-{uuid.uuid4().hex}"
        os.mkdir(publication_name, mode=0o700, dir_fd=destination_fd)
        publication_fd = os.open(
            publication_name, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW,
            dir_fd=destination_fd,
        )
        record["publication_state"] = {
            "parent_fd": destination_fd,
            "temp_name": publication_name,
            "final_name": None,
            "phase": "COPYING",
            "temp_identity": (os.fstat(publication_fd).st_dev, os.fstat(publication_fd).st_ino),
        }
        created: list[Path] = []
        deadline = time.monotonic() + self.timeouts.collection_seconds
        committed_name: str | None = None
        fence = False
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
                try:
                    leaf_fd = os.open(
                        name,
                        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0),
                        dir_fd=source_fd,
                    )
                except OSError as exc:
                    raise ValueError("embedded output custody rejected path") from exc
                output_fd: int | None = None
                try:
                    before = os.fstat(leaf_fd)
                    if (
                        stat.S_IFMT(before.st_mode) != stat.S_IFREG
                        or before.st_nlink != 1
                        or before.st_size != size
                    ):
                        raise ValueError("embedded output custody rejected file")
                    output_fd = os.open(
                        name,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
                        0o600,
                        dir_fd=publication_fd,
                    )
                    digest = hashlib.sha256()
                    copied = 0
                    while copied < size:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("embedded output collection deadline exceeded")
                        chunk = os.read(leaf_fd, min(1024 * 1024, size - copied))
                        if not chunk:
                            break
                        copied += len(chunk)
                        if copied > size:
                            raise ValueError("embedded output exceeded declared size")
                        digest.update(chunk)
                        written = 0
                        while written < len(chunk):
                            if time.monotonic() >= deadline:
                                raise TimeoutError("embedded output collection deadline exceeded")
                            count = os.write(output_fd, chunk[written:])
                            if count <= 0:
                                raise OSError("embedded output short write")
                            written += count
                    if copied != size or os.read(leaf_fd, 1):
                        raise ValueError("embedded output size changed during custody")
                    os.fsync(output_fd)
                    after = os.fstat(leaf_fd)
                    if (
                        after.st_dev, after.st_ino, after.st_nlink, after.st_size, after.st_mtime_ns
                    ) != (
                        before.st_dev, before.st_ino, before.st_nlink, before.st_size, before.st_mtime_ns
                    ):
                        raise ValueError("embedded output mutated during custody")
                finally:
                    os.close(leaf_fd)
                    if output_fd is not None:
                        os.close(output_fd)
                if "sha256:" + digest.hexdigest() != expected:
                    raise ValueError("embedded output digest mismatch")
                created.append(destination / publication_name / name)
            os.fsync(publication_fd)
            final_name = f"pip-embedded-{uuid.uuid4().hex}"
            record["publication_state"].update(final_name=final_name, phase="PREPARED")
            with self._lock:
                if record.get("stop_reason") is not None:
                    raise _PipEmbeddedError("cancelled", "before_commit", nonce=binding.nonce)
                record["publication_state"]["phase"] = "COMMITTING"
            _publish_directory_noreplace(destination_fd, publication_name, destination_fd, final_name)
            committed_name = final_name
            record["publication_state"].update(
                phase="RENAMED", current_name=final_name,
                final_identity=record["publication_state"]["temp_identity"],
            )
            os.fsync(destination_fd)
            final_info = os.stat(final_name, dir_fd=destination_fd, follow_symlinks=False)
            parent_info = os.stat(destination, follow_symlinks=False)
            if (final_info.st_dev, final_info.st_ino) != record["publication_state"]["final_identity"]:
                raise ValueError("embedded output publication custody changed")
            if (parent_info.st_dev, parent_info.st_ino) != (
                destination_info.st_dev, destination_info.st_ino
            ):
                raise ValueError("embedded output destination custody changed")
            record["publication_state"].update(phase="DURABLE")
            return [destination / final_name / Path(path).name for path in created]
        except BaseException as exc:
            state = record.get("publication_state", {})
            current_name = committed_name or state.get("temp_name")
            try:
                if current_name:
                    _remove_tree_at(
                        destination_fd, current_name,
                        timeout=self.timeouts.cleanup_seconds,
                        expected=state.get("temp_identity") if committed_name is None else state.get("final_identity"),
                    )
                state["phase"] = "ROLLED_BACK"
            except BaseException as rollback_exc:
                state["phase"] = "FENCE_PENDING"
                state["rollback_error"] = str(rollback_exc)
                fence = True
                record["publication_fence"] = True
            if fence:
                record["publication_state"]["unresolved_name"] = current_name
            if isinstance(exc, _PipEmbeddedError):
                raise
            raise
        finally:
            if not fence:
                os.close(publication_fd)
            else:
                record["publication_fd"] = publication_fd

    def _control(
        self,
        reason: str,
        task_identity: str | None,
        invocation_nonce: str | None = None,
    ) -> dict[str, Any]:
        identity_bad = False
        post_commit_identity_bad = False
        with self._lock:
            record = self._record
            if record is None:
                cached = self._cached_outcome
                cached_binding = self._cached_binding
                if cached is not None and cached_binding is not None:
                    supplied_identity = self._task_identity(task_identity) if task_identity is not None else None
                    if (
                        task_identity is not None or invocation_nonce is not None
                    ) and (supplied_identity, invocation_nonce) != (
                        cached_binding.identity, cached_binding.nonce
                    ):
                        error = _PipEmbeddedError(
                            "identity_mismatch", "stale invocation identity", nonce=cached_binding.nonce
                        )
                        error.outcome = self._outcome_copy(cached)
                        raise error
                    return self._outcome_copy(cached)
                if self._disposed is None:
                    self._disposed = _freeze_json({
                        "ok": True,
                        "status": "disposed",
                        "transition": "disposed",
                        "phase": "DISPOSED",
                        "terminated": False,
                        "reaped": True,
                        "group_quiescent": True,
                        "cleanup_complete": True,
                        "fence_pending": False,
                        "termination": {"complete": False, "reaped": True, "group_quiescent": True},
                        "reap": {"direct_child": True, "group_quiescent": True},
                        "cleanup": {"complete": True, "state": "DONE"},
                        "publication": None,
                        "fence": {"pending": False},
                    })
                if task_identity is not None or invocation_nonce is not None:
                    error = _PipEmbeddedError("identity_mismatch", "stale invocation identity")
                    error.outcome = self._outcome_copy(self._disposed)
                    raise error
                return self._outcome_copy(self._disposed)
            identity = self._task_identity(task_identity)
            binding: _InvocationBinding = record["binding"]
            publication_phase = (record.get("publication_state") or {}).get("phase")
            post_commit = publication_phase in {"COMMITTING", "RENAMED", "DURABLE", "FENCE_PENDING"}
            if not isinstance(invocation_nonce, str) or not invocation_nonce.strip() or (
                binding.identity, binding.nonce
            ) != (identity, invocation_nonce):
                identity_bad = True
                post_commit_identity_bad = post_commit
                if not post_commit:
                    if record["stop_reason"] is None:
                        record["stop_reason"] = "identity-mismatch"
                    record["control_fault"] = "active invocation identity mismatch"
                    record["failure"] = "active invocation identity mismatch"
                    record["cancel_event"].set()
                event = record["done"]
            else:
                if not post_commit and record["stop_reason"] is None:
                    record["stop_reason"] = reason
                event = record["done"]
            if not identity_bad and not post_commit:
                record["cancel_event"].set()
            handle_available = record.get("handle") is not None
        if handle_available and not post_commit_identity_bad:
            self._ensure_contained(record)
        if not event.wait(timeout=self.timeouts.control_seconds):
            timeout_outcome = {
                "ok": False,
                "status": "containment_pending",
                "transition": "containment_pending",
                "nonce": record["binding"].nonce,
                "identity": record["binding"].identity,
                "phase": record.get("phase"),
                "terminated": False,
                "reaped": False,
                "group_quiescent": False,
                "cleanup_complete": False,
                "fence_pending": True,
                "error_code": "containment_pending",
            }
            if identity_bad:
                error = _PipEmbeddedError(
                    "identity_mismatch", "active invocation identity mismatch",
                    nonce=record["binding"].nonce,
                    outcome=timeout_outcome,
                )
                raise error
            return timeout_outcome
        if identity_bad:
            error = _PipEmbeddedError(
                "identity_mismatch", "active invocation identity mismatch",
                nonce=record["binding"].nonce,
            )
            with self._lock:
                error.outcome = self._outcome_copy(record.get("outcome"))
            raise error
        with self._lock:
            return self._outcome_copy(record["outcome"] or {
                "ok": False,
                "status": "containment_pending",
                "transition": "containment_pending",
                "nonce": record["binding"].nonce,
                "identity": record["binding"].identity,
                "phase": record.get("phase"),
                "terminated": False,
                "reaped": False,
                "fence_pending": True,
            })

    def cancel(
        self, *, task_identity: str | None = None, invocation_nonce: str | None = None
    ) -> dict[str, Any]:
        return self._control("cancelled", task_identity, invocation_nonce)

    def release(
        self, *, task_identity: str | None = None, invocation_nonce: str | None = None
    ) -> dict[str, Any]:
        return self._control("released", task_identity, invocation_nonce)

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
        if pip_session is not None:
            module_origin = Path(getattr(vibecomfy, "__file__", "")).resolve(strict=False)
            try:
                module_origin.relative_to(Path(pip_session.profile.engine_root))
            except ValueError as exc:
                raise _unavailable("parent_template_origin_unbound", phase="admission") from exc
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
