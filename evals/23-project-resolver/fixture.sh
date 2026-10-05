#!/bin/bash
set -e
cp -R "$(cd "$(dirname "$0")" && pwd)/../../config" ./config
