# Design brief: Savings goals + the sourdough starter

> **For**: the Rising Dough designer.
> **From**: product (2026-11-18).
> **Builds on**: the *Rising Dough · Sourdough redesign* handoff (`docs/design/rising-dough-frontend/`). Same design system, same handoff format.
> **Decisions behind this brief**: `docs/plans/gamification/README.md` and its ADRs (0123–0126).

---

## 1. What we are adding, and why

Rising Dough is a personal budgeting app: accounts in several currencies, a ledger of what happened, planned and recurring payments, a monthly budget, a forecast. It is calm, typographic and warm (Unbounded + Geist Mono, crust and crumb colours, block-character bars).

We are adding two things, shipped in two releases:

1. **Savings goals** (release 1). A plain finance feature, useful on its own.
   - **Envelope goal**: "Vacation, 8 000 PLN by June". The user *earmarks* part of a real account's balance for the goal. The money does not move; the account now shows how much of it is allocated and how much is free. One account can hold money for several goals, and one goal can draw from several accounts (even in different currencies). Deadline optional.
   - **Net-worth goal**: "100 000 PLN net worth by May 2027". No earmarking. Progress is the user's overall net worth (all accounts, debts subtracted), which the app already shows. Deadline required (max 5 years out).
2. **The starter** (release 2). A sourdough starter living in a jar. Like a real starter it needs regular feeding, and it is fed by good money habits: saving towards goals, keeping accounts reconciled with the bank, not leaving payments overdue, staying within the month's budget, checking in, and one-time "firsts" while setting the app up. Every goal reached bakes a loaf onto a **bakery shelf**, a permanent trophy.

The point of the starter is to make the boring, healthy habits feel rewarding, especially for a new user setting the app up and for the long middle where nothing exciting happens.

## 2. Tone and principles (please design to these)

- **No death, no guilt.** A neglected starter goes *dormant*: flat, sleepy, lid on. It is never dead, mouldy, sad-crying or angry. One feed wakes it up. People who feel bad about money stop opening the app; the starter must never be the reason.
- **Never reward spending or volume.** Nothing in the visuals should suggest "more transactions = happier starter".
- **No-spend days are good.** A day with nothing to log is a win, not a gap. The "nothing to log today" check-in should feel like a small pat on the back.
- **Calm, adult, a little dry.** It lives inside a finance app next to large figures. A subtle face, gentle motion, no confetti cannons, no mascot shouting. Delight in small doses.
- **Optional.** Users can hide the starter entirely in Preferences. Goals and the shelf stay. Every screen must work and look complete with the starter hidden.
- **The user can name it.** You propose the default name.

## 3. Deliverables

Everything in light and dark, 320–1920 px, phone chrome below 768 px, as in the redesign handoff.

### 3.1 The starter character (release 2)

A **jar with a subtle face** (simple eyes, maybe a mouth; nothing more). The dough, the bubbles and the face carry the state.

| State | When (for your understanding) | Look and feel |
|---|---|---|
| **dormant** | no feeding at all for 14 days | flat dough, eyes closed, lid on or a cloth over it, still. Restful, not sad. |
| **sleepy** | low health | low dough, heavy-lidded eyes, very rare small bubble |
| **bubbly** | moderate | dough a bit risen, eyes open, a few bubbles drifting up |
| **rising** | good | dough well risen, content face, steady bubbles |
| **overflowing** | excellent | dough domed over the rim, happy face, lively bubbles |

For each state we need:

- **Still artwork** as layered SVG (see §5). The still frame is also what reduced-motion users see, so it must read on its own.
- **Idle loop**: subtle, slow, seamless (a few seconds). Dormant can be completely still, or a very slow "breath".
- **Sizes**: the full card illustration (about 160–240 px tall on desktop, smaller on phone) and a **badge glyph** for the app rail (24 px and 32 px). The glyph must still show the five states at that size, so it may simplify (dough level + eyes only).

Transitions and moments:

- **Fed reaction**: plays when any feed happens (saving, reconcile, check-in…). Short (< 1 s): a bubble pop, a little lift. Plays on the rail badge as well as the card.
- **State change**: e.g. bubbly → rising. A short morph or crossfade between the two stills is fine.
- **Wake up**: dormant → awake after the first feed. Slightly bigger moment than a normal feed (lid lifts, eyes open).
- **Welcome**: the very first time a user sees the starter (release 2 launch, or a new account). Introduces the starter by name.

### 3.2 The bakery shelf (release 2)

- A **loaf** illustration, one per reached goal, tinted with the goal's colour (goal colours use the same preset list as category colours, `components/category-colors.css`, via `--cat` / `--cat-edge`). Please give us **3–4 loaf shapes** (boule, batard, baguette, …) so a shelf of ten doesn't look copy-pasted; we will pick the shape deterministically per goal.
- Each loaf shows (on hover / tap / focus) the goal name and the date it was reached.
- States: empty shelf (no goal reached yet; inviting, not empty-sad), 1 loaf, a full shelf, overflow (20+ loaves; wraps or a second shelf, your call).
- Lives on the Goals tab. Stays visible when the starter is hidden.

### 3.3 Screens and states: release 1 (goals)

**Plan → Goals tab** (`/plan/goals`, new tab next to Budget, Year, Forecast, Analytics)

- Goal list in the user's manual order (they can reorder). Each goal row shows: name, colour, kind (envelope / net worth), progress (amount of target + percent; consider the block-character bar language), deadline if any, and a status line:
  - with deadline: **on track** / **behind**, plus "save ~1 200 PLN / month to make it";
  - without deadline (envelopes only): **ETA** at the current pace ("about March 2027"), or "no recent saving" if the pace is zero;
  - **reached** (target met; can drop back if money is released or spent);
  - **unbacked** warning (envelopes only): some allocated money is no longer actually in the account, because it was spent (see Accounts below).
- States: 0 goals (empty state with a clear "new goal"), 1, 3, 10+ goals. Archived goals: a disclosure or filter at the bottom.

**Goal detail**: a page or a large panel, your call.

- Envelope: progress, target, deadline, projection line, a per-account breakdown of the allocated money (account, currency, amount, converted value), and the allocation history (dated allocate / release events; editable and deletable like ledger rows).
- Net worth: current net worth vs target, a small forecast chart to the deadline with the target line, projected value at the deadline, the gap per month.
- Actions: allocate, release (envelope), edit, archive.

**Dialogs** (same dialog/sheet system as the handoff overlays):

- **New / edit goal**: kind first (envelope or net worth, with one line explaining each), then name, target amount + currency (defaults to the user's base currency), deadline (optional for envelope, required for net worth, max 60 months), colour, optional note. Error states.
- **Allocate**: goal, account (combobox; show each account's free balance), amount, date. Error: "Only 1 250 PLN is free in mBank Savings." Phone sheet variant.
- **Release**: same shape, reversed.
- **Archive**: for an envelope that still holds money: "Archiving releases 8 000 PLN back to free balance." Reached vs not-reached wording.

**Accounts** (`/accounts`): each asset account row gains **allocated** and **free** figures when anything is allocated. An **over-allocated** state ("over-allocated by 3 000 PLN: release some from goals") with a path to the goals involved. Liability (credit) accounts never show allocation.

**Today** (`/today`):

- A compact **goals card**: top 3 goals by the user's order, progress + status line, link to the Goals tab. 0-goals state invites creating one.
- The "Can I afford it?" result gets one more variant: the amount fits the budget but **exceeds the free (unallocated) balance**. A warning, not a block: "That would dip into money set aside for Vacation."

### 3.4 Screens and states: release 2 (starter)

**Today**: the **starter card**:

- The starter in its state, its name, and a one-line state message ("Bubbling along.").
- **Recent feeds**: the last several things that fed it, newest first, each with a short label and when ("Reconciled mBank · 2 days ago", "Saved towards Vacation · this week", "Stayed within October's budget"). This is how the user understands *why* the starter looks the way it does. Whether to also show a number (health is 0–100 internally) is your call; our lean is **no number**, state + recent feeds only.
- **"Nothing to log today"** check-in button, plus a way to mark an earlier day ("Nothing on Tuesday"). Disabled/done state once today is covered (either by the tap or because something was logged today).
- Dormant variant: an inviting line that shows the easiest way to wake it ("Log something or check in to wake it up").

**Rail badge**: the small jar glyph in the app chrome (desktop rail and the phone bottom bar; tell us where it fits best on phone). Shows the state; links to the starter card / detail. Plays the fed reaction.

**Starter detail** (drawer or overlay opened from the badge or card): the starter large, its name (rename inline or via Preferences), recent feeds (longer list), and **milestones**: earned ones with date, unearned ones as quiet hints of what to try next. The setup milestones double as a gentle onboarding checklist for new users.

**Milestone toast**: when a milestone is earned, a toast in the existing toast region ("First reconciliation, starter fed"). Routine feeds do **not** toast; they only animate the badge.

**Goal reached moment**: a loaf is baked onto the shelf. A short moment on the Goals tab / toast; no full-screen takeover.

**Settings → Preferences**: "Show the starter" toggle (with one line: goals and shelf stay) and a "Starter's name" field.

## 4. What feeds the starter (so the art and copy fit)

You do not need to design the maths; this is so labels and moments make sense.

| Feed | How often | Label idea |
|---|---|---|
| Saved towards a goal (any net allocation this week) | up to once a week | "Saved towards Vacation" |
| Day checked in (something logged, or "nothing to log") | up to once a day | "Checked in" / "No-spend day" |
| Reconciled an account, and it was already accurate (within 1 %) | per reconcile | "Reconciled mBank, spot on" |
| All accounts reconciled within 30 days | ongoing | "All accounts in sync" |
| Nothing overdue | ongoing | "Nothing overdue" |
| Stayed within the month's total budget | once a month | "Stayed within October's budget" |
| Net worth grew over the month | once a month | "Net worth grew in October" |
| Milestones (one-time) | once each | see below |
| Goal reached | per goal | "Vacation reached, loaf baked" |

**Milestones**: setup: first account · first own category · first ledger entry · first recurring payment · first planned payment · first budget · first reconciliation · first goal · first allocation · passkey added. Achievements: first goal reached · first month within budget · first no-spend check-in · four healthy weeks in a row.

Feeds fade over one to four weeks, so the starter slowly settles if habits stop. It never drops below dormant.

## 5. Technical constraints (same rules as the redesign handoff)

**Format**: extend `docs/design/rising-dough-frontend/` exactly as before: static HTML pages per state, `components.html` entries, tokens in `tokens.css`, `@layer` CSS, BEM `rd-*` classes, fragment boundary comments, overlays as page files, `index.html` links. Please follow its README §1–§8.

**Starter SVG**:

- One inline-able SVG per state (or one SVG with state groups), `viewBox` set, no raster images, no embedded fonts, no `<script>`, no inline `style=""` (CSP), colours via `currentColor` or CSS custom properties from `tokens.css` so light and dark both work.
- **Named layers** as `<g>` with stable classes, at least: `jar`, `jar-glass` / highlight, `lid` (dormant), `dough`, `dough-surface`, `bubbles` (each bubble its own element), `face`, `eyes`, `eyelids`, `mouth`. We animate these groups, so keep their transform origins sensible and document them.
- The badge glyph may be a separate, simplified SVG.

**Motion**:

- Deliver a **motion spec** per animation: which layer, which property, keyframes, duration, easing, delay, loop. CSS `@keyframes` in the handoff are ideal; a short screen recording per animation as reference helps.
- Animate **only `transform` and `opacity`** (no path morphing via `d`, no filters, no width/height). If a state change needs a shape change, crossfade between two drawings.
- **`prefers-reduced-motion: reduce`**: no idle loops, no fed bounce; state changes become instant or a plain fade. Design the still frames to carry everything.
- **No Lottie, no Rive, no GIF/video.** Our page JS budget is 30 kB gzipped for the whole app; animation is CSS + SVG (+ a few lines of Web Animations API we write).

**Accessibility**: WCAG 2.1 AA in both themes. State is never colour- or picture-only: every starter state and every goal status has a text equivalent (the state line, the status line). 44 px touch targets. Toasts are polite live regions. Focus states for loaves on the shelf.

**Runtime values**: the server sets state via classes / `data-*` attributes (e.g. `data-state="rising"` on the starter, `data-color="<preset>"` on loaves and goal rows), never inline styles. Figures, dates and progress bar cells are rendered by the server as in the existing handoff.

**Budgets**: CSS ≤ 50 kB gzipped for the whole app (the starter's CSS must stay small), fonts unchanged (no new families).

## 6. Copy

We provide functional draft copy (above and in the screen list); please **propose the voice** and refine every string: state lines, recent-feed labels, milestone names and toasts, empty states, dormant invitation, the welcome moment, and **the starter's default name**. English. Warm, dry, short; never guilt ("You neglected…"), never pressure ("Don't break your streak!").

## 7. Example data for mockups

- Base currency PLN. Accounts: *mBank Checking* (PLN), *mBank Savings* (PLN, 30 000), *Revolut* (EUR, 2 400), *Credit card* (PLN, liability).
- Goals: *Emergency fund*, envelope, 20 000 PLN, no deadline, 14 500 allocated from mBank Savings. *Vacation*, envelope, 8 000 PLN by 2027-06-30, 5 000 PLN from mBank Savings + 1 000 EUR from Revolut (about 4 300 PLN), reached. *Net worth*, 100 000 PLN by 2027-05-31, currently 71 400, projected 93 000 (behind, about 1 100 PLN / month short). *New laptop*, envelope, 6 000 PLN by 2027-02-28, 1 200 allocated, behind.
- Over-allocated example: mBank Savings balance 25 000, allocated 28 000.
- Starter: named by you; rising; recent feeds: reconciled mBank (spot on) 2 days ago, saved towards New laptop this week, no-spend day yesterday, stayed within October's budget.

## 8. Out of scope

Shared/household goals, automatic recurring allocations, starter levels or growing jars, leaderboards or social sharing, push or e-mail notifications, sound, new fonts, changes to existing screens beyond those listed.

## 9. Delivery order

1. **Release 1 (goals)**: §3.3 + any components it needs. We start building on this.
2. **Release 2 (starter)**: §3.1, §3.2, §3.4, motion spec, copy.

An early look at the character direction (2–3 rough jar sketches against the five states) before full production would save us both time.

## 10. Checklist for the handoff

- [ ] Every screen and state in §3 as an HTML page, light + dark, phone + desktop, linked from `index.html`.
- [ ] New components in `components.html`; new tokens in `tokens.css`.
- [ ] Starter: 5 state SVGs (card + badge), named layers documented, transform origins noted.
- [ ] Motion spec (idle per state, fed, state change, wake up, welcome, loaf baked) + reduced-motion behaviour.
- [ ] Loaf: 3–4 shapes, tintable via `--cat` / `--cat-edge`, shelf states.
- [ ] Copy deck with the default starter name.
- [ ] No inline styles or scripts; validator clean; axe clean, as for the redesign handoff.
