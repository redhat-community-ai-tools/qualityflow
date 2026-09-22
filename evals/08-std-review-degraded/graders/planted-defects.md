---
type: llm
focus: {source: file, path: outputs/CNV-68916/reviews/CNV-68916_std_review.md}
---
This STD was deliberately degraded with three independent defects, each CRITICAL under the
reviewer's rules:

- D1 coverage gap: STP requirement REQ-PCI-02 ("VMs with more than 2G memory get 16 PCI
  ports") has no STD scenario and no stub.
- D2 orphan: STD scenario TS-CNV-68916-048 / REQ-CDROM-EJECT-99 ("CD-ROM can be ejected
  from a paused VM") has no matching STP row.
- D3 missing PSE: stub test_inject_pvc_into_running_vm (TS-CNV-68916-002) has no docstring
  at all — its body is just `pass`.

PASS only if the review names all three (REQ-PCI-02, REQ-CDROM-EJECT-99 or TS-CNV-68916-048,
and the TS-CNV-68916-002 stub) as critical or blocking findings, and its verdict, finding
counts and final YAML block agree with each other.

FAIL if any planted defect is missed or rated only major/minor, or if the review invents a
critical finding that cannot be grounded in the files.
