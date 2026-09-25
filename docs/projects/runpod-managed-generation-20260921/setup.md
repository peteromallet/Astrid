# Receive safely on a clean machine

Required for packet verification: Python 3.11+ standard library. Public source
retrieval additionally requires Git, HTTPS network access and enough disk for
selected source checkouts. No provider credential or GPU is needed. Do not
install or execute product packages merely to read the handoff.

Obtain the ZIP and its external `.sha256` receipt through a trusted transfer.
Compare the full archive SHA-256 with the sender's reported value. The receipt
is outside the ZIP to avoid a self-referential archive hash; it is not a signature.
Archive members use relative sorted paths, regular files only, 0644 permissions,
fixed 1980 timestamps and ZIP_STORED. Compression-library versions cannot change
the resulting bytes.

From a receiving parent directory, copy the small `tools/packet.py` helper
alongside the ZIP and inspect it before running. Its SHA-256 is in the packet
manifest and SHA256SUMS; the archive digest is the initial trust anchor.

```sh
# Use the actual transferred file paths and sender's 64-character digest.
python3 packet.py extract astra-high-program-20260921.zip \
  --output astra-high-program-received --sha256 SENDER_ARCHIVE_SHA256
cd astra-high-program-received
python3 tools/packet.py verify .
```

The helper checks the outer hash, every ZIP path/type, duplicates, then writes
only into an absent destination. It validates the exact file census, all inner
hashes and local Markdown links. It refuses existing destinations and unsafe
members before extraction. Choose a fresh name if it refuses; never use an
overwrite flag, `unzip -o`, checkout reset, or recursive cleanup as a workaround.

Retrieve **every locked public repository**, including exact declaration pins,
into a new parent directory. The report path must also be new:

```sh
python3 tools/receive.py --destination ../astra-high-sources \
  --report ../astra-high-source-retrieval.json
```

This validator performs anonymous HTTPS clone/fetch with credential helpers and
interactive prompts disabled, no recursive submodules, no hooks and no LFS
downloads. It verifies detached HEAD equals the full SHA and the checkout is
clean. Wan2GP is fetched separately at the reigh-worker gitlink; it is not
silently initialized from a moving submodule branch. Runtime, product and skills
are separate named checkouts. Source files are intentionally absent from the ZIP.

Equivalent safe commands for one Project A repository are:

```sh
test ! -e Astrid-032f65bcd84b && test ! -L Astrid-032f65bcd84b &&
GIT_LFS_SKIP_SMUDGE=1 GIT_TERMINAL_PROMPT=0 git -c credential.helper= \
  -c core.hooksPath=/dev/null clone --no-checkout --no-recurse-submodules \
  https://github.com/peteromallet/Astrid.git Astrid-032f65bcd84b &&
git -C Astrid-032f65bcd84b fetch origin 032f65bcd84bd6360f83c260aa902c3a70cc0575 &&
GIT_LFS_SKIP_SMUDGE=1 git -C Astrid-032f65bcd84b -c core.hooksPath=/dev/null \
  checkout --detach 032f65bcd84bd6360f83c260aa902c3a70cc0575 &&
test "$(git -C Astrid-032f65bcd84b rev-parse HEAD)" = \
  032f65bcd84bd6360f83c260aa902c3a70cc0575
```

Run the chain intact; do not execute its checkout tail against a pre-existing
directory. Prefer the validator for the complete lock and consistent behavior.

## Missing-ref fallback

Exact object fetch is attempted first, then a bounded depth-256 fetch of public
branches/tags. The original SHA must still resolve. A failed fetch is
`PIN_UNAVAILABLE`, not approval to use `main` or to substitute a cached local
checkout. Continue independent repositories; hold affected work. The source
owner must expose the same object at an authorized public ref, or explicitly
select a replacement and invalidate affected evidence. Re-run only failed entries
in a fresh destination (a lock containing those unchanged entries is sufficient).
No product push is authorized in this packaging task.

If Git transport is unavailable, control documents remain readable directly
inside this packet. For skills, use [the exported Megado instructions](control/skills/megado/SKILL.md)
and [handover rules](control/skills/megado-handover/SKILL.md). Public baseline
fallback is [Megado at the inspected skills commit](https://raw.githubusercontent.com/peteromallet/poms-skills/f1296034386486d65cf19876d5e5ebfb0547e7cf/megado/SKILL.md).
The exported skill overlay differs from that baseline; use its recorded file
hashes and never claim the public commit contains the dirty overlay. Read from
the extracted packet or fresh clone; do not overwrite globally installed skills.

## CPU-only setup and configuration

[configuration.example.json](configuration.example.json) contains key names and
null provider values and explicit disabled live-test settings. Keep provider
credentials and target/storage fields unset for the current projects. No provider
login or resource discovery belongs in setup. Any later gate-L credentials must
stay in the receiver's own secret store, outside this packet and Git.

Public source/CPU-dependency retrieval is a separate setup operation. Once its
closure is local, build and validate with outbound network denied and fake engine
and provider clients; see [validation](validation.md). Default execution must not
attempt native GPU setup, provider preflight, pod attachment or model downloads.

Before future CPU tests, create a fresh Python 3.11+ virtual environment outside
existing environments; inspect each pinned pyproject/lock and install only the
selected CPU dependencies there. Use the repository paths returned in the
retrieval report. Runtime/Astrid/VibeComfy/lifecycle source installs are separate
from the Python 3.10 Wan2GP GPU runtime. Source-lock identity alone does not solve
dependency compatibility; see [validation](validation.md) and
[dependency-lock.json](dependency-lock.json). No GPU bootstrap/model download is
performed or required for this handoff's validation.
