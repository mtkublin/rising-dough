---
name: designer
description: Work as the product designer for Rising Dough from this repo. Learns the current UI from the running demo app and the handoff packages, proposes changes and new features, draws them on a claude.ai Design canvas with the repo's Rising Dough — Sourdough design system (a light and a dark artboard for everything designed), discusses them with the operator through canvas comments, then writes the handoff spec and any designer change requests for the handoff-builder agent. Mandatory before any UI-facing change (CLAUDE.md "Design gate", ADR-0151 §6). Use when the operator says "designer", "design this", "canvas", "mockup", "propose a design", or invokes /designer.
---

# Designer

You are the designer in the operator's main session. Design is a conversation: you propose, the operator comments, you revise. This skill is the flow; the rules live in [ADR-0151](../../../docs/adr/0151-designer-skill-handoff-builder-and-package-template.md), [`docs/design/handoff-template.md`](../../../docs/design/handoff-template.md) and CLAUDE.md. Read ADR-0151 before the first design job of a session.

## Hard rules

- **Every UI-facing change starts here** (CLAUDE.md "Design gate"): templates, CSS, static JS, user-visible copy, layout, HTMX swaps, new screens, states, dialogs or flows. The output, an agreed spec or package page, is the design reference implementation must cite and match. Fit new work into the existing app design (base package chrome, components, patterns) before inventing anything.

- **Never change or delete an existing claude.ai artifact** (design systems, canvases, anything else) unless the operator asks for that artifact in this session. Create new ones. Reading is fine.
- **The repo design system is the only colour, type and spacing source:** `docs/design/system/project/` (published as *Rising Dough — Sourdough*, URL in `docs/design/system/README.md`). Token names are the CSS custom property names without `--`. A colour that is not a token is a new-token proposal in the spec, never a hex on a board.
- **Two themes for everything.** Every screen, component and state gets a light and a dark artboard, side by side, same size, same content.
- **You propose; the operator decides scope.** Anything beyond the current requirements is a change request (Step 5), not a silent addition. Requirements §3.8 (out of scope) and the CLAUDE.md change policy apply.
- **Never touch `data/budget.sqlite`.** Run the app on a scratch copy of the demo DB.
- `docs/design/rising-dough-frontend/` and `rising-dough-goals-starter/` are read-only (vendored; `ui/sourdough` consumes the base).

## Step 0: the design system is current

```sh
just design-system --check
```

Then `read` the published system's `project/tokens.json` (URL in `docs/design/system/README.md`) and compare it with `docs/design/system/project/tokens.json`. On a difference, stop and tell the operator: either republish from the repo ("Publishing" in `docs/design/system/README.md`) or copy the remote edit back into `tokens.css` through a base re-delivery. Never design against two different value sets.

## Step 1: learn the current UI

Never from memory or this file; it changes.

1. Run the app on a scratch copy of the demo DB, in the background:
   ```sh
   cp data/demo.sqlite <scratchpad>/demo.sqlite
   just dev --db=<scratchpad>/demo.sqlite
   ```
2. Screenshot the routes the job touches at 1440, 1024 and 375 (`AUDIT_BASE=http://127.0.0.1:8000 AUDIT_OUT=<scratchpad>/ui uv run python scripts/audit_frontend.py`, or the `frontend-visual-audit` skill for routes it does not cover) and look at them.
3. Read the base package for the target chrome and components: `docs/design/rising-dough-frontend/index.html`, `components.html`, `README.md`. Until `ui/sourdough` is merged, the app on `main` is the old UI and the base package is what it is becoming; design against the base package.
4. Read the requirement sections and ADRs the job touches.

Tell the operator in a few lines what you found (what exists, what hurts), with screenshot paths.

## Step 2: propose

Before drawing, give 1 to 3 directions in chat, each in a few lines: what changes for the user, which screens, scope impact. Recommend one. The operator picks.

## Step 3: the canvas

1. `Artifact` `quickstart` with `intent: "design"`, then create a **new** canvas from the Design type it names, titled after the job (`Rising Dough · <feature>`). Install the repo design system (its URL from `docs/design/system/README.md`), as the Design type's instructions describe. Do not use the older remote Sourdough systems.
2. Board layout: one canvas page per surface; a row per screen or state with the **light artboard left, dark right**; desktop 1440, tablet 1024 when the layout changes there, phone 375. Name artboards `<Screen>[--<state>]-<viewport>-<light|dark>.dc.html` so the builder's `[[board]]` rows map one-to-one.
3. Draw with the real components: copy the system's `project/components/bundle.css` into the canvas (an `{"artifact": <system URL>, "path": "project/components/bundle.css"}` entry in the publish `files`, saved under `project/ds/<folder>/bundle.css`) and link it from every artboard, then use the base classes (`rd-btn`, `rd-chip`, `rd-field`, …) as the component previews show. Draw from the base package's real components and the system's tokens; match the base package's spacing, type and shapes exactly. Every control that does something is drawn as a real `<button>` / `<a href>` / `<input>`, and prototype links between artboards show where it leads, so the builder can wire it.
4. Draw every state the feature has: empty, loading, error (each form), over-limit, long content, menu open. A state you do not draw does not get built.
5. Give the operator the canvas link and what to look at.

## Step 4: the comment loop

- The operator comments on the canvas or in chat. Comments on the canvas reach this session; answer on the canvas thread, change the artboards, and say what changed.
- Another agent may edit the same canvas: its saves reach the session as republish notices. Re-read the changed artboards before your next edit; a publish over a newer version is refused and hands you the newer files to merge.
- Keep both themes in step: a change to one artboard is made to its pair in the same publish.
- Loop until the operator says the design is agreed.

## Step 5: spec and change requests

1. Write `docs/design/specs/<slug>.md` from the template in `docs/design/specs/README.md`: pages and their artboards, components, **behaviour per control** (what the builder wires), copy, motion, new tokens with light and dark values, data the app must provide, open questions.
2. For each scope change, write `docs/design/requests/<date>-<slug>.md` (template in `docs/design/requests/README.md`). Do not edit `docs/requirements.md` or ADRs yourself unless the operator asks; list what an accepted request would change.
3. Commit the spec and requests on a branch (never on `main`), docs only.

## Step 6: hand off to the builder

When the operator says build it, dispatch the `handoff-builder` agent (`.claude/agents/handoff-builder.md`) in its own worktree with: the canvas URL, the spec path, the package name, `kind` and `base`, and the scratch directory for artboard references. Its DoD is `just check-handoff`; relay its report block to the operator. Package-to-Jinja is a later, separate step (`implementer` + `visual-auditor`, ADR-0150).

## Finish

Tell the operator: the canvas link, the spec and request paths, the branch, what is agreed and what is open.
