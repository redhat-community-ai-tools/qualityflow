---
name: pr-analyzer
description: Analyze GitHub PR diffs and extract meaningful changes and coverage gaps for STP generation
model: claude-opus-4-6
---

# PR Analyzer Skill

**Phase:** Pre-Processing
**User-Invocable:** false

## Purpose

Analyze GitHub PR diffs and extract meaningful changes for STP generation, and
— when the triggering artifact is a pull request — measure which of the PR's
added lines are not covered by tests.

## When to Use

Invoked by the **github-pr-fetcher** subagent after fetching PR details, diffs, and review comments.

## Input

```yaml
pr_data:
  url: https://github.com/example-org/example-repo/pull/1234
  owner: example-org
  repo: example-repo
  pull_number: 1234
  head_sha: 050f6fb5ea92ee84a14c0407d09e60d2d6176002   # required for coverage gap probe
  title: Add CPU hot-plug support
  description: |
    This PR implements CPU hot-plug functionality...
  state: merged
  author: developer
  base_branch: main
  head_branch: feature/cpu-hotplug
  diff: |
    diff --git a/pkg/controllers/vm/vm.go b/pkg/controllers/vm/vm.go
    index abc123..def456 100644
    --- a/pkg/controllers/vm/vm.go
    +++ b/pkg/controllers/vm/vm.go
    @@ -100,6 +100,20 @@ func (c *ResourceController) Reconcile() {
    +func (c *ResourceController) HandleCPUHotplug(res *v1.Resource) error {
    ...
  files:
    - filename: pkg/controllers/vm/vm.go
      status: modified
      additions: 50
      deletions: 10
    - filename: pkg/controllers/vm/hotplug.go
      status: added
      additions: 200
      deletions: 0
    - ...
  review_comments:
    - user: reviewer1
      body: "Consider edge case when VM is migrating"
      path: pkg/controllers/vm/hotplug.go
      line: 45
    - ...
```

## Output Format

```yaml
analysis:
  pr_url: https://github.com/example-org/example-repo/pull/1234
  summary: Implements CPU hot-plug functionality for running VMs

  key_changes:
    functions:
      - name: HandleCPUHotplug
        file: pkg/controllers/vm/vm.go
        action: added
        purpose: Main entry point for CPU hot-plug operations
      - name: ValidateCPUChange
        file: pkg/controllers/vm/hotplug.go
        action: added
        purpose: Validates CPU changes before applying
      - ...

    types:
      - name: CPUHotplugSpec
        file: api/v1/types.go
        action: added
        fields_changed:
          - MaxSockets
          - CurrentSockets
      - ...

    apis:
      - endpoint: /resources/{name}/cpu
        method: PATCH
        action: added
        purpose: Hot-plug CPU to running VM
      - ...

    configurations:
      - name: EnableCPUHotplug
        type: feature_gate
        location: Platform CR
        default: false
      - ...

  files_by_category:
    controllers:
      - pkg/controllers/vm/vm.go
      - pkg/controllers/vm/hotplug.go
    handlers:
      - pkg/handlers/hotplug/cpu.go
    api:
      - api/v1/types.go
      - api/v1/types_swagger_generated.go
    tests:
      - tests/hotplug_test.go
    other:
      - ...

  review_insights:
    edge_cases:
      - "VM migration during hot-plug needs handling"
      - "Consider maximum CPU limit validation"
    concerns:
      - "Performance impact of frequent hot-plug operations"
    suggestions:
      - "Add metrics for hot-plug success/failure rate"

  impact_assessment:
    components_affected:
      - app-controller
      - app-handler
      - app-api
    features_potentially_impacted:
      - VM lifecycle
      - Live migration
      - Resource quotas
    breaking_changes: false
    api_changes: true
    config_changes: true

  # Present only when a coverage source was found (see Coverage Gap Extraction).
  # Omitted entirely when source is `none` — downstream behavior is unchanged.
  coverage_gaps:
    source: codecov-check          # codecov-check | local-profile | coverport | none
    measured_at: 2026-08-18T09:14:00Z
    head_sha: 050f6fb5ea92ee84a14c0407d09e60d2d6176002
    patch_coverage_pct: 28.2       # before-number for the STP gap report
    target_pct: 80.0               # project gate, if the source reports one
    uncovered_total: 188
    files:
      - file: pkg/controllers/vm/hotplug.go
        patch_coverage_pct: 6.5
        uncovered_count: 129
        uncovered_lines: [45, 46, 47, 52, 53, 61]   # exact lines; empty if only file-level data
        precision: line                              # line | file
        uncovered_symbols:                           # cross-referenced with key_changes.functions
          - name: HandleCPUHotplug
            lines: "45-47,52-53"
            branches_missed: ["migration in progress", "max sockets exceeded"]
    runtime_uncovered:             # present only when source coverport data was merged
      - file: pkg/controllers/vm/hotplug.go
        symbol: HandleCPUHotplug
        executed_in_env: false     # never executed by any running pod
```

## Coverage Gap Extraction

**Guard:** run this only when the triggering artifact is a **pull request** and
`COVERAGE_MODE` is unset or not `off`. Skip silently otherwise.

Confirm "is a PR" with `gh pr view {n}`, not by pattern-matching the URL:
GitHub numbers issues and pull requests in a single sequence and serves PRs
under `/issues/` as well as `/pull/`, so the URL shape is not a reliable
discriminator. `pr_data.head_sha` being set is equally good evidence.

The goal is one deterministic answer: **which added lines of this PR are not
executed by any test.** Try the sources below in order and stop at the first
that returns data. Never guess a percentage — if no source answers, emit
`source: none` and omit `coverage_gaps`.

### Source 1 — Codecov check run (preferred, no extra credentials)

The PR's own CI already published this. Read it back with `gh`:

```bash
gh api "repos/${REPO_FULL_NAME}/commits/${HEAD_SHA}/check-runs?per_page=100" \
  --jq '.check_runs[] | select(.name|test("(?i)codecov/patch")) |
        {title: .output.title, summary: .output.summary}'
```

`output.title` is the headline, e.g. `28.24% of diff hit (target 80.00%)`.
Parse `patch_coverage_pct` and `target_pct` from it.

Per-file numbers come from the Codecov bot's PR comment:

```bash
gh api "repos/${REPO_FULL_NAME}/issues/${PR_NUMBER}/comments?per_page=100" \
  --jq '.[] | select(.user.login|test("(?i)codecov")) | .body'
```

The comment body contains a markdown table whose rows read
`| path/to/file.go | 6.52% | 118 Missing and 11 partials |`. Parse each row
into a `files[]` entry with `precision: file` — Codecov's comment carries no
line numbers.

`uncovered_count` = **Missing + partials**. A partial is a line whose branches
are not all taken, which is still a gap worth a scenario. This is also the
arithmetic Codecov itself uses: its headline `N lines in your changes missing
coverage` already includes partials, so summing the per-file rows must equal
the headline. **Check that it does** — if the two disagree, the table was
truncated (Codecov elides files in large PRs) and the report must say so
rather than present a partial list as complete.

Worked example, verified against `fullsend-ai/fullsend#6285`:

| File | Patch % | Row | uncovered_count |
|------|---------|-----|-----------------|
| internal/harness/compose.go | 6.52% | 118 Missing and 11 partials | 129 |
| internal/harness/forge.go | 48.05% | 29 Missing and 11 partials | 40 |
| internal/harness/trigger.go | 57.14% | 9 Missing and 6 partials | 15 |
| internal/harness/harness.go | 33.33% | 2 Missing and 2 partials | 4 |

129 + 40 + 15 + 4 = 188, matching the headline `28.24427% with 188 lines`.

### Source 2 — Local coverage profile (adds exact line numbers)

Run only when `$SOURCE_REPO_DIR` is a checkout of the PR head and the repo's
own coverage command is known from `coverage.yaml`
(`coverage_gap.command`) or the repo's `Makefile`. This is the only source
that yields `precision: line`.

```bash
cd "$SOURCE_REPO_DIR"
go test -coverprofile=/tmp/qf-cov.out ./...     # or coverage_gap.command
go tool cover -func=/tmp/qf-cov.out             # per-function summary
```

The raw profile lines are `file.go:startLine.col,endLine.col numStmts hitCount`.
A block with `hitCount == 0` means every line in `startLine..endLine` is
uncovered. Intersect that set with the lines this PR added — take added line
numbers from the `@@ -a,b +c,d @@` hunk headers in `pr_data.diff`, counting
only `+` lines. The intersection is `uncovered_lines`.

**Cost guard:** run the coverage command scoped to the packages containing
changed files, not `./...`, when the changed set is small. If the command
exceeds 10 minutes or fails, fall back to Source 1's file-level numbers
rather than aborting the pipeline.

### Source 3 — CoverPort runtime coverage (optional, e2e tier only)

Only when `coverage.yaml` defines `product_coverage`. This answers a
*different* question from Sources 1-2: not "is this line unit-tested" but
"has this line ever executed in a live environment". A symbol that is unit-
tested but never runs in a real deployment needs an integration or e2e
scenario, not another unit test.

**Prefer 3a. It needs no cluster access and no new tooling.**

**3a — Read it back from Codecov flags.** CoverPort's own pipeline uploads its
results to Codecov under a flag (`coverport process --codecov-flags=e2e,integration`).
If the project does that, runtime coverage is already in the same check run
Source 1 reads — just partitioned by flag. Compare the `unit-tests` flag
against the `e2e-tests` flag for the same file: lines hit by neither are
runtime-uncovered. No OCI, no `oras`, no kubeconfig.

**3b — Pull the published OCI artifact.** Only when 3a is unavailable. Note
that **CoverPort has no `pull` subcommand** — pulling is done with the
external `oras` binary, and `coverport process` shells out to it:

```bash
oras pull "${COVERAGE_ARTIFACT_REF}"            # requires oras in PATH
coverport process --artifact-ref="${COVERAGE_ARTIFACT_REF}" \
                  --image="${INSTRUMENTED_IMAGE}"
```

The artifact ref is `registry/repository:tag`, where the tag defaults to
`{test-name}-{YYYYMMDD-HHMMSS}` — so "latest" is not addressable by name.
The producing pipeline writes the exact ref to the file named by
`$COVERAGE_ARTIFACT_REF_FILE`; read the ref from there or from
`coverage.yaml`'s `product_coverage.artifact_ref`. Do not guess a tag.

**Format note:** whatever the route, Go CoverPort output lands as an ordinary
Go coverprofile (`mode: atomic`, then `file.go:l.c,l.c numStmts hitCount`) at
`coverage-output/{component}/coverage-{test-name}-{component}/coverage.out`.
That is the **same format Source 2 produces**, so parse it with the same code
path — a zero-hit block means those lines never executed in the live pod.
Python arrives as Cobertura XML, Node as LCOV, Rust as LCOV.

Populate `runtime_uncovered[]`; a symbol with `executed_in_env: false` is a
candidate for an integration or e2e scenario.

Never block on this source. It requires cluster or registry access the sandbox
may not have, and CoverPort has no merge/diff support of its own. On any
failure, omit `runtime_uncovered` and continue — Sources 1-2 still stand.

### Cross-referencing to symbols

For each uncovered line range, map it back to the enclosing function using the
`key_changes.functions` entries already extracted from the diff (a function
owns a line if the line falls inside its diff hunk). This produces
`uncovered_symbols[]`, which is what makes a scenario traceable to
`file:lines` rather than to a whole file.

### Reporting honestly

- Percentages must be copied from the source, never estimated.
- `precision: file` means downstream scenarios cite the file, not line numbers.
  Do not invent line numbers to make a scenario look specific.
- A file with 0 added lines is never a gap, even at 0% coverage.
- Test files (`*_test.go`, `test_*.py`) are excluded from gap accounting — a
  PR that adds tests should not be penalised for those lines being uncovered.

## Analysis Rules

### Function Detection

Parse diff for:

- `func (receiver) FunctionName(` - Go methods
- `func FunctionName(` - Go functions
- Added/Modified/Deleted based on diff markers (+/-)

### Type Detection

Parse diff for:

- `type TypeName struct {`
- `type TypeName interface {`
- Field additions/removals within structs

### API Detection

Look for:

- Route registrations (e.g., `router.Handle`, `http.HandleFunc`)
- OpenAPI/Swagger annotations
- CRD changes (in `api/` or `config/` directories)

### Configuration Detection

Look for:

- Feature gates
- Environment variables
- ConfigMap references
- Platform CR fields

### Review Insight Extraction

From review comments, extract:

- **Edge cases**: Comments mentioning "edge case", "corner case", "what if"
- **Concerns**: Comments with "concern", "worry", "problem", "issue"
- **Suggestions**: Comments with "suggest", "should", "consider", "might want"

## File Categorization

Read `{project_context.config_dir}/components.yaml` for project-specific file categorization rules.

The following is an example of directory-to-category mapping (actual mappings come from `components.yaml`):

| Directory Pattern | Category |
|:------------------|:---------|
| `pkg/controllers/` | controllers |
| `pkg/handlers/` | handlers |
| `pkg/api/` | api |
| `api/`, `staging/` | api |
| `tests/`, `*_test.go` | tests |
| `config/`, `deploy/` | config |
| `cmd/` | cmd |
| `pkg/util/`, `pkg/util*/` | util |

## Usage Notes

1. **Focus on Behavioral Changes**: Identify what the PR changes functionally
2. **Ignore Noise**: Skip formatting-only changes, comment updates
3. **Highlight Test Implications**: Note what new tests should cover
4. **Extract Edge Cases**: Review comments often reveal test scenarios
