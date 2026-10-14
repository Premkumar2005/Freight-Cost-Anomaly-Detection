#!/usr/bin/env bash
# Runs the pipeline 3 times and compares SHA-256 of the outputs.
set -e
cd "$(dirname "$0")"
mkdir -p runs
for i in 1 2 3; do
  python -m costwatch.cli run --output runs/run$i.csv > /dev/null 2>&1
done
sha256sum runs/run1.csv runs/run2.csv runs/run3.csv
if cmp -s runs/run1.csv runs/run2.csv && cmp -s runs/run2.csv runs/run3.csv; then
  echo "REPRODUCIBLE: 3 runs are byte-identical"
else
  echo "MISMATCH between runs"; exit 1
fi
