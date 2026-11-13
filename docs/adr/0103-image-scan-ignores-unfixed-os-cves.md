# ADR-0103: Image Scan Ignores Unfixed OS CVEs; Runtime Stage Applies Debian Upgrades

- **Status**: Accepted
- **Date**: 2026-11-13
- **Relates to**: ADR-0032, ADR-0099, ADR-0102, T-D13, T-D114
- **Amends**: ADR-0102 (image scan policy). Nothing is superseded.

## Context

After the move to `python:3.12-slim-trixie` (ADR-0102), `trivy image` still reports 109 HIGH findings (0 CRITICAL): 29 CVEs across 25 Debian 13.7 OS packages (util-linux family, krb5, curl, ncurses, systemd libraries, sqlite, perl-base, zlib). Only one, zlib1g `CVE-2026-76844`, has a fixed version (`deb13u1`), which is newer than the packages in the base image. The rest have no fix in Debian. A gate that fails on findings nobody can fix blocks every PR and gives no action to take.

## Decision

- **Runtime stage applies Debian updates.** The runtime stage's `apt-get` step runs `apt-get upgrade -y` before installing `curl` and `ca-certificates`, so every build picks up security fixes released after the base image was published. The builder stage is unchanged; it does not ship.
- **Image scan ignores unfixed findings.** In `security.yml`, the `trivy image` scan and its table diagnostic step set `ignore-unfixed: true`. The gate fails when a HIGH/CRITICAL finding has a fix that the image does not contain, which a rebuild or a dependency bump can resolve.
- **Everything else stays strict.** `trivy fs` (`ignore-unfixed: false`), `pip-audit --strict`, and `.security-allowlist.yml` as the only exception mechanism are unchanged.

## Consequences

- The image gate is green on trixie today and stays actionable.
- Known-but-unfixed OS CVEs ship in the image without a per-CVE record. The SARIF output (when `CODEQL_TOKEN` is set) and the table step still list them when the scan fails; a periodic full scan without `ignore-unfixed` is a possible follow-up.
- `apt-get upgrade` makes builds less reproducible: two builds of the same commit can differ in OS package versions. Image tags are commit SHAs and the drill gate tests the built image, so prod receives exactly what was tested.

## Alternatives considered

- **Allowlist each CVE** in `trivy_image`. Explicit audit trail, but every new unfixed Debian CVE breaks the PR until it is added.
- **Distroless or minimal runtime base.** Fewest OS packages, but the healthcheck uses `curl` and the image would have no shell; a larger rework that would delay the v3 merge.
