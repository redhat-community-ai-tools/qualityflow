---
test_case_id: TC-COMPACT-002
source_key: RHAISTRAT-1456
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-06-12"
---
# TC-COMPACT-002: Post-compaction context accuracy

**Objective**: Validate that the model retains critical information
from earlier conversation turns after compaction has compressed
the session history.

**Preconditions**:

- OGX deployed with Compaction API provider enabled
- PostgreSQL session store on port 5432
- Session capable of reaching the configured compaction threshold

**Test Steps**:

1. Create a session with a unique `session_id`
2. Across enough tool-call turns to trigger compaction, embed several
   specific verifiable facts:
   - Turn 3: `read_file` on `/app/config.yaml` revealing
     `db_host: pgdb-prod-03.internal`
   - Turn 10: `bash` returning error
     `ConnectionRefusedError on port 6379`
   - Turn 20: `grep_search` finding variable
     `MAX_RETRIES = 7` in `retry_handler.py`
   - Turn 30: `write_file` creating `/tmp/patch-0612.diff`
   - Turn 45: `edit_file` changing function name from
     `process_batch` to `process_batch_v2` in `worker.py`
3. Continue sending turns until compaction triggers
4. After compaction, query the session validation fixture for the
   stored compaction metadata, including summary size, compaction
   timestamp, and preserved key-fact references.
5. Ask: "What was the database hostname in the config file?",
   "What port had a ConnectionRefused error?", "What was the
   MAX_RETRIES value?", "What diff file did we create?", "What
   function did we rename in worker.py?"

**Expected Results**:

- Model recalls the configured set of critical facts from
  pre-compaction history
- PostgreSQL compaction metadata shows that session history was
  summarized after the threshold was reached, including a recorded
  compaction timestamp and reduced stored-context size
- Stored key-fact references for the configured facts remain present in
  the session validation fixture after compaction
- Responses do not contain hallucinated details (e.g.,
  inventing a different hostname or port number)
- No errors indicating missing session context

**Notes**: To be filled later in the process.
