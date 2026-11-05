---
test_case_id: TC-COMPACT-001
source_key: RHAISTRAT-1456
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-06-12"
---
# TC-COMPACT-001: Compaction triggers at context window limit

**Objective**: Validate that the Compaction API automatically compresses
conversation history when the session approaches the model's context
window limit.

**Preconditions**:

- OGX deployed on port 8321 with Compaction API provider
  registered in config.yaml
- PostgreSQL session store available on port 5432
- Target model served via vLLM with a known context window
- Compaction API (upstream PR #5327) merged or cherry-picked

**Test Steps**:

1. Create a new session by sending a POST to
   `/v1/chat/completions` with a unique `session_id` and
   `stream=true`
2. Send a long sequence of tool-call turns that accumulates enough
   context for the configured compaction policy to activate
3. Monitor OGX behavior for Compaction API invocation
4. After compaction triggers, send a follow-up prompt asking the
   model to summarize the first 5 files read in the session
5. Inspect session state through the supported observability path

**Expected Results**:

- Compaction API is invoked automatically before context window
  overflow
- Post-compaction session state contains a compressed summary
  that is shorter than the raw conversation history
- Model correctly references key facts from pre-compaction turns
  (file names, content patterns) in its summary response
- No HTTP 500 errors or context window overflow errors during
  the session

**Validation**:

- Automation verifies compaction metadata and size reduction using
  the configured harness metrics or storage inspection path.

**Notes**: To be filled later in the process.
