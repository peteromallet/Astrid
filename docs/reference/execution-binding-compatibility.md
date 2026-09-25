# Targeted execution-binding compatibility

Astrid accepts an `execution_request` target only when the Runtime handshake
advertises `execution_binding.targeted.v1`.

The available `workspace.v1` Runtime is incompatible with targeted admission:
its handshake has no capability advertisement, `POST /v1/tasks` has no
first-class target or binding field, and `POST /v1/tasks/claim` claims from a
capability-wide queue without a target/binding match. Carrying a target inside
the task `spec` would therefore be metadata, not scheduler enforcement, and
could run on the wrong machine, pod, provider account, runtime epoch, or
lease fence. Astrid rejects the request before calling `admit_task` and never
queues a bare target or accepts caller-supplied `execution_binding`.

A coordinated Runtime release must add the capability advertisement,
Runtime-issued binding at targeted claim time, binding checks on claim and
settlement, and regenerated clients before this gate can be opened.
