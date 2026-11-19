# T-Q03b - Mutmut exclusion proposals (low value survivors)

Config proposals for Phase 4. mutmut 3.7 has no automatic string/log filter; the options are a `do_not_mutate` list of function patterns, `# pragma: no mutate` comments on the lines, or post-filtering `mutmut results` by diff text. Patterns below are derived from the survivors.

Total low-value survivors: 204 mutants.

## Proposed patterns

1. Post-filter: drop any survivor whose changed line matches `logger\.(debug|info|warning|error|exception)\(`, `get_logger\(`, or `raise \w+\(`; message-only mutation.
2. Post-filter: drop survivors whose diff is only a string literal turned into `XX...XX` or upper-cased and that contain spaces (human-readable message).
3. `do_not_mutate`: exception classes `*Error.__init__` in `services/users.py` (message plumbing).
4. Keep mutating contract strings (status/kind/action/entity_type values, error `code=` consumed by the UI); those are in the real-gap list, not here.

## Survivors by module and reason

| Module | Reason | Count | Example (module:line) |
|---|---|---|---|
| _passwords | log/raise message text | 1 | _passwords:48 |
| _promotion | log/raise message text | 6 | _promotion:47 |
| _promotion | message text case mutation | 4 | _promotion:44 |
| _promotion | string literal / message replaced | 2 | _promotion:44 |
| _promotion | string literal mutated (XX/UPPER) | 1 | _promotion:44 |
| accounts | string literal mutated (XX/UPPER) | 2 | accounts:49 |
| analytics | string literal mutated (XX/UPPER) | 5 | analytics:102 |
| audit | log/raise message text | 5 | audit:60 |
| audit_tail | string literal mutated (XX/UPPER) | 4 | audit_tail:60 |
| balance | log/raise message text | 4 | balance:57 |
| balance | message text case mutation | 1 | balance:57 |
| budget | log/raise message text | 6 | budget:82 |
| budget | message text case mutation | 2 | budget:82 |
| categories | log/raise message text | 5 | categories:28 |
| categories | string literal / message replaced | 1 | categories:69 |
| categories | string literal mutated (XX/UPPER) | 1 | categories:72 |
| export | log/raise message text | 3 | export:49 |
| export | string literal mutated (XX/UPPER) | 2 | export:57 |
| forecast | log/raise message text | 4 | forecast:156 |
| forecast | message text case mutation | 3 | forecast:156 |
| forecast | string literal / message replaced | 1 | forecast:168 |
| forecast | string literal mutated (XX/UPPER) | 1 | forecast:168 |
| fx | log/raise message text | 5 | fx:40 |
| fx | message text case mutation | 2 | fx:40 |
| fx | string literal mutated (XX/UPPER) | 1 | fx:74 |
| income | log/raise message text | 2 | income:63 |
| income | message text case mutation | 1 | income:63 |
| planned | log/raise message text | 4 | planned:158 |
| preferences | log/raise message text | 1 | preferences:60 |
| preferences | message text case mutation | 4 | preferences:64 |
| preferences | string literal / message replaced | 2 | preferences:82 |
| preferences | string literal mutated (XX/UPPER) | 4 | preferences:37 |
| reconciliation | log/raise message text | 11 | reconciliation:54 |
| reconciliation | message text case mutation | 3 | reconciliation:54 |
| recurring | log/raise message text | 8 | recurring:146 |
| recurring | message text case mutation | 3 | recurring:146 |
| recurring | string literal mutated (XX/UPPER) | 6 | recurring:194 |
| recurring_formula | log/raise message text | 13 | recurring_formula:63 |
| recurring_formula | message text case mutation | 8 | recurring_formula:63 |
| recurring_formula | preview error-code label text | 3 | recurring_formula:515 |
| recurring_formula | string literal / message replaced | 2 | recurring_formula:72 |
| recurring_formula | string literal mutated (XX/UPPER) | 5 | recurring_formula:61 |
| recurring_formula | user-facing message text | 15 | recurring_formula:507 |
| replication_health | string literal mutated (XX/UPPER) | 3 | replication_health:44 |
| retention | logger name string | 3 | retention:39 |
| today | log/raise message text | 2 | today:89 |
| today | message text case mutation | 1 | today:89 |
| today | string literal mutated (XX/UPPER) | 1 | today:70 |
| upcoming | string literal mutated (XX/UPPER) | 1 | upcoming:173 |
| users | exception __init__ message plumbing | 4 | users:309 |
| users | log/raise message text | 3 | users:391 |
| users | logger name string | 1 | users:123 |
| users | message text case mutation | 9 | users:99 |
| users | string literal mutated (XX/UPPER) | 9 | users:98 |
