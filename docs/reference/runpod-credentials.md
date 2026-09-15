# RunPod credentials

Astrid, `runpod-lifecycle`, and VibeComfy read the same local RunPod key:
`RUNPOD_API_KEY` in `~/.astrid/astrid.env`. Override the file path with
`ASTRID_ENV_FILE`; absolute paths are used directly, while relative paths are
resolved under Astrid's state home. Otherwise the path follows
`$ASTRID_HOME/astrid.env` or defaults to `~/.astrid/astrid.env`.

The local shared file takes precedence over a stale process value. The
standalone RunPod lifecycle loader also ignores `RUNPOD_API_KEY` in a
project-local `.env`, while continuing to read non-secret RunPod settings
there. On CI, containers, and deployed services, inject the key through that
environment's secret manager when the shared file has no nonempty
`RUNPOD_API_KEY`. If both sources define it, `astrid.env` takes precedence
over the injected process value. Compute profiles store the variable
reference, never the key itself.

## Store or replace the local key

Use the hidden prompt; do not paste the key into chat, shell history, or a
command argument:

```bash
astrid-credential set runpod
```

Astrid writes the value to the shared file with owner-only permissions and
preserves other entries. If the command is not installed in the current
checkout, run it through the Astrid Python environment:

```bash
uv run python -m astrid.core.util.credential_store set runpod
```

The setter changes only the selected shared credential file; it does not
migrate or delete old credential files or project data. After the replacement
has been validated, remove only obsolete `RUNPOD_API_KEY` assignments from old
files if needed, preserving all unrelated settings and data.

## Validation and recovery

Astrid callers resolve the key through `CredentialsScope`. For an external
process that expects an environment variable, use the same resolver through
its wrapper:

```bash
astrid-with-credential --provider runpod -- runpod-lifecycle list --json
```

A read-only `GET /v1/pods` check verifies authentication for that request
without creating or changing a pod; it does not establish that a later pod
launch will succeed. HTTP 401 means the selected key was rejected; it does not
point to a GPU choice or workflow problem. Check which source was selected in
Astrid's safe diagnostics, replace the shared value through the hidden prompt,
and validate again. Never fall through to another stale file after a rejection.

RunPod keys, SSH identities, and provider tokens must not be written to a
compute profile, timeline, workflow, or rendered artifact. For the general
source policy, see [Credential strategy](credentials.md).
