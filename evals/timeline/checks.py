"""Small, model-agnostic semantic checkers for timeline evaluation artifacts.

The visible task brief and this module's hidden expectations are deliberately
separate.  Check functions consume plain JSON-shaped mappings so the evaluator
does not need Astrid Runtime or a particular agent adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Protocol

Json = Mapping[str, Any]


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    status: str
    message: str
    evidence: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return self.status == "pass"


class DecodedMediaVerifier(Protocol):
    """Optional adapter for independent decoded-frame/audio verification."""

    def verify(self, check: Json, artifacts: Mapping[str, Any]) -> CheckResult: ...


def _path(value: Any, path: str) -> Any:
    """Resolve a conservative dotted path with optional numeric list indexes."""
    current = value
    if not path:
        return current
    for part in path.split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        elif isinstance(current, (list, tuple)) and part.isdigit():
            index = int(part)
            if index >= len(current):
                raise KeyError(path)
            current = current[index]
        else:
            raise KeyError(path)
    return current


def _artifact(artifacts: Mapping[str, Any], name: str) -> Any:
    if name not in artifacts:
        raise KeyError(f"missing artifact: {name}")
    return artifacts[name]


def check_path_equals(check: Json, artifacts: Mapping[str, Any]) -> CheckResult:
    """Assert one artifact path equals its hidden expected value."""
    cid = str(check.get("id", "path_equals"))
    artifact_name = str(check.get("artifact", "after"))
    path = str(check.get("path", ""))
    try:
        actual = _path(_artifact(artifacts, artifact_name), path)
    except KeyError as exc:
        return CheckResult(cid, "fail", str(exc), (artifact_name, path))
    passed = actual == check.get("expected")
    return CheckResult(cid, "pass" if passed else "fail",
                       "value matches expected" if passed else "value differs from expected",
                       (f"{artifact_name}:{path}",))


def check_paths_unchanged(check: Json, artifacts: Mapping[str, Any]) -> CheckResult:
    """Assert listed paths have identical values in before and after snapshots."""
    cid = str(check.get("id", "paths_unchanged"))
    try:
        before, after = _artifact(artifacts, "before"), _artifact(artifacts, "after")
        changed = [str(path) for path in check.get("paths", ())
                   if _path(before, str(path)) != _path(after, str(path))]
    except KeyError as exc:
        return CheckResult(cid, "fail", str(exc), ("before.json", "after.json"))
    return CheckResult(cid, "fail" if changed else "pass",
                       "protected values changed: " + ", ".join(changed) if changed
                       else "protected values are unchanged",
                       tuple(changed) if changed else tuple(str(x) for x in check.get("paths", ())))


def check_order(check: Json, artifacts: Mapping[str, Any]) -> CheckResult:
    """Check exact order, including deterministic ID tie-breaking when requested."""
    cid = str(check.get("id", "order"))
    name = str(check.get("artifact", "after"))
    try:
        values = _path(_artifact(artifacts, name), str(check.get("path", "")))
    except KeyError as exc:
        return CheckResult(cid, "fail", str(exc), (name, str(check.get("path", ""))))
    if not isinstance(values, list):
        return CheckResult(cid, "fail", "ordered value is not a list", (name,))
    key = str(check.get("id_path", "id"))
    actual_ids = [_path(item, key) for item in values]
    expected_ids = list(check.get("expected_ids", ()))
    # If expected_ids is supplied it is the fixture's independently prepared
    # oracle.  Otherwise validate ascending key order for equal sort values.
    if expected_ids:
        passed = actual_ids == expected_ids
    else:
        sort_path = str(check.get("sort_path", "brightness"))
        pairs = [(_path(item, sort_path), _path(item, key)) for item in values]
        passed = pairs == sorted(pairs)
    return CheckResult(cid, "pass" if passed else "fail",
                       "ordering matches fixture policy" if passed else "ordering violates fixture policy",
                       (f"{name}:{check.get('path', '')}",))


def check_identity_disjoint(check: Json, artifacts: Mapping[str, Any]) -> CheckResult:
    """Ensure duplicated entities have independent identities and references."""
    cid = str(check.get("id", "identity_disjoint"))
    try:
        before = _artifact(artifacts, str(check.get("before_artifact", "before")))
        after = _artifact(artifacts, str(check.get("after_artifact", "after")))
        original = set(_path(before, str(check.get("original_ids_path", "identity_ids"))))
        duplicate = set(_path(after, str(check.get("duplicate_ids_path", "duplicate.identity_ids"))))
    except KeyError as exc:
        return CheckResult(cid, "fail", str(exc), ("before.json", "after.json"))
    overlap = sorted(original & duplicate)
    passed = bool(duplicate) and not overlap
    return CheckResult(cid, "pass" if passed else "fail",
                       "duplicate identities are independent" if passed
                       else f"duplicate shares identities: {overlap or 'no duplicate identities found'}",
                       tuple(overlap))


def check_panel_coverage(check: Json, artifacts: Mapping[str, Any]) -> CheckResult:
    """Check required panel labels exist and have positive, in-bounds rectangles."""
    cid = str(check.get("id", "panel_coverage"))
    name = str(check.get("artifact", "after"))
    try:
        panels = _path(_artifact(artifacts, name), str(check.get("path", "panels")))
    except KeyError as exc:
        return CheckResult(cid, "fail", str(exc), (name, str(check.get("path", "panels"))))
    if not isinstance(panels, list):
        return CheckResult(cid, "fail", "panels value is not a list", (name,))
    label_path = str(check.get("label_path", "quadrant"))
    required = set(check.get("required", ("top_left", "top_right", "bottom_left", "bottom_right")))
    found: set[str] = set()
    invalid: list[str] = []
    rects: list[tuple[float, float, float, float, str]] = []
    width, height = float(check.get("width", 1)), float(check.get("height", 1))
    for panel in panels:
        try:
            label = str(_path(panel, label_path))
            rect = _path(panel, str(check.get("rect_path", "rect")))
            x, y, w, h = (float(rect[k]) for k in ("x", "y", "width", "height"))
            if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > width or y + h > height:
                invalid.append(label)
            rects.append((x, y, w, h, label))
            found.add(label)
        except (KeyError, TypeError, ValueError):
            invalid.append("malformed")
    missing = sorted(required - found)
    # In-bounds rectangles whose areas sum to the canvas area and do not
    # overlap cover the complete canvas (including corners and edges).
    overlap = []
    for index, (x, y, w, h, label) in enumerate(rects):
        for ox, oy, ow, oh, other in rects[index + 1:]:
            if min(x + w, ox + ow) > max(x, ox) and min(y + h, oy + oh) > max(y, oy):
                overlap.append(f"{label}/{other}")
    area = sum(w * h for _, _, w, h, _ in rects)
    full_area = abs(area - width * height) <= float(check.get("area_tolerance", 1e-9))
    passed = not missing and not invalid
    passed = passed and not overlap and full_area
    return CheckResult(cid, "pass" if passed else "fail",
                       "all required panels are present and in bounds" if passed
                       else f"missing panels={missing}; invalid panels={invalid}; overlap={overlap}; full_area={full_area}",
                       tuple(missing + invalid + overlap))


def check_decoded_media(check: Json, artifacts: Mapping[str, Any],
                        verifier: DecodedMediaVerifier | None = None) -> CheckResult:
    """Delegate independent decoded pixels/audio checks or report capability gap."""
    cid = str(check.get("id", "decoded_media"))
    if verifier is None:
        return CheckResult(cid, "missing_capability",
                           "no decoded-media verifier was supplied; render bytes were not inspected")
    try:
        return verifier.verify(check, artifacts)
    except (FileNotFoundError, NotImplementedError) as exc:
        return CheckResult(cid, "missing_capability", str(exc) or "decoded-media capability unavailable")
    except Exception as exc:  # noqa: BLE001 - third-party adapters have no shared exception type.
        return CheckResult(cid, "fail", f"decoded-media verifier failed: {type(exc).__name__}: {exc}")


Checker = Callable[[Json, Mapping[str, Any]], CheckResult]
CHECKS: dict[str, Checker] = {
    "path_equals": check_path_equals,
    "paths_unchanged": check_paths_unchanged,
    "order": check_order,
    "identity_disjoint": check_identity_disjoint,
    "panel_coverage": check_panel_coverage,
}


def run_checks(checks: Iterable[Json], artifacts: Mapping[str, Any],
               verifier: DecodedMediaVerifier | None = None) -> list[CheckResult]:
    results = []
    for check in checks:
        check_type = str(check.get("check", ""))
        if check_type == "decoded_media":
            results.append(check_decoded_media(check, artifacts, verifier))
        elif check_type in CHECKS:
            results.append(CHECKS[check_type](check, artifacts))
        else:
            results.append(CheckResult(str(check.get("id", "unknown_check")),
                                       "missing_capability",
                                       f"unknown checker {check_type!r}"))
    return results
