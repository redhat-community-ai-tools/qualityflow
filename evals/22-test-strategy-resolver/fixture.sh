#!/bin/bash
# A small repository with clear pytest conventions for the resolver to detect.
set -e
mkdir -p tests/storage tests/network src/storage
printf '[project]\nname = "workload-tests"\nrequires-python = ">=3.11"\ndependencies = ["pytest", "pytest-testconfig", "kubernetes"]\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\nmarkers = ["polarion: test case id", "gating: gating suite"]\n' > pyproject.toml
cat > tests/storage/test_attach.py <<'PY'
import pytest

from src.storage.volumes import attach_volume


@pytest.mark.polarion("PROJ-1111")
@pytest.mark.gating
class TestAttachVolume:
    def test_disk_attached_to_running_instance(self, running_instance, volume_source):
        attach_volume(running_instance, volume_source)
        assert volume_source.name in [v.name for v in running_instance.status.volumes]
PY
cat > tests/network/test_nad.py <<'PY'
import pytest


@pytest.mark.polarion("PROJ-2222")
def test_network_attach(running_instance, net_profile):
    assert net_profile.name in running_instance.interfaces
PY
printf 'def attach_volume(instance, source):\n    return instance.attach(source)\n' > src/storage/volumes.py
