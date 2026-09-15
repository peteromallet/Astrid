# Astrid Intro: worked example

The reusable procedure is [Anchor-to-anchor video generation for any timeline](anchor-to-anchor-video-generation.md). This page records the Astrid Intro inspection from 15 September 2026 so those project facts do not get mistaken for general rules. Reinspect the live timeline before generating; timings, assets, and coverage can change.

## Picture inventory at inspection

| Timeline interval | Picture policy |
| --- | --- |
| 0–27.892 s | Image-backed opening; candidate for animation |
| 27.892–38.280 s | Background image plus terminal content; inspect carefully before animating behind the terminal |
| 38.280–64.592 s | No child-shot background anchor wired in; retain the Remotion/process sequence and terminal layers |
| 64.592–117.072 s | Image-backed ending sections, with overlays where authored |

The 38.280–64.592 s section is not an H3 endpoint target. It is a Remotion/process sequence with no child-shot background anchor, so the opening generation chain should end at 38.280 s and a new chain should begin only when image-backed picture resumes. Giving that section a generated background would require a separate creative decision and newly authored anchors.

The guidance image beginning at 64.592 s continues into the next shot, then changes internally at 74.652 s (72.492 + 2.160). The image at 7.076 s is reused at 10.264 s, so that boundary does not require a transition.

## Project-specific render facts

- The parent timeline inspected was `main-final-blackend2`.
- The editorial timeline is 30 fps; the selected H3 workflow generates at 24 fps with full lengths of `5 + 17*k` frames.
- Existing Remotion layers, terminal footage, narration, and the soundtrack remain authoritative during assembly.
- The black base is not an end-frame target. Use an explicit hold, cut, or new anchor at the boundary.

These facts feed the general guide's interval and duration procedure: each eligible picture interval's editorial gap determines its usable new-picture duration, while H3 context remains overlap rather than added timeline footage.
