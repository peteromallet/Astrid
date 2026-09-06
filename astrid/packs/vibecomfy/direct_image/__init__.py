"""Typed direct image capabilities for the VibeComfy pack.

This package is deliberately disjoint from the generic ``vibecomfy.run``
escape hatch.  It owns image-family request compilation, template attestation,
and result semantics; shared engine lifecycle remains in the Vibe backend.
"""

from .compiler import (
    CANONICAL_CAPABILITIES,
    PROFILE_CONFIGS,
    CompiledImageRequest,
    ImageCompileError,
    ImageRequest,
    compile_image_request,
    normalize_capability_id,
    portable_execution_digest,
)
from .executor import DirectImageExecutor, ImageExecutionError, ImageResult

__all__ = [
    "CANONICAL_CAPABILITIES",
    "PROFILE_CONFIGS",
    "CompiledImageRequest",
    "DirectImageExecutor",
    "ImageCompileError",
    "ImageExecutionError",
    "ImageRequest",
    "ImageResult",
    "compile_image_request",
    "normalize_capability_id",
    "portable_execution_digest",
]
