---
name: pii-sanitizer
description: Sanitize PII and sensitive data from STP documents
model: claude-opus-4-6
---

# PII Sanitizer Skill

**Phase:** Post-Processing
**User-Invocable:** true

## Purpose

Sanitize Personally Identifiable Information (PII) and sensitive data from STP documents.

## When to Use

- Invoked by **document-formatter** subagent during post-processing
- Can be invoked standalone by users via `/pii-sanitizer`

## How to Run

**Step 1 — deterministic regex pass (always run the script first; never apply
these regexes by hand — a missed substitution is a data leak).** From the
repo root:

```bash
# In place:
python3 skills/pii-sanitizer/sanitize.py --project {project_id} --in-place <file>...
# Or as a filter:
python3 skills/pii-sanitizer/sanitize.py --project {project_id} < in.md > out.md
```

The script deterministically handles, honoring the project allowlist in
`config/projects/{project_id}/pii_exceptions.yaml` (all `allowed_*` lists):

| Category | Rule |
|:---------|:-----|
| IP addresses | Any non-RFC-5737 IPv4 is renumbered **statefully and sequentially** into documentation ranges: first unique IP → `192.0.2.1`, second → `192.0.2.2`, ... (same original always maps to the same replacement; spills into `198.51.100.x` / `203.0.113.x` after 254). RFC 5737 addresses are left untouched. |
| Email addresses | → `user@example.com`; role preserved when evident (`admin@...` → `admin@example.com`). `@example.com/org/net` left untouched. |
| UUIDs | → `<uuid>` |
| MAC addresses | Statefully renumbered into the documentation range `00:00:5E:00:53:xx`. |
| Hostnames / FQDNs | Multi-label names (`*.internal`, `*.corp`, `*.com`, ...) → `node-N.example.com`, keeping role indicators: `worker`/`master`/`compute` → `worker-node-N.example.com` etc. Same original always maps to the same replacement; `example.com/org/net` and allowlisted names untouched. |
| Credential-shaped tokens | Vendor-prefixed tokens (`ghp_`, `github_pat_`, `glpat-`, `sk-`, `AKIA…`) → `<token>` / `<api-key>`; PEM private-key blocks → `<private-key>`; `://user:pass@host` URL userinfo → `://<credentials>@host`. Deliberately narrow — the allowlist does **not** apply (a credential is never legitimate output). Credentials in prose are still Step 2. |

It prints a `sanitization_summary` (per-category counts) to stderr — include
it in your report.

**Step 2 — judgment pass (the ONLY LLM part of this skill).** The script
cannot recognize names. After it runs, review the document for the
categories below and replace them yourself.

## Data Categories Requiring Judgment (LLM step)

### Customer Information

| Original | Replacement |
|:---------|:------------|
| Customer names | `<customer>`, `Example Corp`, `ACME Inc` |
| Account IDs | `<account-id>` |
| Organization names | `<organization>` |

### User Identifiers

| Original | Replacement |
|:---------|:------------|
| Usernames (outside email addresses) | `testuser`, `admin-user`, `<username>` |
| Employee IDs | `<user-id>` |

### Credentials

**NEVER include credentials in output.** The script already redacts
recognisably-shaped tokens (see Step 1); this pass covers the rest — secrets
described in prose, unusual token formats, and pasted config values:

- Passwords → `<password>`
- API keys → `<api-key>`
- Tokens → `<token>`
- Certificates → `<certificate>`
- Secrets → `<secret>`

### Infrastructure Names

| Original | Replacement |
|:---------|:------------|
| VM names | `test-vm`, `fedora-vm`, `windows-vm` |
| Pod names | `pod-example` |
| Namespace names | `test-namespace`, `example-namespace` |
| PVC names | `test-pvc`, `pvc-example` |
| Storage classes | `storageclass-example` |
| NIC/Bridge names | `nic-example`, `br-example` |
| Cluster names | `cluster-example` |
| Node names (bare, no domain suffix) | `node-example`, `worker-node-1` |

### File Paths

| Original | Replacement |
|:---------|:------------|
| `/home/jsmith/...` | `/home/<user>/...` |
| `/data/acme/...` | `/data/<customer>/...` |

### Vendor Names

**Never use specific vendor names (except allowed names from project config and open source projects).**

**Read `config/projects/{project_id}/pii_exceptions.yaml` first.** If it has a
`vendor_replacements` mapping, its value for a config key **overrides** the
default below for that category (e.g. `cloud: "Cloud Provider"` means AWS/Azure/GCP
become `Cloud Provider`, not `Cloud Infrastructure Provider`). Keys not listed
there, or a missing file, fall back to the defaults.

| Config key | Vendor Category | Default Replacement |
|:-----------|:----------------|:--------------------|
| `virtualization` | VMware, Hyper-V | Virtualization Infrastructure Vendor |
| `network` | Cisco, Juniper | Network Infrastructure Vendor |
| `storage` | NetApp, Dell EMC | Storage Infrastructure Vendor |
| `cloud` | AWS, Azure, GCP | Cloud Infrastructure Provider |
| `hardware` | Dell, HP | Hardware Vendor |
| `gpu` | NVIDIA, AMD GPU | GPU Vendor |
| `nic` | Mellanox, Broadcom | NIC Vendor |
| `backup` | Veeam, Commvault | Backup/DR Vendor |

**Exceptions (allowed):**

- Names in `config/projects/{project_id}/pii_exceptions.yaml` (project-specific
  allowed vendor/product names, open source projects the team works with)
- Open source projects referenced in project config
- Technical standards: SR-IOV, NVMe, iSCSI, NFS
- CPU tech references: Intel VT-x, AMD-V

## Output Format

```yaml
sanitized_document: |
  # STP content with sanitized data ...

sanitization_summary:
  # script counts (from stderr):
  ips_replaced: 3
  emails_replaced: 2
  uuids_replaced: 0
  macs_replaced: 0
  hostnames_replaced: 5
  credentials_replaced: 0
  # LLM judgment counts:
  customer_names_replaced: 4
  vendor_names_replaced: 1
  credentials_found: 0
  total_replacements: 15
```

## Verification Checklist

Before returning sanitized document:

- [ ] Script was run and its summary captured (never a hand-applied regex pass)
- [ ] No real customer names or identifiers
- [ ] No credentials, tokens, or secrets
- [ ] All infrastructure names are generic
- [ ] No third-party vendor names (except allowed exceptions)
- [ ] All vendor references use generic categories

## When in Doubt

**If uncertain whether data is sensitive: sanitize it.**

It is better to use generic names than risk exposing sensitive information.
