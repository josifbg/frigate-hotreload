#!/usr/bin/env bash
set -euo pipefail

# ---------- Setup ----------
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

API="http://127.0.0.1:8080"
TOKEN_FILE="$ROOT/backend/data/auth_token.txt"

TS="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$ROOT/test_logs_${TS}"
mkdir -p "$RUN_DIR"

LOG_SUMMARY="$RUN_DIR/summary.txt"
ERR_LOG="$RUN_DIR/errors.log"
: >"$LOG_SUMMARY"
: >"$ERR_LOG"

say() { printf '%s\n' "$*"; }
save() { # save HTTP response headers/body pair
  local name="$1" code="$2" hdr="$3" body="$4"
  echo "$hdr" > "$RUN_DIR/${name}.h"
  echo "$body" > "$RUN_DIR/${name}.json"
  printf "[%s] %s -> HTTP %s\n" "$(date +%H:%M:%S)" "$name" "$code" | tee -a "$LOG_SUMMARY"
}

# ---------- Auth helpers ----------
read_token() {
  [[ -f "$TOKEN_FILE" ]] || return 1
  # JSON формат { "token": "...", "expires": 123 } или plain текст
  local t
  t="$(jq -r 'if type=="object" and .token then .token else empty end' "$TOKEN_FILE" 2>/dev/null || true)"
  if [[ -z "$t" ]]; then t="$(tr -d '\r\n' < "$TOKEN_FILE")"; fi
  [[ -n "$t" ]] || return 1
  printf '%s' "$t"
}

AUTH_HEADER=()
set_auth_header() {
  local tok
  if tok="$(read_token 2>/dev/null)"; then
    AUTH_HEADER=( -H "Authorization: Bearer $tok" )
  else
    AUTH_HEADER=()
  fi
  # Диагностика
  {
    echo "== auth debug =="
    echo "time: $(date)"
    if [[ ${#AUTH_HEADER[@]} -gt 0 ]]; then
      echo "token_prefix: $(printf '%s' "$(read_token)" | cut -c1-8)"
      echo "header_used: Authorization: Bearer <redacted>"
    else
      echo "header_used: <none>"
    fi
  } > "$RUN_DIR/auth_debug.txt"
}

generate_token() {
  local gen tok exp
  gen="$(curl -sS -X POST "$API/api/auth/generate" || echo '{}')"
  tok="$(jq -r '.token // empty' <<<"$gen" 2>/dev/null || true)"
  exp="$(jq -r '.expires_at // empty' <<<"$gen" 2>/dev/null || true)"
  mkdir -p "$(dirname "$TOKEN_FILE")"
  if [[ -n "$tok" ]]; then
    if [[ -n "$exp" ]]; then
      printf '{ "token":"%s", "expires": %s }\n' "$tok" "$exp" >"$TOKEN_FILE"
    else
      printf '{ "token":"%s" }\n' "$tok" >"$TOKEN_FILE"
    fi
    return 0
  fi
  return 1
}

auth_enabled() {
  local st; st="$(curl -sS "$API/api/auth/status" || echo '{}')"
  [[ "$(jq -r '.enabled // false' <<<"$st")" == "true" ]]
}

ensure_token() {
  if ! auth_enabled; then
    AUTH_HEADER=()  # auth disabled
    return 0
  fi

  # 1) опитай със съществуващ токен
  set_auth_header
  if [[ ${#AUTH_HEADER[@]} -gt 0 ]]; then
    local code
    code="$(curl -sS -o /dev/null -w '%{http_code}' "${AUTH_HEADER[@]}" "$API/api/config" || echo 000)"
    if [[ "$code" == "200" ]]; then
      return 0
    fi
  fi

  # 2) генерирай нов токен и провери отново (до 2 опита)
  for _ in 1 2; do
    if generate_token; then
      set_auth_header
      local code
      code="$(curl -sS -o /dev/null -w '%{http_code}' "${AUTH_HEADER[@]}" "$API/api/config" || echo 000)"
      if [[ "$code" == "200" ]]; then
        return 0
      fi
    fi
  done

  # оставяме header (може да е празен) — заявката ще се логне като 403
  return 0
}

# ---------- Request wrapper ----------
req_json() {
  # usage: req_json NAME METHOD PATH [DATA_JSON or empty]
  local name="$1" method="$2" path="$3" data="${4:-}"

  ensure_token

  local tmp_body="$RUN_DIR/.tmp_body.$$"
  local code hdr
  if [[ -n "$data" ]]; then
    code="$(curl -sS -D "$RUN_DIR/${name}.h" -o "$tmp_body" \
      -w '%{http_code}' "${AUTH_HEADER[@]}" -H 'Content-Type: application/json' \
      -X "$method" "$API$path" --data-binary "$data" || echo 000)"
  else
    code="$(curl -sS -D "$RUN_DIR/${name}.h" -o "$tmp_body" \
      -w '%{http_code}' "${AUTH_HEADER[@]}" \
      -X "$method" "$API$path" || echo 000)"
  fi
  hdr="$(cat "$RUN_DIR/${name}.h")"

  # pretty JSON ако може
  local body
  if jq -e . >/dev/null 2>&1 <"$tmp_body"; then
    body="$(jq . <"$tmp_body")"
  else
    body="$(cat "$tmp_body")"
  fi
  rm -f "$tmp_body"

  save "$name" "$code" "$hdr" "$body"

  if [[ "$code" =~ ^2 ]]; then
    say "✔ $name"
    echo "--- STEP OK ---"
    return 0
  else
    say "✖ $name -> HTTP $code (see $RUN_DIR/${name}.h)"
    echo "$body" >>"$ERR_LOG"
    echo "--- STEP FAILED (rc=1) ---"
    while true; do
      read -rp "Retry (r), skip (s), quit (q) or Enter to retry: " a
      case "${a:-r}" in
        q|Q) exit 130;;
        s|S) return 1;;
        r|R|'') return 2;;
      esac
    done
  fi
}

run_step() {
  local title="$1"; shift
  while true; do
    printf "\n[%s] %s\n" "$(date +%H:%M:%S)" "$title"
    if "$@"; then
      read -rp "Continue (Enter), skip (s), retry (r), quit (q): " x
      case "${x:-}" in
        q|Q) exit 130;;
        s|S) return 0;;
        r|R) continue;;
        *)   return 0;;
      esac
    else
      return 0
    fi
  done
}

# ---------- Steps ----------
step_ping() { req_json ping GET /api/ping; }
step_auth_status() { req_json auth_status GET /api/auth/status; }
step_get_config() { req_json get_config GET /api/config; }

step_validate_current() {
  ensure_token
  local cfg; cfg="$(curl -sS "${AUTH_HEADER[@]}" "$API/api/config" || echo '{}')"
  req_json validate POST /api/config/validate "$cfg"
}

step_apply_dry() {
  ensure_token
  local cfg; cfg="$(curl -sS "${AUTH_HEADER[@]}" "$API/api/config" || echo '{}')"
  req_json apply_dry POST "/api/config/apply?dry=true" "$cfg"
}

step_clone_cam() {
  ensure_token
  local cfg keys src tgt
  cfg="$(curl -sS "${AUTH_HEADER[@]}" "$API/api/config" || echo '{}')"
  keys="$(jq -r '.cameras | keys[]?' <<<"$cfg" 2>/dev/null || true)"
  src="$(head -n1 <<<"$keys" || true)"
  [[ -z "$src" ]] && { echo "✖ No cameras in config" | tee -a "$ERR_LOG"; return 1; }
  tgt="__test_cam"
  req_json clone_dry POST /api/cameras/clone "$(jq -nc --arg s "$src" --arg t "$tgt" '{source_key:$s,target_key:$t,overwrite:true,apply:false}')"
  req_json clone_apply POST /api/cameras/clone "$(jq -nc --arg s "$src" --arg t "$tgt" '{source_key:$s,target_key:$t,overwrite:true,apply:true}')"
}

step_reorder() {
  ensure_token
  local cfg order
  cfg="$(curl -sS "${AUTH_HEADER[@]}" "$API/api/config" || echo '{}')"
  order="$(jq -r '.cameras | keys | if length>0 then [.[-1]] + (.[0:-1]) else . end' <<<"$cfg" 2>/dev/null || echo '[]')"
  echo "$order" > "$RUN_DIR/reorder_in.json"
  req_json reorder POST /api/cameras/reorder "$(jq -nc --argjson o "$order" '{order:$o, apply:true}')"
}

step_set_then_delete() {
  local body='{"key":"__tmp_cam","value":{"name":"tmp","enabled":true,"ffmpeg":{"url":"rtsp://user:pass@h/stream","width":1280,"height":720,"fps":10}},"apply":true}'
  echo "$body" > "$RUN_DIR/set_cam_in.json"
  req_json set_cam POST /api/cameras/set "$body" || return 1
  req_json del_cam POST /api/cameras/delete '{"key":"__tmp_cam","apply":true}'
}

step_bulk_dry() {
  echo '["__test_cam","__tmp_cam"]' > "$RUN_DIR/bulk_dry_in.json"
  req_json bulk_dry POST /api/cameras/bulk_delete '{"keys":["__test_cam","__tmp_cam"],"apply":false}'
}

step_export() { req_json export GET /api/config/export; }
step_rollback() { req_json rollback POST /api/config/rollback ''; }

# ---------- Run ----------
echo "Run dir: $(basename "$RUN_DIR")"
run_step "[1/11] PING"                         step_ping
run_step "[2/11] AUTH STATUS"                  step_auth_status
run_step "[3/11] SNAPSHOT CONFIG"              step_get_config
run_step "[4/11] VALIDATE CURRENT CONFIG"      step_validate_current
run_step "[5/11] APPLY (DRY)"                  step_apply_dry
run_step "[6/11] CLONE CAMERA (DRY + APPLY)"   step_clone_cam
run_step "[7/11] REORDER (MOVE LAST FIRST)"    step_reorder
run_step "[8/11] ADD TEMP CAMERA, THEN DELETE" step_set_then_delete
run_step "[9/11] BULK DELETE (DRY)"            step_bulk_dry
run_step "[10/11] EXPORT CONFIG"               step_export
run_step "[11/11] ROLLBACK LATEST"             step_rollback

echo "All steps finished. See $RUN_DIR"
exit 0
