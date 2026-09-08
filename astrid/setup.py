"""Provision validated external packs and reconcile their skill view."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from astrid.core.pack.source_setup import declarations_from_json, provision


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m astrid.setup")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--disable-pack")
    parser.add_argument("--restore-pack")
    parser.add_argument("--declarations", type=Path)
    parser.add_argument("--deep", action="store_true")
    args = parser.parse_args(argv)
    try:
        source = provision(
            declarations_from_json(args.declarations),
            offline=args.offline,
            check=args.check,
            disable_pack=args.disable_pack,
            restore_pack=args.restore_pack,
        )
        from astrid.skills import sync

        skills = sync(deep=args.deep, dry_run=args.check)
        result = {"ok": bool(source.get("ok", False)), "source": source, "skills": skills}
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result["ok"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
