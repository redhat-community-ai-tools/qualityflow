#!/bin/bash
# ponytail: add_dirs never reached the agent (early-access eval build), so copy the input into the run's cwd.
cp "$(dirname "$0")/fixtures/input.yaml" .
