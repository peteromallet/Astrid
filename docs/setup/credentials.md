# Credentials

Configure only what your work needs.

## Your workspace

The launcher creates the workspace connection credentials automatically. Keep them separate from creative-provider API keys and let the launcher manage them.

For a source checkout, `config/astrid-runtime.json` selects `Astrid/.astrid-data` as the default Runtime support root; a wheel installation uses `~/.astrid-data`. An explicit `BANODOCO_LOCAL_DATA_ROOT` or launcher `--data-root` overrides this location. The support root contains the launcher catalog, credentials, and Runtime realm. See [Getting Started](../getting-started.md) for details.

`BANODOCO_LOCAL_SOURCE_MANIFEST` selects an explicit source-profile file when needed. `BANODOCO_RUNTIME_CREDENTIAL` identifies a Runtime credential file for connection paths that use that override. Normal launcher setup supplies its connection information automatically.

## Creative providers

The selected pack tells you which service it needs and where its executing process reads the key. Common names include:

| Service | Environment variable |
| --- | --- |
| OpenAI | `OPENAI_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY` |
| Gemini | `GEMINI_API_KEY` |
| fal | `FAL_KEY` |
| WaveSpeed | `WAVESPEED_API_KEY` |
| RunPod | `RUNPOD_API_KEY` |
| Replicate | `REPLICATE_API_TOKEN` |
| Hugging Face | `HF_TOKEN` |

Enter secrets locally through the selected integration’s configuration. Keep them out of chat and source control. A key in your interactive shell is not proof that an already-running worker can see it; follow the pack’s execution setup.

## Store a provider key once

Use the hidden local prompt for the provider you need:

```bash
astrid-credential set runpod
astrid-credential set openai
```

The command updates that key in `~/.astrid/astrid.env`, preserves other settings, and applies owner-only permissions. This file belongs to your login on this computer and is shared across local Astrid projects and checkouts. Do not commit it or copy it to another computer.

Local credential resolution checks an explicit value, then the shared Astrid credential file, then the process environment, and finally an explicitly named fallback environment file. It does not search arbitrary folders for `.env` files. See the maintained [Credential strategy](../reference/credentials.md) for supported providers, `ASTRID_ENV_FILE` and `ASTRID_HOME` overrides, and other execution environments.

[Back to setup](README.md)
