#!/usr/bin/env python3
"""QualityFlow deterministic PII sanitizer.

Applies the mechanical regex categories from the pii-sanitizer SKILL.md
(audit finding AI-02): IP addresses (stateful sequential renumbering into
RFC 5737 ranges), email addresses, UUIDs, MAC addresses, hostnames/FQDNs, and
credential-shaped tokens (SEC-02-F4: vendor-prefixed tokens, PEM private-key
blocks, `://user:pass@` URL userinfo).
Judgment calls (person names, customer names, vendor names, credentials in
prose) remain an LLM step — see SKILL.md.

Usage:
    python3 skills/pii-sanitizer/sanitize.py [--project ID] --in-place FILE...
    python3 skills/pii-sanitizer/sanitize.py [--project ID] < in.md > out.md

A YAML summary of replacement counts is printed to stderr.
Exit codes: 0 = ok, 2 = usage / file problem.
"""

import argparse
import re
import sys

import yaml

DOC_IP_PREFIXES = ("192.0.2.", "198.51.100.", "203.0.113.")
DOC_IP_NETS = ["192.0.2.%d", "198.51.100.%d", "203.0.113.%d"]
ALLOWED_EMAIL_DOMAINS = ("example.com", "example.org", "example.net")

IP_RE = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
    r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
MAC_RE = re.compile(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b")
# Hostnames/FQDNs: 2+ dotted labels ending in a common TLD or internal suffix.
HOST_RE = re.compile(
    r"\b(?=[A-Za-z0-9-]*[A-Za-z])[A-Za-z0-9][A-Za-z0-9-]*"
    r"(?:\.[A-Za-z0-9][A-Za-z0-9-]*)*"
    r"\.(?:internal|local|corp|lan|intra|com|net|org|io|cloud)\b")

ROLE_INDICATORS = ("worker", "master", "compute")

# Credential-shaped strings (audit finding SEC-02-F4). Deliberately narrow:
# only tokens with an unambiguous vendor prefix / PEM banner / URL userinfo.
# Credentials in prose ("the password is hunter2") stay an LLM judgment call —
# a false positive on ordinary ticket text is worse than a rare miss for a
# category that already has a second pass. Placeholders match SKILL.md.
CRED_RES = (
    (re.compile(r"\bghp_[A-Za-z0-9]{36,}"), "<token>"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "<token>"),
    (re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}"), "<token>"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}"), "<api-key>"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "<api-key>"),
    # Whole PEM block when the footer is present, banner alone otherwise.
    (re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----"
                r"(?s:.*?-----END (?:[A-Z]+ )?PRIVATE KEY-----)?"),
     "<private-key>"),
    (re.compile(r"://[^/\s:@]+:[^/\s@]+@"), "://<credentials>@"),
)


class Sanitizer:
    def __init__(self, allowlist=()):
        self.allow = {a.lower() for a in allowlist}
        self.ip_map, self.mac_map, self.host_map = {}, {}, {}
        self.counts = {"ips_replaced": 0, "emails_replaced": 0,
                       "uuids_replaced": 0, "macs_replaced": 0,
                       "hostnames_replaced": 0, "credentials_replaced": 0}

    def allowed(self, value):
        return value.lower() in self.allow

    # -- category handlers --------------------------------------------------

    def _ip(self, m):
        ip = m.group(0)
        if any(int(o) > 255 for o in ip.split(".")):
            return ip  # not a real IPv4 (e.g. a version string)
        if ip.startswith(DOC_IP_PREFIXES) or self.allowed(ip):
            return ip
        if ip not in self.ip_map:
            n = len(self.ip_map)
            # 1..254 per documentation /24, then spill to the next RFC 5737 net
            self.ip_map[ip] = DOC_IP_NETS[(n // 254) % 3] % (n % 254 + 1)
        self.counts["ips_replaced"] += 1
        return self.ip_map[ip]

    def _email(self, m):
        email = m.group(0)
        local, _, domain = email.partition("@")
        if domain.lower() in ALLOWED_EMAIL_DOMAINS or self.allowed(email):
            return email
        self.counts["emails_replaced"] += 1
        # Preserve the role when evident (SKILL.md: admin@... -> admin@example.com)
        role = "admin" if local.lower().startswith("admin") else "user"
        return role + "@example.com"

    def _uuid(self, m):
        if self.allowed(m.group(0)):
            return m.group(0)
        self.counts["uuids_replaced"] += 1
        return "<uuid>"

    def _mac(self, m):
        mac = m.group(0)
        if mac.upper().startswith("00:00:5E:00:53:") or self.allowed(mac):
            return mac
        if mac not in self.mac_map:
            self.mac_map[mac] = "00:00:5E:00:53:%02X" % (len(self.mac_map) + 1 & 0xFF)
        self.counts["macs_replaced"] += 1
        return self.mac_map[mac]

    def _creds(self, text):
        # No allowlist check: a credential is never legitimate output, so an
        # allowlist entry must not be able to un-redact one.
        for rx, placeholder in CRED_RES:
            text, n = rx.subn(placeholder, text)
            self.counts["credentials_replaced"] += n
        return text

    def _host(self, m):
        host = m.group(0)
        low = host.lower()
        if (low.endswith(ALLOWED_EMAIL_DOMAINS) or self.allowed(host)
                or self.allowed(low.split(".")[0])):
            return host
        if host not in self.host_map:
            role = next((r for r in ROLE_INDICATORS if r in low), None)
            prefix = (role + "-node") if role else "node"
            n = sum(1 for v in self.host_map.values()
                    if v.startswith(prefix + "-")) + 1
            self.host_map[host] = "%s-%d.example.com" % (prefix, n)
        self.counts["hostnames_replaced"] += 1
        return self.host_map[host]

    # -- driver -------------------------------------------------------------

    def sanitize(self, text):
        # Order matters: credentials first so a `://user:pass@host` userinfo is
        # gone before the host/email/IP passes rewrite pieces of it; emails
        # before hostnames so email domains are not re-matched as FQDNs;
        # UUIDs/MACs before IPs is harmless.
        text = self._creds(text)
        text = UUID_RE.sub(self._uuid, text)
        text = MAC_RE.sub(self._mac, text)
        text = EMAIL_RE.sub(self._email, text)
        text = IP_RE.sub(self._ip, text)
        text = HOST_RE.sub(self._host, text)
        return text

    def summary(self):
        s = dict(self.counts)
        s["total_replacements"] = sum(self.counts.values())
        return s


def load_allowlist(project):
    """Flatten config/projects/{p}/pii_exceptions.yaml allowed_* lists."""
    if not project:
        return []
    path = "config/projects/%s/pii_exceptions.yaml" % project
    try:
        doc = yaml.safe_load(open(path)) or {}
    except OSError:
        print("warning: %s not found; no project allowlist" % path,
              file=sys.stderr)
        return []
    names = []
    for key, val in doc.items():
        if key.startswith("allowed_") and isinstance(val, list):
            names.extend(str(v) for v in val)
    return names


# ----------------------------------------------------------------- self-test

def self_test():
    s = Sanitizer(allowlist=["kubernetes.io"])
    out = s.sanitize(
        "VM on node 'k8s-worker-1.acme-corp.internal' (IP: 10.42.15.87) to "
        "'k8s-worker-2.acme-corp.internal' (IP: 10.42.15.88), again 10.42.15.87. "
        "User jsmith@acme-corp.com and admin@acme.com reported it. "
        "Volume 6f9619ff-8b86-d011-b42d-00c04fc964ff on 00:1B:44:11:3A:B7. "
        "Docs IP 192.0.2.55 stays. See kubernetes.io and example.com.")
    assert "192.0.2.1" in out and "192.0.2.2" in out, out
    assert out.count("192.0.2.1)") == 1 and "again 192.0.2.1" in out, out  # stable map
    assert "10.42.15" not in out, out
    assert "user@example.com" in out and "admin@example.com" in out, out
    assert "acme" not in out.lower(), out
    assert "<uuid>" in out and "00:1B:44" not in out, out
    assert "00:00:5E:00:53:01" in out, out
    assert "worker-node-1.example.com" in out and "worker-node-2.example.com" in out, out
    assert "192.0.2.55" in out, out                      # RFC 5737 untouched
    assert "kubernetes.io" in out and "example.com" in out, out  # allowlist

    # version-ish string with >255 octet is not an IP
    assert Sanitizer().sanitize("v1.2.3.400") == "v1.2.3.400"

    # -- credential tier (SEC-02-F4) ---------------------------------------
    c = Sanitizer()
    out = c.sanitize(
        "curl -H 'Authorization: Bearer ghp_" + "A" * 36 + "' \n"
        "export PAT=github_pat_" + "b" * 30 + "\n"
        "glpat-" + "c" * 20 + " and sk-" + "d" * 24 + "\n"
        "aws_access_key_id = AKIA1234567890ABCDEF\n"
        "psql postgres://dbuser:s3cr3t@db.acme-corp.internal:5432/app\n"
        "-----BEGIN RSA PRIVATE KEY-----\nMIIabc123\n-----END RSA PRIVATE KEY-----\n")
    assert "ghp_" not in out and out.count("<token>") == 3, out
    assert "github_pat_" not in out and "glpat-" not in out, out
    assert "sk-" not in out and "AKIA" not in out, out
    assert out.count("<api-key>") == 2, out
    assert "PRIVATE KEY" not in out and "MIIabc123" not in out, out
    assert "<private-key>" in out, out
    assert "dbuser" not in out and "s3cr3t" not in out, out
    assert "postgres://<credentials>@" in out, out
    assert "acme" not in out.lower(), out   # host pass still runs after creds
    assert c.counts["credentials_replaced"] == 7, c.counts

    # conservative: ordinary ticket prose is not rewritten
    plain = ("The sk-prefixed flag and AKIAB (short) stay. "
             "See https://docs.example.com:8443/a@b for the port syntax.")
    assert Sanitizer().sanitize(plain) == plain, Sanitizer().sanitize(plain)
    print("self-test: OK")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help="files to sanitize (with --in-place)")
    ap.add_argument("--in-place", action="store_true",
                    help="rewrite the given files; default is stdin -> stdout")
    ap.add_argument("--project",
                    help="project id, loads config/projects/{p}/pii_exceptions.yaml")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        self_test()
        return

    san = Sanitizer(allowlist=load_allowlist(args.project))
    if args.in_place:
        if not args.files:
            ap.error("--in-place requires at least one file")
        for path in args.files:
            try:
                text = open(path, encoding="utf-8").read()
                open(path, "w", encoding="utf-8").write(san.sanitize(text))
            except OSError as e:
                print("error: %s" % e, file=sys.stderr)
                sys.exit(2)
    else:
        if args.files:
            ap.error("positional files need --in-place (or pipe via stdin)")
        sys.stdout.write(san.sanitize(sys.stdin.read()))

    yaml.safe_dump({"sanitization_summary": san.summary()}, sys.stderr,
                   default_flow_style=False, sort_keys=False)


if __name__ == "__main__":
    main()
