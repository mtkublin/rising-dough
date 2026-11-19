"""Scenarios + targets agreed 2026-11-19."""

from __future__ import annotations

from dataclasses import replace

from engine import RANK, Behaviour, Scenario

CAREFUL_NO_GOALS = Behaviour(p_log=0.8, recon_every=14, p_budget_met=0.75, p_nw=0.75)
CAREFUL = replace(CAREFUL_NO_GOALS, alloc_p_week=0.9, goal_every=90)
POWER = Behaviour(p_log=0.97, p_nothing=0.9, recon_every=7, p_accurate=0.98, alloc_p_week=1.0,
                  goal_every=30, p_budget_met=1.0, p_nw=0.95, p_promote=0.95)
ABSENT = Behaviour(active=False)
NEW_SETUP = {1: 0, 2: 0, 3: 0, 4: 1, 5: 1, 6: 1, 7: 3, 8: 4, 9: 4, 10: 6}

SCENARIOS = [
    Scenario("s1", "Careful, no goals", ((0, CAREFUL_NO_GOALS),), pre=60),
    Scenario("s2", "Careful with goals (A)", ((0, CAREFUL),), pre=60),
    Scenario("s3", "Power user (B)", ((0, POWER),), pre=60, n_accounts=4),
    Scenario("s4", "New user, clean", ((0, CAREFUL),), setup=NEW_SETUP, budget_from=1),
    Scenario("s5", "New user, messy",
             ((0, Behaviour(p_log=0.7, burst=(0.6, 0.6), recon_every=30, p_accurate=0.5,
                            p_budget_met=0.5, p_nw=0.5, p_promote=0.3)),),
             setup={1: 0, 3: 0, 6: 10}, budget_from=10),
    Scenario("s6", "Frugal, many no-spend days",
             ((0, replace(CAREFUL, p_log=0.35, p_nothing=0.7)),), pre=60),
    Scenario("s7", "Existing user at launch", ((-120, CAREFUL_NO_GOALS), (0, CAREFUL)), pre=120),
    Scenario("s8", "Holiday", ((0, CAREFUL), (70, ABSENT), (84, replace(CAREFUL, backfill_on_return=3))), pre=60),
    Scenario("s9", "Drops out", ((0, CAREFUL), (60, ABSENT)), pre=60),
    Scenario("s10", "Diligent but struggling",
             ((0, Behaviour(p_log=0.95, recon_every=10, p_budget_met=0.0, p_nw=0.0)),), pre=60),
    Scenario("s11", "Monthly catch-up",
             ((0, Behaviour(log_mode="monthly", p_log=0.8, recon_every=25, p_promote=0.15)),), pre=60),
    Scenario("s12", "Goals only",
             ((0, Behaviour(p_log=0.15, recon_every=45, alloc_p_week=0.9, goal_every=90,
                            p_budget_met=0.5, p_nw=0.75, p_promote=0.5)),), pre=60),
    Scenario("s13", "Very frugal (~1 purchase a week)",
             ((0, replace(CAREFUL, p_log=0.15, p_nothing=0.85)),), pre=60),
    Scenario("h1", "Many accounts (held back)", ((0, CAREFUL),), pre=60, n_accounts=6, holdout=True),
    Scenario("h2", "Weekend logger (held back)",
             ((0, replace(CAREFUL, log_mode="weekend")),), pre=60, holdout=True),
    Scenario("h3", "Point farmer (held back)",
             ((0, Behaviour(p_log=0.0, p_nothing=1.0, recon_every=1, p_accurate=1.0,
                            has_budget=False, p_nw=0.0)),), pre=60, n_accounts=3, holdout=True),
]


# ---------- metrics ----------
def frac(states, pred, lo=0, hi=None):
    xs = states[lo:hi]
    return sum(1 for s in xs if pred(s)) / max(1, len(xs))


def at_least(name):
    return lambda s: RANK[s] >= RANK[name]


def below(name):
    return lambda s: RANK[s] < RANK[name]


def eq(name):
    return lambda s: s == name


def max_changes_per_week(states):
    best = 0
    for i in range(0, len(states) - 7, 7):
        w = states[i : i + 8]
        best = max(best, sum(1 for a, b in zip(w, w[1:]) if a != b))
    return best


def bounces_per_30d(states, within=3):
    """A->B->A returns within `within` days (jitter), per 30 days."""
    n = 0
    i = 1
    while i < len(states):
        if states[i] != states[i - 1]:
            a = states[i - 1]
            if any(states[j] == a for j in range(i + 1, min(len(states), i + within + 1))):
                n += 1
        i += 1
    return n / (len(states) / 30)


def first_day(states, pred, lo=0):
    for i in range(lo, len(states)):
        if pred(states[i]):
            return i
    return None


def mean_band(states, lo=0, hi=None):
    xs = states[lo:hi]
    return sum(RANK[s] for s in xs) / max(1, len(xs))


# check: (label, metric fn(run)->float, lo, hi, aggregate) ; aggregate "med" or "p90" (worst-case-ish) or "p10"
M1 = 30


def checks_for(key):
    S = lambda r: r["states"]
    c = {
        "s1": [
            ("≥bubbly after m1 (share)", lambda r: frac(S(r), at_least("bubbly"), M1), 0.97, 1, "p10"),
            ("rising+ share", lambda r: frac(S(r), at_least("rising"), M1), 0.40, 0.70, "med"),
            ("overflowing share", lambda r: frac(S(r), eq("overflowing")), 0, 0.0, "p90"),
        ],
        "s2": [
            ("rising share", lambda r: frac(S(r), eq("rising"), M1), 0.60, 0.80, "med"),
            ("overflowing share", lambda r: frac(S(r), eq("overflowing"), M1), 0.10, 0.30, "med"),
            ("<bubbly after m1", lambda r: frac(S(r), below("bubbly"), M1), 0, 0.02, "p90"),
        ],
        "s3": [
            ("overflowing share", lambda r: frac(S(r), eq("overflowing"), M1), 0.60, 1, "med"),
            ("<rising after m1", lambda r: frac(S(r), below("rising"), M1), 0, 0.02, "p90"),
        ],
        "s4": [
            ("rising+ weeks 1-2", lambda r: frac(S(r), at_least("rising"), 0, 14), 0.9, 1, "med"),
            ("sleepy- weeks 3-4", lambda r: frac(S(r), below("bubbly"), 14, 28), 0, 0.0, "p90"),
            ("rising+ month 2+", lambda r: frac(S(r), at_least("rising"), 30), 0.7, 1, "med"),
        ],
        "s5": [
            ("bubbly share", lambda r: frac(S(r), eq("bubbly"), M1), 0.45, 1, "med"),
            ("dormant share", lambda r: frac(S(r), eq("dormant")), 0, 0.05, "med"),
        ],
        "s6": [
            ("mean band vs s2 (abs diff)", None, 0, 1.0, "cmp:s2"),
            ("rising+ share", lambda r: frac(S(r), at_least("rising"), M1), 0.6, 1, "med"),
        ],
        "s7": [
            ("overflowing days, first 14", lambda r: sum(1 for s in S(r)[:14] if s == "overflowing"), 0, 3, "med"),
            ("≥bubbly day 0", lambda r: float(RANK[S(r)[0]] >= RANK["bubbly"]), 1, 1, "p10"),
            ("rising share days 21-60", lambda r: frac(S(r), eq("rising"), 21, 60), 0.5, 1, "med"),
        ],
        "s8": [
            ("<sleepy wk1 away", lambda r: frac(S(r), below("sleepy"), 70, 77), 0, 0, "p90"),
            ("dormant before day 13 away", lambda r: frac(S(r), eq("dormant"), 70, 82), 0, 0, "p90"),
            ("≥bubbly 1d after return", lambda r: float(RANK[S(r)[85]] >= RANK["bubbly"]), 1, 1, "p10"),
            ("rising+ in week after return", lambda r: float(any(RANK[s] >= RANK["rising"] for s in S(r)[84:91])), 1, 1, "p10"),
        ],
        "s9": [
            ("days to ≤sleepy after stop", lambda r: (first_day(S(r), below("bubbly"), 60) or 999) - 60, 7, 24, "med"),
            ("dormant at day 60+20", lambda r: float(S(r)[80] == "dormant"), 1, 1, "p10"),
            ("non-dormant share days 90+", lambda r: frac(S(r), lambda s: s != "dormant", 90), 0, 0.05, "p90"),
        ],
        "s10": [
            ("<bubbly after m1", lambda r: frac(S(r), below("bubbly"), M1), 0, 0.02, "p90"),
            ("mean band (2=bubbly,3=rising)", lambda r: mean_band(S(r), M1), 2.0, 3.3, "med"),
            ("overflowing share", lambda r: frac(S(r), eq("overflowing")), 0, 0.0, "p90"),
        ],
        "s11": [
            ("rising+ share", lambda r: frac(S(r), at_least("rising"), M1), 0, 0.25, "med"),
            ("bubbly- share", lambda r: frac(S(r), lambda s: RANK[s] <= RANK["bubbly"], M1), 0.7, 1, "med"),
        ],
        "s12": [
            ("mean band", lambda r: mean_band(S(r), M1), 2.0, 3.3, "med"),
            ("overflowing share", lambda r: frac(S(r), eq("overflowing"), M1), 0, 0.10, "med"),
        ],
        "s13": [
            ("mean band vs s2 (abs diff)", None, 0, 1.0, "cmp:s2"),
            ("rising+ share", lambda r: frac(S(r), at_least("rising"), M1), 0.6, 1, "med"),
        ],
        "h1": [
            ("mean band vs s2 (abs diff)", None, 0, 0.5, "cmp:s2"),
            ("overflowing share", lambda r: frac(S(r), eq("overflowing"), M1), 0, 0.35, "med"),
        ],
        "h2": [
            ("mean band vs s2 (s2 - h2)", None, -0.3, 1.0, "cmpsigned:s2"),
        ],
        "h3": [
            ("overflowing share", lambda r: frac(S(r), eq("overflowing")), 0, 0.0, "p90"),
            ("rising+ share", lambda r: frac(S(r), at_least("rising"), M1), 0, 0.10, "med"),
        ],
    }[key]
    return c + [("bounces (A->B->A ≤3d) per 30d", lambda r: bounces_per_30d(S(r)), 0, 1, "p90")]
