---
name: approve
description: Approve (or reject) a reviewed STP or STD so the next phase can run — the CLI counterpart of the dashboard's Approve button
argument-hint: <JIRA_ID> stp|std [--reject] [--comment "<text>"]
allowed-tools: Bash, Read
---

# Approve a reviewed STP or STD

`/std-builder` waits for a person to approve the reviewed STP, and
`/generate-tests` for the reviewed STD. This records that decision, as the
dashboard's Approve and Reject buttons do.

`$ARGUMENTS`: the ticket, `stp` or `std`, then optional `--reject` and
`--comment "<text>"`.

1. Show the latest verdict first, so the person approves knowingly:
   `python skills/pipeline-state/state.py status {JIRA_ID}`, and the review report
   (`outputs/{JIRA_ID}/reviews/{JIRA_ID}_{stp|std}_review.md`) verdict line when
   it exists.
2. Record the decision:

   ```bash
   python skills/pipeline-state/state.py approve {JIRA_ID} {stp|std} --by "<name>" [--reject] [--comment "<text>"]
   ```

   `--by` is the person approving: their name as they gave it, else
   `git config user.name`. Never approve on your own initiative: run this only
   when the person asked for it in this command.
3. Report the decision and the next step: `/std-builder {JIRA_ID}` after an STP
   approval, `/generate-tests {JIRA_ID}` after an STD approval, or
   `/refine-stp|std {JIRA_ID} --address-findings` after a rejection.
