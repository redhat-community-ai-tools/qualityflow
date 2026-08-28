# stp-reviewer — review_rules key map

Read this file only when a `review_rules.yaml` has been loaded and you need to resolve
which config key refines which rule. Without config, every rule uses the built-in
defaults in SKILL.md — config adds precision, never coverage.

| Key | Feeds | Effect |
|:----|:------|:-------|
| `stp_rules.abstraction.internal_components` | Rule A | additional project-specific internal component names to flag |
| `stp_rules.abstraction.qe_terms_allowed` | Rule A | extends the QE technical terms allowlist |
| `stp_rules.abstraction.internal_to_user_mappings` | Rule A | internal-to-user term translations |
| `stp_rules.abstraction.acceptable_locations` | Rule A | where internal mechanisms are acceptable |
| `stp_rules.dependencies.infrastructure_not_dependency` | Rule D | infrastructure items that are NOT dependencies |
| `stp_rules.dependencies.dependency_examples` | Rule D | valid dependency examples |
| `stp_rules.upgrade.persistent_state_indicators` | Rule E, Dim 6 | project-specific markers of persistent state |
| `stp_rules.testing_tools.standard_tools` | Rule G | standard tools that should not be listed in II.3.1 |
| `stp_rules.testing_tools.standard_frameworks` | Rule G | standard frameworks that should not be listed |
| `stp_rules.strategy.always_y` | Dim 6 | strategy checkbox items that must always be checked |
| `stp_rules.strategy.requires_justification_for_y` | Dim 6 | checkbox items needing justification when checked |
| `stp_rules.metadata.version_source` | Rule F | which Jira field drives version derivation (e.g. `fix_version`) |
| `stp_rules.metadata.sig_field` | Dim 7 | which metadata field maps to SIG ownership |
| `stp_rules.scope.layered_product` | Dim 2 | layered product ownership boundaries |
| `stp_rules.coverage_threshold` | Dim 2 | acceptance-criteria coverage threshold (default 0.70) |
