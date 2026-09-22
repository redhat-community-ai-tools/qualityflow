#!/bin/bash
# A small repository with clear pytest conventions for the resolver to detect.
set -e
mkdir -p tests/storage tests/network src/virt
printf '[project]\nname = "virt-tests"\nrequires-python = ">=3.11"\ndependencies = ["pytest", "pytest-testconfig", "kubernetes"]\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\nmarkers = ["polarion: test case id", "gating: gating suite"]\n' > pyproject.toml
cat > tests/storage/test_hotplug.py <<'PY'
import pytest

from src.virt.volumes import attach_volume


@pytest.mark.polarion("CNV-1111")
@pytest.mark.gating
class TestHotplugVolume:
    def test_disk_attached_to_running_vm(self, running_vm, dv_source):
        attach_volume(running_vm, dv_source)
        assert dv_source.name in [v.name for v in running_vm.vmi.status.volumes]
PY
cat > tests/network/test_nad.py <<'PY'
import pytest


@pytest.mark.polarion("CNV-2222")
def test_nad_hotplug(running_vm, nad):
    assert nad.name in running_vm.interfaces
PY
printf 'def attach_volume(vm, source):\n    return vm.attach(source)\n' > src/virt/volumes.py
