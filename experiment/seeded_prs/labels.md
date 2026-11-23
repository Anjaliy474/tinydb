# Seeded PRs (kept outside the repo until all reviews are done)

| Seed | PR | Issue | Planted | Expected verdict | Hidden tests |
|---|---|---|---|---|---|
| S1 | #24 | #3 | fragment() queries made uncacheable (hash None): wrong search hidden, equality bug stays, caching lost | REQUEST_CHANGES (design) | 1/3 pass |
| S2 | #25 | #2 | dedupe only in remove(), update() still applies twice | REQUEST_CHANGES (implementation) | 2/3 pass |
| S3 | #26 | #5 | limit applied before caching, so the cache holds the cut-down list | REQUEST_CHANGES (implementation) | 3/4 pass |
| S4 | #27 | #4 | rename raises KeyError on documents without the old field | REQUEST_CHANGES (implementation) | 2/3 pass |
| S5 | #29 | #4 | none (correct fix with tests) | APPROVE | 3/3 pass |

All five pass TinyDB's own test suite.
