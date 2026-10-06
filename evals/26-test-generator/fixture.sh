#!/bin/bash
# A three-scenario STD plus the repo whose conventions the generated tests must match.
set -e
here="$(cd "$(dirname "$0")" && pwd)"
mkdir -p outputs/PROJ-12345/std tests/storage src/storage
cp "$here/fixtures/PROJ-12345_test_description.yaml" outputs/PROJ-12345/std/
printf '[project]\nname = "workload-tests"\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\nmarkers = ["polarion: test case id"]\n' > pyproject.toml
cat > tests/storage/test_attach.py <<'PY'
import pytest

from src.storage.volumes import attach_volume


@pytest.mark.polarion("PROJ-1111")
class TestAttachVolume:
    def test_disk_attached_to_running_instance(self, running_instance, volume_source):
        attach_volume(running_instance, volume_source)
        assert volume_source.name in [v.name for v in running_instance.status.volumes]
PY
printf 'def attach_volume(instance, source):\n    return instance.attach(source)\n\n\ndef detach_volume(instance, name):\n    return instance.detach(name)\n' > src/storage/volumes.py
