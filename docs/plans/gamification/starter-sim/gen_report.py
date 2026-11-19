"""Builds report.html from results/c*.json."""

import html
import json
from pathlib import Path

HERE = Path(__file__).parent
R = {c: json.loads((HERE / "results" / f"{c}.json").read_text()) for c in ["c0", "c1", "c2", "c3", "c4", "c5", "d1", "d3", "d4h10"]}
B, F = R["c0"], R["d3"]

TARGETS = {
    "s1": "≥ bubbly after month 1, rising 40–70%, never overflowing",
    "s2": "Rising 60–80%, overflowing 10–30%, never below bubbly after month 1",
    "s3": "Overflowing ≥ 60%, never below rising",
    "s4": "Rising+ in weeks 1–2, no sleepy in weeks 3–4, rising+ from month 2",
    "s5": "Mostly bubbly, sleepy fine, dormant < 5%",
    "s6": "Same band as #2 (±1): no-spend days never penalised",
    "s7": "Awake at launch, overflowing ≤ 3 days, at #2's level within 3 weeks",
    "s8": "≤ sleepy in week 1 away, dormant only near day 14, bubbly 1 day after return, rising within a week",
    "s9": "Sleepy within ~3 weeks, dormant after 14 days without an event, stays dormant",
    "s10": "Bubbly to low rising, never sleepy, never overflowing",
    "s11": "Mostly sleepy/bubbly, short spike after each catch-up",
    "s12": "Bubbly to low rising",
    "s13": "Same band as #2 (±1), rising+ ≥ 60%: spending little is never penalised",
    "h1": "Same as #2; reconciles must not push it into overflowing",
    "h2": "Close to #2, at most one band below",
    "h3": "Never overflowing, rising on ≤ 10% of days",
}
BEHAVIOUR = {
    "s1": "Logs 80% of days, reconciles 2 accounts every ~2 weeks, budget met 3/4 months, net worth up 3/4 months.",
    "s2": "#1 plus a goal allocation 9 weeks in 10, a goal reached every ~3 months.",
    "s3": "Logs or checks in daily, 4 accounts reconciled weekly, allocates every week, goal reached ~monthly, always within budget.",
    "s4": "All setup milestones in week 1, then #2.",
    "s5": "Partial setup, logs in bursts (70% of days while engaged), reconciles monthly and is often off, budget met half the time.",
    "s6": "#2, but only 35% of days have a purchase; 70% of the rest get a “nothing to log” check-in.",
    "s7": "120 days of #1 history before launch, then #2 from launch.",
    "s8": "#2, away days 70–83, backfills the last 3 days on return.",
    "s9": "#2 for 2 months, then never opens the app again.",
    "s10": "Logs 95% of days, reconciles every ~10 days, never within budget, net worth falls every month.",
    "s11": "Logs the whole month on the 2nd of the next month, reconciles in the same sitting, promotes recurring rows late.",
    "s12": "Allocates most weeks, logs 15% of days, reconciles every ~6 weeks.",
    "s13": "#2, but only 15% of days have a purchase (about one a week); 85% of the rest get a “nothing to log” check-in.",
    "h1": "#2 with 6 accounts.",
    "h2": "#2, but logs the week in a Saturday/Sunday sitting.",
    "h3": "No real data: “nothing to log” every day, zero-delta reconcile of 3 accounts daily, no budget.",
}
STATES = ["dormant", "sleepy", "bubbly", "rising", "overflowing"]

W, H, PL, PR, PT, PB = 560, 200, 34, 10, 10, 24


def x(d, n):
    return PL + d / (n - 1) * (W - PL - PR)


def y(v):
    return PT + (1 - v / 100) * (H - PT - PB)


def path(vals):
    n = len(vals)
    return "M" + " L".join(f"{x(i, n):.1f},{y(v):.1f}" for i, v in enumerate(vals))


def band(lo, hi):
    n = len(lo)
    up = " L".join(f"{x(i, n):.1f},{y(v):.1f}" for i, v in enumerate(hi))
    dn = " L".join(f"{x(i, n):.1f},{y(v):.1f}" for i, v in reversed(list(enumerate(lo))))
    return f"M{up} L{dn} Z"


def chart(key):
    b, f = B["scenarios"][key], F["scenarios"][key]
    n = len(f["median_health"])
    thr = F["tuning"]["thr"]
    g = []
    for v in (0, 25, 50, 75, 100):
        g.append(f'<line class="grid" x1="{PL}" x2="{W-PR}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                 f'<text class="tick" x="{PL-6}" y="{y(v)+3.5:.1f}" text-anchor="end">{v}</text>')
    for name in ("bubbly", "rising", "overflowing"):
        g.append(f'<line class="thr" x1="{PL}" x2="{W-PR}" y1="{y(thr[name]):.1f}" y2="{y(thr[name]):.1f}"/>'
                 f'<text class="thrl" x="{W-PR-2}" y="{y(thr[name])-3:.1f}" text-anchor="end">{name} {thr[name]}</text>')
    for m in range(0, n, 30):
        g.append(f'<text class="tick" x="{x(m, n):.1f}" y="{H-8}" text-anchor="middle">{"day " if m == 0 else ""}{m}</text>')
    data = json.dumps({"b": [round(v) for v in b["median_health"]], "f": [round(v) for v in f["median_health"]],
                       "lo": [round(v) for v in f["p10"]], "hi": [round(v) for v in f["p90"]]})
    return f'''<figure class="chart" data-series='{data}'>
<svg viewBox="0 0 {W} {H}" role="img" aria-label="Median starter health over {n} days for {html.escape(f['title'])}, baseline vs final tuning">
{''.join(g)}
<path class="bandf" d="{band(f['p10'], f['p90'])}"/>
<path class="lb" d="{path(b['median_health'])}"/>
<path class="lf" d="{path(f['median_health'])}"/>
<line class="cross" x1="0" x2="0" y1="{PT}" y2="{H-PB}" hidden/>
<rect class="hit" x="{PL}" y="{PT}" width="{W-PL-PR}" height="{H-PT-PB}"/>
</svg><div class="tip" hidden></div></figure>'''


def share_bar(share, label):
    segs = "".join(
        f'<span class="seg st-{s}" style="flex-grow:{share[s]*1000:.0f}" title="{s} {share[s]:.0%}"></span>'
        for s in STATES if share[s] > 0.004)
    txt = " · ".join(f"{s} {share[s]:.0%}" for s in STATES if share[s] >= 0.01)
    return f'<div class="share"><span class="sl">{label}</span><div class="bar">{segs}</div><span class="st">{txt}</span></div>'


def checks(key):
    rows = []
    for cb, cf in zip(B["scenarios"][key]["checks"], F["scenarios"][key]["checks"]):
        rows.append(
            f'<tr><td>{html.escape(cf["label"])}</td><td class="num">[{cf["lo"]}, {cf["hi"]}]</td>'
            f'<td class="num {"ok" if cb["ok"] else "bad"}">{cb["value"]}</td>'
            f'<td class="num {"ok" if cf["ok"] else "bad"}">{cf["value"]} <span class="pill {"p-ok" if cf["ok"] else "p-bad"}">{"pass" if cf["ok"] else "miss"}</span></td></tr>')
    return ('<table class="checks"><thead><tr><th>Check</th><th>Target</th><th>Before</th><th>After</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table>")


def counts(r):
    t = [c for s in r["scenarios"].values() if not s["holdout"] for c in s["checks"]]
    h = [c for s in r["scenarios"].values() if s["holdout"] for c in s["checks"]]
    return sum(c["ok"] for c in t), len(t), sum(c["ok"] for c in h), len(h)


cards = []
for key, f in F["scenarios"].items():
    ok = all(c["ok"] for c in f["checks"])
    tag = "Held back" if f["holdout"] else f"#{key[1:]}"
    cards.append(f'''<article class="card" id="{key}">
<header><span class="key">{tag}</span><h3>{html.escape(f["title"].replace(" (held back)", ""))}</h3>
<span class="pill {"p-ok" if ok else "p-bad"}">{"all checks pass" if ok else "misses a target"}</span></header>
<p class="beh">{html.escape(BEHAVIOUR[key])}</p>
<p class="tgt"><b>Target</b> {html.escape(TARGETS[key])}</p>
{chart(key)}
{share_bar(B["scenarios"][key]["share"], "Before")}
{share_bar(f["share"], "After")}
{checks(key)}
</article>''')

CYCLES = [
    ("c0", "ADR-0125 starting tuning (after fixing a dormancy bug in the simulator).", ""),
    ("c1", "Reconcile counts once per week across all accounts. Budget and net-worth feeds need check-ins on ≥ 50% of the period's days. States move down only 5 points below a threshold. State signals 15 → 10 each. Saving week 25 → 10… first 15.", "Everyone still near the top; flicker gone."),
    ("c2", "Saving week 15 → 10, budget 30 → 20, net worth 20 → 15, welcome 30/14 d → 15/7 d. Rising 50 → 55, overflowing 80 → 85.", "Shape right, about 3 points too high."),
    ("c3", "Hysteresis 5 → 8, reconcile 10 → 8, budget 20 → 15, welcome 15 → 10.", "Most targets met."),
    ("c4", "Net worth 15 → 12.", "Careful-no-goals on the edge (70%)."),
    ("c5", "Check-in 4 → 5, state signals 10 → 8 each.", "End of round 1."),
    ("d1", "Round 2, your decisions: 7-day comeback bonus ×1.5 after a 7-day gap; “nothing to log” needs a real entry in the last 14 days; overflowing needs a live goal feed; a budget for a category that had none counts.", "All tuning checks pass."),
    ("d3", "Comeback bonus sized by sweep (×1.25 / ×1.5 / ×2, below); kept ×1.5. Validated with 100 runs per user.", "Final."),
    ("d4h10", "Tried hysteresis 8 → 10 (and 12) against power-user bounces. I had misread the d3 output: those bounces were the weekend logger's.", "Rejected: careful users stick in rising too long."),
]
cyc_rows = "".join(
    f'<tr><td>{c.upper()}</td><td>{html.escape(what)}</td><td class="num">{a}/{b}</td><td class="num">{hc}/{hd}</td><td>{html.escape(note)}</td></tr>'
    for c, what, note in CYCLES for a, b, hc, hd in [counts(R[c])])
cyc_rows = cyc_rows.replace("<td>D4H10</td>", "<td>D4</td>")
cyc_rows = cyc_rows.replace("Saving week 25 → 10… first 15.", "Saving week 25 → 15.")

bt, ft = B["tuning"], F["tuning"]
TUNE = [
    ("Saving week", f'{bt["w"]["saving_week"]} / {bt["fade"]["saving_week"]} d', f'{ft["w"]["saving_week"]} / {ft["fade"]["saving_week"]} d', "Goals were adding ~25 points on top of an already full score."),
    ("Check-in day", f'{bt["w"]["checkin"]} / {bt["fade"]["checkin"]} d', f'{ft["w"]["checkin"]} / {ft["fade"]["checkin"]} d', "The daily habit is the main driver; helps comebacks."),
    ("Accurate reconcile", f'{bt["w"]["reconcile"]} / {bt["fade"]["reconcile"]} d, ≤ 1 per account per day', f'{ft["w"]["reconcile"]} / {ft["fade"]["reconcile"]} d, ≤ 1 per ISO week (all accounts)', "Stacked per account: 6 accounts or daily zero-delta reconciles pinned health at 100."),
    ("Accounts in sync", f'{bt["state"]["in_sync"]}', f'{ft["state"]["in_sync"]}', "Free points for doing nothing; kept a no-show user afloat."),
    ("Nothing overdue", f'{bt["state"]["no_overdue"]}', f'{ft["state"]["no_overdue"]}', "Same."),
    ("Within budget", f'{bt["w"]["budget"]} / {bt["fade"]["budget"]} d', f'{ft["w"]["budget"]} / {ft["fade"]["budget"]} d, needs check-ins on ≥ 50% of the period', "A user who stops logging shows 0 spent, so “met”: it woke an abandoned starter every month."),
    ("Net-worth growth", f'{bt["w"]["networth"]} / {bt["fade"]["networth"]} d', f'{ft["w"]["networth"]} / {ft["fade"]["networth"]} d, same coverage rule', "Month-start spikes pushed no-goal users into overflowing."),
    ("Welcome", f'{bt["w"]["welcome"]} / {bt["fade"]["welcome"]} d', f'{ft["w"]["welcome"]} / {ft["fade"]["welcome"]} d', "Existing users already have recent history; 30 points gave a 2-week overflowing burst."),
    ("Setup / achievement / goal reached", "10 · 30 · 40 first, 20 later", "unchanged", "Correct as peaks."),
    ("State thresholds", f'{bt["thr"]["bubbly"]} / {bt["thr"]["rising"]} / {bt["thr"]["overflowing"]}', f'{ft["thr"]["bubbly"]} / {ft["thr"]["rising"]} / {ft["thr"]["overflowing"]}', "Overflowing reserved for goal peaks and power users."),
    ("Comeback bonus", "none", "×1.5 for 7 days after ≥ 7 days without events", "Return from a break: rising within a week in 97% of runs (63% without). ×2 gave ~6 overflowing days after a break, which rewards absence."),
    ("“Nothing to log”", "counts every day", "counts only with a real ledger entry in the 14 days before", "Stops a no-data farmer; someone buying once a week still gets full credit (#13)."),
    ("Overflowing", "health ≥ threshold", "also needs a live saving-week or goal-reached feed", "Overflowing is for users actively saving."),
    ("Budget baseline (§5)", "pre-change total of the month", "per category: a category with a budget at period start counts min(start, final); a category with none counts min(final, its spending)", "A raise mid-period still doesn't count; a new category budget no longer penalises, and an unused one can't cover other categories. The first month of a new user can now be met."),
    ("Hysteresis", "none", f'{ft["hysteresis"]} points', "Drop a state only when health is 8 below its threshold; stopped up-down-up flicker."),
]
tune_rows = "".join(f"<tr><td>{a}</td><td class='num'>{html.escape(b)}</td><td class='num'>{html.escape(c)}</td><td>{html.escape(d)}</td></tr>" for a, b, c, d in TUNE)

bp, bn, bhp, bhn = counts(B)
fp, fn, fhp, fhn = counts(F)

page = f'''<title>Starter Tuning Simulation</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Unbounded:wght@500;700&family=Geist+Mono:wght@400;500&family=Geist:wght@400;500;600&display=swap">
<style>
/* Layout: a lab notebook — summary and tuning diff first, then one card per simulated user, two columns on wide screens. */
:root {{
  --bg: #f7f5f0; --surface: #fffefb; --ink: #1d1a16; --ink-2: #5a544b; --ink-3: #8a8378; --rule: #e4dfd5;
  --accent: #2a78d6; --base: #a29a8c; --band: rgba(42,120,214,.14);
  --ok: #0a7d0a; --ok-bg: #e3f3e1; --bad: #b3261e; --bad-bg: #fbe5e2;
  --st-dormant: #cfc9be; --st-sleepy: #b7d3f6; --st-bubbly: #86b6ef; --st-rising: #3987e5; --st-overflowing: #184f95;
  --display: "Unbounded", "Arial Black", system-ui, sans-serif; --body: "Geist", system-ui, -apple-system, sans-serif;
  --mono: "Geist Mono", ui-monospace, "SF Mono", Menlo, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #171512; --surface: #201e1a; --ink: #f0ede6; --ink-2: #c3bdb1; --ink-3: #8f887c; --rule: #37332d;
  --accent: #5598e7; --base: #7d766a; --band: rgba(85,152,231,.18);
  --ok: #6fd36f; --ok-bg: #1f3a1f; --bad: #ff8a80; --bad-bg: #44201d;
  --st-dormant: #4a463f; --st-sleepy: #184f95; --st-bubbly: #256abf; --st-rising: #3987e5; --st-overflowing: #9ec5f4;
  color-scheme: dark; }} }}
:root[data-theme="dark"] {{
  --bg: #171512; --surface: #201e1a; --ink: #f0ede6; --ink-2: #c3bdb1; --ink-3: #8f887c; --rule: #37332d;
  --accent: #5598e7; --base: #7d766a; --band: rgba(85,152,231,.18);
  --ok: #6fd36f; --ok-bg: #1f3a1f; --bad: #ff8a80; --bad-bg: #44201d;
  --st-dormant: #4a463f; --st-sleepy: #184f95; --st-bubbly: #256abf; --st-rising: #3987e5; --st-overflowing: #9ec5f4;
  color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{ background: var(--bg); color: var(--ink); font: 15px/1.55 var(--body);
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); padding-block: 32px 64px; }}
main {{ max-width: 1180px; margin: 0 auto; display: grid; gap: 40px; }}
h1 {{ font: 700 clamp(26px, 4vw, 40px)/1.1 var(--display); margin: 0; letter-spacing: -.01em; text-wrap: balance; }}
h2 {{ font: 500 20px/1.2 var(--display); margin: 0 0 12px; }}
h3 {{ font: 600 17px/1.3 var(--body); margin: 0; }}
.lede {{ max-width: 68ch; color: var(--ink-2); margin: 10px 0 0; }}
.eyebrow {{ font: 500 12px var(--mono); letter-spacing: .08em; text-transform: uppercase; color: var(--ink-3); }}
.kpis {{ display: flex; flex-wrap: wrap; gap: 12px 32px; margin-top: 20px; }}
.kpi b {{ display: block; font: 700 30px/1 var(--display); font-variant-numeric: tabular-nums; }}
.kpi span {{ font-size: 13px; color: var(--ink-2); }}
.scroll {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; }}
th, td {{ text-align: left; padding: 7px 10px 7px 0; border-bottom: 1px solid var(--rule); vertical-align: top; }}
th {{ font: 500 11.5px var(--mono); text-transform: uppercase; letter-spacing: .06em; color: var(--ink-3); }}
.num {{ font-family: var(--mono); font-variant-numeric: tabular-nums; white-space: nowrap; }}
.grid2 {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 520px), 1fr)); gap: 20px; }}
.card {{ background: var(--surface); border: 1px solid var(--rule); border-radius: 10px; padding: 18px; display: grid; gap: 10px; min-width: 0; }}
.card header {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 10px; }}
.card .key {{ font: 500 12px var(--mono); color: var(--ink-3); }}
.card header .pill {{ margin-left: auto; }}
.beh, .tgt {{ margin: 0; font-size: 13.5px; color: var(--ink-2); }}
.tgt b {{ font: 500 11px var(--mono); text-transform: uppercase; letter-spacing: .06em; color: var(--ink-3); margin-right: 6px; }}
.pill {{ font: 500 11px var(--mono); padding: 2px 7px; border-radius: 99px; white-space: nowrap; }}
.p-ok {{ background: var(--ok-bg); color: var(--ok); }} .p-bad {{ background: var(--bad-bg); color: var(--bad); }}
td.ok {{ color: var(--ink); }} td.bad {{ color: var(--bad); }}
.checks td:first-child {{ width: 46%; }}
.chart {{ position: relative; margin: 0; }}
.chart svg {{ width: 100%; height: auto; display: block; }}
.grid {{ stroke: var(--rule); stroke-width: 1; }}
.thr {{ stroke: var(--ink-3); stroke-width: 1; stroke-dasharray: 3 4; }}
.tick, .thrl {{ fill: var(--ink-3); font: 10px var(--mono); }}
.bandf {{ fill: var(--band); stroke: none; }}
.lb {{ fill: none; stroke: var(--base); stroke-width: 1.5; stroke-dasharray: 4 3; }}
.lf {{ fill: none; stroke: var(--accent); stroke-width: 2; }}
.cross {{ stroke: var(--ink-3); stroke-width: 1; }}
.hit {{ fill: transparent; cursor: crosshair; }}
.tip {{ position: absolute; top: 4px; pointer-events: none; background: var(--surface); border: 1px solid var(--rule); border-radius: 6px;
  padding: 5px 8px; font: 12px/1.4 var(--mono); color: var(--ink); white-space: nowrap; box-shadow: 0 2px 8px rgba(0,0,0,.08); }}
.legend {{ display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 13px; color: var(--ink-2); align-items: center; }}
.sw {{ display: inline-block; width: 18px; height: 0; border-top: 2px solid var(--accent); vertical-align: middle; margin-right: 6px; }}
.sw.b {{ border-top: 2px dashed var(--base); }} .sw.band {{ height: 10px; border: 0; background: var(--band); }}
.sw.st {{ width: 12px; height: 12px; border: 0; border-radius: 3px; }}
.share {{ display: grid; grid-template-columns: 52px 1fr; gap: 2px 10px; align-items: center; font-size: 12px; }}
.share .sl {{ font: 500 11px var(--mono); color: var(--ink-3); text-transform: uppercase; }}
.share .st {{ grid-column: 2; color: var(--ink-2); font-family: var(--mono); font-size: 11.5px; }}
.bar {{ display: flex; gap: 2px; height: 12px; }}
.seg {{ flex-basis: 0; border-radius: 3px; }}
.st-dormant {{ background: var(--st-dormant); }} .st-sleepy {{ background: var(--st-sleepy); }} .st-bubbly {{ background: var(--st-bubbly); }}
.st-rising {{ background: var(--st-rising); }} .st-overflowing {{ background: var(--st-overflowing); }}
.open {{ display: grid; gap: 14px; max-width: 80ch; padding-left: 0; list-style: none; margin: 0; }}
.open li {{ border-left: 3px solid var(--rule); padding-left: 14px; }}
.open b {{ display: block; }}
.note {{ font-size: 13.5px; color: var(--ink-2); max-width: 80ch; }}
section > p {{ max-width: 76ch; }}
</style>
<main>
<header>
  <div class="eyebrow">Rising Dough · gamification · ADR-0125 tuning</div>
  <h1>Starter tuning simulation</h1>
  <p class="lede">15 simulated users, 6 months each, 20 random runs per user, scored day by day with the ADR-0125 rules. Round 1 (5 cycles) tuned the weights on 12 users. Round 2 (3 cycles plus one rejected try) applied your decisions and added a 13th user. 3 users were held back and only checked against the final tuning. Starting and final numbers use 100 runs per user.</p>
  <div class="kpis">
    <div class="kpi"><b>{bp}/{bn} → {fp}/{fn}</b><span>tuning-set checks, starting → final</span></div>
    <div class="kpi"><b>{fhp}/{fhn}</b><span>held-back checks with the final tuning ({bhp}/{bhn} before)</span></div>
    <div class="kpi"><b>7</b><span>rule changes beyond weights (need an ADR amendment)</span></div>
  </div>
</header>

<section>
  <h2>Proposed tuning</h2>
  <p class="note">Points / fade window. Everything here goes into <code>domain/starter_tuning.py</code>; the reconcile cap, the coverage rule and hysteresis also change ADR-0125 §2–§3 text.</p>
  <div class="scroll"><table><thead><tr><th>Signal</th><th>ADR-0125 now</th><th>Proposed</th><th>Why</th></tr></thead><tbody>{tune_rows}</tbody></table></div>
</section>

<section>
  <h2>Cycles</h2>
  <div class="scroll"><table><thead><tr><th>Cycle</th><th>Change</th><th>Tuning set</th><th>Held back</th><th>Result</th></tr></thead><tbody>{cyc_rows}</tbody></table></div>
  <p class="note">C0, C5 and D3 use 100 runs per user; the others 20. Held-back results never steered a change. Comeback bonus sweep on the holiday user (100 runs): ×1 → rising within a week in 63% of runs, ×1.25 → 87%, ×1.5 → 97%, ×2 → 100% but ~6 overflowing days in the two weeks after return.</p>
</section>

<section>
  <h2>Decisions applied</h2>
  <ul class="open">
    <li><b>Coming back after a break.</b> A bonus period instead of a one-off bump: for 7 days after a gap of 7 or more days without events, every feed is worth ×1.5. 97% of holiday runs reach rising within a week.</li>
    <li><b>Point farming.</b> A “nothing to log” day counts only when there is a real ledger entry in the 14 days before it. Someone who buys once a week (#13) scores the same as the careful user; the farmer drops to bubbly.</li>
    <li><b>Budget baseline.</b> Per category. Raising an existing category's budget mid-period still doesn't count. A budget for a category that had none counts, up to that category's own spending, so a new user's first month can be met and a large made-up budget can't cover overspending elsewhere. The simulator models budget outcomes per month, so this rule was checked by its effect on new users, not line by line.</li>
    <li><b>Overflowing is for active savers.</b> It needs a live saving-week or goal-reached feed; without one the starter tops out at rising. No user without goals overflows on any day.</li>
    <li><b>Accepted as is.</b> Weekend batch loggers bounce about twice a month and monthly catch-up users are dormant about half the time; the feature is meant to reward regular activity. That bounce is the one held-back miss.</li>
  </ul>
</section>

<section>
  <h2>Simulated users</h2>
  <div class="legend" aria-label="Legend">
    <span><i class="sw"></i>Median health, proposed tuning</span>
    <span><i class="sw band"></i>10th–90th percentile, proposed</span>
    <span><i class="sw b"></i>Median health, ADR-0125 now</span>
    <span>States:</span>
    {''.join(f'<span><i class="sw st st-{s}"></i>{s}</span>' for s in STATES)}
  </div>
  <p class="note">Dashed lines mark the proposed thresholds. State shares count days from day 30 on. Hover a chart for daily values.</p>
  <div class="grid2">{''.join(cards)}</div>
</section>

<section>
  <h2>How it was run</h2>
  <p class="note">Behaviour is random per day (fixed seeds, so reruns match). Fiscal period is the calendar month. Budget and net-worth outcomes are drawn per month; a period counts as “met” when nothing was recorded, as the real rule would see it. Existing users have 60–120 days of history before launch. Changes I made to the measuring, not to the starter: fixed a simulator bug that ended dormancy too early; replaced “≤ 2 state changes per week” with “≤ 1 A→B→A bounce within 3 days per month”, because real feeds legitimately move the state several times a week; let the holiday check allow dormancy from day 12 away, since the rule counts from the last event, not from leaving.</p>
</section>
</main>
<script>
document.querySelectorAll(".chart").forEach(fig => {{
  const d = JSON.parse(fig.dataset.series), svg = fig.querySelector("svg"), hit = fig.querySelector(".hit"),
        cross = fig.querySelector(".cross"), tip = fig.querySelector(".tip"), n = d.f.length;
  const L = {PL}, R = {W - PR}, VW = {W};
  function show(ev) {{
    const r = svg.getBoundingClientRect(), sx = (ev.clientX - r.left) / r.width * VW;
    const i = Math.max(0, Math.min(n - 1, Math.round((sx - L) / (R - L) * (n - 1))));
    const px = L + i / (n - 1) * (R - L);
    cross.setAttribute("x1", px); cross.setAttribute("x2", px); cross.hidden = false;
    tip.innerHTML = "day " + i + "<br>proposed " + d.f[i] + " (" + d.lo[i] + "–" + d.hi[i] + ")<br>now " + d.b[i];
    tip.hidden = false;
    const left = px / VW * r.width;
    tip.style.left = (left > r.width / 2 ? left - tip.offsetWidth - 8 : left + 8) + "px";
  }}
  hit.addEventListener("pointermove", show);
  hit.addEventListener("pointerleave", () => {{ cross.hidden = true; tip.hidden = true; }});
}});
</script>
'''
(HERE / "report.html").write_text(page)
print("ok", len(page))
