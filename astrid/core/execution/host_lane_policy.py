"""Bounded lane policy for Astrid's canonical generic pack host."""

from __future__ import annotations

from typing import Any


CANONICAL_PACK_HOST_MAX_CONCURRENCY = 2
CANONICAL_PACK_HOST_LANE_POLICY_ID = "astrid-pack-host-orchestration-executor-v1"


def canonical_pack_host_capacity() -> dict[str, Any]:
    """Return the immutable-by-convention two-lane readiness contract."""
    return {
        "max_concurrency": CANONICAL_PACK_HOST_MAX_CONCURRENCY,
        "lane_policy_id": CANONICAL_PACK_HOST_LANE_POLICY_ID,
        "lanes": {
            "orchestration": {
                "slots": 1,
                "reservation_key": "astrid-orchestration",
            },
            "executor": {
                "slots": 1,
                "reservation_key": "capability-defined",
            },
        },
    }


def effective_host_capacity(
    max_concurrency: int,
    *,
    parallel_lanes_enabled: bool,
    resource_keys: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    """Describe actual host capacity without inferring it from repr strings."""
    keys = sorted({str(key) for key in resource_keys if isinstance(key, str)})
    if (
        max_concurrency == CANONICAL_PACK_HOST_MAX_CONCURRENCY
        and parallel_lanes_enabled
    ):
        value = canonical_pack_host_capacity()
        value["registered_resource_keys"] = keys
        return value
    return {
        "max_concurrency": int(max_concurrency),
        "lane_policy_id": "astrid-pack-host-serial-v1",
        "lanes": {"executor": {"slots": 1, "reservation_key": "capability-defined"}},
        "registered_resource_keys": keys,
    }
