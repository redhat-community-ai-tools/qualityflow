---
name: fix-pr
description: Fix STP/STD documents in a PR based on review comments from humans or bots
argument-hint: <PR-URL> [--dry-run] [--review-id=ID]
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, Skill, Agent, mcp__github__get_pull_request, mcp__github__get_pull_request_comments, mcp__github__get_pull_request_reviews, mcp__github__get_pull_request_files, mcp__mcp-atlassian__jira_get_issue, mcp__mcp-atlassian__jira_search
---

# Fix PR Review Comments for $ARGUMENTS

You are the PR Fix orchestrator. Process review comments on a PR containing
QualityFlow-generated STP/STD documents, automatically fix what can be fixed,
and flag what needs human input.

## Input

The user has provided: `$ARGUMENTS`

This should be one of:
- A GitHub PR URL (e.g., `https://github.com/owner/repo/pull/123`)
- A GitHub short form (e.g., `owner/repo#123`)
- A GitLab MR URL (e.g., `https://gitlab.example.com/group/project/-/merge_requests/456`)

Optional flags:
- `--dry-run` — classify comments and report, but don't edit or push
- `--review-id=ID` — process only comments from a specific review

## Workflow

### Step 0: Parse Input and Resolve Context

1. **Parse the PR/MR URL** from `$ARGUMENTS`:
   - Extract `owner`, `repo`, `pr_number` (GitHub) or `project`, `mr_iid` (GitLab)
   - Detect `--dry-run` and `--review-id` flags

2. **Fetch PR metadata:**

   For GitHub:

   ```bash
   gh pr view {pr_number} --repo {owner}/{repo} --json number,headRefName,baseRefName,title,body,state
   ```

   **If PR is closed or merged:** Inform user and exit.

3. **Detect document type** from changed files:

   ```bash
   gh pr diff {pr_number} --repo {owner}/{repo} --name-only
   ```

   Match both QualityFlow output conventions and external repo conventions:
   - STP: files matching `*_test_plan.md` OR `*-stp.md`
   - STD: files matching `*_test_description.yaml` OR `*-std.md` OR `*-std.yaml`
   - Neither → exit with "No QualityFlow documents found in this PR."

   Store the matched file paths — these are the files that will be edited and staged.

4. **Extract issue identifier** using a multi-source fallback chain:

   a. **Filename pattern:** Look for `{PREFIX}-{NUMBER}` in filenames
      (e.g., `CNV-12345_test_plan.md` → `CNV-12345`)
   b. **PR body:** Scan for Jira URLs (`/browse/{KEY}`), Jira IDs (`CNV-\d+`),
      or GitHub issue URLs (`github.com/{owner}/{repo}/issues/{number}`)
   c. **PR title:** Same patterns as PR body
   d. **PR labels:** Look for labels matching Jira prefixes (e.g., `CNV-12345`)
   e. **Branch name:** Extract from branch (e.g., `feature/CNV-12345-fix`)

   If no Jira ID found from any source, check if a GitHub issue URL was found
   in the PR body and use that instead.

   **If no issue identifier found:** Warn but continue — the fix agent can
   still classify and fix comments without project context, using the target
   repo's own review rules.

5. **Read target repo review rules** (if available):

   ```bash
   # Check if the target repo has its own review rules
   gh api repos/{owner}/{repo}/contents/AGENTS.md --jq '.content' 2>/dev/null | base64 -d
   ```

   If `AGENTS.md` exists in the target repo, pass its content to the
   comment-classifier as `target_repo_rules`. This allows the classifier to
   understand the review standards that human reviewers and bots (CodeRabbit)
   are enforcing — which may differ from QualityFlow's internal rules.

6. **Resolve project context:**

   Use the Skill tool to invoke the project-resolver skill:

   **Tool:** Skill
   **Parameters:**
   - skill: "project-resolver"
   - args: "{extracted_issue_id}"

   This returns `project_context` with `config_dir`, `feature_toggles`, etc.

   **If project resolution fails** (unknown prefix, no route):
   - Log the warning but do NOT exit
   - Continue with `project_context: null` — the comment-classifier can still
     classify comments using the target repo's `AGENTS.md` rules
   - The fix agent can still apply simple fixes (checkbox flips, text removals)
     without project-specific config

### Step 1: Fetch Review Comments

Fetch all review data from the PR:

```bash
# Top-level reviews (APPROVED, CHANGES_REQUESTED, COMMENTED)
gh api repos/{owner}/{repo}/pulls/{pr_number}/reviews --jq '.[] | {id, user: .user.login, state: .state, body: .body, submitted_at: .submitted_at}'

# Inline review comments (attached to specific lines)
gh api repos/{owner}/{repo}/pulls/{pr_number}/comments --jq '.[] | {id, user: .user.login, body: .body, path: .path, line: .line, original_line: .original_line, in_reply_to_id: .in_reply_to_id, created_at: .created_at}'
```

**Filter to actionable comments:**

- If `--review-id` was provided: only comments from that review
- Otherwise: collect comments from the **latest** `CHANGES_REQUESTED` review,
  plus any unresolved inline comments from any reviewer
- **Exclude:**
  - Comments from QualityFlow itself (body contains `<!-- qualityflow:pr-fix-agent -->`)
  - Reply comments (`in_reply_to_id` is not null) — these are discussion, not requests
  - Comments on files that are NOT QualityFlow documents
- **Include:**
  - Top-level review body (if non-empty and from a CHANGES_REQUESTED review)
  - All inline comments on STP/STD files

**If no actionable comments found:**
- Inform user: "No actionable review comments found on this PR."
- Exit.

**Enrich comments with section context:**

For each inline comment with `path` and `line`:
1. Read the file at that path
2. Scan upward from the comment line to find the nearest section heading
3. Attach `section` metadata (e.g., "III", "II.3", "I.1")

### Step 1.5: Check for Approval Replies (Re-run Mode)

On re-run, the fix agent checks for approval replies to its previous
proposed fixes before classifying new comments.

1. **Find the fix agent's last comment:**
   ```bash
   gh api repos/{owner}/{repo}/issues/{pr_number}/comments \
     --jq '[.[] | select(.body | contains("<!-- qualityflow:pr-fix-agent -->"))] | last'
   ```

2. **If a previous fix agent comment exists with a "Proposed Fixes" table:**
   Extract the proposed fix numbers and their proposed changes from that table.

3. **Fetch comments posted AFTER the fix agent's last comment:**
   ```bash
   gh api repos/{owner}/{repo}/issues/{pr_number}/comments \
     --jq '[.[] | select(.created_at > "{last_fix_comment_created_at}")]'
   ```

4. **Search for approval replies in those newer comments:**
   Match comment bodies against: `approve\s+[\d,\s]+` (case-insensitive)

   Examples that match:
   - "approve 1, 3"
   - "approve 1,3,5"
   - "Approve 2"

   Extract the approved numbers as an integer set.

5. **If approvals found — apply them:**
   For each approved proposal number:
   a. Look up the corresponding proposed change from the previous comment's table
   b. Read the target document file
   c. Locate the section referenced by the original review comment
   d. Apply the proposed text change
   e. Log: "Applied approved proposal #{N}: {summary}"

6. **Update the PR comment** to reflect applied status:
   Edit the previous fix agent comment (using `gh api --method PATCH`)
   to update the "Proposed Fixes" table — mark applied proposals with
   **Applied** in the Status column.

7. **If no approval replies found:** Continue to Step 2 (classify new comments).

8. **If all proposals already applied and no new comments:** Report
   "All approved proposals applied. No new comments to process." and exit.

### Step 2: Classify Comments

Invoke the **comment-classifier** skill with the enriched comments:

**Tool:** Skill
**Parameters:**
- skill: "comment-classifier"
- args: (pass the comments data, document type, and project context)

**Provide the classifier with:**

```yaml
comments: <filtered and enriched comment list>
document_type: "stp" | "std"
project_context: <from Step 0, or null if project resolution failed>
target_repo_rules: <content of AGENTS.md from target repo, or null>
target_repo: "{owner}/{repo}"
```

**Display classification summary to user:**

```text
Comment Classification for PR #{pr_number}:
  Total comments:  {total}
  Auto-fixable:    {auto_fix_count}
  Propose-fix:     {propose_fix_count}
  Needs human:     {needs_human_count}
```

**If `--dry-run` flag is set:**
- Display the full classification details (which comments map to which rules)
- For propose-fix comments, show the proposed text and research sources
- Exit without making any edits

**If all comments are needs-human (no auto-fix AND no propose-fix):**
- Display the needs-human report
- Post PR comment (Step 5a format) listing what needs human input
- Exit without making any edits

### Step 3: Checkout PR Branch and Apply Fixes

**Check for local repo before cloning:**

If `project_context` was resolved, read `repositories.yaml` from `config_dir`
and check if any repo entry matches `{owner}/{repo}`. If a match is found and
the entry has a `local_path_env` field:

```bash
# Check if env var points to a local clone
LOCAL_PATH="${!local_path_env}"
if [ -n "$LOCAL_PATH" ] && [ -d "$LOCAL_PATH/.git" ]; then
  cd "$LOCAL_PATH"
  echo "Using local repo at $LOCAL_PATH"
fi
```

If a local repo is found, use it directly (fetch + checkout the PR branch).
If not found, fall back to `gh pr checkout` which clones as needed.

**Ensure we're on the PR branch:**

```bash
gh pr checkout {pr_number} --repo {owner}/{repo}
```

**If checkout fails** (e.g., not in a git repo, auth issues):
- Report the error
- Exit

**Create a pre-fix checkpoint:**

```bash
git stash push -m "qualityflow-fix-agent-checkpoint"
```

**Process auto-fixable comments in priority order:**

1. CRITICAL severity first, then MAJOR, then MINOR
2. Within same severity: structural → rule-violation → missing-scenario →
   tier-mismatch → metadata-error

**For each auto-fix comment, apply the fix:**

Read the target document, locate the relevant section/line, and apply the
appropriate edit based on the classification:

- **`rewrite-scenario` (Rule A, A.2, C, K):** Read the scenario text at the
  target line. Rewrite it following scenario-builder rules:
  - Rule A: Replace internal-mechanism language with user-observable language
  - Rule A.2: Remove vague qualifiers, make measurable
  - Rule C: Move prerequisite to Section II.3, replace with behavioral scenario
  - Rule K: Remove regression-only scenario, note in Test Strategy regression checkbox
  Use the Edit tool for targeted replacement.

- **`add-scenario`:** Identify the requirement, generate scenarios per
  scenario-builder conventions (action verb, 5-10 words, positive + negative).
  Insert under the correct requirement in Section III.

- **`restructure` (Rules B, D, E, F, G, H, J):** Compare against template,
  fix structural issues using the Edit tool.

- **`reclassify`:** Update tier assignment in Section III.

- **`update-metadata`:** Correct version, date, or component fields.

**After each edit:**
- Verify the edit was applied (Edit tool confirms success)
- Log what was changed

### Step 4: Validate

After all fixes are applied:

1. **Structural validation:**

   **Tool:** Skill
   **Parameters:**
   - skill: "output-validator"
   - args: "{JIRA_ID}"

   If validation fails:
   - Identify which fix broke structure
   - Revert the breaking edit: `git checkout -- {file_path}`
   - Re-apply remaining fixes
   - Re-validate

2. **PII check** (if `pii_sanitization` toggle is true):

   **Tool:** Skill
   **Parameters:**
   - skill: "pii-sanitizer"
   - args: "{JIRA_ID}"

3. **Self-review** (optional — only if `stp_review` or `std_review` toggle is true):
   - Invoke stp-reviewer or std-reviewer on the fixed document
   - If new CRITICAL findings introduced → log warning (do not revert — the human
     reviewer will catch it in the next review cycle)

### Step 5: Report and Push

#### 5a. Post Fix Summary Comment

Post a comment on the PR summarizing what was done. Use the `gh` CLI:

```bash
gh pr comment {pr_number} --repo {owner}/{repo} --body "$(cat <<'COMMENT_EOF'
<!-- qualityflow:pr-fix-agent -->
## QualityFlow Fix Agent Report

**Document:** {document_type} for {JIRA_ID}
**Comments processed:** {total_comments}

### Auto-Fixed ({auto_fix_count})

| # | Comment | Rule/Category | Fix Applied |
|:--|:--------|:--------------|:------------|
| 1 | {comment_summary} | {rule_or_category} | {fix_description} |
| ... | ... | ... | ... |

### Proposed Fixes — Awaiting Approval ({propose_fix_count})

| # | Comment | Proposed Change | Source | Confidence |
|:--|:--------|:----------------|:-------|:-----------|
| 1 | {comment_summary} | {proposed_text} | {source} | {confidence} |
| ... | ... | ... | ... | ... |

> **How to approve:** Reply to this comment with the numbers you approve (e.g., "approve 1, 3").
> The fix agent will apply approved proposals on the next run.

### Needs Human Input ({needs_human_count})

| # | Comment | Reason |
|:--|:--------|:-------|
| 1 | {comment_summary} | {reason} |
| ... | ... | ... |

### Validation

- Structural: {PASS/FAIL}
- PII check: {PASS/FAIL/skipped}
- Self-review: {verdict/skipped}
COMMENT_EOF
)"
```

#### 5b. Commit and Push

Stage and commit the changes. Stage the actual modified files from
the PR (not a hardcoded directory — files may be in `outputs/`, `stps/`,
or other repo-specific paths):

```bash
git add -u
git add outputs/ stps/ 2>/dev/null || true
git commit -m "fix({doc_type}): address review comments for {JIRA_ID}

Auto-fixed {N} review comment(s):
{bulleted list of fix summaries}

{M} comment(s) flagged for human input.

Co-Authored-By: QualityFlow <noreply@qualityflow>"

git push origin HEAD
```

**If push fails:**
- Report the error to the user
- The local changes remain on the branch for manual resolution
- Do NOT retry or force-push

#### 5b.5. Update PR Description

After a successful push, append a QualityFlow status section to the PR body.
This gives reviewers an at-a-glance summary when they open the PR.

**Skip this step if `--dry-run` is set.**

1. Read current PR body:

   ```bash
   gh pr view {pr_number} --repo {owner}/{repo} --json body --jq .body
   ```

2. If the body already contains `<!-- qualityflow:pr-status -->`, strip
   everything from that marker through `<!-- /qualityflow:pr-status -->`
   (idempotent on re-runs).

3. Append the status section to the (cleaned) body:

   ```markdown
   <!-- qualityflow:pr-status -->
   ---
   **QualityFlow Status** — updated {YYYY-MM-DD}

   | Metric | Value |
   |:-------|:------|
   | Document | {document_type} for {JIRA_ID} |
   | Review comments | {auto_fixed} fixed, {propose_fix} proposed, {needs_human} flagged |
   | Validation | Structural: {PASS/FAIL} |
   | Fix iterations | {iteration_count} |

   [Detailed fix report]({fix_comment_url})
   <!-- /qualityflow:pr-status -->
   ```

4. Update the PR:

   ```bash
   gh pr edit {pr_number} --repo {owner}/{repo} --body "$updated_body"
   ```

**If `gh pr edit` fails:** Log a warning but do not fail the overall run —
the fixes are already pushed and the PR comment is posted.

#### 5c. Final Report

Display to the user:

```text
PR Fix Complete: PR #{pr_number}

Document:       {document_type} for {JIRA_ID}
Comments:       {total} processed ({auto_fixed} fixed, {propose_fix} proposed, {needs_human} flagged)
Commit:         {commit_sha}
PR comment:     Posted fix summary

{If propose_fix > 0:}
The following fixes were proposed and need approval:
  - {comment 1 summary} — proposed: "{proposed_text}" (confidence: {confidence})
  - {comment 2 summary} — proposed: "{proposed_text}" (confidence: {confidence})

{If needs_human > 0:}
The following comments need human attention:
  - {comment 1 summary} — {reason}
  - {comment 2 summary} — {reason}

{If all auto-fixed and propose_fix == 0:}
All review comments have been addressed. The PR is ready for re-review.
```

## Error Handling

- **Invalid PR URL:** "Could not parse PR URL. Expected format: https://github.com/owner/repo/pull/123"
- **PR not found:** "PR #{pr_number} not found in {owner}/{repo}. Check the URL and your access."
- **No QualityFlow docs:** "No STP or STD files found in this PR's changed files."
- **Project resolution fails:** "Could not resolve project for Jira ID {id}. Check config/routing.yaml."
- **No actionable comments:** "No actionable review comments found. Nothing to fix."
- **Checkout fails:** "Could not checkout PR branch. Ensure you have write access."
- **Push fails:** "Could not push to PR branch: {error}. Changes saved locally."

## Example Usage

```text
User: /fix-pr https://github.com/kubevirt/kubevirt/pull/12345
User: /fix-pr kubevirt/kubevirt#12345
User: /fix-pr https://github.com/kubevirt/kubevirt/pull/12345 --dry-run
User: /fix-pr https://github.com/kubevirt/kubevirt/pull/12345 --review-id=987654
```
