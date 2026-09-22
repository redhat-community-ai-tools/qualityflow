#!/bin/bash
# A three-requirement STP: the same STD build as case 05, small enough to run cheaply.
set -e
here="$(cd "$(dirname "$0")" && pwd)"
mkdir -p outputs/PROJ-12345/stp tests/storage
cp "$here/fixtures/PROJ-12345_test_plan.md" outputs/PROJ-12345/stp/
printf '[project]\nname = "virt-tests"\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n' > pyproject.toml
printf 'import pytest\n\n\nclass TestHotplugVolume:\n    def test_disk_attached(self, running_vm):\n        assert running_vm.volumes\n' > tests/storage/test_hotplug.py
