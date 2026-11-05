---
test_case_id: TC-UPG-001
source_key: RHAISTRAT-2277
objectives: [3, 9]
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
upgrade_phase: both
---
# TC-UPG-001: The 3.5-to-3.6 routing switchover preserves state and opens no traffic black hole

**Objective**: Verify that the upgrade repoints external routing to Praxis only after Praxis is
healthy, that no window exists in which the public endpoint serves neither backend, and that all
pre-upgrade state survives the transition.

**Preconditions**:

- Cluster at RHOAI 3.5 GA with OGX public and populated state: files, vector stores, conversations,
  and responses history
- A pre-upgrade state inventory captured with counts and sampled IDs per resource type
- A continuous probe able to issue `POST /v1/responses` against the external hostname at a fixed
  interval throughout the upgrade, recording every status code and timestamp

**Test Steps**:

1. Capture the pre-upgrade state inventory.
2. Start the continuous probe at a two-second interval against the unchanged external hostname.
3. Begin the 3.5-to-3.6 upgrade and let rhods-operator reconcile the Gateway and HTTPRoutes.
4. Throughout the upgrade, record the Ready condition transitions of the Praxis workload and the
   generation changes of the HTTPRoutes.
5. When the upgrade reports complete, stop the probe and analyse the recorded status codes,
   identifying the longest consecutive run of non-2xx responses.
6. Correlate the timestamp at which the HTTPRoute began pointing at Praxis against the timestamp at
   which Praxis first reported Ready.
7. Re-run the state inventory and compare against the pre-upgrade capture.

**Expected Results**:

- The HTTPRoute repoint timestamp is later than the first Praxis Ready timestamp — the switchover
  follows readiness rather than preceding it
- The probe records no consecutive run of failures longer than the documented acceptable upgrade
  disruption window. No such window is defined in the strategy, so the observed maximum gap is
  recorded as a measured baseline and reported for PM sign-off rather than asserted against a
  threshold
- Post-upgrade counts for files, vector stores, conversations, and responses equal the pre-upgrade
  counts
- Every sampled ID resolves with HTTP 200 after the upgrade
- The probe's external hostname is never changed during the run

**Validation**:

- `psql -c "SELECT count(*) FROM files_metadata;"` and the equivalent counts on
  `vector_store_metadata` and `ogx_kvstore` are unchanged across the upgrade

**Notes**: To be filled later in the process.
