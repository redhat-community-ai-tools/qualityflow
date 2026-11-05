---
test_case_id: TC-PROVIDER-002
strat_key: RHAISTRAT-1061
priority: P1
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---

# TC-PROVIDER-002: Bedrock provider with session token and role ARN

**Objective**: Verify that an OGXServer CR with a Bedrock inference provider correctly includes
sessionToken and roleArn fields (added in PR #294) in the generated config.yaml.

**Preconditions**:

- OpenShift cluster with RHOAI operator installed
- OGX operator deployed and healthy (version including PR #294 changes)
- `oc` CLI authenticated with cluster-admin or namespace-admin privileges
- Dedicated test namespace created
- AWS credentials (access key, secret key, session token) available for Bedrock access, or mock
  values for config generation validation

**Test Steps**:

1. Create the test namespace and the AWS credentials secret:

   ```bash
   oc new-project tc-provider-002
   oc create secret generic bedrock-credentials \
     -n tc-provider-002 \
     --from-literal=access-key="${AWS_ACCESS_KEY_ID}" \
     --from-literal=secret-key="${AWS_SECRET_ACCESS_KEY}" \
     --from-literal=session-token="${AWS_SESSION_TOKEN}"
   ```

2. Apply the OGXServer CR with a Bedrock inference provider including sessionToken and roleArn:

   ```bash
   oc apply -f - <<EOF
   apiVersion: ogx.io/v1beta1
   kind: OGXServer
   metadata:
     name: ogx-bedrock
     namespace: tc-provider-002
   spec:
     providers:
       inference:
         - provider_id: bedrock-default
           provider_type: remote::bedrock
           config:
             aws_access_key_id: ${AWS_ACCESS_KEY_ID}
             aws_secret_access_key: ${AWS_SECRET_ACCESS_KEY}
             aws_session_token: ${AWS_SESSION_TOKEN}
             region: us-east-1
             role_arn: arn:aws:iam::123456789012:role/OGXBedrockRole
   EOF
   ```

3. Wait for the OGXServer to reconcile
   (it may not reach Ready without valid AWS credentials, but the ConfigMap should be generated):

   ```bash
   sleep 30
   oc get ogxserver ogx-bedrock -n tc-provider-002 -o yaml
   ```

4. Inspect the generated ConfigMap for correct Bedrock provider configuration:

   ```bash
   CM_NAME=$(oc get configmaps -n tc-provider-002 -l app.kubernetes.io/instance=ogx-bedrock -o jsonpath='{.items[0].metadata.name}')
   oc get configmap "$CM_NAME" -n tc-provider-002 -o jsonpath='{.data.config\.yaml}'
   ```

5. Verify the sessionToken and roleArn fields are present in the generated config:

   ```bash
   oc get configmap "$CM_NAME" -n tc-provider-002 -o jsonpath='{.data.config\.yaml}' | grep -E 'session_token|role_arn'
   ```

6. Check the CRD schema accepts these fields without validation errors:

   ```bash
   oc get crd ogxservers.ogx.io -o jsonpath='{.spec.versions[0].schema.openAPIV3Schema.properties.spec.properties.providers}' | python3 -m json.tool 2>/dev/null | head -60
   ```

7. Clean up:

   ```bash
   oc delete project tc-provider-002
   ```

**Expected Results**:

- The CR is accepted without validation errors
- The generated config.yaml contains a Bedrock inference provider entry with:
  - `provider_id: bedrock-default`
  - `provider_type: remote::bedrock`
  - `config.aws_access_key_id` set correctly
  - `config.aws_secret_access_key` set correctly
  - `config.aws_session_token` set correctly (PR #294 addition)
  - `config.region` set to `us-east-1`
  - `config.role_arn` set to the specified ARN (PR #294 addition)
- The sessionToken and roleArn fields are not stripped or ignored during config generation
- The CRD schema allows these fields in the provider config

**Test Data**:

```yaml
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: ogx-bedrock
spec:
  providers:
    inference:
      - provider_id: bedrock-default
        provider_type: remote::bedrock
        config:
          aws_access_key_id: ${AWS_ACCESS_KEY_ID}
          aws_secret_access_key: ${AWS_SECRET_ACCESS_KEY}
          aws_session_token: ${AWS_SESSION_TOKEN}
          region: us-east-1
          role_arn: arn:aws:iam::123456789012:role/OGXBedrockRole
```

**Notes**:

- The sessionToken and roleArn fields were added in PR #294 to support AWS STS temporary credentials
  and cross-account access
- Full end-to-end validation (actually invoking Bedrock) requires valid AWS credentials with Bedrock
  access; this test can be partially validated by inspecting config generation only
- To be filled later in the process.
