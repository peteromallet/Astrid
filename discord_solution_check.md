# Discord Scenarios — Does the Thread Contain a Working Solution?

Scan: ±6h channel window around each question; ANSWER (substantive advice), OP-CONFIRM ("fixed!"),
EXPERT (kijai/doctorpangloss/Tachyon/rattus128/NRTnarathip) classification over post-question responses.

**Verdicts across 114 Discord scenarios: YES 8 · YES (expert) 6 · PARTIAL 44+2 · NO 54**

## Solved — OP confirmed the fix in-thread (8)

| scenario | thread confirmation |
|---|--- |
| I redid my previously working SVI workflow, and I think I didn't reconnect something right, because after the reference  | it was a simple mixup with connections although hidden in a subgraph that I fixed in one instance, and then forgot that I didn't fix the oth |
| oh man... "here's the workflow" ... srsly? | I just got it working. The workflow is kind of a mess, so I spent a long time back & forth in Claude cleaning it up and deleting all the Flu |
| guys , do you have a workflow that can upscale an existing lowquality long video (pixel upscale or other technique - and | <@1166951985573003363> so.. i solved most of the errors, now i have this stage
should i just load the mp3 not the video ?
and should i fill  |
| Does anyone have a good working multi-character workflow with loras that does not degrade the image quality into the gro | Note: Claude once again ignored it's explicit command of never using the sandbox environment and prepared a commit based on truncated files, |
| Why do I get these errors in ComfyUI console? I'm using the default I2V workflow from LTX-Video's own templates . I2V Di | I saw this , someone posted this today, that the BF16 and FP8 checkpoints had been updated with the correct VAE:

HOwever I grabbed that new |
| Accidentally put this in gens whoops.....  So, I didn't know if this would be needed over here but I have a couple T2V/I | thanks for that btw, also the gguf was the only way i got it working. so thanks for the vaes and nodes all that jazz |
| Are these settings ok for GGUF Wan 2.2? I can run normal Wan 2.2 i2v (Native workflow) no issues, no OOM, super fast, bu | the wanvideowrapper one works now anyway |
| Humo workflow:  hit the AudioEncoder Encode node and crashes with: ``` # ComfyUI Error Report ## Error Details - **Node  | looks like a torch 2.9 problem... downgraded to torch 2.8 and it works. |

## Solved — expert (kijai/doctorpangloss/etc.) answered (6)

| scenario | expert answer |
|---|--- |
| Anyone understand what python dependancy handles loading models etc into vram? Just finished training a lora with musubi | you have the nodes bypassed? who knows what is going on. you also misspelled hyper realistic |
| i can't improve the quality, i tried different samplers, different amount of steps... what can i try? goddamit. I'll sha | does anything appear in the web console logs (as opposed to the logs in comfyui)? |
| I tried re-creating this 3 sampler setup in my comfycore workflow, but the results are garbage. Any insight as to what I | I just did some i2v with SVI Pro 2 now, just happy how easy it is compared to LTX2 |
| Anyone know why I'm getting this error? I never got it before in the same workflow | Just a suggestion - try a Wan 2.2 I2V checkpoint like Smoothmix or Dasiwa which has lightx already baked in |
| ok gotcha thank you also I know this is a huge ask but I finally got this upgrade in my computer and don't need the clou | <@228118453062467585> do you know what version of numpy is needed for lynx? |
| for the keyframe workflow... trying to wrap my head around why the video/audio latents would be the same amounts (81 vs  | If it’s blurry - then you probably are using just 20 steps without the distill Lora in the upscale phase ? |

## Partial — advice given, no confirmation (46)

| scenario | best answer |
|---|--- |
| Hi everyone, I'm having trouble using a GGUF model. I'm testing the same workflow on two different computers. On the mac |  |
| am I using the right checkpoints and vae for the 4 step H3 turbo Lora Workflow?(ckpt500) it's throwing up an error |  |
| I'm testing it in 21:9 and getting this error:  !!! Exception during processing !!! The expanded size of the tensor (1)  |  |
| Can anyone help me with Rune's LTX 2.3 workflows? It has a prompt enhancer node that seems to break with this error: "No |  |
| trying to run one of the ltx workflows, and I get this split_with_sizes error. anyone know what the issue is? |  |
| Hi everyone, I'm having trouble using a GGUF model. I'm testing the same workflow on two different computers. On the mac |  |
| When running LTX video workflows, ComfyUI crashes every time it reaches the "load latent upscale model" node. Does anyon |  |
| why do my minimax generations look like this? i tried several different sizes and settings... it's the only model i can  |  |
| not sure why yours has so much ghosting, especially for an API, but here is a gen i did right when the model dropped on  |  |
| hey <@421446598703317015> - pasting a screenshot showing my workflow!   this is dev bf16, euler, 25 steps, CFG at 5, res |  |
| output still super bugged when trying the resize upscale trick not sure why. i saw cseti's workflow use it just fine. bu |  |
| Am I the only one who gets this error when running this workflow ? |  |
| Guys, is using Stand-In outdated? I’m just starting to work with video now, I’m trying to use a Stand-In workflow with f |  |
| Is <@228118453062467585> 's infintetalk workflow meant to only be used with a maximum of 4 steps? I tired removing the l |  |
| Hey hey, I'm trying to run <@228118453062467585> 's bigger example workflow for Scail, but I'm getting this error. Anyon |  |
| Same seed+prompt. Someone suggested I should be using some attention node in my workflow. Checked Spectrum and it increa |  |
| anyone know how to prevent/disable these evil little fuckers from magically appearing in my workflow and connecting to t |  |
| i know quality shared his character swap workflow, curious if anyone else has a consistent process going? I've got a dec |  |
| Can someone help me verify a possible bug here, real quick? Using H3. I'll post the image with metadata for the workflow |  |
| im getting even weirder results with that lol... workflow issue? |  |
| This workflow raises another question. When using several reference images, you can connect each ref image to its slot " |  |
| can someone maybe explain to me why my workflow barely changes anything in this vid 2 vid ltx 2.3 workflow? i't supposed |  |
| Why are my videos coming out muddy with runexx new 3 pass workflow? |  |
| can someone please clarify for me once and for all, do you need to load the embeddings connector when using transformers |  |
| <@228118453062467585> i tried your new workflow with 2.3 and it works really well with the distill model and t2v but i2v |  |
| Has anyone tried mixing FML workflows with IC lora workflows with Depth_anything? I am trying to do something similar to |  |
| Hello, I'd like to see if maybe someone has had this same issue with SVI, left is just wan normally (no SVI lora), middl |  |
| Guys I need some help please. As per usual trying to use a CivitAI workflow takes a million years to fix all the issues. |  |
| Hello guys, in yesterday's daily summary, it was said ltx can be used for v2v lipsync and that it was far better than In |  |
| maybe anyone know how can I fix it? already updated comfy. Attached workflow |  |
| <@228118453062467585> after updating Comfy running into this issue with workflow that was fine prior. This a me thing? U |  |
| hey yall, i am looking to try and use this latest model, im wondering, i have a qwen clip i use with wan which is gguf a |  |
| <@228118453062467585> hi kj，the moe lora uploaded can not work in native workflow, is it for wanvideowarrper only? |  |
| anyone elses ltx broken the past few hours with comfyui update? not sure whats going on, was working fine 12 hrs ago bef |  |
| can anyone that's done generation in qwen 2512 can you share or direct me to a decent workflow that eliminates the waxy  |  |
| cuda12.9 with fresh comfyui 0.12.2, only 2 custom nodes installed: ComfyUI-GGUF:latest and ComfyUI-KJNodes:latest , erro |  |
| I tried Wan 2.1 + PUSA like you suggested, but I'm getting some color popping at the seams. Any idea how to fix this? Al |  |
| Could someone please help me? I'm using the LTX-2 - First to Last Frame video workflow, but the results are pixelated. T |  |
| <@330829305477333022> I'm getting a bit wild with postprocessing long sequences; the chunking works well at first, takin |  |
| Does anyone know what this "Meta Batch Manager 🎥🅥🅗🅢" is for?  GPT gave very vague answers and didn't explain anything.   |  |
| finally got image to video to work on my pc. someone chared a GGUF workflow and its actaully pretty fast i think??? i di |  |
| btw I've just updated and the same workflow now gives this error, is related to any change you made it Kijai? |  |
| Alright, well I don't know what the fuck this is 🤷‍♂️ 🤔 🙃  but here is 1920x1080, 30s on a 3090 on my infinite workflow  |  |
| So, I didn't know if this would be needed over here but I have a couple T2V/I2V GGUF workflows posted on civit. V1.1 has |  |
| <@256636116763934731> Thank you for the tricks about VACE. Now I understand more about controlling videos through VACE.  |  |
| anyone know why the native nodes are so much more ram hungry than the wrapper ones? Granted I have a fairly heavy workfl |  |
| anyone know why the SCAIL example workflow cuts off frames? Input is 41 frames (valid WAN length) but output is 37 frame |  |
