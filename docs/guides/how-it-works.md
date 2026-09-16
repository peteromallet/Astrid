# How Astrid works

Astrid gives agents the tools to act and the knowledge to use them—so you can work together towards a creative outcome.

## Tools to act with

Packs bring tools and instructions together. They help agents work with:

- **Open-source software:** connecting creative tools into a workflow, such as working with ComfyUI. Tools such as AI Toolkit are another example of the kind of software a pack can connect.
- **Creative approaches:** editing a timeline, shaping a sequence, or building audio-reactive visuals on top of it.

Each pack’s skill explains to your agent how to use it and helps the agent discover its tools on your machine. The available capabilities depend on the packs and dependencies you have configured.

## Knowledge to draw on

Astrid connects to [**Hivemind**](https://github.com/banodoco/hivemind), a shared body of practical knowledge with two complementary layers:

- **Raw sources:** community messages, model discussions, Reddit posts, and other material people contribute as they discover it.
- **Guides and evidence:** practical resources that agents help write and improve, with reports and observations about what works.

Agents can draw on that knowledge to choose tools, understand models, and find approaches worth trying.

## Workspace and execution

The workspace Runtime owns projects, media, timelines, tasks, runs, receipts, and event history. Astrid’s CLI and Python SDK are clients of that Runtime; a checkout-local project database is not live authority.

For generation work, Reigh submits a typed request to Runtime, a Worker executes it through `GenericPackHost`, and Runtime records the result for gallery and timeline readback. The retired Reigh `create-task` endpoint and legacy timeline-agent task tools are not alternate admission paths. Current CPU acceptance evidence does not establish GPU, model, or provider availability.

## Better together

The aim is a growing commons: people contribute tools and experience, agents help turn that experience into useful resources, and the next creative project starts with more to draw on.

Over time, better tools and shared knowledge let agents do more with open models—and give people more ways to make what they imagine.

[Contribute knowledge](contributing-knowledge.md) · [Create a pack](create-a-pack.md)

[Back to Astrid](../../README.md)
