#!/usr/bin/env bash
set -u

# -------- Settings --------
BASE="${BASE:-http://127.0.0.1:8080}"
DATA_DIR="${DATA_DIR:-/Users/josifbg/Documents/VSCode/frigate-hotreload/backend/data}"
TOKEN_FILE="${TOKEN_FILE:-$DATA_DIR/auth_token.txt}"

# -------- Logging --------
TS="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="${LOG_DIR:-test_logs_$TS}"
mkdir -p "$LOG_DIR"
ERR_LOG="$LOG_DIR/errors.log"
SUMMARY="$LOG_DIR/summary.txt"

pass=0
fail=0

note()  { echo "[$(date +%H:%M:%S)] $*" | tee -a "$SUMMARY"; }
ok()    { echo "✅  $*" | tee -a "$SUMMARY"; pass=$((pass+1)); }
bad()   { echo "❌  $*" | tee -a "$SUMMARY"; echo "[$(date)] $*" >> "$ERR_LOG"; fail=$((fail+1)); }

# -------- Helpers --------
json() { jq -e "$1" >/dev/null 2>&1; }

ensure_token() {
  if [ -f "$TOKEN_FILE" ]; then
    TOKEN="$(tr -d '\r\n' < "$TOKEN_FILE" 2>/dev/null || true)"
  else
    TOKEN=""
  fi
  if [ -z "${TOKEN:-}" ]; then
    note "No token found; generating…"
    curl -sS -X POST "$BASE/api/auth/generate" -o "$LOG_DIR/gen_token.json"
    TOKEN="$(jq -r '.token' "$LOG_DIR/gen_token.json" 2>/dev/null || true)"
    if [ -n "$TOKEN" ]; then
      mkdir -p "$DATA_DIR"
      printf "%s" "$TOKEN" > "$TOKEN_FILE"
      ok "Token generated"
    else
      bad "Failed to generate token"
    fi
  fi
  AUTH=(-H "Authorization: Bearer $TOKEN")
}

# curl wrapper that stores headers/body and returns http code
# usage: http NAME METHOD PATH [DATA_FILE]
http() {
  local name="$1" method="$2" path="$3" data_file="${4:-}"
  local hdr="$LOG_DIR/${name}.h" body="$LOG_DIR/${name}.json"
  local code
  if [ -n "$data_file" ]; then
    code=$(curl -sS -D "$hdr" -o "$body" -w "%{http_code}" \
      "${AUTH[@]}" -H 'Content-Type: application/json' \
      -X "$method" "$BASE$path" --data-binary @"$data_file" || echo 000)
  else
    code=$(curl -sS -D "$hdr" -o "$body" -w "%{http_code}" \
      "${AUTH[@]}" -X "$method" "$BASE$path" || echo 000)
  fi
  echo "$code"
}

require_200_json() {
  local name="$1" code="$2"
  local hdr="$LOG_DIR/${name}.h" body="$LOG_DIR/${name}.json"
  if [ "$code" != "200" ]; then
    bad "$name -> HTTP $code (see $hdr / $body)"
    return 1
  fi
  if ! jq . "$body" >/dev/null 2>&1; then
    bad "$name -> non-JSON body (see $body)"
    return 1
  fi
  ok "$name"
}

# -------- Start --------
note "Logs at: $LOG_DIR"
ensure_token

# 0) Ping
code=$(http ping GET /api/ping)
require_200_json ping "$code" || true

# 1) Auth status
code=$(http auth_status GET /api/auth/status)
require_200_json auth_status "$code" || true

# 2) Snapshot current config (for restore)
code=$(http get_config GET /api/config)
if require_200_json get_config "$code"; then
  cp "$LOG_DIR/get_config.json" "$LOG_DIR/original_config.json"
else
  note "Skipping the rest because /api/config failed."
fi

# 3) Validate current config
cp "$LOG_DIR/get_config.json" "$LOG_DIR/validate_in.json"
code=$(http validate POST /api/config/validate "$LOG_DIR/validate_in.json")
require_200_json validate "$code" || true

# 4) Dry-apply current config
code=$(http apply_dry POST "/api/config/apply?dry=true" "$LOG_DIR/get_config.json")
require_200_json apply_dry "$code" || true

# 5) Camera clone (dry then apply) -> __test_cam
jq '. as $cfg | $cfg.cameras | keys[0] // "cam1"' "$LOG_DIR/get_config.json" > "$LOG_DIR/_first_cam.json"
FIRST_CAM="$(tr -d '"' < "$LOG_DIR/_first_cam.json")"
TARGET="__test_cam"

echo "{\"source_key\":\"$FIRST_CAM\",\"target_key\":\"$TARGET\",\"overwrite\":true,\"apply\":false}" > "$LOG_DIR/clone_dry_in.json"
code=$(http clone_dry POST /api/cameras/clone "$LOG_DIR/clone_dry_in.json")
require_200_json clone_dry "$code" || true

echo "{\"source_key\":\"$FIRST_CAM\",\"target_key\":\"$TARGET\",\"overwrite\":true,\"apply\":true}" > "$LOG_DIR/clone_apply_in.json"
code=$(http clone_apply POST /api/cameras/clone "$LOG_DIR/clone_apply_in.json")
require_200_json clone_apply "$code" || true

# 6) Reorder: make __test_cam first
jq --arg t "$TARGET" '
  .cameras as $c | {order: ([ $t ] + ([ $c | keys[] ] | unique ) ) | unique, apply:true}
' "$LOG_DIR/get_config.json" > "$LOG_DIR/reorder_in.json"
code=$(http reorder POST /api/cameras/reorder "$LOG_DIR/reorder_in.json")
if require_200_json reorder "$code"; then
  if jq -e '.order[0] == "'$TARGET'"' "$LOG_DIR/reorder.json" >/dev/null 2>&1; then
    ok "reorder placed $TARGET first"
  else
    bad "reorder: $TARGET not first"
  fi
fi

# 7) Set camera (__tmp_add), then delete it
cat > "$LOG_DIR/set_cam_in.json" <<JSON
{"key":"__tmp_add","value":{
  "name":"Temporary Cam",
  "enabled":true,
  "ffmpeg":{"url":"rtsp://user:pass@host/stream","width":1280,"height":720,"fps":10}
},"apply":true}
JSON
code=$(http set_cam POST /api/cameras/set "$LOG_DIR/set_cam_in.json")
require_200_json set_cam "$code" || true

echo '{"key":"__tmp_add","apply":true}' > "$LOG_DIR/del_tmp_in.json"
code=$(http del_tmp POST /api/cameras/delete "$LOG_DIR/del_tmp_in.json")
require_200_json del_tmp "$code" || true

# 8) Bulk delete dry for __test_cam
echo '{"keys":["__test_cam"],"apply":false}' > "$LOG_DIR/bulk_dry_in.json"
code=$(http bulk_dry POST /api/cameras/bulk_delete "$LOG_DIR/bulk_dry_in.json")
require_200_json bulk_dry "$code" || true

# 9) Export config
code=$(http export GET /api/config/export)
require_200_json export "$code" || true

# 10) Cleanup: delete __test_cam (apply)
echo '{"key":"__test_cam","apply":true}' > "$LOG_DIR/del_test_in.json"
code=$(http del_test POST /api/cameras/delete "$LOG_DIR/del_test_in.json")
# allow 404 here (if previous runs already removed it)
if [ "$code" = "200" ]; then ok "del_test"; else note "del_test -> HTTP $code (may be already deleted)"; fi

# 11) Restore original config (safety)
code=$(http restore POST /api/config/import "$LOG_DIR/original_config.json")
require_200_json restore "$code" || true

# -------- Summary --------
echo "" | tee -a "$SUMMARY"
echo "Passed: $pass" | tee -a "$SUMMARY"
echo "Failed: $fail" | tee -a "$SUMMARY"
echo "Logs:   $LOG_DIR" | tee -a "$SUMMARY"
[ "$fail" -eq 0 ] && exit 0 || exit 1
