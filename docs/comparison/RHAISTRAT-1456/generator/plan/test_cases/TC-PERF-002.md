---
test_case_id: TC-PERF-002
source_key: RHAISTRAT-1456
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-06-12"
---
# TC-PERF-002: OGX proxy overhead

**Objective**: Measure the latency overhead introduced by the
OGX proxy layer between the client and vLLM using paired request
samples.

**Preconditions**:

- OGX deployed on port 8321
- vLLM serving target model on port 8000
- Both services accessible from the test client pod
- No other load on the cluster during measurement
- Warm-up iterations completed before measurement starts
- Network latency and baseline repeatability are within the configured
  thresholds for the target cluster

**Test Steps**:

1. Prepare an identical request payload:
   `{"model": "<target_model>", "messages": [{"role": "user",
   "content": "What is 2 + 2?"}], "stream": true}`
2. For each prompt in the sample set, rapidly interleave paired
   direct and proxied requests to minimize cache, CPU, and network
   drift between samples.
3. For each pair, send a direct request to vLLM at
   `http://<vllm>:8000/v1/chat/completions` and the matching request
   through OGX at `http://<llamastack>:8321/v1/chat/completions`,
   recording TTFT for the same prompt and state.
4. Calculate the paired per-request overhead:
   `overhead = ttft_ogx - ttft_vllm`
5. Compute p50, p95, and p99 over the paired overhead distribution

**Expected Results**:

- Proxy overhead remains within the configured performance budget
  for the selected model and hardware
- Paired samples show stable overhead without unexplained outliers
- Any warning-level latency signals are captured by automation for
  follow-up triage

**Notes**: To be filled later in the process.
