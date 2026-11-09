# RHAISTRAT-2493 run 10 (vLLM-Omni serving runtime; QualityFlow main 3b7ffa3 on the shipped code, GLM 5.3): test grading

Paths: R = `<local>`, O = `R/qf/outputs/RHAISTRAT-2493`.
Product: `R/ship/odh-model-controller` at 1053962. `template:N` = `config/runtimes/vllm-omni/vllm-omni-cuda-template.yaml`.
Suite: `R/ship/opendatahub-tests` at 7ffaacc. `vo/` = `tests/model_serving/model_runtime/vllm_omni/`.
QF test file: `T` = `vo/test_qf_vllm_omni.py`, 11 tests in 5 classes. `git status` shows only this file as added, so no team file was touched. The file in O/python-tests is identical to it.

The STD has 29 scenarios. QF wrote tests for 11, declined 10 and marked 8 EXISTING_COVERAGE (3+8+9+12+13+14+18+26). Several QF tests are close copies of team tests that already ship in `vo/`: case 10 of `test_vllm_omni_probe_configuration`, case 15 of stability.py:141-226, case 16 of stability.py:252-413, case 25 of tts.py:296-347 and case 27 of tts.py:412-487. These cases are tagged PARTIAL_COVERAGE, but the copies do not test the gap the tag names.

## 1. QualityFlow tests (11)

| test (T::…) | plan case | class | evidence |
|---|---|---|---|
| TestQFVllmOmniReferenceDeployment::test_minimum_reference_gpu_allocation_serves_the_model | 7 serves on exactly two GPUs | REAL | Deploys Qwen3-Omni with `gpu_count: 2` through the suite fixtures (T:124-142; vo/conftest.py:179-184). It asserts the pod is Ready, the GPU request and limit are 2, and a chat completion returns 200 with content (T:156-176). The model name matches `--served-model-name={{.Name}}` (template:52). Caveats: the fixture uses `create_isvc`'s default 15-minute timeout (utilities/inference_utils.py:650), while the team gives this model 40 minutes (vo/s3/test_vllm_omni_e2e.py:94). The int-to-int compare at T:160-161 may also fail if an admission webhook rewrites the quantity as the string "2". |
| …::test_normal_initialization_avoids_premature_liveness_restarts | 10 no premature liveness restart | REAL | After Ready, every container restart count is 0 (T:186-188). The startup, readiness and liveness probes equal the shipped values (T:189-203; vo/constant.py:62-78 = template:62-79). |
| …::test_pipeline_metrics_expose_required_stage_dimensions | 23 native and wrapped metric families with stage and replica labels | WRONG | The assertion can never pass. `_extract_metric_families(prefix=VLLM_OMNI_METRIC_PREFIX)` keeps only `# TYPE` names that start with `vllm_omni:` (vo/constant.py:23; vo/utils.py:79-88). The required names (T:65-70) all start with `vllm:`, so `issubset` (T:229-230) is always false. The `_bucket` name could not match even with the right prefix, because `_bucket` series never appear on `# TYPE` lines. `vllm:gpu_cache_usage_perc` is the name the product's dashboard queries (internal/controller/constants/runtime-metrics.go:287), but the suite and Jira read the runtime's `vllm:kv_cache_usage_perc` (vo/constant.py:21; jira_data.yaml:25). The stage/replica label check (T:231-233) is never reached. |
| TestQFVllmOmniSpeechQuality::test_speech_streaming_and_supported_text_api_conformance | 11 speech streaming plus text API conformance | WEAK | One non-streaming WAV request is checked with `validate_tts_output` (Content-Type, size, RIFF; T:267-278; vo/utils.py:192-222), and `/v1/models` is checked for list shape and model id (T:280-291). The "speech streaming" half is never exercised, the `/v1/models` media type is not checked, and the speech part repeats the team's `test_vllm_omni_tts_qwen3_basic` (tts.py:160). |
| …::test_warm_tts_route_latency_meets_percentile_targets | 15 TTFB p95 ≤ 350 ms, E2E p95 ≤ 1.2 s per TTS model | WEAK | Sends 200 timed requests after warm-up but asserts the suite's relaxed limits, `TTFB_P95_THRESHOLD_S = 3.5` and `E2E_P95_THRESHOLD_S = 7.0` (T:319-320; vo/constant.py:26, :31). The plan and Jira require 350 ms and 1.2 s (jira_data.yaml:24, :89), so latencies 10x over target pass. Only Qwen3-TTS is measured, not Voxtral. In effect it re-runs the team test with the same limits (stability.py:141-226). |
| …::test_continuous_dialogue_maintains_latency_and_memory_stability | 16 ten-minute dialogue: no restart, TTFB ratio ≤ 1.25, memory growth within 15% | WEAK | The restart check (T:373-374) and the TTFB ratio (T:369-371) match the plan. Memory growth is checked as an absolute change in the 0-1 KV-cache fraction, `final - baseline <= 0.15` (T:372), which accepts 0.05 → 0.19 (+280%). The plan and Jira say "within 15% of GPU memory at minute 1" (jira_data.yaml:25), and the team's test checks the ratio (stability.py:395, :409). The test also lacks the team's `cluster_monitoring_config` (stability.py:248), so `get_metrics_value` can return None and `float(None)` fails at T:372. |
| …::test_voice_content_remains_absent_from_persistent_artifacts | 25 voice content absent from persistent logs and artifacts | REAL | Sends three PII prompts to `/v1/audio/speech`, then asserts the kserve-container log has no base64 audio block, no `RIFF`, no biometric keywords and no copy of any prompt (T:386-403). The pod has no other persistent store: only an emptyDir shm volume (template:59-61, :87-91). Only the default log level is covered. It duplicates tts.py:296-347. |
| …::test_restricted_egress_permits_local_model_serving | 27 local serving works while external egress is blocked | WRONG | The egress probe runs `exec` in a pod named `f"{isvc.name}-predictor-00000"` (T:118-120, :441-445). This class deploys in `Standard` mode, which is a raw deployment (utilities/constants.py:12-16). A raw deployment's pods carry generated ReplicaSet suffixes, and nothing in the suite builds that name (the suite looks pods up by label: utilities/infra.py:570-595; vo/conftest.py:232-241). The pod lookup therefore fails and the assertion `probe.rc != 0` (T:459) is never reached. The team's test of the same case resolves the pod by label (tts.py:461-466). |
| TestQFVllmOmniMissingStorage::test_missing_model_storage_prevents_successful_serving | 5 missing model storage stays unhealthy | REAL | Creates an ISVC on a model path that does not exist (T:468, :490-503). It waits for `FailedToLoad`, then asserts the ISVC is not Ready and that the model state contains `FailedToLoad` (T:505-515). The suite uses the same KServe signal for storage-initializer failures (tests/model_serving/model_server/kserve/negative/test_invalid_s3_credentials.py:59). No inference request is sent. |
| TestQFVllmOmniUndersizedGpu::test_undersized_gpu_allocation_cannot_falsely_report_readiness | 6 one GPU never reports Ready or healthy | WEAK | It only asserts "not Ready after 300 s" (T:562-567). A correct two-GPU deployment of the same model is also not Ready at 300 s: the startup probe allows 1200 s (template:62-67), and the team waits 40 minutes for Readiness (e2e.py:94). The assertion cannot tell failure from a normal slow start. The plan's health-endpoint check is missing. |
| TestQFVllmOmniUnavailableImage::test_unavailable_mirrored_images_prevent_successful_serving | 20 unavailable image stays visibly unhealthy | WEAK | It drives the product with a non-existent runtime image (T:596-616) but has the same "not Ready after 300 s" check as case 6 (T:617-620), which a valid image also passes. Nothing checks that the failure is visible (no ImagePullBackOff or model-state check), and no inference request is sent. |

Loads: 11/11 (loading/RHAISTRAT-2493.md: 1 file, no conftest changed, collected 11; pytest-tests.log shows SETUP for all 11).

## 2. QualityFlow declines (`not_implemented`, 10)

| plan case | class | evidence |
|---|---|---|
| 1 dashboard discovery and preview acceptance | JUSTIFIED | Needs dashboard UI automation. There is none in `tests/` or `utilities/` (no playwright or selenium), and the dashboard is not in the product checkout. The metadata half is in the template (template:5, :9, :17, :28) and the team already checks it (vo/s3/test_vllm_omni_template.py:123). |
| 2 declining preview acceptance | JUSTIFIED | Same reason: a dashboard dialog. |
| 4 dashboard deployment without YAML | JUSTIFIED | Same reason. The API deployment is already covered (vo/s3/test_vllm_omni_e2e.py:134). |
| 17 blinded listening with five raters | JUSTIFIED | Needs human raters; it cannot be automated. |
| 21 preview documentation matches the capability matrix | JUSTIFIED | No docs in either checkout. The template only links to the upstream project (template:12). |
| 22 deployment guide covers security and storage | JUSTIFIED | Same reason: no docs. |
| 24 unauthorized client cannot read `/metrics` | JUSTIFIED | The shipped runtime does not have this behaviour (see section 4). The runtime serves `/metrics` on port 8080 (template:34-35, :48, :56-58) in a single container with no auth proxy (template:41-86). The team's shipped test asserts an unauthenticated GET through the Route returns 200 (tts.py:633-664). |
| 19 mirrored runtime serves local PVC weights | AVOIDABLE | QF's reason is file placement, not a missing capability. The PVC fixtures (`vllm_omni_model_pvc`, `vllm_omni_pvc_downloaded_model_data`, `vllm_omni_pvc_inference_service`, vo/pvc/conftest.py:30-138) live in `vo/pvc/`, a subdirectory of the STD's own target directory, next to the team's PVC test (vo/pvc/test_vllm_omni_pvc.py:63). "No external download" can be enforced with the suite's egress NetworkPolicy pattern (tts.py:412-487). |
| 28 Omni configuration survives a product upgrade | AVOIDABLE | The suite has an upgrade mechanism: the `--pre-upgrade`/`--post-upgrade` split in the root conftest (conftest.py:289-309) and the `pre_upgrade`/`post_upgrade` markers. It has a model-serving pattern to copy: pre-upgrade inference, then post-upgrade "exists" and "not_modified" checks (tests/model_serving/model_server/upgrade/test_upgrade.py:20-60). |
| 29 invalid post-upgrade deployment stays unhealthy | AVOIDABLE | A `post_upgrade`-marked negative deployment uses the same mechanism (conftest.py:289-309). The test body is the kind QF already wrote for cases 5, 6 and 20. |

Totals: 7 JUSTIFIED, 3 AVOIDABLE.

## 3. `existing_coverage` entries (8)

| plan case | named test | class | evidence |
|---|---|---|---|
| 3 dashboard shows only variants whose digest differs from stable | vo/s3/test_vllm_omni_template.py::test_vllm_omni_template_variants_present | FALSE | Only asserts that the stable template exists (:398-422). Its own docstring says the fast variants are tested elsewhere and deselected (:405-406). There is no digest comparison and no visibility check, despite the STD's claim of "stable and fast variants and digest-based visibility". |
| 8 readiness stays false until every stage loads | vo/probes/test_vllm_omni_probes.py::test_vllm_omni_health_endpoint_transitions | VERIFIED | Polls `/health` (the readiness probe target, template:68-73) from the moment the pod is Running. It requires a non-200, then the switch to 200 (:157-191), then 60 s with no flapping (:195-206). |
| 9 failed stage keeps serving unavailable | test_vllm_omni_probes.py::test_vllm_omni_failed_stage_init_stays_not_ready | VERIFIED | Uses a model with no TTS stages and `--omni`. It fails if the pod ever becomes Ready (:305), and asserts `/health` is never 200 and the container crashes (:284-325). Recovery after a fix ("until corrected") is not exercised. |
| 12 malformed speech requests return client errors, never 500 | vo/s3/test_vllm_omni_tts.py::test_vllm_omni_tts_invalid_payload_errors | VERIFIED | Three malformed bodies; asserts status in {400, 422}, which excludes 500, and a non-empty body (:245-294). |
| 13 single word gives proportionally sized audio with no white noise | test_vllm_omni_tts.py::test_vllm_omni_tts_qwen3_single_word_prompt | PARTIAL | Checks a valid WAV (via `run_tts_inference` → `validate_tts_output`, vo/utils.py:353) and that the single-word audio is smaller than a multi-word one (:229-238). "Proportionally sized" and "no white noise" are not checked: a one-word clip almost as long as a sentence passes. |
| 14 50 consecutive turns, no restart, no HTTP error | vo/s3/test_vllm_omni_stability.py::test_vllm_omni_tts_50_turn_session | VERIFIED | 50 sequential speech requests; asserts no non-200 turn, no restart and the pod still Ready (:105-139). |
| 18 image digest-pinned and in the release inventory | test_vllm_omni_template.py::test_vllm_omni_runtime_template_exists | VERIFIED | Asserts an `@sha256:` image with `vllm-omni` in the path, and that it equals an entry in the CSV relatedImages (:85-120). The CSV check is skipped only when a custom image override is set (:94-100). |
| 26 runtime loads only safetensors and rejects untrusted pickle files | test_vllm_omni_tts.py::test_vllm_omni_safetensors_only_model_format | PARTIAL | Checks that the logs mention safetensors and no pickle extension, and that `/mnt/models` has `.safetensors` and no pickle files (:361-405). The bucket has no pickle files, so the plan's mixed-format storage is never created and rejection is never exercised. |

PARTIAL_COVERAGE references (not counted) name tests that exist. Two notes: case 4 cites `test_vllm_omni_predictor_pod_ready` in test_vllm_omni_template.py, but it is in vo/s3/test_vllm_omni_e2e.py:134. And the case 15 and 16 gaps are not closed by the QF copies (section 1).

## 4. The plan

**Expects unshipped behaviour (1): case 24.** It expects an unauthorized `/metrics` request to be rejected. The shipped runtime serves metrics on the same port 8080 that the Route exposes (template:34-35, :48, :56-58), in a single container with no auth sidecar (template:41-86). The team's shipped test asserts the unauthenticated Route GET returns 200 (tts.py:633-664).

Doubtful, not counted:
- Case 26's "rejects untrusted pickle files". The template sets no load-format restriction (template:44-52), so any rejection depends on vLLM defaults outside the checkout.
- Cases 1-3: the preview-acceptance dialog and digest-based variant visibility are dashboard and operator behaviour outside the checkout. The fast-1/-2 variants do ship (config/runtimes-fast-1/kustomization.yaml:4-9; config/default/kustomization.yaml:31-32).

Case 15's 350 ms / 1.2 s is a Jira target, not a code fact; the suite relaxes it to 3.5 s / 7.0 s.

**Shipped behaviour the plan misses:**
- The `csr-kserve-vllm-omni-cuda` ClusterServingRuntime (config/runtimes/vllm-omni/csr-kserve-vllm-omni-cuda.yaml; commit 44f272a). No scenario covers it.
- The metrics-dashboard ConfigMap for `vllm-omni` runtimes (internal/controller/serving/reconcilers/kserve_metrics_dashboard_reconciler.go:229-230; constants/runtime-metrics.go:231-312). Case 23's product_refs cite it, but no scenario checks it. A check would have been worth having: its KV-cache chart queries `vllm:gpu_cache_usage_perc` (:287), while the runtime metric the suite and Jira use is `vllm:kv_cache_usage_perc` (vo/constant.py:21; jira_data.yaml:25), so that chart may come up empty.
- The container securityContext: runAsNonRoot, no privilege escalation, drop ALL (template:80-86). The team checks it at test_vllm_omni_template.py:328.

## 5. Acceptance criteria

`main_issue.acceptance_criteria` is a list of 8 items (jira_data.yaml:85-93).

| AC | text (short) | status | plan scenario |
|---|---|---|---|
| AC-1 | runtime appears in the dashboard with Tech Preview labeling | COVERED | 1 |
| AC-2 | deploys without YAML; Ready only after multi-stage init | COVERED | 4 (and 8) |
| AC-3 | 50 consecutive voice turns, no reset or restart | COVERED | 14 |
| AC-4 | warm TTS TTFB p95 ≤ 350 ms, E2E p95 ≤ 1.2 s over ≥ 200 requests | COVERED | 15 |
| AC-5 | 10-minute dialogue: no OOM or restart, TTFB ≤ 1.25x, memory growth ≤ 15% | COVERED | 16 |
| AC-6 | image digest-pinned in operator relatedImages | COVERED | 18 |
| AC-7 | template and docs labeled Tech Preview with a capability matrix | COVERED | 21 (template labeling also in 1) |
| AC-8 | failed stage init keeps the pod NotReady and health non-200 | COVERED | 9 |

SCORE RHAISTRAT-2493 | QF tests=11 real=4 weak=5 hollow=0 wrong=2 loads=11 declined=10 justified=7 avoidable=3 cases=29 real_cases=4 covered=8 verified=5 partial=2 false=1 plan_wrong=1 acs=8 ac_covered=8 ac_out_of_scope=0 ac_missed=0
