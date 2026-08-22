# Reference: expected findings for the degraded CNV-68916 STP

> **This is not a captured reviewer run.** The other two cases in this suite ship a
> real `*_stp_review.md` produced by the pipeline. This file is *derived*: it states
> what the five documented degradations in `annotations.yaml` must produce, according
> to `skills/stp-reviewer/SKILL.md`'s own rule and severity definitions. Treat it as a
> checklist of must-find items, not as a gold-standard prose review. Judges that
> compare produced prose against this file should score coverage of the listed
> findings, not stylistic resemblance.

The baseline document — the same STP with none of these edits — was reviewed by the
real pipeline as `APPROVED_WITH_FINDINGS` with **0 critical / 7 major / 9 minor**
(see `../cnv-68916-cdrom-hotplug/reference.md`). Every critical below is therefore
attributable to a degradation and nothing else.

---

## Verdict: NEEDS_REVISION

Follows deterministically from SKILL.md's verdict table: 1+ critical finding blocks
approval. A run that reports any other verdict on this input has failed.

## Expected critical findings (4)

### C1 — Rule A (Abstraction Level), Scope of Testing II.1 — from degradation D2

The Scope of Testing sentence now names the internal reconcile path directly:
"the virt-controller reconciler sync loop that propagates hotplug volume status
annotations onto the VMI object, the VMI mutating webhook trigger path". Rule A
classifies internal component references (`controller`, `reconciler`, `sync`,
`annotation`, `trigger`, `webhook` used as an internal mechanism) found in
Scope/Goals/Scenarios as CRITICAL. The user-facing rewrite belongs in Scope; the
mechanism belongs in Technology Challenges (I.2) at most.

### C2 — Rule A (Abstraction Level), Testing Goals — from degradation D3

Two Testing Goals were rewritten in implementation terms:

- "Verify the virt-controller reconciler syncs the hotplug volume status annotation
  from the VM spec onto the VMI object and re-triggers the volume propagation loop"
- "Validate the PCI port allocator's internal free-port bookkeeping and the
  hotplug-status annotation the controller writes back after each reconcile pass"

Both use internal component names plus implementation verbs (`reconcile`, `sync`,
`trigger`, `propagate`) that Rule A lists explicitly. A reviewer may legitimately
merge C1 and C2 into a single Rule A critical finding; the finding-count tolerance in
`annotations.yaml` accommodates that.

### C3 — Rule C (Prerequisites vs Test Scenarios), REQ-EMPTY-CDROM-01 — from degradation D4

The scenario for REQ-EMPTY-CDROM-01 is now purely a prerequisite — "Verify the
`DeclarativeHotplugVolumes` feature gate is enabled in the HyperConverged CR and that
CDI is deployed with a dynamic-provisioning StorageClass before test execution" —
with no behavioural verification of the requirement it claims to cover ("Empty CD-ROM
drive can be defined in VM spec"). Rule C: CRITICAL when a prerequisite appears as a
test scenario in Section III without a corresponding behavioural verification. The
content belongs in Entry Criteria (II.4) / Test Environment (II.3).

### C4 — Dimension 2 (Requirement Coverage), two acceptance criteria with zero coverage — from degradation D1

`jira_data.main_issue.acceptance_criteria` lists five criteria. Two now have no
covering scenario anywhere in Section III:

| Acceptance criterion | Coverage before | Coverage now |
|:---|:---|:---|
| virtctl addvolume/removevolume persist to the VM spec by default | REQ-VIRTCTL-01..04 | none |
| Ephemeral hotplug restriction is enforced and observable via a metric/alert | REQ-EPHEMERAL-01, REQ-EPHEMERAL-02 | none |

Missing coverage of an acceptance criterion is CRITICAL per the severity table
("missing coverage ... makes the STP unusable"). A reviewer that reports one combined
coverage-gap finding rather than two is also acceptable.

## Expected non-critical findings

These should also appear; they are not scored deterministically.

- **Rule J (One Tier Per Row) — CRITICAL or MAJOR, from degradation D5.** REQ-E2E-LIFECYCLE-01 now carries
  `Tier 1 / Tier 2` in a single Tier cell. SKILL.md lists multi-tier cells as a Rule J
  CRITICAL red flag; if a run reports it as CRITICAL the total rises to 5, which is
  inside tolerance.
- **Rule K (Cross-Section Consistency) — MAJOR, a side effect of D1.** Section II.2 still marks Monitoring
  and Backward Compatibility as `Y` and cites the metric and the deprecated `--persist`
  flag, and the Testing Goals still promise virtctl and ephemeral-hotplug validation,
  but Section III no longer contains a single scenario for either. Goals and strategy
  now contradict the traceability matrix.
- **The baseline's own findings should survive.** Performance Testing and Security
  Testing marked `Y` without SLAs or feature-specific RBAC, in-product components
  listed as Dependencies, standard tools listed in II.3.1, feature content in the
  Section I Details/Notes column, `sig-network` listed with no matching scenario,
  verbose scenario text, `VMI status` in scenario prose, and the placeholder sign-off
  entries. A run that finds the four criticals but loses most of these has changed its
  sensitivity, not just its verdict — worth investigating even though the case passes.
