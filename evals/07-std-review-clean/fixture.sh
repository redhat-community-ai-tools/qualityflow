#!/bin/bash
# Seeds a finished STD for review: project config, the approved STP, the STD YAML and its stubs.
set -e
here="$(cd "$(dirname "$0")" && pwd)"
J=CNV-68916
cp -R "$here/../../config" ./config
mkdir -p "outputs/$J/stp" "outputs/$J/std"
cp "$here/fixtures/${J}_test_plan.md" "outputs/$J/stp/"
cp "$here/fixtures/${J}_test_description.yaml" "outputs/$J/std/"
cp -R "$here/fixtures/python-tests" "outputs/$J/std/"
