# Pack-hosted tools and interface contributions

**Status:** Architecture proposal, 2026-09-22. This document records a product direction; it does not amend the canonical pack schema, SDK, discovery behavior, or trust policy.

The end-user and agent-facing outcome is described in the workspace's [Astrid pack extension end state](../../../docs/architecture/astrid-packs-and-extensions/end-state.md).

The companion [gap analysis](../../../docs/architecture/astrid-packs-and-extensions/gap-to-end-state.md) checks the 2026-09-22 source, distinguishes reusable Video Editor infrastructure from missing shared platform work, and proposes phased acceptance criteria. It does not change this proposal's non-normative status or the canonical pack contract.

## Purpose

Astrid's pack should become the coherent unit through which its capabilities and user interfaces are described, discovered, reused, and composed. A local agent should be able to create a pack that adds an app tool, uses existing Astrid services, and optionally contributes to an established interface such as the video editor.

This extends Astrid's pack-first model. It is not a second, parallel extension package ecosystem.

The agent workflow has three abilities: **create a tool; define extension points that make the tool extensible; and give the tool access to the shared extension platform so it can discover, load, and host contributions at those points.** A tool may also consume an existing extensible interface without hosting extensions itself.

## Fit with the existing pack model

The v2 `pack.yaml` already has a canonical pack identity, `extensions` metadata, resource declarations, and capability declarations. This gives a natural home for future interface contributions. But the current SDK capability kinds and runtime are executor, orchestrator, and element; v2's open-ended `extensions` value is metadata flexibility, not a working UI plugin API.

The proposed model keeps a single owner and version for related pack contributions:

```text
one pack identity and version
├── executable capabilities (executor / orchestrator / element)
├── optional app tool contributions
├── optional embeddable interface contributions
└── optional interface-specific contributions (for example, video editor)
```

Contribution kind and interface target belong in typed, validated manifests. Stable contribution IDs should be scoped to the owning pack. UI resources should be pack-relative and identity-bound to that pack's version and content digest. Specific field names and schema shape remain undecided; examples like `extensions.app.tools` are sketches, not contracts.

The app's frontend needs a UI-capable pack projection in addition to the current execution-capability catalog. That projection should point back to canonical Astrid pack identity and resource provenance. It should not add React entrypoints to the workspace runtime's generic task/capability readiness records. Agents can continue to discover and invoke capabilities through the SDK while the app discovers pack-owned interfaces through a corresponding manifest-backed surface.

## Pack ownership and reuse

A pack may offer a user-facing tool, a capability, both, or neither UI contribution. Packs should be grouped around coherent ownership and change/version boundaries; the rule is not one pack per screen or one pack per button. Related app tools and capabilities can share a pack when they belong together. A focused extension pack can depend on another pack's published interface contract.

For example, a footage-review pack might provide an app tool and analysis capability, then contribute a review panel to the video editor. It depends on the editor pack's published extension contract and uses its supported editor embedding surface. It does not import editor implementation modules.

The existing `video_editing` Astrid pack owns production executors and orchestrators. The React video editor is presently part of the frontend source tree. Whether that UI belongs in `video_editing` or in a separate first-party `video_editor` pack should follow actual ownership and release boundaries; names alone do not establish the right pack split.

## Two platform layers, three contract boundaries

The platform has two layers:

1. **Interface extensibility platform:** common pack identity, contribution discovery, loading, compatibility, resources, lifecycle, trust, and diagnostics. Each interface implements its own host contract. The video editor is the reference example for this layer: it publishes editor-specific extension points and hosts contributions supplied by other packs.
2. **Pack-based tool creation:** local agents create app tools that compose capabilities and existing interfaces. Tool authors can choose to expose their own extension points and opt into the shared extension host/runtime. A tool can therefore be both a complete app workflow and an extensible host.

These layers connect through three contract boundaries:

1. **Astrid pack envelope:** identity, version, dependencies, declared resources, visibility/enablement, trust information, contribution enumeration, and common discovery/inspection behavior.
2. **App host contract:** tool registration, navigation, project context, supported services, activation/cleanup, compatibility, and failure reporting.
3. **Interface contract:** the editor, gallery, or an agent-created tool defines its own extension points, renderer props, host state, and lifecycle scope.

Astrid can standardize contribution discovery, provenance, compatibility, lifecycle conventions, and diagnostics without pretending the semantics of an inspector panel and a gallery selection action are the same. The host owns authentication and durable runtime state. Tools consume approved APIs and reuse host-rendered surfaces such as media selection, task progress, and editor embedding. A tool that publishes extension points declares its interface contract, then relies on the shared platform to connect packs that implement contributions to it.

App tools activate in app scope. Editor contributions activate and dispose with each editor instance. A pack may contribute to both, so cross-scope lifecycle and disable behavior must be explicit.

## Trust boundary

Astrid's current [DEC-001](decisions.md#dec-001-v1-pack-trust-boundary) says only first-party, author-written in-repository packs are trusted for code execution; external/catalog installation is outside the current trust model until sandboxing, signing, or equivalent protection exists. Under the current rule, local agent authoring means editing or creating an in-repository source pack through an explicit user-controlled development workflow. It must not silently imply that arbitrary downloaded browser code is safe to execute. Supporting personal source roots outside the Astrid repository requires a deliberate trust-policy decision.

Resource hashes and pack provenance help identify what will load; they do not sandbox code. The pack UI proposal needs to align with Astrid's trust policy and the frontend's actual loading and dependency model before runtime implementation.

## Suggested proof

Prove the two layers in order:

1. The video editor publishes an extension contract, and a separate local pack contributes one editor feature through the shared discovery/loading/lifecycle platform. This validates Layer 1 with a real host.
2. An agent creates a local clip-review pack as a new app tool, then gives it an extension point of its own. A second pack contributes through that contract. This validates Layer 2 and proves a new tool can use the platform as an extension host.

The clip-review tool should also show the value of composition:

- Astrid discovers its canonical pack manifest, capabilities, and UI contribution metadata.
- The app shows its app tool without a source edit to the tool manifest or route table.
- The tool uses supported project/media and task APIs, then shows results.
- It opens or embeds the video editor through a supported host surface.
- It contributes one editor panel through the editor's published extension contract.
- Activation, disable/re-enable, reload, errors, version mismatch, and cleanup behave at the correct app or editor scope.

Only after this path works should the design add declarative recipes for common tool layouts or extension points for more interfaces. This keeps agent authorship the guiding workflow while grounding shared APIs in actual use.

## Open design questions

- Which typed pack contributions are needed in the first vertical slice, and where should each manifest live?
- What resource projection lets the app load first-party/local pack UI while preserving pack identity and avoiding a second registry?
- What minimum app host services should local pack tools receive?
- How are host-owned UI components shared without requiring third-party code to import private React modules?
- What is the compatibility and dependency model for React, the app host SDK, and the editor extension SDK?
- What exact user action authorizes a local agent-authored pack to execute, consistent with Astrid DEC-001?
- Does the standalone editor UI share the existing `video_editing` pack boundary or merit its own pack with a declared dependency?

Until those questions have answers and a validated example, do not document UI contributions as currently discoverable or executable pack capabilities.
