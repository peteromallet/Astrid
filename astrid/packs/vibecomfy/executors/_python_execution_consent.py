"""Explicit task consent for VibeComfy operations that load canonical Python."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

CONSENT_INPUT = "python_execution_consent"
CONFIRMED_VALUE = "confirmed"


class PythonExecutionConsentError(ValueError):
    """The task did not explicitly consent to loading canonical workflow Python."""


def validate_python_execution_consent(value: str | None, *, required: bool = True) -> bool:
    """Validate the single supported consent token, without inferring consent."""
    if value == CONFIRMED_VALUE:
        return True
    if not required and value in (None, ""):
        return False
    raise PythonExecutionConsentError(
        f"{CONSENT_INPUT} must be exactly {CONFIRMED_VALUE!r} to load canonical workflow Python"
    )


@contextmanager
def confirmed_python_execution_scope(value: str | None) -> Iterator[Any]:
    """Map explicit consent to VibeComfy's audited non-interactive ``--yes`` gate."""
    validate_python_execution_consent(value)
    from vibecomfy.security import GateContext, set_gate_context

    gate = GateContext(non_interactive=True, assume_yes=True)
    token = set_gate_context(gate)
    try:
        yield gate
    finally:
        token.var.reset(token)
