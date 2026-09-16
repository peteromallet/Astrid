# Get help

Start in the Python environment you installed Astrid into.

```bash
python3 -m astrid doctor --json
banodoco-local doctor --json
```

## Command or module not found

Activate `.venv` from your installation folder. If the launcher script is missing from `PATH`, try the installed module:

```bash
python3 -m banodoco_local up --profile astrid
```

## Source profile missing

Complete [Connect Runtime](README.md#2-connect-runtime-once). The manifest must use absolute paths to the actual checkouts. Avoid symlinked installation folders. If the manifest already exists, inspect its paths instead of overwriting it.

## Runtime cannot connect

Run `banodoco-local up --profile astrid` and read the reported error. Check that the source folders and environment still exist. Do not delete workspace state or credentials to force a fresh start.

## A tool needs a key or dependency

Read that pack’s skill and configure the executing environment. A healthy Runtime connection does not mean every optional tool is ready. See [Credentials](credentials.md).

## A run failed

```bash
python3 -m astrid runs show <run-id> --project <project> --json --evidence
python3 -m astrid runs events <run-id> --project <project> --json
```

Replace the bracketed values with your run and project. Correct the reported cause before retrying. For rendering issues, continue with the [renderer guide](../guides/debugging.md).

[Back to setup](README.md)
