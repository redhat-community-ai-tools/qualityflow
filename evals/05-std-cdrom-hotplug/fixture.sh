#!/bin/bash
# Seeds the workspace /std-builder expects after an approved STP: project config,
# the STP, pipeline state with stp completed + approved, and a small pytest repo to
# auto-detect the test language from.
set -e
here="$(cd "$(dirname "$0")" && pwd)"
root="$here/../.."
J=CNV-68916
cp -R "$root/config" ./config
# The STD review chain has its own suite; isolate generation here.
perl -pi -e 's/^(\s*std_review:\s*)true/${1}false/' config/projects/cnv/project.yaml
mkdir -p skills/pipeline-state "outputs/$J/stp" "outputs/$J/state"
cp "$root/skills/pipeline-state/state.py" skills/pipeline-state/
cp "$here/fixtures/${J}_test_plan.md" "outputs/$J/stp/"
python3 skills/pipeline-state/state.py init "$J" --project-id cnv --display-name "OpenShift Virtualization" >/dev/null
python3 skills/pipeline-state/state.py start-phase "$J" stp >/dev/null
python3 skills/pipeline-state/state.py complete-phase "$J" stp --output "outputs/$J/stp/${J}_test_plan.md" >/dev/null
printf 'approvals:\n  stp_review: {status: approved}\n' > "outputs/$J/state/approvals.yaml"
# Repository under test: pytest, storage tests grouped by feature.
mkdir -p tests/storage
printf '[project]\nname = "virt-tests"\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n' > pyproject.toml
cat > tests/storage/test_hotplug.py <<'PY'
import pytest


@pytest.mark.polarion("CNV-0000")
class TestHotplugVolume:
    def test_hotplug_disk_attached(self, running_vm):
        """Preconditions: running VM. Steps: hotplug a disk. Expected: disk visible in guest."""
        assert running_vm.vmi.status.volume_status
PY
