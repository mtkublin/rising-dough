# Designer change requests

A design proposal that changes scope (a new feature, a changed flow, data the app lacks, a requirement it contradicts) is written here as `<YYYY-MM-DD>-<slug>.md` by the `/designer` skill ([ADR-0151](../../adr/0151-designer-skill-handoff-builder-and-package-template.md) §2). The designer proposes; the operator decides. An accepted request changes `docs/requirements.md` or adds an ADR before any package or code is built (CLAUDE.md change policy).

## Template

```markdown
# <Title>

- Date: <YYYY-MM-DD> · Status: proposed | accepted | rejected
- Canvas: https://claude.ai/artifact/<id> (artboards: …)

## Problem
What the user cannot do or does badly today, with evidence (screenshots from the demo app, routes).

## Proposal
What changes, by screen.

## Scope impact
Requirements sections, ADRs and plans it touches; v1 out-of-scope items (requirements §3.8) it would pull in.

## Operator decision
<filled by the operator>
