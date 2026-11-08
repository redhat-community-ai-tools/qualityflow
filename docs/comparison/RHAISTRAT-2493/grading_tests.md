# RHAISTRAT-2493 (vLLM-Omni serving runtime): run 5 grading, both tools on GLM 5.3

Product: `odh-model-controller` at 1053962. It ships the vLLM-Omni ServingRuntime template
(`config/runtimes/vllm-omni/vllm-omni-cuda-template.yaml`, cited as `template:N`) and the stable / fast-1 / fast-2
image wiring (`config/base/kustomization.yaml:492-540`, `config/runtimes-fast-1/kustomization.yaml`). The engine
(v0.26.0, `template:27`) is an image, so engine behaviour is taken from the suite's vLLM-Omni tests at 7ffaacc, which
were verified against that build (`vllm_omni/` = `opendatahub-tests/tests/model_serving/model_runtime/vllm_omni/`).

Engine facts that decide several grades:
- Qwen3-Omni does not serve `/v1/audio/speech`; its interface is chat (`vllm_omni/s3/test_vllm_omni_e2e.py:188-189`).
- `/v1/completions` on Qwen3-Omni returns 400 with "use chat" guidance (`s3/test_vllm_omni_e2e.py:314-349`).
- The route serves inference and `/metrics` without auth (`s3/test_vllm_omni_tts.py:198-215`, `:653-655`; template has no auth sidecar, `template:41-86`).
- The suite's latency thresholds are 3.5 s TTFB / 7.0 s E2E (`vllm_omni/constant.py:26,31`), ten times looser than both plans' 350 ms / 1.2 s.
- The suite's only "GPU memory" signal is `vllm:kv_cache_usage_perc` (`constant.py:21`), a KV-cache fill gauge, not GPU memory.

## QualityFlow tests (13, `vllm_omni/s3/test_qf_rhaistrat_2493.py`)

All 13 load (collected 13, setup-plan clean). It also added `s3/conftest.py`, a new file that only registers the
`qf_test_id` marker.

| test (file::name) | plan case | class | evidence (one line) |
|---|---|---|---|
| TestQfVllmOmniE2EServing::test_qf_rhaistrat_2493_004_... | TS-004 | WEAK | Qwen3-Omni chat 200 + non-empty content (:185-204). The case covers every supported model and its speech or text capability, but Qwen3-TTS, Voxtral, OmniVoice and FLUX.2 (`constant.py:86-90`) are never deployed |
| ::test_qf_rhaistrat_2493_007_... | TS-007 | WEAK | 2-GPU Qwen3-Omni pod Ready + `/health` 200 (:217-220). The expected "valid supported inference response" is not requested in this test |
| ::test_qf_rhaistrat_2493_023_... | TS-023 | WEAK | Reads /metrics: ≥15 `vllm_omni:`, ≥30 `vllm:` families, `stage`/`replica` on the KV-cache line, plus a Prometheus sample (:232-254). Real names, but these are the suite's floors, not the plan's confirmed 17/32, and the test sends no request of its own, so "request observations for the exercised stages" is unchecked |
| TestQfVllmOmniHealthTransition::test_qf_rhaistrat_2493_008_... | TS-008 | REAL | Fresh pod: `/health` (the readiness probe path, `template:68-73`) is non-200 during init and then 200 (:293-312), same contract as `probes/test_vllm_omni_probes.py:139-192` |
| TestQfVllmOmniFailedStageInit::test_qf_rhaistrat_2493_009_... | TS-009 | REAL | Text-only opt-125m with `--omni`: never Ready, `/health` never 200, CrashLoopBackOff (:351-382), the failure the suite verified (`probes/test_vllm_omni_probes.py:239-326`). Only one failure variant |
| TestQfVllmOmniTTS::test_qf_rhaistrat_2493_011_... | TS-011 | WEAK | One Qwen3-TTS WAV request validated by `run_tts_inference` (:417-423, `utils.py:192-233`). The case covers every model/endpoint pair and streamed audio |
| ::test_qf_rhaistrat_2493_012_... | TS-012 | REAL | Empty input, missing input and `{}` each return 400/422 with an OpenAI error body (:435-451), the suite contract (`s3/test_vllm_omni_tts.py:245-294`); a 4xx carries no audio |
| ::test_qf_rhaistrat_2493_013_... | TS-013 | WEAK | Single-word bytes < multi-word bytes (:462-469). The case is "intelligible speech under the approved protocol", which a size proxy does not show |
| ::test_qf_rhaistrat_2493_014_... | TS-014 | REAL | 50 Qwen3-TTS voice turns from the fixed 50-prompt corpus (`data/prompts.json`: 5 single-word, median 16 words), all 200, no restart increase (:482-513) |
| ::test_qf_rhaistrat_2493_015_... | TS-015 | WEAK | Harness and 200 samples are right (:525-547), but it asserts the suite's 3.5 s / 7.0 s (`constant.py:26,31`), not the case's 350 ms / 1.2 s, and covers one TTS model |
| ::test_qf_rhaistrat_2493_016_... | TS-016 | WEAK | 10-min soak, TTFB p95 ratio ≤1.25 and no restarts are right (:561-601). "GPU memory growth" is `vllm:kv_cache_usage_perc` (:569,602-608), the KV-cache gauge the case says to report separately from actual GPU memory |
| test_qf_rhaistrat_2493_018_... | TS-018 | WEAK | Only checks that CSV vllm-omni images are `@sha256` (:620-626). It never compares the Template image (`template:43`) with that CSV entry or with an approved digest |
| test_qf_rhaistrat_2493_024_... | TS-024 | WRONG | Unprivileged PATCH of the Template expecting 403 (:638-652) tests Template RBAC, a copy of `s3/test_vllm_omni_security.py:31-59`, not metrics access. The product serves /metrics on 8080 with no auth (`template:34-36,48`; the suite asserts an unauthenticated GET returns 200, `s3/test_vllm_omni_tts.py:653-655`) |

## QualityFlow declines (not_implemented: 16)

| plan case | class | evidence |
|---|---|---|
| TS-001 dashboard preview acceptance, Limited badge | JUSTIFIED | The dashboard UI is in neither checkout. Only template metadata exists (`template:17,28`) |
| TS-002 declining acceptance | JUSTIFIED | Same reason |
| TS-017 blinded 5-rater listening | JUSTIFIED | A human panel |
| TS-019 mirrored images + local weights, disconnected | JUSTIFIED | No mirror-registry or disconnected fixture in the suite; the mirror mapping depends on the environment |
| TS-021 documentation matches capabilities | JUSTIFIED | Docs are in neither checkout |
| TS-022 guide security/storage disclosures | JUSTIFIED | Same reason |
| TS-026 untrusted artifacts refused | JUSTIFIED | The template has no load-format restriction (`template:44-52`), so there is no safeguard to test |
| TS-003 variants follow image divergence | AVOIDABLE | Three variants with separate image params ship (`config/base/kustomization.yaml:492-540`, `runtimes-fast-1/kustomization.yaml:4-8`). Fast Templates are readable (`vllm_omni/fast/conftest.py:31-40`) and CSV images via `utilities/operator_utils.py:30`, which QF already uses at :620 |
| TS-005 missing storage never serves | AVOIDABLE | QF's own `vllm_omni_unready_isvc` (:90-122) takes any model dir, and its TS-009 loop (:351-382) is the stays-unhealthy check |
| TS-006 one-GPU reference not Ready | AVOIDABLE | The same fixture takes `gpu_count` (:100), and Qwen3-Omni is the 2-GPU model (`s3/test_vllm_omni_e2e.py:83-101`) |
| TS-010 normal init without restarts | AVOIDABLE | `get_restart_counts`/`pod_is_ready` (`model_runtime/utils.py:510,522`) are already imported (:33) and used on the same pod (:217, :482). Run 4 had a REAL test for this case |
| TS-020 unavailable image never serves | AVOIDABLE | `vllm_omni_runtime_image` overrides the image (`vllm_omni/conftest.py:108-109`); pair it with the unready fixture |
| TS-025 no voice content in persistent artifacts | AVOIDABLE | `s3/test_vllm_omni_tts.py:296-347` (PII prompts, base64/WAV/biometric scan of pod logs); log levels via `model_env_variables` (`conftest.py:213-214`) |
| TS-027 restricted egress still serves | AVOIDABLE | `s3/test_vllm_omni_tts.py:412-491` (egress NetworkPolicy + inference 200 + blocked probe) |
| TS-028 configuration survives upgrade | AVOIDABLE | The suite's upgrade-lane pattern (pre_upgrade/post_upgrade markers, `tests/model_serving/model_server/upgrade/test_upgrade.py:29-58`) needs no version pair in the test |
| TS-029 invalid post-upgrade deployment stays unhealthy | AVOIDABLE | Same markers plus the unready loop (:351-382) |

## Generator tests (62 graded, `tests/vllm_omni_serving/`; collected 63 including the skip-only TC-QUAL-001)

Generator-wide: 46 of the 62 tests are suite test methods re-bound as class attributes (`test_tc_x = _SuiteClass.test_y`). Under the rule set in run 3 (`score-tests/RHAISTRAT-1245.md`, Test Plan Generator section), a re-bound test has no product call or assertion written by the tool, so it is HOLLOW. The last column gives, for reference only, the class the delegated suite test would earn against this plan case (re-bound reference: 31 REAL, 15 WEAK). The other 16 tests have bodies the generator wrote and keep their own class. Loading: its `conftest.py` re-exports suite fixtures but not `vllm_omni_runtime_image` (`vllm_omni/conftest.py:60-69`, needed by `vllm_omni_serving_runtime`), `vllm_omni_stable_template`/`vllm_omni_runtime_spec` (module fixtures in `s3/test_vllm_omni_template.py`) or `vllm_omni_modelcar_serving_runtime`. Confirmed: 58 of 63 error at setup. Only TC-QUAL-001 (skip), TC-RBAC-002, TC-REG-001, TC-REG-002 and TC-TMPL-008 load, so 4 graded tests load, and of those only TC-TMPL-008 is REAL.

| test (file::name) | plan case | class | evidence (one line) | delegated team test would earn |
|---|---|---|---|---|
| test_api::TestVllmOmniApi::test_tc_api_001 | TC-API-001 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Suite `/v1/models`: object=list, served name (`--served-model-name={{.Name}}`, `template:52`) in ids, each object=model (`s3/test_vllm_omni_e2e.py:269-312`) | REAL |
| ::test_tc_api_003 | TC-API-003 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Suite chat contract: chat.completion, assistant role, content, finish_reason, usage (`e2e.py:351-430`) | REAL |
| ::test_tc_api_004[missing-model] | TC-API-004 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: 400/422 + OpenAI error object (`e2e.py:417-465`) | REAL |
| ::test_tc_api_004[empty-body] | TC-API-004 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Same | REAL |
| ::test_tc_api_004[invalid-model-name] | TC-API-004 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: 400/404 + error object, as planned | REAL |
| ::test_tc_api_005[missing-messages] | TC-API-005 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: 400/422 + error object (`e2e.py:467-521`) | REAL |
| ::test_tc_api_005[invalid-messages-format] | TC-API-005 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Same | REAL |
| ::test_tc_api_005[message-missing-role] | TC-API-005 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Same | REAL |
| ::test_tc_api_002 | TC-API-002 | WRONG | Expects 200 + text_completion from `/v1/completions` on Qwen3-Omni (:59-92). The shipped engine returns 400 there (`e2e.py:314-349`) | n/a (own body) |
| test_disc::test_tc_disc_001 | TC-DISC-001 | WEAK | Digest pin plus "not registry.redhat.io" on the SR image and imageID (:58-72). Mirroring by IDMS/ICSP leaves the reference as the CSV value (`template:43`), so this never shows a pull from the mirror | n/a (own body) |
| ::test_tc_disc_002 | TC-DISC-002 | WEAK | CSV image digest-pinned and equal to the SR image (:84-94). The mirrored-digest match and ICSP resolution are not checked | n/a (own body) |
| ::test_tc_disc_003 | TC-DISC-003 | WRONG | Requires `/v1/completions` 200 on Qwen3-Omni (:119-132); the engine returns 400 (`e2e.py:314-349`) | n/a (own body) |
| test_e2e::test_tc_e2e_001 | TC-E2E-001 | WRONG | POSTs `/v1/audio/speech` to Qwen3-Omni expecting 200 (:85-101). Qwen3-Omni does not support speech (`e2e.py:188-189`) | n/a (own body) |
| ::test_tc_e2e_003 | TC-E2E-003 | WRONG | Same speech-on-Qwen3-Omni expectation (:129-143) | n/a (own body) |
| test_img::test_tc_img_001 | TC-IMG-001 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Suite FLUX.2: 200, JSON, b64 decodes to PNG/JPEG, no restarts (`s3/test_vllm_omni_img.py:54-120`) | REAL |
| test_init::TestVllmOmniInitialization::test_tc_init_001 | TC-INIT-001 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Suite marker check (`e2e.py:707-729`): the markers are "launching 3 stages" and the Stage-0/1 device setup (`e2e.py:68-72`), not completion of LLM, TTS and Code2Wav, and the Ready-time bound is not checked | WEAK |
| ::test_tc_init_005 | TC-INIT-005 | WRONG | Injects the fault with `kill -STOP 1` inside the container (:67). PID 1 is `vllm serve` (`template:44-46`), and SIGSTOP from inside a PID namespace to its init is ignored (pid_namespaces(7)). `/health` never fails, so the restart it waits for (:73-83) never happens. The generator flagged this case 6/10 itself | n/a (own body) |
| TestVllmOmniHealthInitialization::test_tc_init_002 | TC-INIT-002 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Suite transition test: non-200 during init, then 200, then 60 s stable (`probes/test_vllm_omni_probes.py:139-213`) | REAL |
| TestVllmOmniEmptyModelPath::test_tc_init_006 | TC-INIT-006 | WEAK | Not-Ready plus generic words ("not found", "empty") in kserve-container logs (:154-159). The missing-model error comes from the storage initializer, and `/health`, CrashLoop and ISVC status are unchecked | n/a (own body) |
| test_mcar::test_tc_mcar_001 | TC-MCAR-001 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Suite modelcar: OCI ISVC, valid WAV, zero restarts (`modelcar/test_vllm_omni_modelcar.py:185-222`) | REAL |
| test_metr::TestVllmOmniMetrics::test_tc_metr_001 | TC-METR-001 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: ≥15 `vllm_omni:` families after a chat warm-up, plus a Prometheus sample of `vllm:prompt_tokens_total` (`e2e.py:524-582`). It never checks `audio_ttfp_s`/`e2e_request_latency_s` or that Prometheus scrapes `vllm_omni:*` | WEAK |
| ::test_tc_metr_002 | TC-METR-002 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: `kv_cache_usage_perc` has stage+replica, ≥30 `vllm:`, both prefixes on one endpoint (`e2e.py:584-633`), exactly the plan | REAL |
| TestVllmOmniMetricsDisabled::test_tc_metr_003 | TC-METR-003 | WEAK | Asserts no metrics when the ISVC args omit `--log-stats` (:61, :92-104). The ServingRuntime still comes from the template, which has `--log-stats` (`template:51`, `conftest.py:111`), and the suite calls metrics on by default (`e2e.py:111,533`). Nothing in either checkout shows the flag is removed or that its absence hides metrics | n/a (own body) |
| test_neg::test_tc_neg_001 | TC-NEG-001 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Suite failed-init test: crash, `/health` non-200 (`probes/test_vllm_omni_probes.py:248-332`). The diagnostic log message and the "subsequent valid deployment" are not checked | WEAK |
| ::test_tc_neg_002 | TC-NEG-002 | WEAK | Not-Ready plus guessed log words "gpu"+"insufficient/minimum" (:89-101). No OOM distinction and no follow-up valid deployment | n/a (own body) |
| test_perf::test_tc_perf_001 | TC-PERF-001 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Suite latency test asserts 3.5 s / 7.0 s (`constant.py:26,31`; `s3/test_vllm_omni_stability.py:219-226`), not the case's 350 ms / 1.2 s | WEAK |
| test_pvc::test_tc_pvc_001 | TC-PVC-001 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: PVC-backed Qwen3-TTS returns valid WAV (`pvc/test_vllm_omni_pvc.py:63-100`). The planned "no pod restarts" is not checked | WEAK |
| test_rbac::TestVllmOmniRbac::test_tc_rbac_001 | TC-RBAC-001 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Admin GET + PATCH of the ServingRuntime only (`s3/test_vllm_omni_tts.py:493-527`). No create/delete and no InferenceService CRUD | WEAK |
| ::test_tc_rbac_003 | TC-RBAC-003 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: View-role user: GET ok, create 403, delete 403 (`s3/test_vllm_omni_tts.py:555-631`) | REAL |
| ::test_tc_rbac_004 | TC-RBAC-004 | WRONG | Expects an unauthenticated TTS POST to get 401/403 (:65-74). The route serves inference without auth (`s3/test_vllm_omni_tts.py:198-215`, `utils.py:342-352` sends no token) | n/a (own body) |
| TestVllmOmniDataScienceUserRbac::test_tc_rbac_002 | TC-RBAC-002 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: DS user PATCH of the Template returns 403 (`s3/test_vllm_omni_security.py:31-59`). The planned 201 ISVC create in the user's own project is missing | WEAK |
| test_reg::test_tc_reg_001 | TC-REG-001 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: CUDA template exists without `--omni` (`s3/test_vllm_omni_regression.py:66-110`). It never checks that CUDA ISVCs still serve 200, or that annotations are unchanged | WEAK |
| ::test_tc_reg_002 | TC-REG-002 | WEAK | ROCm/Gaudi/CPU/Spyre templates exist, no `--omni`, declare vLLM (:33-68; names `utilities/constants.py:90-94`). Images and annotations are not checked | n/a (own body) |
| test_sec::test_tc_sec_001[info] | TC-SEC-001 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Suite PII test: PII prompts sent, no base64/WAV/biometric/verbatim prompt in logs (`s3/test_vllm_omni_tts.py:296-347`) | REAL |
| ::test_tc_sec_002[info] | TC-SEC-002 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: safetensors in logs and `/mnt/models`, no `.bin`/pickle files (`tts.py:349-410`) | REAL |
| ::test_tc_sec_004[info] | TC-SEC-004 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Egress NetworkPolicy: inference 200 and an external connect blocked (`tts.py:412-491`) | REAL |
| ::test_tc_sec_001[debug] | TC-SEC-001 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: The DEBUG phase rests on `--log-level=DEBUG` (:43). That flag appears nowhere in either checkout, and the suite sets engine options through env (`conftest.py:213-214`), so nothing shows this deployment logs at DEBUG | WEAK |
| ::test_tc_sec_002[debug] | TC-SEC-002 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Same checks as the info param (duplicate run) | REAL |
| ::test_tc_sec_004[debug] | TC-SEC-004 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Same (duplicate run) | REAL |
| test_stab::TestVllmOmniStability::test_tc_stab_001 | TC-STAB-001 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: 50 Qwen3-TTS turns 200, no restarts, Ready before and after (`s3/test_vllm_omni_stability.py:71-139`) | REAL |
| ::test_tc_stab_002 | TC-STAB-002 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: TTFB ratio and restarts are right, but "GPU memory growth" is `vllm:kv_cache_usage_perc` (`stability.py:292-310,385-410`), not GPU memory | WEAK |
| TestVllmOmniVoxtralStability::test_tc_stab_003 | TC-STAB-003 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: The case is Qwen3-Omni-30B 50 turns; the class deploys Voxtral (:51-69). The suite's Qwen3-Omni version is `e2e.py:635-705` | WEAK |
| TestVllmOmniOmniVoiceStability::test_tc_stab_004 | TC-STAB-004 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: OmniVoice 50 turns, voice omitted per `OMNI_TTS_VOICE` (`constant.py:96`, `stability.py:455-515`), all 200, no restarts | REAL |
| test_tmpl::test_tc_tmpl_001 | TC-TMPL-001 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Template exists, image `@sha256`, contains vllm-omni, and equals the CSV entry (`s3/test_vllm_omni_template.py:57-121`, `template:43`) | REAL |
| ::test_tc_tmpl_002 | TC-TMPL-002 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Label, support-status=unsupported, accelerators, runtime-version, spec annotations with values, format vLLM (`template.py:123-188`, `template:26-40`) | REAL |
| ::test_tc_tmpl_003 | TC-TMPL-003 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Command, `--port`/`--model`/`--omni` and HF_HOME (`template.py:190-224`). The plan's `--log-stats` (`template:51`) is not asserted | WEAK |
| ::test_tc_tmpl_004 | TC-TMPL-004 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Exact probe values, no initialDelaySeconds (`template.py:226-281`, `template:62-79`) | REAL |
| ::test_tc_tmpl_005 | TC-TMPL-005 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Same body as TMPL-001, whose CSV-entry and digest assertions are this case's outcome | REAL |
| ::test_tc_tmpl_006 | TC-TMPL-006 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Exactly one format, "vLLM" (`template.py:283-304`, `template:38-40`) | REAL |
| ::test_tc_tmpl_007 | TC-TMPL-007 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: runtime-version present and non-empty (`template.py:306-326`, `template:27`) | REAL |
| ::test_tc_tmpl_009 | TC-TMPL-009 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: allowPrivilegeEscalation/privileged false, runAsNonRoot, drop ALL (`template.py:328-362`, `template:80-86`) | REAL |
| ::test_tc_tmpl_008 | TC-TMPL-008 | REAL | The three Template names the kustomization creates (`config/base/kustomization.yaml:505,521,537`; `utilities/constants.py:98-100`) exist in the cluster | n/a (own body) |
| test_tts::TestVllmOmniTts::test_tc_tts_001[wav] | TC-TTS-001 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Valid WAV (`s3/test_vllm_omni_tts.py:160-184`). The planned voices-list 200 and 20-word no-504 checks are absent | WEAK |
| ::test_tc_tts_001[mp3] | TC-TTS-001 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Same, mp3 (the case expects audio/wav) | WEAK |
| ::test_tc_tts_001[flac] | TC-TTS-001 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Same, flac | WEAK |
| ::test_tc_tts_002 | TC-TTS-002 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Valid WAV and single-word bytes < multi-word bytes (`tts.py:217-243`), the plan's own white-noise criterion | REAL |
| ::test_tc_tts_003[empty-input] | TC-TTS-003 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: 400/422 with a non-empty error body (`tts.py:245-294`) | REAL |
| ::test_tc_tts_003[missing-input] | TC-TTS-003 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Same | REAL |
| ::test_tc_tts_003[empty-body] | TC-TTS-003 | HOLLOW | Re-binds a suite test method, no product call or assertion of its own. Suite body: Same | REAL |
| TestVllmOmniMultiModelTts::test_tc_tts_004[qwen3] | TC-TTS-004 | REAL | Qwen3-TTS deployment, valid WAV via `run_tts_inference` (`utils.py:324-354`) | n/a (own body) |
| ::test_tc_tts_004[voxtral] | TC-TTS-004 | REAL | Voxtral deployment, same validation | n/a (own body) |
| TestVllmOmniOmniVoice::test_tc_tts_005 | TC-TTS-005 | WEAK | Valid WAV + no restart (:136-149), but no voices-list check, and `run_tts_inference` falls back to voice "vivian" (`utils.py:338-339,367-369`) where the suite says OmniVoice needs the voice omitted (`utils.py:259-261`, `constant.py:96`) | n/a (own body) |

## Generator skips

| plan case | class | evidence |
|---|---|---|
| TC-QUAL-001 blind listening for timbre drift (skip-only test, `test_qual_vllm_omni_serving.py:6-14`) | JUSTIFIED | A human panel; the generator marked it manual |

Versus run 3 (luna): QF went from 4 tests (1 REAL) to 13 (4 REAL) and 9 avoidable declines. The generator went from hand-written tautologies (3 REAL of 51) to mostly re-binding the suite's verified tests (46 HOLLOW by the delegation rule). Of its 16 own bodies, 3 are REAL and 6 WRONG. Its fixture wiring still loads only 4.

QF real_and_loads=4
GEN real_and_loads=1

SCORE RHAISTRAT-2493 | QF tests=13 real=4 weak=8 hollow=0 wrong=1 loads=13 declined=16 justified=7 avoidable=9 cases=29 real_cases=4 real_and_loads=4 | GEN tests=62 real=3 weak=7 hollow=46 wrong=6 loads=4 declined=1 justified=1 avoidable=0 cases=51 real_cases=2 real_and_loads=1
