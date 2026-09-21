# RunPod practical-path review — 2026-09-21

## Verdict

The standalone lifecycle path solves reuse/upload/script execution/result
collection/leave-running today: verified live on the user's existing pod.
It does not prove H3 readiness or create Astrid managed task/output history.
The Astrid runpod.exec wrapper exists but was not live-verified in this review;
its handle, environment and network-boundary prerequisites remain unresolved.
No remote generic-worker scheduler implementation is necessary for the basic job.

This was a direct source review and practical test, not a separate Astra agent
review; no Astra delegation tool was available in this session.

## Source findings

- runpod-lifecycle discovery.get_pod attaches by exact ID. Existing-pod runner
  mode skips launch and volume placement; storage_name does not verify attachment.
- CLI run uses the script parent as local_root. --keep-pod passes
  terminate_after_exec=False to ship_and_run_detached. Fixed out/output directories
  are downloaded to local_root/artifacts.
- Timeout returns 124 without killing remote work in keep-pod mode. Temporary
  script/log/marker/archive paths are shared across jobs. Use one job at a time.
- Tarball upload deletes/replaces remote_root; use a fresh isolated destination.
- --json emits progress lines before the final object. Artifact download errors
  can leave returncode=0; verify files and hashes separately.
- Astrid exec reads handle.config_snapshot.api_key_ref and hourly_rate. The
  existing astrid.runpod.claim.v1 handle lacks these fields. Native environment
  and SSH/broker compatibility must also be verified before execution.
- The checked Astrid .venv cannot import runpod_lifecycle, although the standalone
  installed CLI imports the sibling lifecycle checkout. A dedicated executor
  environment may differ; no native runtime execution was attempted.

## Bounded live proof

Command:

```text
runpod-lifecycle run 8f18jbuh81vko9 \
  --script /tmp/astrid-runpod-review.GQlIxl/run.sh \
  --remote-root /workspace/astrid-runpod-review-GQlIxl \
  --upload-mode sftp_walk --timeout 60 --keep-pod --json
```

The two-file payload was a challenge text and a script. The entire script body
ran under timeout --kill-after=2s 15s. It wrote a challenge checksum, GPU identity,
mount observation and success marker into out/. No inference was queued.
A precheck found no active lifecycle remote-run script before starting.

Observed final result: returncode=0, terminated=false,
artifact_root=/private/tmp/astrid-runpod-review.GQlIxl/artifacts.

- Result marker: astrid-runpod-review-GQlIxl:ok.
- Local input SHA-256 and returned remote checksum both:
  430d15ee1234dabcdf9ed18d3d30436388a7d01e99723c6b1d238022d3332776.
- GPU: NVIDIA GeForce RTX 5090; driver 570.211.01.
- Mount observation: /workspace, filesystem type fuse.
- Direct provider GET after execution: ID 8f18jbuh81vko9, desiredStatus RUNNING,
  networkVolumeId sfak8553dy, volumeMountPath /workspace, containerDiskInGb 200.
- Separate volume inventory: sfak8553dy is backup, size 250 GB, EUR-IS-1.

The small remote test directory and local downloaded diagnostics were retained.
These are diagnostic files, not Astrid-managed generated assets. The pod was
neither created nor terminated; no shared model/release directory was changed.

## H3 readiness is not established

The provider image is runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04.
The candidate executable exists at
/workspace/h3-golden/releases/h3-cu130-v1-candidate/runtime/venv/bin/python,
but a separate 20-second-bounded import torch probe exited 1 with
ModuleNotFoundError: No module named 'torch'. No model downloads, environment
repair, H3 inference or continuation test was performed.

## Documentation decisions

- The operator guide now leads with lifecycle run --keep-pod and states the
  exact distinction from native runpod.exec and remote vibecomfy.run scheduling.
- The lifecycle guide retains H3 compatibility gates, marks remote-worker
  scheduling as incomplete, and corrects stale CUDA placement-flag claims.
- The RunPod pack skill uses the actual connected SDK and manifest input names.
- The scheduler build brief is explicitly optional, not a prerequisite for
  executing this practical job.

Small follow-up implementation: pod-ID/handle normalization and exact storage
verification in runpod.exec; runner job isolation, remote cancellation and
artifact-delivery failure reporting; native transport/dependency smoke. These
are focused lifecycle integration changes, not a new scheduler project.
