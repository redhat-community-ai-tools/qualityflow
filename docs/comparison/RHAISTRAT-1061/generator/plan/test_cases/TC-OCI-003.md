---
test_case_id: TC-OCI-003
strat_key: RHAISTRAT-1061
priority: P1
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---

# TC-OCI-003: OCI label format validation

**Objective**: Verify that official OGX distribution images carry the required OCI labels with
correct format and valid base64-encoded YAML content.

**Test Steps**:

1. Inspect the official distribution image for all OGX-related labels:

   ```bash
   skopeo inspect --no-tags docker://<official-distribution-image>:<tag> | \
     jq '.Labels | to_entries[] | select(.key | startswith("com.ogx."))'
   ```

2. Verify the `com.ogx.distribution.name` label exists and is non-empty:

   ```bash
   skopeo inspect --no-tags docker://<official-distribution-image>:<tag> | \
     jq -r '.Labels["com.ogx.distribution.name"]'
   ```

3. Verify the `com.ogx.distribution.version` label exists and is non-empty:

   ```bash
   skopeo inspect --no-tags docker://<official-distribution-image>:<tag> | \
     jq -r '.Labels["com.ogx.distribution.version"]'
   ```

4. Verify the `com.ogx.distribution.default-config` label exists and names a valid config file:

   ```bash
   skopeo inspect --no-tags docker://<official-distribution-image>:<tag> | \
     jq -r '.Labels["com.ogx.distribution.default-config"]'
   ```

5. Verify the `com.ogx.distribution.configs` label exists and contains a comma-separated list of
   filenames:

   ```bash
   skopeo inspect --no-tags docker://<official-distribution-image>:<tag> | \
     jq -r '.Labels["com.ogx.distribution.configs"]'
   ```

6. For each filename listed in `com.ogx.distribution.configs`, verify the corresponding
   `com.ogx.config.<filename>` label contains valid base64-encoded YAML:

   ```bash
   CONFIGS=$(skopeo inspect --no-tags docker://<official-distribution-image>:<tag> | \
     jq -r '.Labels["com.ogx.distribution.configs"]')

   for cfg in $(echo "$CONFIGS" | tr ',' ' '); do
     echo "--- Validating com.ogx.config.${cfg} ---"
     skopeo inspect --no-tags docker://<official-distribution-image>:<tag> | \
       jq -r ".Labels[\"com.ogx.config.${cfg}\"]" | \
       base64 -d | \
       python3 -c "import sys, yaml; yaml.safe_load(sys.stdin) and print('PASS: ${cfg}')"
   done
   ```

7. Verify the default config filename from step 4 appears in the configs list from step 5.

**Expected Results**:

- `com.ogx.distribution.name` label exists and contains the distribution name string.
- `com.ogx.distribution.version` label exists and contains a version string.
- `com.ogx.distribution.default-config` label exists and names a config file (e.g., `config.yaml`).
- `com.ogx.distribution.configs` label exists and contains a comma-separated list of config
  filenames.
- Each `com.ogx.config.<filename>` label decodes from base64 to valid YAML without errors.
- The default config filename is present in the configs list.

**Test Data**:

Use the official OGX distribution image for the RHOAI version under test. The image reference will
vary by release.

**Notes**: To be filled later in the process.
