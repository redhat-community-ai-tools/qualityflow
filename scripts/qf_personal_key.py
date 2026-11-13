#!/usr/bin/env python3
"""Make a personal dashboard key (deploy/README.md "Signing in", QF_API_KEYS_FILE).

    uv run scripts/qf_personal_key.py "Ada Lovelace" ada@example.com

Prints the key once, for that person to paste into Settings > Dashboard API
key, and the line to add to the keys file. The file holds only the key's
sha256, so it can sit in a Secret or a repo without giving anyone access.
Remove the line to take the key away; the dashboard picks the change up
without a restart.
"""
import hashlib
import json
import secrets
import sys

if len(sys.argv) != 3 or "@" not in sys.argv[2]:
    sys.exit(__doc__)
name, email = sys.argv[1], sys.argv[2].lower()
key = "qfp_" + secrets.token_urlsafe(24)
print(f"Key for {name} (give it to them; it is not stored anywhere):\n\n  {key}\n")
print("Add to the keys file:\n")
print(f"- name: {json.dumps(name)}\n  email: {email}\n  sha256: {hashlib.sha256(key.encode()).hexdigest()}")
