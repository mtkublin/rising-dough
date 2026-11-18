# Faster CI — Baseline and Results

> Plan: [README.md](README.md). Tasks: [tasks.md](tasks.md) (T-CS01 baseline, T-CS06 after).

## Method

- **GitHub CI is the absolute reference.** Hosted runners are clean; the developer machine usually runs several agents at once (load average 9–27 on 8 cores while measuring on 2026-11-18), so local wall times are not comparable between runs.
- **Local numbers** are used to rank slow tests and to compare before/after **back-to-back**, as CPU time (user + sys) as well as wall time, with `uptime` recorded next to each figure.
- Branch runs are measured through the draft PR for `feat/ci-speed` (CI runs on each push).

## GitHub `ci` job — last 5 green runs on `main` (2026-11-18)

| Run start (UTC) | Job | `just ci` step | Setup (checkout → sync → npm) |
|---|---|---|---|
| 13:06:42 | 3:36 | 3:16 | ~16 s |
| 13:33:05 | 4:14 | 3:53 | ~16 s |
| 13:33:39 | 5:08 | 4:42 | ~19 s |
| 14:54:44 | 5:10 | 4:50 | ~15 s |
| 15:31:03 | 3:34 | 3:13 | ~16 s |
| **median** | **4:14** | **3:53** | **~16 s** |

Breakdown of the `just ci` step (run 15:31:03):

| Step | Time |
|---|---|
| ruff | 0.1 s |
| sqlfluff | 5.3 s |
| djlint | 2.5 s |
| stylelint | 0.7 s |
| mypy (cold, no cache) | 6.5 s |
| pytest (2,233 passed, 53 skipped, 16 deselected) | 176.9 s |

Run-to-run spread is wide (3:13–4:50 for the same step), so before/after comparisons use the median of several runs.

**Observation:** pytest is ~95% of the step. mypy without a cache is only ~6.5 s, so the mypy cache (T-CS05) has a small ceiling.

## Local (8 cores, shared machine)

_Pending — serial profile with `--durations=60`._

## Slow tests by cause

_Pending._
