# QualityFlow config for this repo

QualityFlow reads this `.qualityflow/` directory when it plans or generates
tests for code in this repo. A `.qualityflow/` in a child directory (for
example `tests/e2e/.qualityflow/`) applies to the code under it, and a deeper
one wins over a shallower one and over the repo root's. Changes here are
reviewed like any other change to the repo.

## What may be here

| File | Merges over the central file of the same name |
|------|------------------------------------------------|
| `project.yaml` | Required. `version: 1` and `project_id`, then any of `feature_toggles`, `versioning`, `stp_document`, `scope_boundaries`, `scenario_tiers`, `stub_marks`, `sig_mappings`, `decorator_mappings` |
| `components.yaml`, `environment.yaml`, `coverage.yaml` | |
| `review_rules.yaml`, `code_generation_config.yaml` | |
| `tier*.yaml`, `patterns/*.yaml` | |
| `templates/**`, `reference/**` | Copied whole: this copy replaces the central one |
| `README.md` | This file; never loaded |

Any other file or key is an error. `jira.yaml`, `github.yaml`,
`repositories.yaml` and `polarion-migration/` always stay in QualityFlow's
central config; `pii_exceptions.yaml` only when the central
`repositories.yaml` lists it in `config_sources.allow_sensitive`.

## Merge rules

- Mappings merge key by key; this file wins.
- Lists replace, except lists of mappings that all carry an `id` (else a
  `name`): those merge item by item. `{merge: append, value: [...]}` appends
  to the central list instead, `{merge: replace, value: [...]}` replaces it.
- `null` removes the key.
- `pii_sanitization`, `repo_files_fetch`, `stp_review` and `std_review` can be
  turned on here, never off.

Check this directory before you push:

```bash
uv run <qualityflow checkout>/config/validate.py --repo .
```
