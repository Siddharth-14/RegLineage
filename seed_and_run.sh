#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

python3 data/generate_synthetic_data.py
streamlit run app.py
