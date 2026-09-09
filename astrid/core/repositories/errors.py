"""Compatibility surface for shared semantic repository contracts.

The concrete contracts live in :mod:`astrid.core.contracts.repository` so
the event and repository packages depend on a neutral lower layer instead of
on each other. This module preserves the established repository import path.
"""

from astrid.core.contracts.repository import (
    ACTOR_KINDS,
    CommandVocabularyError,
    EventVocabularyError,
    RepositoryError,
    StreamAgreementError,
    StreamVocabularyError,
)

__all__ = [
    "ACTOR_KINDS",
    "CommandVocabularyError",
    "EventVocabularyError",
    "RepositoryError",
    "StreamAgreementError",
    "StreamVocabularyError",
]
