#!/usr/bin/env bash
set -euo pipefail
python -m pytest
ruff check src tests
mypy src
python -m twinguard.cli doctor
python -m twinguard.cli export-schemas
python -m twinguard.cli list-scenarios
for scenario in scenarios/*.yaml; do
  python -m twinguard.cli validate-config "$scenario"
done
python -m twinguard.cli validate-data datasets/synthetic/observation.json --kind SensorObservation
python -m twinguard.cli validate-data datasets/synthetic/manifest.json --kind DatasetProvenance
