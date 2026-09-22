#!/bin/bash
# A three-scenario STD plus the repo whose conventions the generated tests must match.
set -e
here="$(cd "$(dirname "$0")" && pwd)"
mkdir -p outputs/PROJ-12345/std tests/storage src/virt
cp "$here/fixtures/PROJ-12345_test_description.yaml" outputs/PROJ-12345/std/
printf '[project]\nname = "virt-tests"\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\nmarkers = ["polarion: test case id"]\n' > pyproject.toml
cat > tests/storage/test_hotplug.py <<'PY'
import pytest

from src.virt.volumes import attach_volume


@pytest.mark.polarion("CNV-1111")
class TestHotplugVolume:
    def test_disk_attached_to_running_vm(self, running_vm, dv_source):
        attach_volume(running_vm, dv_source)
        assert dv_source.name in [v.name for v in running_vm.vmi.status.volumes]
PY
printf 'def attach_volume(vm, source):\n    return vm.attach(source)\n\n\ndef detach_volume(vm, name):\n    return vm.detach(name)\n' > src/virt/volumes.py
