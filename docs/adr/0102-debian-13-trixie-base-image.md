# ADR-0102: Debian 13 (trixie) Base Image

- **Status**: Accepted
- **Date**: 2026-11-13
- **Relates to**: ADR-0099, T-D13, T-D101, T-D114
- **Amends**: ADR-0032 section 2 (container base image). Nothing is superseded.

## Context

The `trivy image` job in `security.yml` had never run to completion on v3: `trivy fs` failed first and the image job depends on it (`needs: trivy-fs`). Once T-D101 fixed `trivy fs`, the image scan reported 109 HIGH/CRITICAL findings, all in Debian 12.15 OS packages of `python:3.12-slim-bookworm` (zlib, util-linux, ncurses, perl-base and others). Every Python package in the venv was clean. None of the OS findings has a fixed version in bookworm; their status is `affected`, `will_not_fix` or `fix_deferred`. The prod image `sha-075f986` carries the same set.

## Decision

- Both Dockerfile stages move from `python:3.12-slim-bookworm` to `python:3.12-slim-trixie` (Debian 13, the current stable). Python stays 3.12. No other Dockerfile change: the stages install only `build-essential`, `curl` and `ca-certificates`, which exist under the same names in trixie.
- The image scan policy is unchanged: `severity: HIGH,CRITICAL`, `ignore-unfixed: false`, exceptions only through `.security-allowlist.yml` (`trivy_image`).
- The new image reaches prod only through the normal path (ADR-0099): a passing `drill-gate` on the PR head, then the release from `main`.

## Consequences

- Newer OS packages, so fewer known CVEs, and the base stays on Debian's main security support line.
- trixie may still carry unfixed HIGH/CRITICAL CVEs. If `trivy image` still fails after the switch, the remaining findings need a separate decision (allowlist entries, or `ignore-unfixed: true` on the image scan via a new ADR). This ADR does not make that call. (Decided in ADR-0103.)
- glibc and OpenSSL major versions change under the venv. The venv is built in the same base, so wheels and compiled extensions match; the drill gate restore and smoke test cover runtime behaviour.

## Alternatives considered

- **`ignore-unfixed: true` on the image scan.** Standard practice, and it keeps the gate actionable. The user chose to reduce the CVE surface first.
- **Allowlist the 37 CVE ids.** Explicit but noisy; every new bookworm CVE would break the PR again.
