"""ADR-0125 starter rules as a day-by-day simulator.

Day 0 = starter launch for the user (welcome). Negative days = pre-launch history
(events dated before 0 still count by their dates; milestones before 0 are retro, 0 pts).
Calendar: day 0 = 2027-01-04 (Monday). Fiscal period = calendar month.
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass, field, replace

EPOCH = dt.date(2027, 1, 4)
STATES = ["dormant", "sleepy", "bubbly", "rising", "overflowing"]
RANK = {s: i for i, s in enumerate(STATES)}

BASE_TUNING = {
    "w": {
        "saving_week": 25, "checkin": 4, "reconcile": 10, "budget": 30, "networth": 20,
        "setup": 10, "achievement": 30, "goal_first": 40, "goal_later": 20, "welcome": 30,
    },
    "fade": {
        "saving_week": 14, "checkin": 7, "reconcile": 30, "budget": 30, "networth": 30,
        "setup": 14, "achievement": 30, "goal": 30, "welcome": 14,
    },
    "state": {"in_sync": 15, "no_overdue": 15},
    "thr": {"bubbly": 25, "rising": 50, "overflowing": 80},
    "dormant_days": 14,
    # structural knobs (None/0 = ADR-0125 as written)
    "reconcile_week_cap": None,      # max reconcile events counted per ISO week, all accounts
    "budget_min_coverage": 0.0,      # min share of period days with a check-in for budget/networth events
    "state_requires_recent_event": False,  # state signals count only while not dormant
    "hysteresis": 0,                 # drop a band only when health < threshold - hysteresis
    # decisions 2026-11-19
    "comeback": None,                # {"gap": 7, "days": 7, "mult": 1.5}: events in the first `days` after a
                                     # >= `gap`-day gap without events are worth `mult` x
    "nothing_needs_real_entry": None,  # nothing-to-log counts only with a real entry in the last N days
    "overflow_needs_goal_activity": False,  # overflowing only while a saving-week or goal-reached feed is live
    "new_budget_counts": False,      # a budget set for a category with none at period start counts (first month ok)
}


def day_date(t: int) -> dt.date:
    return EPOCH + dt.timedelta(days=t)


def iso_week(t: int) -> tuple[int, int]:
    y, w, _ = day_date(t).isocalendar()
    return (y, w)


@dataclass(frozen=True)
class Behaviour:
    active: bool = True
    log_mode: str = "realtime"      # realtime | weekend | monthly
    p_log: float = 0.8              # P(day has a purchase / ledger entry)
    p_nothing: float = 0.0          # realtime: P(nothing-to-log check-in) on a day without a log
    burst: tuple[float, float] | None = None  # (P(stay on), P(stay off)) Markov engagement
    recon_every: float = 14         # mean days between reconciles per account (0 = never)
    p_accurate: float = 0.95
    alloc_p_week: float = 0.0       # P(net allocation > 0 in a week)
    goal_every: float = 0           # mean days between goals reached (0 = never)
    p_budget_met: float = 0.75
    has_budget: bool = True
    p_nw: float = 0.75
    has_recurring: bool = True
    p_promote: float = 0.8          # P(promote a due recurring row on an active day)
    backfill_on_return: int = 0     # on return from inactivity, log the last N days


@dataclass(frozen=True)
class Scenario:
    key: str
    title: str
    phases: tuple[tuple[int, Behaviour], ...]   # (start_day, behaviour), sorted
    days: int = 182
    pre: int = 0                                 # pre-launch history days
    n_accounts: int = 2
    setup: dict[int, int] = field(default_factory=dict)  # milestone -> day (new users)
    budget_from: int | None = None               # day budget set (None = before history)
    goals_from: int = 0
    holdout: bool = False


def behaviour_at(sc: Scenario, t: int) -> Behaviour:
    cur = sc.phases[0][1]
    for start, b in sc.phases:
        if t >= start:
            cur = b
    return cur


@dataclass
class Event:
    kind: str
    date: int
    visible: int
    pts: float
    fade: int


def simulate(sc: Scenario, tuning: dict, seed: int) -> dict:
    rng = random.Random(f"{sc.key}:{seed}")
    w, fade = tuning["w"], tuning["fade"]
    start = -sc.pre
    end = sc.days
    events: list[Event] = []
    checkin_days: dict[int, int] = {}       # op_date -> recorded day (earliest)
    nothing_days: set[int] = set()
    last_checked = [start] * sc.n_accounts
    next_recon = [start + rng.uniform(0, 14) for _ in range(sc.n_accounts)]
    pending_purchases: list[int] = []
    pending_due: list[int] = []
    next_due = start + 2
    goal_countdown: float | None = None
    goals_reached = 0
    week_alloc_day: dict[tuple[int, int], int] = {}
    milestones: dict[int, int] = {}
    engaged = True
    was_active = True
    period_truth: dict[tuple[int, int], tuple[bool, bool]] = {}

    def add(kind, date, visible, pts, fd):
        if pts > 0:
            events.append(Event(kind, date, visible, pts, fd))

    def milestone(m: int, t: int):
        if m in milestones:
            return
        milestones[m] = t
        if t < 0:
            return  # retro
        if m <= 10:
            add("setup", t, t, w["setup"], fade["setup"])
        elif m >= 12:
            add("achievement", t, t, w["achievement"], fade["achievement"])

    def record_checkin(op: int, rec: int):
        if op not in checkin_days:
            checkin_days[op] = rec

    add("welcome", 0, 0, w["welcome"], fade["welcome"])
    for m, d in sc.setup.items():
        milestones_day = d
        if m == 7:
            continue  # first reconciliation detected from reconcile below
        milestone(m, milestones_day)

    states: list[str] = []
    prev: str | None = None
    healths: list[float] = []
    healthy_weeks: dict[tuple[int, int], bool] = {}

    for t in range(start, end):
        b = behaviour_at(sc, t)
        d = day_date(t)
        # engagement (bursty users)
        if b.active and b.burst:
            engaged = rng.random() < (b.burst[0] if engaged else 1 - b.burst[1])
        active = b.active and (engaged if b.burst else True)
        # life: purchases happen regardless; recurring dues appear
        purchase = rng.random() < b.p_log if b.p_log > 0 else False
        if b.has_recurring and t >= next_due:
            pending_due.append(t)
            next_due = t + 5
        # return from inactivity: backfill
        if b.active and not was_active and b.backfill_on_return:
            for op in range(t - b.backfill_on_return, t):
                if rng.random() < b.p_log:
                    record_checkin(op, t)
        was_active = b.active
        if active:
            if b.log_mode == "realtime":
                if purchase:
                    record_checkin(t, t)
                elif rng.random() < b.p_nothing:
                    record_checkin(t, t)
                    nothing_days.add(t)
                    if t >= 0:
                        milestone(13, t)
            else:
                if purchase:
                    pending_purchases.append(t)
                session = (b.log_mode == "weekend" and d.weekday() >= 5 and rng.random() < 0.9) or (
                    b.log_mode == "monthly" and d.day == 2
                )
                if session:
                    for op in pending_purchases:
                        record_checkin(op, t)
                    pending_purchases = []
            # reconcile
            if b.recon_every > 0:
                for a in range(sc.n_accounts):
                    if t >= next_recon[a]:
                        if b.log_mode == "monthly" and d.day != 2:
                            continue
                        last_checked[a] = t
                        milestone(7, t)
                        if rng.random() < b.p_accurate:
                            add("reconcile", t, t, w["reconcile"], fade["reconcile"])
                        next_recon[a] = t + max(1, rng.uniform(0.6, 1.4) * b.recon_every)
            # promote recurring rows
            pending_due = [x for x in pending_due if rng.random() >= b.p_promote]
            # allocations
            if t >= sc.goals_from and b.alloc_p_week > 0:
                wk = iso_week(t)
                if wk not in week_alloc_day and d.weekday() == 0:
                    week_alloc_day[wk] = (t + rng.randint(0, 6)) if rng.random() < b.alloc_p_week else -1
                if week_alloc_day.get(wk) == t:
                    add("saving_week", t, t, w["saving_week"], fade["saving_week"])
                    if goal_countdown is None and b.goal_every > 0:
                        goal_countdown = rng.uniform(0.5, 1.5) * b.goal_every
            if goal_countdown is not None:
                goal_countdown -= 1
                if goal_countdown <= 0:
                    first = goals_reached == 0
                    goals_reached += 1
                    add("goal", t, t, w["goal_first"] if first else w["goal_later"], fade["goal"])
                    if first:
                        milestones.setdefault(11, t)
                    goal_countdown = rng.uniform(0.5, 1.5) * b.goal_every if b.goal_every > 0 else None
        elif not b.active:
            if purchase:
                pending_purchases.append(t) if b.log_mode != "realtime" else None

        # month truth draws (once per month, at first day seen)
        mkey = (d.year, d.month)
        if mkey not in period_truth:
            period_truth[mkey] = (rng.random() < b.p_budget_met, rng.random() < b.p_nw)

        # ---- derived scoring at day t ----
        dyn: list[Event] = []
        # check-in events
        nreal = tuning["nothing_needs_real_entry"]
        for op, rec in checkin_days.items():
            if op in nothing_days and nreal and not any(
                x not in nothing_days and checkin_days[x] <= t for x in range(op - nreal + 1, op + 1) if x in checkin_days
            ):
                continue
            if rec <= t and op <= t and t - op < max(fade["checkin"], tuning["dormant_days"]):
                dyn.append(Event("checkin", op, rec, w["checkin"], fade["checkin"]))
        # closed periods
        pd = d.replace(day=1) - dt.timedelta(days=1)  # last day of previous month
        for back in range(2):
            pend = pd
            pstart = pend.replace(day=1)
            ps, pe = (pstart - EPOCH).days, (pend - EPOCH).days
            if pe < start:
                break
            ndays = pe - ps + 1
            cov = sum(1 for x in range(ps, pe + 1) if x in checkin_days and checkin_days[x] <= t) / ndays
            met_true, nw_true = period_truth.get((pend.year, pend.month), (False, False))
            budget_set_before = sc.budget_from is None or sc.budget_from <= ps
            bb = behaviour_at(sc, pe)
            min_cov = tuning["budget_min_coverage"]
            if bb.has_budget and (sc.budget_from is None or sc.budget_from <= pe):
                recorded_met = (met_true and (budget_set_before or tuning["new_budget_counts"])) or cov < 0.3
                if recorded_met and cov >= min_cov:
                    dyn.append(Event("budget", pe, pe + 1, w["budget"], fade["budget"]))
                    if pe < 0:
                        milestones.setdefault(12, pe)
                    elif 12 not in milestones:
                        milestone(12, pe + 1)
            if nw_true and cov >= max(0.3, min_cov):
                dyn.append(Event("networth", pe, pe + 1, w["networth"], fade["networth"]))
            pd = pstart - dt.timedelta(days=1)

        all_ev = [e for e in events if e.visible <= t] + dyn
        cap = tuning["reconcile_week_cap"]
        if cap:
            seen: dict[tuple[int, int], int] = {}
            capped = []
            for e in sorted(all_ev, key=lambda e: e.date):
                if e.kind == "reconcile":
                    k = iso_week(e.date)
                    seen[k] = seen.get(k, 0) + 1
                    if seen[k] > cap:
                        continue
                capped.append(e)
            all_ev = capped
        cb = tuning["comeback"]
        mult_from: list[int] = []
        if cb:
            # full history: every recorded check-in day, not only the ones still inside the dormancy window
            hist = {op for op, rec in checkin_days.items() if rec <= t and (op not in nothing_days or not nreal)}
            dates = sorted({e.date for e in all_ev if e.kind != "welcome"} | {op for op in hist if op <= t})
            mult_from = [b for a, b in zip(dates, dates[1:]) if b - a >= cb["gap"]]

        def mult(e):
            if cb and any(r <= e.date < r + cb["days"] for r in mult_from):
                return cb["mult"]
            return 1.0

        pts = sum(e.pts * mult(e) * (1 - (t - e.date) / e.fade) for e in all_ev if 0 <= t - e.date < e.fade)
        goal_live = any(e.kind in ("saving_week", "goal") and 0 <= t - e.date < e.fade for e in all_ev)
        recent = any(0 <= t - e.date < tuning["dormant_days"] for e in all_ev)

        in_sync = sc.n_accounts > 0 and all(t - lc <= 30 for lc in last_checked)
        no_overdue = not any(x < t - 3 for x in pending_due)
        st_pts = (tuning["state"]["in_sync"] if in_sync else 0) + (tuning["state"]["no_overdue"] if no_overdue else 0)
        if tuning["state_requires_recent_event"] and not recent:
            st_pts = 0
        health = min(100.0, pts + st_pts)

        # healthy week detection (milestone 14) on Sundays
        if d.weekday() == 6:
            wk = iso_week(t)
            kinds = {e.kind for e in all_ev if iso_week(e.date) == wk}
            healthy_weeks[wk] = len(kinds) >= 3
            run = 0
            for k in sorted(healthy_weeks)[-4:]:
                run = run + 1 if healthy_weeks[k] else 0
            if run >= 4 and len(healthy_weeks) >= 4:
                milestone(14, t)

        thr = tuning["thr"]
        hy = tuning["hysteresis"]
        bands = [("overflowing", thr["overflowing"]), ("rising", thr["rising"]), ("bubbly", thr["bubbly"])]
        raw = next((n for n, v in bands if health >= v), "sleepy")
        if tuning["overflow_needs_goal_activity"] and not goal_live:
            bands = bands[1:]
            raw = next((n for n, v in bands if health >= v), "sleepy")
        if not recent:
            s = "dormant"
        elif prev in (None, "dormant") or RANK[raw] >= RANK[prev]:
            s = raw
        else:  # going down: only as far as health is below threshold - hy
            s = next((n for n, v in bands if health >= v - hy and RANK[n] <= RANK[prev]), "sleepy")
        prev = s
        if t >= 0:
            states.append(s)
            healths.append(health)

    return {"states": states, "health": healths}
