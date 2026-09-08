# Cold skill navigation: reusable animated title effect

Query: `Build a reusable animated title effect I can use in Astrid videos.`

## Navigation action log

1. Read the required starting point, `Astrid/astrid/packs/_core/skill/SKILL.md`.
2. Resolved that skill path with `realpath` before following checkout-relative links.
3. Read `_core/skill/creative-work/SKILL.md`; the request is creative work and needs the narrowest owning pack route.
4. Read `_core/skill/pack-builder/SKILL.md`; it classifies reusable visual behavior as an element and points to the authoring contracts.
5. Read `docs/guides/creating-tools.md`; its decision rule says effects, animations, and transitions consumed by a timeline are elements.
6. Read `docs/packs/creating-packs.md`; it supplies the pack layout, manifest requirements, and static validation command.
7. Read `docs/templates/element/element.yaml`; this established the element manifest shape (`schema_version`, bare `id`, singular `kind`, `pack_id`, `schema`, `defaults`, `dependencies`, and Remotion runtime).
8. Read the local `text-card` element manifest and component, plus the local pack manifest; this supplied the closest existing title precedent and showed the component prop boundary, frame timing, opacity/transform helpers, and `elements: elements` content root. The same read also checked the available local source rather than relying on a missing title-specific style.
9. Read `astrid/core/pack/schemas/v1/element.json`; this confirmed the allowed kinds (`effect`, `animation`, `transition`) and manifest-level validation constraints. A first guessed contracts path was absent, so I treated that as a backtrack and did not infer its location.
10. Read the corrected shared contract at `astrid/packs/rendering/elements/_shared/contracts.ts`, a nearby `sliding-media` element manifest, and `docs/guides/discovery-for-agents.md`; these confirmed the stable `ElementComponentProps` boundary, the `effect` convention, and SDK discovery as the cold-agent inspection surface.

## Result and authoring plan

The supported extension shape is a reusable **element**, most naturally an
`effect` under the local source pack:

```text
Astrid/astrid/packs/local/
  pack.yaml
  elements/effects/animated-title/
    element.yaml
    component.tsx
```

Use `pack_id: local`, `kind: effect`, a stable bare id such as
`animated-title`, and `runtime.adapter: remotion`. Keep the visual behavior in
`component.tsx`, using `ElementComponentProps` and `narrowParams` at the
boundary. Read the title text and style from the clip's declared text/params,
and derive animation from `useCurrentFrame()` plus `useVideoConfig()` so the
timeline remains editable. A reasonable first contract is text content,
font/style, anchor/position, duration or phase controls, and an explicit
entrance/exit mode; put those fields in `schema` and matching `defaults`.

For the effect itself, follow the existing `text-card` precedent: use the
shared clip effect helpers for fade/slide behavior, preserve anchor/manual
positioning semantics, and make the component render a title overlay rather
than hiding animation in an executor. If the effect later needs a coordinated
multi-step workflow, add an orchestrator separately; the title visual primitive
itself remains an element.

The pack manifest already declares the local element content root. If creating
a separate distributable pack instead, scaffold it with the pack CLI, declare
`elements: elements` in `pack.yaml`, include agent guidance, and keep all
component paths inside the pack. Do not add a gateway command or a local state
store.

## Concrete validation and inspection entrypoints

After authoring, the static validation entrypoint is:

```bash
python3 -m astrid.core.pack.cli validate Astrid/astrid/packs/local
```

That validates the pack manifest and element manifest shape without executing
the component. Then inspect the discovered element through the SDK's
manifest-ledger surface (`astrid.sdk.discover()` and the resolved capability
metadata) before any runtime smoke render. A runtime smoke invocation is only
appropriate once the request includes runtime behavior and the rendering
dependencies are available; normal timeline rendering remains behind the
`rendering.render` facade.

## Measured route versus shorter recommended route

Measured navigation took 10 tool actions, including one failed guessed-path
lookup followed by correction. The shorter recommended cold route is:

1. Read core `SKILL.md`.
2. Read `creative-work/SKILL.md` and `pack-builder/SKILL.md`.
3. Read `creating-tools.md` for the element decision rule.
4. Read the element template and `creating-packs.md` for the manifest and
   validation command.
5. Inspect the local `text-card` precedent and shared element contracts.

The absence of a title-specific style is expected and does not indicate a
navigation failure; the existing text-card effect is the closest authoring
precedent.
