# North Star — one GPU execution path

Every supported Wan2GP and VibeComfy task, regardless of whether it originates
in Astrid or Reigh, enters one neutral Banodoco Workspace Runtime task
lifecycle and is executed by Astrid's typed pack through `GenericPackHost` on
the Reigh Worker GPU substrate.

The runtime alone owns durable task truth, leases, retries, events, artifact
publication, and settlement. Astrid packs alone own capability schemas,
engine-specific request compilation, template selection, result semantics, and
execution identity. Reigh Worker owns only pinned GPU environments, verified
model roots, hardware/readiness telemetry, process prerequisites, and the thin
launcher for the sole host.

Aligned progress makes the system smaller: each migrated route deletes its old
router, selector, database writer, queue consumer, and fallback in the same
merge train. Warm models are an optional performance policy; losing warmth can
never change task meaning or recovery.

Avoid hollow success: no dual authorities, compatibility shims, hidden
fallbacks, Worker plugin registry, engine-specific Worker routing, Supabase
task lifecycle, direct task-table mutation, fake “GPU” proof, or passing tests
that do not exercise the supported launch path.
