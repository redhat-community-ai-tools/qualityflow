# std-reviewer — review_rules key map

Read this file only when a `review_rules.yaml` has been loaded and you need to resolve
which config key refines which dimension. Without config, every dimension uses the
built-in general rules in SKILL.md — config adds precision, never coverage.

| Key | Feeds | Effect |
|:----|:------|:-------|
| `std_rules.patterns.keyword_to_pattern` | Dim 3a | keyword-to-pattern mapping table |
| `std_rules.patterns.pattern_to_helpers` | Dim 3b | pattern-to-helper-library mapping |
| `std_rules.patterns.sig_to_decorator` | Dim 3c | SIG-to-decorator mapping |
| `std_rules.patterns.closure_scope_required` | Dim 2c | required closure scope variables |
| `std_rules.patterns.test_id_format` | Dim 2b | expected test ID format (default `TS-{JIRA_ID}-{NUM:03d}`) |
| `std_rules.patterns.framework_structure` | Dim 6c | expected test framework structure |
| `std_rules.timeouts` | Dim 6d | expected timeout ranges by operation type |
| `std_rules.stub_conventions` | Dim 4.5b, 5 | stub file conventions (pending markers, package rules) |
