#!/bin/bash
# Config and pipeline state exist, but no STP was ever generated for this ticket.
set -e
root="$(cd "$(dirname "$0")" && pwd)/../.."
cp -R "$root/config" ./config
mkdir -p skills/pipeline-state
cp "$root/skills/pipeline-state/state.py" skills/pipeline-state/
