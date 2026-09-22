---
type: llm
focus: last_message
---
config/routing.yaml routes the CNV Jira prefix to the project at config/projects/cnv, whose
project.yaml sets test_strategy "auto" and keeps stp_review and std_review on. The defaults
in config/_defaults.yaml set polarion false.

PASS if the answer names the cnv project and its config directory, and reports the settings
from those files (auto test strategy, reviews enabled) without contradicting them.

FAIL if it resolves the ticket to a different project (e.g. the example project), claims
tier mode, or invents settings that are not in the config files.
