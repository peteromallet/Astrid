# Managed generation result v1

`managed-generation-result.v1` is Astrid's engine- and location-neutral strict
profile of the universal `manifest.json` result contract. The implementation is
[`astrid.core.contracts.managed_generation_result`](../../astrid/core/contracts/managed_generation_result.py).

## Wire shape

The profile retains the universal fields `schema_version`, `kind`, `inputs`,
`outputs`, `created`, and `warnings`, and adds:

- `task_id`, `attempt_id`, and `producer_run_id` for correlation;
- `outputs[]` rows with `producer_output_id`, `output_port`, `ordinal`, a
  staging-relative `path`, `media_type`, exact `bytes`, and a bare lowercase
  64-character `sha256` digest;
- `outcomes.execution`, `.retrieval`, `.verification`, and `.publication`,
  each with a lifecycle `status` and optional `code`/`message`;
- `evidence.producer` and `evidence.transport`, kept as opaque namespaced
  objects. Engine-native evidence is not copied into neutral output fields.

`kind` is `managed-generation-result.v1` and `schema_version` is `1`. The
output list is ordered; `producer_output_id` is required and unique, while
`ordinal` is required and unique. Output bytes are independently checked by
Astrid's universal result-manifest containment, size, and SHA-256 validators.

## Phase rules

Execution must be terminal. A successful execution requires at least one
output. Retrieval cannot succeed after a failed execution; verification can
only leave `not_started` after retrieval has succeeded; publication can only
leave `not_started` after verification has succeeded. Publication is never
inferred from a verified result. When the producer and server share a
filesystem, the producer establishes custody under its run root before
emitting the envelope; Astrid still rebases and verifies those bytes before
publication.

Use `validate_managed_generation_result` or
`ManagedGenerationResult.from_json` with the assigned staging root and,
where available, expected task and attempt IDs. `GenerationResult` remains an
SDK projection and is not this wire contract.
