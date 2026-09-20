#!/usr/bin/env python3
"""Claim an RTX 5090 on the existing Astrid ``backup`` volume.

This is an operator-facing waiter, not a second RunPod client.  It uses the
shared Astrid environment and the canonical ``runpod-lifecycle`` launch path:
the exact GPU/storage request is retried until capacity appears.  The
network-volume size is discovered and echoed back unchanged; the 200 GB
request applies only to the pod's disposable container disk.

On success the script prints a secret-free pod handle and exits, leaving the
pod running.  Pass ``--handle-path`` when a durable local breadcrumb is useful;
the handle can be handed to ``runpod-lifecycle terminate <pod-id> --yes``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runpod_lifecycle import (
    LaunchFailure,
    RunPodConfig,
    get_network_volumes,
    launch_when_available,
)


DEFAULT_GPU = "NVIDIA GeForce RTX 5090"
DEFAULT_STORAGE = "backup"
DEFAULT_CONTAINER_DISK_GB = 200
DEFAULT_POLL_SECONDS = 30
DEFAULT_CAPACITY_WINDOW_SECONDS = 3600
DEFAULT_READY_TIMEOUT_SECONDS = 900


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _log(message: str) -> None:
    print(f"{_utc_now()} {message}", file=sys.stderr, flush=True)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _volume_by_name_or_id(volumes: list[dict[str, Any]], name_or_id: str) -> dict[str, Any] | None:
    return next(
        (
            volume
            for volume in volumes
            if isinstance(volume, dict)
            and (str(volume.get("name") or "") == name_or_id or str(volume.get("id") or "") == name_or_id)
        ),
        None,
    )


async def _require_existing_volume(config: RunPodConfig, name_or_id: str) -> dict[str, Any]:
    volumes = await asyncio.to_thread(get_network_volumes, config.api_key)
    volume = _volume_by_name_or_id(volumes, name_or_id)
    if volume is None:
        raise RuntimeError(f"RunPod network volume {name_or_id!r} was not found; refusing to create one")
    size = volume.get("size")
    if isinstance(size, bool) or not isinstance(size, (int, float)) or int(size) <= 0:
        raise RuntimeError(f"RunPod network volume {name_or_id!r} has no valid size: {volume!r}")
    return volume


def _handle(
    *,
    pod: Any,
    ssh: dict[str, Any],
    config: RunPodConfig,
    volume: dict[str, Any],
    claimed_at: str,
) -> dict[str, Any]:
    selected_gpu = getattr(pod, "_gpu_type", None) or config.gpu_type
    selected_storage = getattr(pod, "_storage_name", None) or config.storage_name
    return {
        "schema_version": "astrid.runpod.claim.v1",
        "pod_id": str(pod.id),
        "name": str(pod.name),
        "ssh": f"root@{ssh['ip']} -p {ssh['port']}",
        "claimed_at": claimed_at,
        "gpu_type": selected_gpu,
        "storage_name": selected_storage,
        "network_volume_id": getattr(pod, "_storage_volume", None) or volume.get("id"),
        "network_volume_size_gb": int(volume["size"]),
        "container_disk_gb": config.container_disk_gb,
        "volume_mount_path": config.volume_mount_path,
        "allowed_cuda_versions": list(config.allowed_cuda_versions),
        "name_prefix": config.name_prefix,
    }


async def _claim(args: argparse.Namespace) -> dict[str, Any]:
    # RunPodConfig.from_env() is the shared Astrid credential/config boundary;
    # explicit values below prevent ambient GPU/storage fallbacks from changing
    # the request this waiter is intended to claim.
    config = RunPodConfig.from_env(
        gpu_type=args.gpu_type,
        storage_name=args.storage_name,
        storage_volumes=(args.storage_name,),
        container_disk_gb=args.container_disk_gb,
        min_memory_gb=args.min_memory_gb,
        name_prefix=args.name_prefix,
    )
    volume = await _require_existing_volume(config, args.storage_name)
    # The lifecycle substrate uses disk_size_gb as the desired network-volume
    # size when checking an attached volume.  Pin it to what exists so this
    # script never expands or shrinks the persistent backup volume.
    config = config.merge(disk_size_gb=int(volume["size"]))
    _log(
        f"watching gpu={args.gpu_type!r} storage={args.storage_name!r} "
        f"volume_id={volume.get('id')!r} volume_size_gb={int(volume['size'])} "
        f"container_disk_gb={args.container_disk_gb} poll_seconds={args.poll_seconds}"
    )

    deadline = (
        time.monotonic() + args.max_wait_seconds
        if args.max_wait_seconds > 0
        else None
    )

    while True:
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"capacity did not appear within {args.max_wait_seconds}s")
            window = min(args.capacity_window_seconds, max(1, int(remaining)))
        else:
            window = args.capacity_window_seconds

        _log(f"starting capacity window={window}s")
        pod = None
        claimed = False
        readiness_error: Exception | None = None
        try:
            pod = await launch_when_available(
                config,
                max_wait_sec=window,
                retry_interval_sec=args.poll_seconds,
            )
            # launch_when_available returns immediately after RunPod allocates
            # the pod.  Do not report success until the canonical readiness
            # check and SSH metadata lookup both pass.
            await pod.wait_ready(timeout=args.ready_timeout_seconds)
            ssh = await pod._ensure_ssh_details()
            result = _handle(
                pod=pod,
                ssh=ssh,
                config=config,
                volume=volume,
                claimed_at=_utc_now(),
            )
            if args.handle_path:
                result["handle_path"] = str(Path(args.handle_path).expanduser())
                _write_json(Path(args.handle_path), result)
            claimed = True
            return result
        except LaunchFailure as exc:
            if pod is None:
                # launch_when_available has already exhausted this bounded
                # window; start another one until the caller's optional
                # overall deadline.
                _log(f"capacity window exhausted: {exc}")
            else:
                # A terminal/readiness failure after allocation is not a
                # capacity miss.  Let the cleanup-and-backoff path handle it.
                readiness_error = exc
        except Exception as exc:
            if pod is None:
                # Preflight/auth/config/provider errors before a pod was
                # allocated are actionable and should not be hidden by a loop.
                raise
            readiness_error = exc
        finally:
            # A pod may have been allocated before readiness failed or the
            # process was interrupted.  Clean up that exact pod before retrying
            # so the waiter cannot leak paid instances.
            if pod is not None and not claimed:
                try:
                    await pod.terminate()
                except Exception as cleanup_exc:
                    raise RuntimeError(
                        f"failed to clean up allocated pod {pod.id}: {cleanup_exc}"
                    ) from cleanup_exc
        if readiness_error is not None:
            _log(
                f"allocated pod {pod.id} failed readiness: "
                f"{type(readiness_error).__name__}: {readiness_error}"
            )
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        f"capacity did not appear within {args.max_wait_seconds}s"
                    ) from readiness_error
                await asyncio.sleep(min(args.poll_seconds, remaining))
            else:
                await asyncio.sleep(args.poll_seconds)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpu-type", default=DEFAULT_GPU)
    parser.add_argument("--storage-name", default=DEFAULT_STORAGE)
    parser.add_argument("--container-disk-gb", type=int, default=DEFAULT_CONTAINER_DISK_GB)
    parser.add_argument("--min-memory-gb", type=int, default=32)
    parser.add_argument("--poll-seconds", type=int, default=DEFAULT_POLL_SECONDS)
    parser.add_argument(
        "--capacity-window-seconds",
        type=int,
        default=DEFAULT_CAPACITY_WINDOW_SECONDS,
        help="Bound each launch_when_available call; the outer waiter starts another window.",
    )
    parser.add_argument(
        "--max-wait-seconds",
        type=int,
        default=0,
        help="Overall limit; 0 waits indefinitely (default).",
    )
    parser.add_argument("--ready-timeout-seconds", type=int, default=DEFAULT_READY_TIMEOUT_SECONDS)
    parser.add_argument("--name-prefix", default="astrid-claim-5090-backup")
    parser.add_argument("--handle-path", help="Optional path for the secret-free pod handle JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    for name in (
        "container_disk_gb",
        "min_memory_gb",
        "poll_seconds",
        "capacity_window_seconds",
        "ready_timeout_seconds",
    ):
        if getattr(args, name) <= 0:
            raise SystemExit(f"--{name.replace('_', '-')} must be positive")
    if args.max_wait_seconds < 0:
        raise SystemExit("--max-wait-seconds must be zero or positive")

    try:
        result = asyncio.run(_claim(args))
    except KeyboardInterrupt:
        _log("interrupted before a pod was claimed")
        return 130
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
