# RHOAIENG-70680 — QualityFlow round 6

Same counting rules and 23 requirements as `h2h-round2/neutral/part2.md`; generator and round-4 numbers carried forward from the supplied scorecards. All 36 STD scenarios checked for correctness and coverage; all are NEW. Shipped reference: model-registry `6fd5bce`, opendatahub-tests `c9ce889`, and the previously verified metadata-collection code available under `scratchpad/h2h/score4/src/model-metadata-collection/`.

| Metric | Generator | QF round 4 | QF round 6 |
|---|---|---|---|
| Wrong / total | 23/47 | 0/52 (3/52 strict overclaim reading) | **4/36** |
| Redundant new cases / total | 40/47 | 3/52 | **0/36** |
| Requirements covered / total | 14/23 | 21/23 | **18/23** |
| Runnable as written / after TBDs / total | 5/10 sampled; after-TBD count not separately reported | 6/6/10 sampled | **0/0/10 sampled** |
| Real problems found, verified | 0 | 6 | **0** |

Wrong: TS-02 explicitly sends “framework, agent-type and tag filters separately and together”; TS-06 expects “framework, agentType and tags options.” Shipped `api/openapi/src/plugins/agent.yaml:137` defines framework and labels, with no agentType or tags fields. These are concrete assumptions outside TBDs.
TS-20 expects image-artifact and template-artifact items in the artifact listing; TS-21 requires both kinds in paginated, type-filtered artifact requests. The shipped endpoint serves template artifacts; `AgentArtifactTypeQueryParam` at `agent.yaml:247–250` permits only template-artifact. Inline images remain valid (TS-22). Other unresolved contracts are not counted wrong; unattached Jira-derived constant values are not treated as executed commands.

Redundant: compare against the actual pre-feature tests snapshot, **c7ea74c**, not current-main c9ce889 used in the earlier rounds. Searching snapshot `tests/ai_hub/` for `agent_catalog`, agent test names and `/agents` finds no agent-specific tests; the regression analysis independently records `existing_test_coverage: []`.
Thus none of the 36 NEW cases duplicates an existing agent assertion as of this snapshot. Later agent tests on current main do not make these cases redundant retroactively.

Covered: R1→11, R2→12, R4→01/02, R5→03, R6→08/09, R7→06, R8→07, R9→07, R11→16, R13→16/17, R14→35/36, R15→20/21, R17→23, R18→27, R19→28/29, R20→25/26, R22→30/31, R23→32/33/34 (numbers are TS suffixes). Wrong cases still count toward coverage.
Missing: R3 registered/healthy agent plugin, R10 operator ConfigMap/mount/`--catalogs-path` wiring, R12 removeDefaultSource, R16 default template name agent.yaml, R21 authoring skill (explicitly excluded). TS-10 checks empty-source startup, not plugin registration/readiness; TS-28 checks content equality with an input agent.yaml, not the default artifact name. Jira constants naming operator wiring are not test assertions.

Runnable: **36 > 20**, so `random.seed(70680); random.sample(range(1,37),10)` over sorted test_id selects **004, 005, 016, 021, 023, 025, 029, 033, 034, 036** (shown sorted). None is runnable as written or solely by answering its TBDs.
Examples: TS-23 says “Send an artifact request” without a request; TS-25 supplies no update configuration or reload synchronization; TS-33 supplies no Markdown input or generation command; TS-36 names no reference examples. All retain prose setup/execution and empty `api_endpoints`/`resource_definitions`; TS-21 is also wrong. Go stubs only call `t.Skip`, so compilation would not execute the checks.

Problems: no verified shipped-code defect, test defect, or explicitly identified shipped-coverage gap is raised. The STP's route disagreements and remote-fetch contracts are requests for clarification, excluded by metric 5.
The regression analysis reports no agent implementation in the pinned checkout and labels every agent scenario an unvalidated recommendation. Proposing TS-25/26, TS-30 and TS-32 does not itself identify a missing shipped test; round-2/4 findings cannot be credited to this output.

`lsp_status: partial`. Exact note: “Shared catalog definitions and cross-file references traced; AgentLoader not found. No agent implementation exists in pinned checkouts.” Shared ReadSourceConfig and RegisterAllFlags traces are reported; agent scenarios have `lsp_validated: false`.

Solution exposure: **no evidence found**. The apparently implementation-specific constants `resolveReadmeLinks()`, `net/url.ResolveReference`, `ReadmePath`, and `FetchReadme` explicitly cite linked Jira descriptions in `source_file`, rather than solution code. The regression note says “Proposed agent scenarios are unvalidated recommendations, not observed implementation behavior”; source snapshot HEAD is `352ff43`. This is consistent with pre-feature access, though output inspection alone cannot prove access history.

SUMMARY | RHOAIENG-70680 | wrong 4/36 | redundant 0/36 | covered 18/23 | runnable 0/10 | problems 0
