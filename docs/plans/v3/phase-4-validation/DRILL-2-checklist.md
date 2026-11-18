# DRILL-2 checklist (explore drill)

Goals: (1) passkey registration + sign-in on a real host (T-D135), (2) T-D43 smoke, (3) T-D33 break + rollback through `rollback.yml`, (4) T-D136 Litestream restart does not re-force a generation and keeps replicating.

Never run any of this against prod. No password is ever put in argv, a chat or a log: it is piped.

## Result 2026-11-18

Explore drill run 44356288331 (host `budget-planner-drill-44356288331`, image `sha-bd4c4c3`). Recorded in `tasks.md`.

- **T-D135 passkey (PASS):** `scripts/drill/passkey_check.py` passed: password sign-in, forced rotation, passkey registered, signed out, passkey sign-in.
- **T-D136 Litestream restart (PASS):** `docker restart budget-planner-litestream` gave no ADR-0114 forcing line and no errors, same generation `6ce9a8950d6d4780`. After a DB write, WAL segments 00000004 and 00000005 were written to s3 in that generation.
- **T-D43 smoke (PASS on run 3):** runs 1 and 2 failed on test bugs (T-D43-FIX, T-D43-FIX2). Run 3 passed (1 passed, 11.85 s) on `sha-bd4c4c3`. Follow-up T-D145.
- **T-D33 rollback (PASS both ways):** rollback run 44360554182 (`target=v3.0.2`) converged to v3.0.2, app healthy, but renamed the host (T-D139-FIX). Repair run 44362948854 rolled forward to `sha-bd4c4c3` with the name restored. Runs 44364434084 (rollback, no target, no id) and 44365282708 (roll forward) kept `budget-planner-drill-44356288331`.
- **T-D139-FIX (PROVEN):** runs 44362948854, 44364434084, 44365282708.
- **T-D144 `/health/replication` (PASS on drill):** 200 `status: ok` on the real S3 replica, generation `6ce9a8950d6d4780`, age 126 s, still 200 after every rollback. Prod verify and the second monitor follow v3.0.3.
- **Teardown:** `drill-destroy.yml` run 44365679103 dispatched (orchestrator confirms the result).

Not covered by these results: the `failed` (`ready_timeout`) state on a break image (T-D33 detection, T-D129e), and the T-D138 negative case (covered 2026-11-18: run 44383745599 (lock held by explore drill 44381760469) and run 44387134093 (lock passes after destroy)).

## Prerequisites

- No other drill is up (ADR-0115 drill lock). `gh run list -R mtkublin/rising-dough -w drill.yml -L 3` and `-w restore-drill.yml -L 3`: nothing `queued` or `in_progress`.
- Operator machine is on the tailnet (`tailscale status`), repo checked out, `uv sync` done, `uv run playwright install chromium` done once.
- The drill host name is `budget-planner-drill-<run_id>.<tailnet>.ts.net` (ADR-0116). `<run_id>` is the id of the `drill.yml` run.
- Rollback needs two releases: the drill runs the newest release; `rollback.yml env=drill` goes to the previous ref (or pass `target`).

## Steps

1. **Dispatch the drill (operator).** `gh workflow run drill.yml -R mtkublin/rising-dough --ref main -f mode=explore -f keep=true -f ttl_minutes=180`
2. Get the run id and wait for the gate to finish its smoke leg: `RUN=$(gh run list -R mtkublin/rising-dough -w drill.yml -L 1 --json databaseId -q '.[0].databaseId'); gh run watch $RUN -R mtkublin/rising-dough --exit-status`
3. Set shell variables (no secrets yet). Use your tailnet suffix: `HOST=budget-planner-drill-$RUN.<tailnet>.ts.net`; `SSHH=operator@$HOST`
4. Host health: `curl -fsS https://$HOST/ready | jq .` and `curl -fsS https://$HOST/.well-known/bp-deploy-status.json | jq '{state,running_ref,error}'` (expect state `ok`).
5. Read the admin e-mail (not secret): `ADMIN=$(ssh $SSHH "sudo sed -n 's/.*BUDGET_PLANNER_ADMIN_EMAIL: \"\(.*\)\"/\1/p' /etc/budget-planner/docker-compose.yml")`
6. Pick a new admin password once, held only in this shell: `read -rs NEWPW` (type 12+ characters, nothing is echoed).

### Goal 1 and 2: passkey + smoke (T-D135, T-D43)

7. **Passkey check.** The password goes from ssh straight into the script's stdin (line 1 = current, line 2 = new for the forced rotation); nothing is printed:
   `{ ssh $SSHH "sudo sed -n 's/.*BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD: \"\(.*\)\"/\1/p' /etc/budget-planner/docker-compose.yml"; printf '%s\n' "$NEWPW"; } | uv run python scripts/drill/passkey_check.py --base-url https://$HOST --username "$ADMIN"`
   Expect `PASS: https://... password sign-in -> forced password rotation -> passkey registered -> signed out -> passkey sign-in`. A `FAIL: ... after step 'passkey registered'` or a sign-in failure points at `BUDGET_WEBAUTHN_RP_ID` / `_ORIGIN` not matching `$HOST` (T-D135).
8. **Smoke journey.** The admin is rotated now, so the smoke test uses `$NEWPW` for both (it falls back to the new password): see [`runbooks/deploy.md`](../runbooks/deploy.md) "Post-deploy smoke journey" for the exact command and notes. Run it with `SMOKE_BASE_URL=https://$HOST SMOKE_ADMIN_EMAIL=$ADMIN SMOKE_ADMIN_PASSWORD=$NEWPW SMOKE_ADMIN_NEW_PASSWORD=$NEWPW`. Record routes and result in T-D43.

### Goal 4: Litestream restart (T-D136) — do this before the rollback

9. Marker and generation are set once: `ssh $SSHH 'sudo cat /data/.litestream-age-generation; sudo docker logs budget-planner-litestream 2>&1 | grep -c "forcing a new generation"'` (expect a timestamp and `1`).
10. Generation before (the identity is read inside the container, never printed): `ssh $SSHH "sudo docker exec budget-planner-litestream sh -c 'LITESTREAM_AGE_IDENTITY=\$(grep -m1 ^AGE-SECRET-KEY- /run/litestream-age.key) litestream generations -config /etc/litestream.yml /data/budget.db'" | tee /tmp/gen-before.txt`
11. Restart: `ssh $SSHH 'sudo docker restart budget-planner-litestream'`
12. Make a write (any UI edit in the drill app, or re-run step 7 with a new `--label`), wait 30 s, repeat step 10 into `/tmp/gen-after.txt`.
13. Verify: same generation id in both files (no new generation), `end` time later in the second file, `docker logs` still shows exactly one `forcing a new generation` line, no error lines: `ssh $SSHH 'sudo docker logs --since 10m budget-planner-litestream 2>&1 | grep -ci error'` (expect 0).

### Goal 3: break + rollback (T-D33)

14. **Break (operator decision).** Procedure and the sanctioned way to produce a bad release on the drill: [`runbooks/rollback.md`](../runbooks/rollback.md) and [`runbooks/deploy.md`](../runbooks/deploy.md). Do not touch prod.
15. Roll back: `gh workflow run rollback.yml -R mtkublin/rising-dough --ref main -f env=drill` (optionally `-f target=vX.Y.Z`); `gh run watch -R mtkublin/rising-dough --exit-status`.
16. Verify as in rollback.md "Verification": `/ready`, `bp-deploy-status.json` shows `state: ok` and the target `running_ref`.
17. Re-check goal 4 quickly (step 10 output id unchanged) and `/ready`.

## Teardown

18. `gh workflow run drill-destroy.yml -R mtkublin/rising-dough --ref main` (or wait for the TTL sweeper). Confirm: `gh run watch ... --exit-status`, no `budget-planner-drill-*` node in `tailscale status`.
19. `rm -f /tmp/gen-before.txt /tmp/gen-after.txt; unset NEWPW`.
20. Record results: T-D135, T-D43, T-D33, T-D136 lines in `docs/plans/v3/tasks.md` and a dated `docs/CHANGELOG.md` line.

## Operator-only steps

Steps 1 (dispatch, drill lock), 3 (tailnet name), 6 (choose the new password), 14 (decide how to break). Everything else is a command.
