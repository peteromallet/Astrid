"""Run the skills installer as ``python -m astrid.skills``."""

from .cli import main


if __name__ == "__main__":  # pragma: no cover - exercised by the CLI smoke
    raise SystemExit(main())

