---
test_case_id: TC-TMPL-005
source_key: RHAISTRAT-2493
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-TMPL-005: Verify RELATED_IMAGE reference in operator CSV

**Objective**: Confirm that the RHOAI operator ClusterServiceVersion
includes the vLLM-Omni container image in its `relatedImages` list
for disconnected deployment support.

**Preconditions**:

- RHOAI operator is installed on the cluster

**Test Steps**:

1. Via `ClusterServiceVersion.get()`, retrieve the RHOAI operator CSV.
2. Access `.instance.spec.relatedImages` and search for an entry where
   `.image` contains `vllm-omni`.
3. Assert the matching entry uses `@sha256:<digest>` format, not a
   mutable tag.

**Expected Results**:

- The CSV `relatedImages` list contains an entry with `vllm-omni`
  in the image path (registry namespace is release-channel-dependent:
  `registry.redhat.io/rhaii/` for GA, `registry.redhat.io/rhaii-early-access/`
  for EA; do NOT assert a hardcoded registry path)
- The image reference uses `@sha256:<digest>` format, not a
  mutable tag
- The `RELATED_IMAGE` environment variable in the ServingRuntime
  resolves to the same digest

**Notes**: To be filled later in the process.
