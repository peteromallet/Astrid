# Credential strategy

Astrid uses one file on this computer, under your login, as the local source of
truth for scalar API keys: `~/.astrid/astrid.env`. Astrid and its
RunPod/VibeComfy tools use the same path and dotenv syntax. The file has
owner-only permissions (`0600`); it is not a project asset and must never be
committed or copied to another computer or login.

Set `ASTRID_ENV_FILE` to use a mounted or non-default file. Absolute paths are
used directly; relative paths are resolved under Astrid's state home so tools
launched from different working directories still find the same file.
Otherwise Astrid uses `$ASTRID_HOME/astrid.env` when `ASTRID_HOME` is set, or
`~/.astrid/astrid.env` by default. `ASTRID_HOME` itself defaults to `~/.astrid`.

## Set a key

Run the hidden prompt once for each provider:

```bash
astrid-credential set runpod
astrid-credential set openai
astrid-credential set huggingface
```

The command updates only that key, preserves other settings, and reports the
file it wrote. It does not prove that the key authenticates successfully; use
the provider's read-only validation step after saving it.

For a profile-specific or app-specific secret, pass its uppercase environment
variable name instead, such as `astrid-credential set HUGGING_FACE_HUB_TOKEN`.
For environment-based tools, `astrid-with-credential` resolves the same shared
file and passes the value only to the child process. For example:

```bash
astrid-with-credential --provider runpod -- runpod-lifecycle list --json
```

Profiles and project configuration store the variable name, never the
credential value.

## Resolution

For local Astrid commands, use `CredentialsScope.get_local()` or
`CredentialsScope.resolve_local()`. All local API-key integrations use the same
order:

1. A credential explicitly supplied for the operation.
2. The matching variable in the shared `astrid.env` file.
3. The process environment, for CI, containers, and deployed services.
4. An explicitly named fallback env file when a command supports one.

The shared file wins over a stale shell or project copy. Astrid does not scan
arbitrary repositories or working directories for credential files.
`resolve_local()` returns safe source metadata (`explicit`, `astrid_env_file`,
`environment`, or `env_file`) and may log the provider and source at debug
level; it never logs the credential value. A rejected credential is reported
rather than silently replaced with another candidate.

The registered API-key references are:

| Provider | Setter name | Variable |
|---|---|---|
| fal.ai | `fal` | `FAL_KEY` |
| WaveSpeed | `wavespeed` | `WAVESPEED_API_KEY` |
| OpenAI | `openai` | `OPENAI_API_KEY` |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` |
| DeepSeek | `deepseek` | `DEEPSEEK_API_KEY` |
| Fireworks | `fireworks` | `FIREWORKS_API_KEY` |
| Gemini | `gemini` | `GEMINI_API_KEY` |
| GIPHY | `giphy` | `GIPHY_API_KEY` |
| Hugging Face | `huggingface` | `HF_TOKEN` |
| RunPod | `runpod` | `RUNPOD_API_KEY` |

The setter never puts the value in command history or output. It writes
atomically, removes duplicate assignments for that key, and applies owner-only
file permissions. Credentials are stored as literal values; `${...}` is not
expanded.

## Other execution environments

CI jobs, containers, and deployed services should receive credentials from the
secret manager belonging to that environment through process variables or
explicit SDK arguments. Those environments do not depend on a developer's
local file. RunPod API keys belong on the host controller; pass a separate
worker-scoped token only when the remote workload needs it.

This file handles scalar API credentials. SSH private keys remain protected
files addressed by path, and OAuth credentials should use the provider's own
flow. Do not use macOS Keychain as a second local source for Astrid API keys.

For RunPod-specific validation and migration instructions, see [RunPod
credentials](runpod-credentials.md). Do not delete project data or unrelated
settings while moving credentials; remove only old duplicate assignments
after the shared value is validated.
