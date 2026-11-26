# Design Workflow From the Repo — Implementation Plan

Decision: [ADR-0154](../../adr/0154-designer-skill-handoff-builder-and-package-template.md). Tasks: [tasks.md](tasks.md).

## Flow

```
/designer (main session)                handoff-builder (agent, worktree)        implementer + visual-auditor
  current UI (dev-demo screenshots)       canvas + spec  ->  docs/design/<name>/    package -> Jinja (ADR-0150)
  canvas: light + dark artboards          just check-handoff --render --parity
  comments loop with the operator         --write-manifest; commit
  spec + change requests
```

## Order

1. T-DW01 decision, then T-DW02 (design system) and T-DW03 (template) in either order.
2. T-DW04 check script against the template, T-DW05 skill, T-DW06 agent.
3. T-DW07 on the first real design job; T-DW08 after `ui/sourdough` is merged.

## Guardrails

- Never change or delete an existing claude.ai artifact (design systems, canvases) unless the operator asks in the session; publish new ones.
- `docs/design/rising-dough-frontend/` is untouched while `ui/sourdough` is in flight.
- Scope changes from design work go through a change request, then `docs/requirements.md` / an ADR, before code.
