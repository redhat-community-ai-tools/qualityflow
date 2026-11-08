---
test_case_id: TC-STAB-004
source_key: RHAISTRAT-2493
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-STAB-004: Verify OmniVoice (k2-fsa) 50-turn session stability

**Objective**: Confirm that OmniVoice (k2-fsa, 0.6B) sustains 50 consecutive
voice turns without pod restart or session reset — no latency or quality
thresholds applied (deferred to eval framework per strategy).

**Preconditions**:

- OmniVoice InferenceService is deployed and Ready (shares class-scoped
  deployment with TC-TTS-005 via TestOmniVoiceInference class; model weights
  available in S3 models bucket, downloaded by KServe storage initializer at
  pod startup)
- 50-prompt corpus available

**Test Steps**:

1. Send 50 sequential `/v1/audio/speech` POST requests via `OpenAIClient.post()`
   using the fixed prompt corpus (15-word median, 10-20 word range).
2. Record pod restart count before and after via `get_restart_counts()`.
3. Assert all 50 requests return HTTP 200.
4. Assert pod restart count delta == 0.

**Expected Results**:

- All 50 requests return HTTP 200 with non-empty audio response
- Pod restart count remains 0
- No OOM events in pod logs

**Notes**: To be filled later in the process.
No TTFB or E2E latency assertions. Parametrize with TC-STAB-001 and TC-STAB-003
over (model, assert_latency: bool). pytest.param id: `test_omni_omnivoice_50turn_stability`
@pytest.mark.soak
@pytest.mark.vllm_omni
