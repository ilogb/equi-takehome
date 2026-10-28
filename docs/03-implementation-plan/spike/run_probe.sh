#!/usr/bin/env bash
set -euo pipefail
set -a; source "$(dirname "$0")/../../../.env"; set +a
cd "$(dirname "$0")"
uv run --no-project --with google-auth-oauthlib --with requests python drive_probe.py --folder-id 1vMG2qvqZ5h74hzdyOstiUwGpslMobKhc --wait 60
