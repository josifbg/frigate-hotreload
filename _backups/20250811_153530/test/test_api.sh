#!/usr/bin/env bash
# Interactive API test runner for Frigate Hot-Reload
# Writes consolidated log to: /Users/josifbg/Documents/VSCode/frigate-hotreload/test/test_api.log

set -u

# --- Settings ---
BASE="${BASE:-http://127.0.0.1:8080}"
DATA_DIR="${DATA_DIR:-/Users/josifbg/Documents/VSCode/frigate-hotreload/backend/data}"
TOKEN_FILE="${TOKEN_FILE:-$DATA_DIR/auth_token.txt}"
MAIN_LOG_DIR="/Users/josifbg/Documents/VSCode/frigate-hotreload/test"
mkdir -p "$MAIN_LOG_DIR"
MAIN_LOG_FILE="$MAIN_LOG_DIR/test_api.log"

# Colors
c_reset="\033[0m"; c_green="\033[32m"; c_red="\033[31m"; c_yellow="\033[33m"; c_cyan="\033[36m"; c_bold="\033[1m"

# Per-run logs
TS="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="${LOG_DIR:-test_logs_$TS}"
mkdir -p "$LOG_DIR"
ERR_LOG="$LOG_DIR/errors.log"
SUMMARY="$LOG_DIR/summary.txt"

pass=0; fail=0

log_all() { tee -a "$SUMMARY" "$MAIN_LOG_FILE"; }
note()  { echo -e "${c_cyan}[$(date +%H:%M:%S)] $*${c_reset}" | log_all; }
ok()    { echo -e "${c_green}✔ $*${c_reset}" | log_all; pass=$((pass+1)); }
bad()   { echo -e "${c_red}✖ $*${c_reset}" | log_all; echo "[$(date)] $*" >> "$ERR_LOG"; fail=$((fail+1)); }
warn()  { echo -e "${c_yellow}⚠ $*${c_reset}" | log_all; }

echo "===== API Test Run $(date) =====" >> "$MAIN_LOG_FILE"
echo "Run dir: $LOG_DIR" | log_all

pause_step() {
  local prompt="${1:-Press Enter to continue, (s)kip, (r)etry, (q)uit: }"
  while true; do
    read -r -n1 -p "$prompt" key || key=""
    echo
    case "$key" in
      "")   return 0 ;;
      s|S)  return 10 ;;
      r|R)  return 20 ;;
      q|Q)  echo "Aborted by user."; exit 130 ;;
      *)    echo "Options: [Enter]=continue, s=skip, r=retry, q=quit";;
    esac
  done
}

show_last_http() {
  local name="$1"
  local hdr="$LOG_DIR/${name}.h"
  local body="$LOG_DIR/${name}.json"
  echo -e "${c_bold}--- ${name} RESPONSE (headers) ---${c_reset}"
  sed -n '1,20p' "$hdr" | tee -a "$MAIN_LOG_FILE"
  echo -e "${c_bold}--- ${name} BODY (pretty) ---${c_reset}"
  if jq . "$body" >/dev/null 2>&1; then
    jq . "$body" | tee -a "$MAIN_LOG_FILE"
  else
    cat "$body" | tee -a "$MAIN_LOG_FILE"
  fi
}

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
      bad "Failed to generate token"; return 1
    fi
  fi
  AUTH=(-H "Authorization: Bearer $TOKEN")
}

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
  { echo -e "\n# ${name} [$method $path]"; cat "$hdr"; echo; cat "$body"; echo; } >> "$MAIN_LOG_FILE"
  echo "$code"
}

require_200_json() {
  local name="$1" code="$2"
  if [ "$code" != "200" ]; then
    bad "$name -> HTTP $code (see $LOG_DIR/${name}.h)"
    return 1
  fi
  if ! jq . "$LOG_DIR/${name}.json" >/dev/null 2>&1; then
    bad "$name -> non-JSON body"
    return 1
  fi
  ok "$name"
}

# --- Steps ---
step_ping() {
  note "[1/11] PING"
  local code; code=$(http ping GET /api/ping)
  show_last_http ping
  require_200_json ping "$code"
}

step_auth_status() {
  note "[2/11] AUTH STATUS"
  local code; code=$(http auth_status GET /api/auth/status)
  show_last_http auth_status
  require_200_json auth_status "$code"
}

step_snapshot_config() {
  note "[3/11] SNAPSHOT CONFIG"
  local code; code=$(http get_config GET /api/config)
  show_last_http get_config
  if require_200_json get_config "$code"; then
    cp "$LOG_DIR/get_config.json" "$LOG_DIR/original_config.json"
    ok "Saved baseline to original_config.json"
  fi
}

step_validate_config() {
  note "[4/11] VALIDATE CURRENT CONFIG"
  cp "$LOG_DIR/get_config.json" "$LOG_DIR/validate_in.json"
  local code; code=$(http validate POST /api/config/validate "$LOG_DIR/validate_in.json")
  show_last_http validate
  require_200_json validate "$code"
}

step_apply_dry() {
  note "[5/11] APPLY (DRY)"
  local code; code=$(http apply_dry POST "/api/config/apply?dry=true" "$LOG_DIR/get_config.json")
  show_last_http apply_dry
  require_200_json apply_dry "$code"
}

step_clone_dry_apply() {
  note "[6/11] CLONE CAMERA (DRY + APPLY)"
  local first; first=$(jq -r '.cameras | keys[0]' "$LOG_DIR/get_config.json")
  [ -z "$first" ] && { bad "No cameras in config"; return 1; }
  echo "{\"source_key\":\"$first\",\"target_key\":\"__test_cam\",\"overwrite\":true,\"apply\":false}" > "$LOG_DIR/clone_dry_in.json"
  local code; code=$(http clone_dry POST /api/cameras/clone "$LOG_DIR/clone_dry_in.json")
  show_last_http clone_dry
  require_200_json clone_dry "$code" || return 1
  echo "{\"source_key\":\"$first\",\"target_key\":\"__test_cam\",\"overwrite\":true,\"apply\":true}" > "$LOG_DIR/clone_apply_in.json"
  code=$(http clone_apply POST /api/cameras/clone "$LOG_DIR/clone_apply_in.json")
  show_last_http clone_apply
  require_200_json clone_apply "$code"
}

step_reorder() {
  note "[7/11] REORDER (PUT __test_cam FIRST)"
  jq --arg t "__test_cam" '.cameras as $c | {order: ([ $t ] + ([ $c | keys[] ] | unique)), apply:true}' \
    "$LOG_DIR/get_config.json" > "$LOG_DIR/reorder_in.json"
  local code; code=$(http reorder POST /api/cameras/reorder "$LOG_DIR/reorder_in.json")
  show_last_http reorder
  require_200_json reorder "$code"
}

step_set_and_delete_tmp() {
  note "[8/11] ADD TEMP CAMERA, THEN DELETE"
  cat > "$LOG_DIR/set_cam_in.json" <<JSON
{"key":"__tmp_add","value":{
  "name":"Temporary Cam",
  "enabled":true,
  "ffmpeg":{"url":"rtsp://user:pass@host/stream","width":1280,"height":720,"fps":10}
},"apply":true}
JSON
  local code; code=$(http set_cam POST /api/cameras/set "$LOG_DIR/set_cam_in.json")
  show_last_http set_cam
  require_200_json set_cam "$code" || return 1
  echo '{"key":"__tmp_add","apply":true}' > "$LOG_DIR/del_tmp_in.json"
  code=$(http del_tmp POST /api/cameras/delete "$LOG_DIR/del_tmp_in.json")
  show_last_http del_tmp
  require_200_json del_tmp "$code"
}

step_bulk_delete_dry() {
  note "[9/11] BULK DELETE (DRY)"
  echo '{"keys":["__test_cam"],"apply":false}' > "$LOG_DIR/bulk_dry_in.json"
  local code; code=$(http bulk_dry POST /api/cameras/bulk_delete "$LOG_DIR/bulk_dry_in.json")
  show_last_http bulk_dry
  require_200_json bulk_dry "$code"
}

step_export() {
  note "[10/11] EXPORT CONFIG"
  local code; code=$(http export GET /api/config/export)
  show_last_http export
  require_200_json export "$code"
}

step_cleanup_and_restore() {
  note "[11/11] CLEANUP (__test_cam) + RESTORE BASELINE"
  echo '{"key":"__test_cam","apply":true}' > "$LOG_DIR/del_test_in.json"
  local code; code=$(http del_test POST /api/cameras/delete "$LOG_DIR/del_test_in.json")
  show_last_http del_test
  cp "$LOG_DIR/original_config.json" "$LOG_DIR/restore_in.json"
  code=$(http restore POST /api/config/import "$LOG_DIR/restore_in.json")
  show_last_http restore
  require_200_json restore "$code"
}

run_step() {
  local fn="$1"
  while true; do
    "$fn"; local rc=$?
    if [ $rc -eq 0 ]; then
      echo -e "${c_green}--- STEP OK ---${c_reset}"
      pause_step "Continue (Enter), skip (s), retry (r), quit (q): "
      local action=$?
      if [ $action -eq 20 ]; then warn "Retrying…"; continue
      elif [ $action -eq 10 ]; then warn "Skipping."; return 0
      else return 0; fi
    else
      echo -e "${c_red}--- STEP FAILED (rc=$rc) ---${c_reset}"
      pause_step "Retry (r), skip (s), quit (q) or Enter to retry: "
      local action=$?
      if [ $action -eq 10 ]; then warn "Skipping failed step."; return 0
      elif [ $action -eq 20 ] || [ $action -eq 0 ]; then warn "Retrying…"; continue
      else exit 1; fi
    fi
  done
}

main() {
  note "Ensuring token…"; ensure_token || exit 1

  run_step step_ping
  run_step step_auth_status
  run_step step_snapshot_config
  run_step step_validate_config
  run_step step_apply_dry
  run_step step_clone_dry_apply
  run_step step_reorder
  run_step step_set_and_delete_tmp
  run_step step_bulk_delete_dry
  run_step step_export
  run_step step_cleanup_and_restore

  echo "" | log_all
  echo "Passed: $pass" | log_all
  echo "Failed: $fail" | log_all
  echo "Run logs: $LOG_DIR" | log_all
  echo "Main log (append): $MAIN_LOG_FILE" | log_all

  echo -e "${c_bold}Done.${c_reset} See ${c_cyan}$LOG_DIR${c_reset} and ${c_cyan}$MAIN_LOG_FILE${c_reset}."
}

main "$@"
