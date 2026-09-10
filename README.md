# Astrid

A Python SDK for building and running open-source agentic UXes — a harness for agents and humans to make art.

**Give this to your agent to get started:**

<div align="center">

<pre>
╭──────────────────────────── ◇ ─────────────────────────────╮
│                                                            │
│                   A   S   T   R   I   D                    │
│                                                            │
│              agents harnessed, humans free —               │
│               open tools for what could be:                │
│              moving image, voice, and frame,               │
│            clone it, run it, stake your claim.             │
│                                                            │
│                          ·  ·  ·                           │
│                                                            │
│       <em>$ git clone https://github.com/banodoco/Astrid</em>       │
│              <em>$ cd Astrid &amp;&amp; pip install -e .</em>               │
│                 <em>$ python3 -m astrid --help</em>                 │
│                                                            │
│                          ·  ·  ·                           │
│                                                            │
│                 ask the maker what to do,                  │
│             runs/ holds all it makes for you —             │
│              no map, no plan, no perfect day:              │
│         begin, hold fast  — you'll find your way.          │
│                                                            │
╰──────────────────────────── ◇ ─────────────────────────────╯
</pre>

</div>

Astrid's product CLI and Python SDK are clients of the Banodoco workspace
runtime. Until its certified wheel is published, install the pinned runtime
source with:

```bash
python3 -m pip install 'banodoco-workspace-runtime @ git+https://github.com/banodoco/banodoco-workspace-runtime.git@afccb430e2a983c968b6a8a96fd630ba3a6262fc'
```

Configure it once with `banodoco-local up --profile astrid`, then use
the generated-client-backed `python3 -m astrid` gateway or `import astrid`.
The runtime owns projects, media, timelines, tasks, runs, receipts, and event
history; Astrid does not use a checkout-local project database as live
authority. See [Getting Started](docs/getting-started.md).

## Unified execution boundary

For generation work, the canonical sequence is Reigh UI producer → Runtime
admission with typed family, project, CAS/input references, and idempotency →
Worker `GenericPackHost` execution → Runtime-owned settlement and receipts →
CAS/gallery/timeline readback. Runtime is the authority for task/run identity,
provenance, and publication. The retired Reigh `create-task` endpoint and
legacy timeline-agent task tools are not alternate Astrid admission paths.

The current acceptance evidence is CPU-bound and does not claim GPU, model, or
provider availability.

## License

Open Source Native License (OSNL) v0.2 — see [`LICENSE`](LICENSE).
