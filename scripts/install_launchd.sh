#!/usr/bin/env bash
# Install two launchd plists:
#   1. com.jobsearch.agent    — runs run_pipeline.py every 3 hours
#   2. com.jobsearch.discovery — runs run_discovery.py once daily
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$HOME/Library/Logs/job-search-agent"
mkdir -p "$LOG_DIR"

PYTHON="$(command -v python3)"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
fi

PROFILE="${JOB_SEARCH_PROFILE:-jeff}"

# --- 1. Feed pipeline plist (every 3 hours) ---
PIPELINE_LABEL="com.jobsearch.agent"
PIPELINE_PLIST="$HOME/Library/LaunchAgents/${PIPELINE_LABEL}.plist"

cat >"$PIPELINE_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${PIPELINE_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON}</string>
    <string>${ROOT}/scripts/run_pipeline.py</string>
    <string>--profile</string>
    <string>${PROFILE}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT}</string>
  <key>StartInterval</key>
  <integer>10800</integer>
  <key>KeepAlive</key>
  <false/>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/pipeline.launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/pipeline.launchd.err.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
</dict>
</plist>
EOF

launchctl unload "$PIPELINE_PLIST" 2>/dev/null || true
launchctl load "$PIPELINE_PLIST"
echo "Loaded $PIPELINE_PLIST (every 3h)"

# --- 2. Discovery plist (once daily) ---
DISCOVERY_LABEL="com.jobsearch.discovery"
DISCOVERY_PLIST="$HOME/Library/LaunchAgents/${DISCOVERY_LABEL}.plist"

cat >"$DISCOVERY_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${DISCOVERY_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${ROOT}/scripts/run_daily_discovery.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT}</string>
  <key>StartInterval</key>
  <integer>86400</integer>
  <key>KeepAlive</key>
  <false/>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/discovery.launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/discovery.launchd.err.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
</dict>
</plist>
EOF

launchctl unload "$DISCOVERY_PLIST" 2>/dev/null || true
launchctl load "$DISCOVERY_PLIST"
echo "Loaded $DISCOVERY_PLIST (once daily)"

echo ""
echo "Both schedules active. Check with: launchctl list | grep jobsearch"
