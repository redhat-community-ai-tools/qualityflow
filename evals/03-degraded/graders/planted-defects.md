---
type: llm
focus: last_message
weight: 1
---
You are grading a QE review of a deliberately degraded Software Test Plan. The
STP is a real, clean baseline (which reviewed at 0 critical) with five itemised
degradations applied, each targeting a specific reviewer rule. This is the
suite's sensitivity probe: it fails when a reviewer stops noticing rule
violations it is supposed to catch. Every critical here is attributable to a
listed edit.

The five planted defects the review must catch:

- **C1 — Rule A (Abstraction), Scope of Testing.** The Scope sentence now names
  the internal reconcile path directly ("virt-controller reconciler sync loop
  that propagates hotplug volume status annotations onto the VMI object, the VMI
  mutating webhook trigger path") — internal component names and implementation
  verbs in a user-facing section.
- **C2 — Rule A (Abstraction), Testing Goals.** Two Testing Goals were rewritten
  in implementation terms (reconciler syncs annotations / re-triggers propagation
  loop; PCI port allocator internal free-port bookkeeping). C1 and C2 may
  legitimately be MERGED into a single Rule A finding — count that as catching
  both.
- **C3 — Rule C (Prerequisites vs Test Scenarios).** The REQ-EMPTY-CDROM-01
  Section III scenario is now a bare environment prerequisite (feature gate
  enabled, CDI deployed with a StorageClass "before test execution") with no
  behavioural verification of the requirement it claims to cover.
- **C4 — Dimension 2 (Requirement Coverage).** Two acceptance criteria now have
  zero covering scenarios: virtctl addvolume/removevolume persisting to the VM
  spec by default, and the ephemeral hotplug restriction observable via a
  metric/alert (the REQ-VIRTCTL-* and REQ-EPHEMERAL-* rows were deleted). May be
  reported as one combined coverage-gap finding or two.
- **D5 — Rule J (One Tier Per Row).** REQ-E2E-LIFECYCLE-01 now carries
  "Tier 1 / Tier 2" in a single Tier cell.

The review PASSES only if it names **at least 4 of these 5** defects (with C1+C2
counting as one when merged, so catching the merged Rule A finding + C3 + C4 + D5
= 4 = pass). Wording, rule letter, dimension number, and severity may differ from
the labels above; what matters is that the underlying defect at that location is
named. A finding you cannot ground in the STP text is a hallucination — note it,
and it does not count toward the four.

Return whether the review passes and a short rationale naming which of the five
planted defects were caught and which were missed.
