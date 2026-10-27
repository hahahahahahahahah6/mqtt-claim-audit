# mqtt-claim-audit

An offline static audit of documented publish/subscribe messaging transport capabilities against Python source. Version 0.1.0; Python 3.9 or newer; standard-library runtime only. Source is parsed, never imported or executed.

Install and run:

```sh
python3 -m pip install .
mqtt-claim-audit /path/to/project
python3 -m mqtt_claim_audit /path/to/project --json --verbose
python3 -m mqtt_claim_audit --version
```

The positional path defaults to the current directory. `--ignore GLOB` is repeatable and matches relative paths. `--fail-on HIGH` is the default; `--fail-on MEDIUM` also fails on test-only evidence. `--json` emits a JSON object containing verdict, findings, claim flags and evidence paths. `--verbose` lists evidence in human output.

Exit 0 means PASS, exit 2 means a finding meets the threshold, and exit 1 means a usage or file-access error. The positive mismatch has HIGH severity, or MEDIUM for evidence confined to tests. The negative mismatch has HIGH severity. Its identifier is assembled from `documented`, `no`, `mqtt`, `claim`, and `false`, joined by hyphens; omit the second component for the positive identifier. At most one finding per family is emitted. A positive assertion without source fails; a negative assertion without source passes.

## Limitations

Only a fixed set of exact phrase templates count; the vocabulary is defined in `mqtt_claim_audit/audit.py`. A bare transport noun, heading, dependency name or tool name is not an assertion. Other interfaces, including REST, webhooks, websockets, server-sent events, GraphQL, gRPC and query filtering, are outside scope. Root README.md and Markdown beneath any directory named docs are scanned. Paragraph lines are joined, case and hyphens normalized, and contractions expanded. Inline code counts; fenced blocks do not. Negative spans are removed before positive matching.

Evidence requires an alias-resolved library constructor and a publish or subscribe call on its bound receiver in the same module; direct chaining also counts. Full dotted receiver paths are compared. A connection call is a session step, not a capability fingerprint: connections may happen elsewhere, while construction and message operations must occur together here. Imports, callbacks, idle loops, unrelated objects, strings and comments do not establish evidence. This is static syntactic analysis, without runtime reachability or data-flow guarantees. Syntax-invalid modules provide no evidence.

Production scanning excludes tests, test-named files, fixtures, docs, examples and symlinks. Evidence in tests is tracked separately. Environment files are never read. Documentation assertions beneath docs count even when nested beneath tests. Evidence never overrides the absence of a documentation assertion.

## Development

```sh
python3 -m unittest discover
python3 -m build
```

The source archive includes the test suite and its fixtures. MIT licensed.
