---
name: std-reviewer
description: Semantic QE review of STD YAML and test stubs against STP traceability, pattern correctness, and PSE quality
model: claude-opus-4-6
version: 1.1.0
---

# STD Reviewer Skill

**Phase:** Post-Generation Review · **User-Invocable:** false
Invoked by the **review-std** command after `/std-builder` generates an STD.

## Purpose

A comprehensive **semantic QE review** of a generated STD (YAML + test stubs):
traceability to the source STP, pattern matching correctness, test step quality, PSE
docstring quality, and code generation readiness.

**Zero-trust principle:** never trust STD metadata counts — count actual scenarios. Never
trust traceability claims — verify every requirement_id against the source STP.

## Two-Layer Review Architecture

- **Layer 1 (General):** shared pipeline rules embedded in this file — always active.
- **Layer 2 (Project-specific):** pattern mappings, helper libraries, and code
  conventions from `{project_context.config_dir}/review_rules.yaml`, passed as context
  by review-std.

Loaded `std_rules.*` keys refine individual dimensions (pattern tables, decorator maps,
test ID formats, timeout ranges, stub conventions). The full key→dimension mapping table
is in **`reference/key-maps.md`** in this skill directory — Read it only when
review_rules is actually loaded and you need to resolve a key. **Graceful degradation:**
with no `review_rules.yaml`, all dimensions still apply using the built-in general rules;
config adds precision, never coverage.

## Input

```yaml
std_yaml_path: "outputs/{JIRA_ID}/std/{JIRA_ID}_test_description.yaml"
stp_file_path: "outputs/{JIRA_ID}/stp/{JIRA_ID}_test_plan.md"
go_stubs_dir: "outputs/{JIRA_ID}/std/go-tests/"       # may not exist
python_stubs_dir: "outputs/{JIRA_ID}/std/python-tests/" # may not exist
project_context: <from project-resolver, includes repo_rules>
review_rules: <from review_rules.yaml, if available>
```

### repo_rules Integration

When `project_context.repo_rules` is available, validate stubs against the target repo's
standards. **Severity: MAJOR** for any violation — these are the team's own standards and
violations cause PR review friction.

**From `repo_rules.agents_rules` (AGENTS.md):** `tier2` marker NOT explicitly added
(implicit); team markers (`network`, `storage`, ...) NOT explicitly added; no
`pytest.skip/skipif` anywhere; fixture names are nouns, not verbs; `__test__ = False`
placement per rules (class-level for grouped, after function for standalone);
`conftest.py` holds only fixtures (no helpers); module docstring contains the STP link;
resources named by function ("client pod"), not generic labels ("pod-A");
`@pytest.mark.incremental` for dependent tests, not `pytest-dependency`.

**From `repo_rules.std_format` (SOFTWARE_TEST_DESCRIPTION.md):** PSE docstrings use exact
section names `Preconditions:`, `Steps:`, `Expected:`; `[NEGATIVE]` indicator on failure
scenarios; assertion wording follows the document's patterns; shared preconditions in
class/module docstring, test-specific in test docstring; each test verifies ONE thing
with ONE `Expected:` assertion; no fixture names in Preconditions (natural language).

## Output

Review report written to `outputs/{JIRA_ID}/reviews/{JIRA_ID}_std_review.md`.

---

## Review Dimensions

7 dimensions; every finding is classified:

| Severity | Meaning | Impact on Verdict |
|:---------|:--------|:------------------|
| **CRITICAL** | Missing traceability, invalid YAML, or error producing broken tests | Blocks approval |
| **MAJOR** | Quality issue, wrong pattern, or gap to address | Flags for attention |
| **MINOR** | Improvement suggestion / stylistic | Informational only |

---

### Dimension 1: STP-STD Traceability

Verify complete bidirectional traceability between STP and STD.

#### 1a. Forward Traceability (STP → STD)

Parse STP Section III; per row extract Requirement ID, Requirement Summary, Test
Scenario(s), Tier, Priority; search the STD `scenarios` array for a match.

**Matching algorithm (deterministic, in order):**
1. **Requirement ID exact match (required):** STD `requirement_id` must exactly match a
   Section III Requirement ID; no match → orphan.
2. **Scenario text similarity (for multi-scenario requirements):** keyword overlap —
   extract keywords (nouns/verbs, minus stop words); overlap =
   `shared / min(keywords_A, keywords_B)`; ≥ 0.50 counts as a match; multiple matches →
   highest overlap wins.
3. **Tier match** and 4. **Priority match** (P0/P1/P2): a mismatch is a separate MAJOR
   finding, not a traceability failure.

**Classification:** Full match = ID match AND overlap ≥ 0.50 → traced. Weak match = ID
match, overlap < 0.50 → MAJOR ("scenario text diverges significantly from STP — verify
correct mapping"). No ID match → CRITICAL (orphan).

**Red flags:** **CRITICAL:** STP scenario with no STD scenario (coverage gap).
**MAJOR:** tier or priority mismatch for the same scenario.

#### 1b. Reverse Traceability (STD → STP)

Per STD scenario: `requirement_id` exists in STP Section III; description relates to the
STP row.
**CRITICAL:** STD scenario with no STP row (orphan). **MAJOR:** requirement_id not found
in STP.

#### 1c. Count Consistency

`document_metadata.total_scenarios`, `tier_counts`, and `p0_count` must match actual
array counts. **CRITICAL:** any mismatch.

#### 1d. STP Reference

`document_metadata.stp_reference.file` points to the actual STP file, valid path,
expected pattern. **MAJOR:** wrong path or missing file.

#### 1e. Priority-Testability Consistency

**CRITICAL:** a P0 scenario whose test_objective/test_steps say it "cannot be verified at
this stage" or "requires infrastructure not yet available" — cannot be both
highest-priority and untestable. Downgrade priority, resolve the blocker, or defer to a
follow-up STD.

#### 1f. Traceability ID Checklist (required on EVERY scenario)

- [ ] `requirement_ids` present and non-empty — copied verbatim from the STP scenario's
  requirement references: Jira keys and/or two-tier `REQ-{JIRA_KEY}-{NN}` ids
  (e.g. `REQ-PROJ-72329-01`).
- [ ] `stp_scenario_id` present — the STP scenario heading id in `TS-{NN}` form
  (e.g. `TS-01`), copied verbatim.

**MAJOR:** either field missing or empty on any scenario.

---

### Dimension 2: STD YAML Structure (v2.1-enhanced)

#### 2a. Document-Level Structure

- [ ] `document_metadata` with all required fields; `std_version` = "2.1-enhanced"
- [ ] `code_generation_config` exists (v2.1); its `std_version` = "2.1-enhanced";
  `package_name` inferred from `owning_sig`
- [ ] `common_preconditions` exists
- [ ] `scenarios` array exists and is non-empty

#### 2b. Per-Scenario Required Fields

Every scenario must have: `scenario_id` (sequential); `test_id` (format per config
`patterns.test_id_format`, default `TS-{JIRA_ID}-{NUM:03d}`); `tier` (a project-defined
tier); `priority` ("P0"/"P1"/"P2"); `requirement_id` (Jira key); `requirement_ids`
(v2.1: non-empty, verbatim from STP); `stp_scenario_id` (v2.1: e.g. "TS-01", verbatim);
`patterns` (primary + helpers); `variables` (closure_scope array); `test_structure`
(describe/context/it); `code_structure`; `test_objective` (title, what, why,
acceptance_criteria); `test_data` (resource_definitions and/or api_endpoints);
`test_steps` (setup, test_execution, cleanup arrays); `assertions` (≥1).

**CRITICAL:** any required field missing; `test_id` not in the expected format.
**MAJOR:** duplicate `scenario_id`/`test_id`; `tier` not matching any project tier.

#### 2c. v2.1-Specific Checks

**Universal (all tiers):** `variables.closure_scope` includes the tier-appropriate
required variables (config `patterns.closure_scope_required`); every scenario with setup
steps has corresponding cleanup steps.

**Per-tier framework checks** — match each scenario's `tier` to its tier config's
`language`/`framework`; do NOT assume which tier uses which language — read the project's
`tier*.yaml`.

*Go (tier config `language: "go"`):* `test_structure.context.decorators` includes Ordered
(if `ginkgo-v2`); code templates use `=` not `:=` for closure variables; `Expect(err)` →
`ExpectWithOffset(1, err)` (if `ginkgo-v2`); closure_scope includes `ctx` and `namespace`
(or per config).

*Python (tier config `language: "python"`):* no Go constructs (Ordered, BeforeAll,
ExpectWithOffset); `@pytest.mark.incremental` for dependent tests, not
`pytest-dependency` (if `pytest`); fixture names are nouns (per repo_rules); no
`pytest.skip/skipif` (per repo_rules).

*Cross-framework:* no constructs from one tier's language in a different-language tier's
scenarios.

**MAJOR:** missing required closure_scope variables; missing Ordered on a Go/Ginkgo
scenario; framework mismatch across languages; `pytest-dependency` instead of
`@pytest.mark.incremental`. **MINOR:** `:=` for a Go closure variable (should be `=`).

---

### Dimension 3: Pattern Matching Correctness

#### 3a. Primary Pattern

Per scenario, read test_objective.title and test_steps; verify the primary pattern
matches the dominant action/domain (config `patterns.keyword_to_pattern` when loaded;
otherwise keyword heuristics).
**MAJOR:** pattern doesn't match scenario keywords; no primary pattern. **MINOR:**
too-generic pattern when a more specific one exists.

#### 3b. Helper Library Mapping

`patterns.helpers_required` must include the correct libraries for the matched patterns
(config `patterns.pattern_to_helpers`; otherwise consistency with the pattern and steps).
**MAJOR:** missing required helper. **MINOR:** unneeded extra helper.

#### 3c. Decorator Assignment

Config `patterns.sig_to_decorator` when loaded; otherwise verify tier decorators match
the scenario's tier, SIG/domain decorators match the subject area, and ordering
decorators exist where tests have dependencies. Always: scenario with tier X → decorator
matching tier X; ordered tests → Ordered decorator.
**MAJOR:** wrong tier decorator; missing SIG/domain decorator. **MINOR:** missing Ordered
decorator (should always be present).

#### 3d. Pattern Library Validation

If `{project_context.config_dir}/patterns/tier1_patterns.yaml` exists, every `pattern_id`
in test_steps must reference a real pattern.
**MAJOR:** pattern_id not in the library. **MINOR:** code template diverges significantly
from the library template.

---

### Dimension 4: Test Step Quality

#### 4a. Step Completeness

Per scenario: ≥1 setup step, ≥1 test_execution step, ≥1 cleanup step.
**CRITICAL:** no test_execution steps. **MAJOR:** no cleanup (resource leak).
**MINOR:** no setup (may be intentional via common_preconditions).

#### 4b. Step Quality

Per step: `action` specific and actionable; `command`/code reference where applicable;
`validation` describes the expected outcome; step IDs sequential (SETUP-01, TEST-01, ...).
**MAJOR:** vague action ("Verify it works", "Check the result"); missing validation on a
test_execution step; uncertain verification language ("may be set", "might appear",
"should probably") — verification must be definitive. **MINOR:** non-sequential step IDs.

#### 4b.2. Abstraction Level in Test Steps

Steps and assertions use user-observable language.
**MAJOR:** internal component names ("controller removes", "handler unmounts",
"reconciler updates"); internal API object references where user-facing language
suffices; implementation verbs (reconcile, sync, propagate).
**Acceptable:** user-observable descriptions ("volume is automatically removed from the
running instance"); API-level descriptions when the API is the user interface ("resource
status shows Ready").

#### 4c. Logical Flow

Setup creates resources before execution uses them; cleanup removes what setup created;
no circular dependencies.
**MAJOR:** step references a resource not created in setup. **MINOR:** cleanup misses
some setup resources.

#### 4c.2. STP Customer Use Case Alignment

Cross-reference test setup against the STP's customer use cases — setup should reflect
realistic user workflows.
**MAJOR:** multi-step resource creation where the STP describes a single-shot user
action; setup implying a workflow no real user follows; unnecessary dependencies between
independent scenarios (each independently verifiable unless explicitly modeling a
sequential workflow, e.g. upgrade before/after).
**MINOR:** intermediate verification steps that belong in preconditions ("Verify no
connectivity" as a setup step).

#### 4d. Upgrade Test Structure

Upgrade scenarios (Tier 2, "upgrade" in title/objective) must follow before/after:
(1) verify pre-upgrade, (2) perform upgrade, (3) verify post-upgrade.
**MAJOR:** missing "before" verification (can't detect regression) or missing "after"
verification (incomplete). **MINOR:** not placed in the dedicated upgrade module/
directory structure.

#### 4e. Test Dependency Structure

Dependencies between scenarios must be justified. **Acceptable:** upgrade sequences;
ordered classes with early-failure markers; sequential lifecycle
(create→modify→verify→delete).
**MAJOR:** B depends on A but they test independent features (fragile suites); dependency
chain without an early-failure marker / ordered decorator (failures must cascade);
resource sharing between unrelated scenarios just to save setup cost — prefer
independence over speed.
**MINOR:** justified dependency with no documented direction (`depends_on`/ordering note).

#### 4f. Assertion Quality

Per assertion: `description` specific; `condition` measurable; `priority` assigned
(P0/P1).
**MAJOR:** generic description; no assertions in a scenario. **MINOR:** all assertions P0
(unrealistic — some should be P1).

---

### Dimension 4.5: STD Content Policy

STD artifacts contain design-level content only — no implementation details, invalid
references, or other-phase content.

#### 4.5a. Banned Content

**STD YAML — MAJOR:** `related_prs` or any PR URL list in `document_metadata` (PR URLs
are implementation artifacts belonging in the STP; the STD describes *what* to test, not
*what code changed*); branch names, commit SHAs, or review links in metadata.
**Stub files — MAJOR:** PR URLs/references (`PR #16412`, `github.com/.../pull/...`) in
docstrings; branch/commit references; developer names or assignees (QE Owner "TBD" is
fine).
**MINOR:** references to nonexistent documents; hardcoded local paths.

#### 4.5b. No Implementation Details in Stubs

Stubs describe **what** to test, not **how** — they are design artifacts for review.
**MAJOR:** fixture implementations (yield/return bodies); helper function
implementations; imports of project-internal modules that only make sense at
implementation time; concrete API/SDK calls in stub bodies (pending-marker bodies only).
**Acceptable:** PSE docstrings; pending-marker bodies per project conventions (config
`stub_conventions`, e.g. `PendingIt()` for Go, `pass` for Python); stdlib imports for
type annotations; declarations with descriptive names.

#### 4.5c. Test Environment Separation

Tests assume infrastructure is in place — no environment setup in stubs.
**MAJOR:** infrastructure device creation/configuration; cluster node setup/labeling;
feature-gate enablement code; network/storage provisioning.
**MINOR:** comments describing environment requirements that belong in STP II.3.

---

### Dimension 5: PSE Docstring Quality (Stub Files)

#### 5a. Go Stubs (if present)

Read each `*_stubs_test.go`. Per pending test block: PSE comment block present;
**Preconditions** specific with concrete resources (GOOD: "Running instance with network
interface on test network"; BAD: "Resource exists"); **Steps** numbered, actionable,
unambiguous (GOOD: "1. Patch resource spec to change network reference"; BAD: "1. Change
the network"); **Expected** measurable (GOOD: "Instance connects to new network;
connectivity check succeeds"; BAD: "It works"). Also: each block contains a test_id in
the expected format; module comment references the STP file (not PR URLs); proper test
framework structure (compiles conceptually).

#### 5b. Python Stubs (if present)

Read each `test_*_stubs.py`. Per test function: PSE docstring in the body; same quality
criteria as Go; test collection disabled at module level (per stub conventions); body
contains only the pending marker.

#### 5c. PSE Section Classification (strict)

- **Preconditions** = true BEFORE the test: resource existence, state conditions,
  configuration, data recorded at class/setup level ("MAC address recorded").
- **Steps** = ACTIONS the test performs: API calls, user operations, state changes.
  Never "Verify..." — verification belongs in Expected.
- **Expected** = OBSERVABLE OUTCOMES with HOW to verify, measurable (GOOD: "Connectivity
  check from instance to peer on network2 succeeds with 0% packet loss"; BAD: "Instance
  is connected to network2" — no verification method; GOOD: "Resource status shows Ready
  within expected timeout"; BAD: "Resource works correctly").

**MAJOR:** "Verify..." in Steps; baseline verification in Steps ("Verify no connectivity
before change" — that's a precondition confirming initial state); Expected without a
verification method. **MINOR:** a precondition listed as a Step ("Ensure instance is
running").

**Other red flags:** **CRITICAL:** missing PSE docstring in a stub. **MAJOR:**
generic/vague P, S, or E; missing test_id in name or docstring; PSE not
standalone-readable — a reader without the STP must understand the test; unexplained
abbreviations/domain references need a brief inline explanation (BAD: "1. Perform
measurement X"; GOOD: "1. Measure network connectivity downtime during rolling update").
**MINOR:** PSE references internal mechanisms instead of user actions.

#### 5d. Stub Completeness for Integration Areas

Stubs must cover all integration areas in the STD scenarios.
**MAJOR:** STD has upgrade scenarios but no upgrade stub file; migration scenarios but no
migration stub. **MINOR:** area stubs exist but miss some scenarios (including
snapshot/restore areas).

---

### Dimension 6: Code Generation Readiness

Will the STD YAML produce valid, compilable test code?

#### 6a. Variable Declarations

Per `variables.closure_scope` entry: valid identifier and type for the target language;
`initialized_in` is a valid lifecycle hook; `used_in` hooks valid.
**MAJOR:** invalid type; initialized in a hook that runs after its usage hook.
**MINOR:** declared but never referenced in code_structure.

#### 6b. Import Completeness

Cross-reference `patterns.helpers_required` across scenarios against
`code_generation_config.imports`.
**MAJOR:** helper used but import missing. **MINOR:** import listed but unused.

#### 6c. Code Structure Validity

Per `code_structure`: valid framework structure (config `patterns.framework_structure`
when loaded); brackets matched; test_id placeholder in correct format; no syntax errors
in the template.
**MAJOR:** malformed structure. **MINOR:** missing test_id in test block description.

#### 6d. Timeout Appropriateness

Config `std_rules.timeouts` when loaded; otherwise heuristics: long-running operations
(resource creation, migration) need larger timeouts than quick ones (API calls, status
checks).
**MINOR:** oversized timeout for a simple operation; no timeout for a long-running one.

---

## Review Report Format

Markdown with these sections, in order:

1. `# STD Review Report: {JIRA_ID}` + header lines: Reviewed (STD YAML, STP source, Go
   stubs dir or "N/A", Python stubs dir or "N/A"), Date, Reviewer `QualityFlow Automated
   Review (v1.1.0)`, Review Rules Schema
   (`review_rules._extraction_metadata.schema_version` or "N/A").
2. `## Verdict: {APPROVED | APPROVED_WITH_FINDINGS | NEEDS_REVISION}` — human-readable.
3. `## Summary` — table: Dimensions reviewed (X/7), Critical/Major/Minor finding counts,
   Confidence (HIGH/MEDIUM/LOW).
4. `## Traceability Summary` — table: STP scenarios, STD scenarios, forward coverage
   STP→STD (X/Y, %), reverse coverage STD→STP (X/Y, %), orphan STD scenarios, missing
   STD scenarios.
5. `## Findings by Dimension` — one subsection each for Dimensions 1, 2, 3, 4, 4.5, 5,
   6. Dim 3: per-scenario table `Scenario | Primary Pattern | Helpers | Decorators |
   Status (PASS/WARN/FAIL)`. Dim 4: per-scenario table `Scenario | Setup | Execution |
   Cleanup | Assertions | Status`. Dim 5: findings per stub file, split Go/Python.
   Others: findings prose.
6. `## Recommendations` — numbered, severity-ordered, each prefixed
   **[CRITICAL]**/**[MAJOR]**/**[MINOR]**.
7. `## Confidence Notes` — factor table (STD YAML parseable; STP available; Go stubs
   present; Python stubs present; pattern library available; all scenarios reviewed;
   review rules loaded — YES/NO each) + confidence rationale.
8. The machine-readable verdict block — the very last content in the file.

Abbreviated example:

````markdown
# STD Review Report: PROJ-123
## Verdict: NEEDS_REVISION
## Summary
| Metric | Value |
|:-------|:------|
| Critical findings | 1 |
## Traceability Summary
| Forward coverage (STP→STD) | 11/12 (92%) |
## Findings by Dimension
### Dimension 1: STP-STD Traceability
...
## Recommendations
1. **[CRITICAL]** ...
## Confidence Notes
```yaml
verdict: NEEDS_REVISION
critical_count: 1
major_count: 3
minor_count: 2
```
````

## Machine-Readable Verdict Block (required)

The report MUST end with exactly one fenced yaml block as its final content:

```yaml
verdict: APPROVED | APPROVED_WITH_FINDINGS | NEEDS_REVISION
critical_count: N
major_count: N
minor_count: N
```

Exactly these four keys; `verdict` is one of the three values; counts are integers
matching the Summary table. This block supplements — never replaces — the human-readable
`## Verdict:` line and does not change verdict semantics.

---

## Verdict Criteria

| Verdict | Criteria |
|:--------|:---------|
| `APPROVED` | 0 critical findings, 0 major findings |
| `APPROVED_WITH_FINDINGS` | 0 critical findings, 1+ major or minor findings |
| `NEEDS_REVISION` | 1+ critical findings |

---

## Confidence Scoring

| Level | Criteria |
|:------|:---------|
| `HIGH` | STD YAML valid, STP available, stubs present, pattern library available, all 7 dimensions reviewed, review rules `default_ratio <= 0.30` |
| `MEDIUM` | STD YAML valid and STP available, but stubs or pattern library missing, OR review rules `default_ratio <= 0.60` |
| `LOW` | STD YAML valid but STP unavailable (STD-only review), OR review rules `default_ratio > 0.60` |

When `review_rules._extraction_metadata.default_ratio > 0.50`, add to Confidence Notes:
"Review precision reduced: {X}% of rules using generic defaults. Consider adding
project-specific `review_rules.yaml` or enabling `repo_files_fetch`."

---

## Error Handling

- **STD YAML not found:** return error, no review report.
- **STD YAML invalid:** CRITICAL finding; attempt partial review of what parses.
- **STP not found:** skip Dimension 1 (traceability); confidence LOW; note in report.
- **Stub files not found:** skip Dimension 5 (PSE quality); note in report.
- **Pattern library not found:** skip 3d; note in report.
- **project_context unavailable:** skip pattern library and import checks; note in report.
- **review_rules.yaml not found:** general rules only (all dimensions still apply,
  reduced precision); note in Confidence Notes.

---

**End of STD Reviewer Skill**
