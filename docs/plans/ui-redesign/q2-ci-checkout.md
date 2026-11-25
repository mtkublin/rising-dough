# Q2: CI checkout depth (operator applies)

Operator decision Q2 (2026-11-25): full commit history, no blobs (1,726 commits, 49 MiB packed);
history-based guards need the merge base. Applying it needs a push with workflow scope.

In `.github/workflows/ci.yml`, in the `ci` job (the job that runs the guards), add a `with:` block
to the first checkout step (`uses: actions/checkout@...`):

```yaml
        with:
          fetch-depth: 0
          filter: blob:none
```
