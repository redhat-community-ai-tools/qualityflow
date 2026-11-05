---
test_case_id: TC-SEC-001
source_key: RHAISTRAT-2493
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-SEC-001: Verify no audio content logged in pod logs (biometric PII)

**Objective**: Confirm that the vLLM-Omni pod does not log audio content,
base64-encoded audio data, or other biometric PII at any log level (DEBUG, INFO,
WARNING, ERROR), satisfying the Tech Preview ship gate requirement.

**Preconditions**:

- vLLM-Omni InferenceService is deployed and Ready
- Pod log level is at the default INFO level as set by the template
- A second deployment with container log level set to DEBUG is available or can be
  created for the DEBUG-level audit phase

**Test Steps**:

1. **Phase A — INFO level audit**:
   a. Via `OpenAIClient.post("/v1/audio/speech")`, send at least 3 TTS requests
      with varied input prompts (include prompts with PII-like content such as
      names and phone numbers).
   b. Via `Pod.get_logs()`, collect all container logs for the pod.
   c. Assert no base64-encoded audio data, raw PCM content, or WAV/MP3 binary
      markers appear in the log output.
   d. Assert the input prompt text does not appear verbatim in the logs.
   e. Assert no speaker identifiers or biometric labels appear in the logs.
2. **Phase B — DEBUG level audit**:
   a. Re-deploy the InferenceService (or patch the existing pod) with container
      log level set to DEBUG (e.g., via `--log-level DEBUG` container arg).
   b. Repeat steps 1a through 1e against the DEBUG-level deployment.
   c. Via `Pod.get_logs()`, collect all container logs at DEBUG verbosity.
   d. Assert the same PII-absence conditions hold at DEBUG log level.

**Expected Results**:

- No audio binary data, base64-encoded audio, or raw PCM content appears in pod
  logs at either INFO or DEBUG level
- Input text prompts are not logged verbatim at either log level
- No speaker identifiers or biometric PII indicators appear in log output at
  either log level
- The default template does not set the log level to DEBUG (Phase A validates
  this indirectly)

**Notes**: To be filled later in the process.
