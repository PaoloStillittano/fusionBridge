# Intake: from request to brief

## What a request should contain

| | Item | Example |
|---|---|---|
| Required | What it is and what it does | "desk stand for headphones" |
| Required | Key dimensions in mm (measured, ideally with calipers) | "headband 45 mm wide, base max 120x120" |
| Required | What it mates with | "2 x M4 screws into the wall", "holds a 50x70 PCB with M3 holes" |
| Optional | Style | "minimal, chamfered edges" / "organic, soft" |
| Optional | Print constraints | "no supports", "must hold 2 kg", "outdoor", "PETG", "0.2 nozzle" |
| Optional | Output | 3MF (default), STL, STEP; separate parts or not |

If something **critical** is missing (a mating dimension, a screw size, the overall size),
ask - at most 3 questions in one message. Everything else: choose a sensible default, say
which one, and make it a user parameter.

## Brief (complex parts only)

A part is complex when it has several bodies/components, mates with other objects, has
moving/snap features, or the user gave an aesthetic reference. Then, before modeling, reply
with a brief of at most 6 lines and wait for an ok:

```
Part: <name> - <function>
Envelope: <x> x <y> x <z> mm, print orientation <...>
Interfaces: <screws / fits / clearances with values>
Setup: <nozzle> / <material> / <plate> (+ why, if not the defaults)
Assumptions: <defaults you chose>
Plan: <2-3 modeling stages>
```
Simple parts (one body, clear dimensions, nothing to mate with): skip the brief and model.

## Images from the user

Images give shape and context, **not dimensions**: never measure from a photo. If a
dimension matters and is only in an image, ask for the number.

| Case | Images | What to ask for |
|---|---|---|
| Simple mechanical part | 0 | text is enough |
| Mates with an existing object | 1-2 | photo square to the object, ruler or calipers in frame, plus written dimensions |
| Hand sketch | 1 | sketch with dimensions written on it (the best input for mechanical parts) |
| Aesthetic object | 1-3 references | inspiration photos, different angles, and what the user likes in each |
| Changing an existing model | 0 | take your own `f360 shot` |

More than 3-4 images rarely help and each costs ~1.6k tokens of context.
To read an image the user gives as a path, open it with your file/image reading tool.

## Images you take (verification)

| When | Views |
|---|---|
| After each step that changes geometry | 1: `-v iso` |
| End of a stage (main body, details) | 3: `-v iso,front,top` (aesthetic: `-v iso,front --style shaded`) |
| Before export | `-v iso_bottom` (bed face, overhangs) + `f360 fdm --bed 256x256x256` |
| To the user | 2 final renders, plus drafts when you need feedback on shape |

Always open and look at the images you take; never report a result you haven't looked at.

## Workflow and checkpoints

1. Request -> brief (complex parts only) -> user ok.
2. Draft: main shape and envelope, 1-2 renders. For aesthetic parts **stop here for feedback**
   on proportions before adding details.
3. Details -> `f360 fdm` -> export -> final summary to the user:
   dimensions, parameters (name = value), print orientation, supports needed or not, file paths.

## Working folder

Every part lives in `~/Desktop/3d/<part-name>/` (kebab-case):

```
brief.md          request, brief/assumptions, printer profile used
steps/01_base.py  one script per stage, in order: rerunning them all on a new
steps/02_holes.py document must rebuild the part
shots/            renders
export/           .3mf / .stl / .step
```
At the end, save the Fusion document: `f360 save <part-name>`.
When modifying a part later, read `brief.md` and `steps/` first, then edit or add steps.
