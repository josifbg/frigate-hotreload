#!/usr/bin/env bash
set -euo pipefail

# ----- Resolve project root -----
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

API="http://127.0.0.1:8080"

echo "=== Backup Script (with tests) ==="

# ----- Token paths & helpers -----
TOKEN_FILE="$ROOT/backend/data/auth_token.txt"
mkdir -p "$(dirname "$TOKEN_FILE")"  # ensure data dir exists

read_token() {
  if [[ -f "$TOKEN_FILE" ]]; then
    # Try JSON { "token": "..." }
    local j
    if j="$(jq -r 'if type=="object" and .token then .token else empty end' "$TOKEN_FILE" 2>/dev/null)" && [[ -n "$j" ]]; then
      printf '%s' "$j"
      return 0
    fi
    # Fallback: plain string
    tr -d '\n' < "$TOKEN_FILE"
    return 0
  fi
  return 1
}

set_auth_header() {
  local tok
  if tok="$(read_token 2>/dev/null)"; then
    AUTH_HEADER=( -H "Authorization: Bearer $tok" )
  else
    AUTH_HEADER=()
  fi
}

ensure_token() {
  echo "[TOKEN] Checking token status…"
  # 1) Check server auth status
  local status_json
  status_json="$(curl -sS "$API/api/auth/status" || echo '{}')"
  local enabled
  enabled="$(jq -r '.enabled // false' <<<"$status_json" 2>/dev/null || echo false)"

  if [[ "$enabled" != "true" ]]; then
    echo "[TOKEN] Auth is disabled on server."
    AUTH_HEADER=()
    return 0
  fi

  # 2) Probe with existing token
  set_auth_header
  if [[ "${#AUTH_HEADER[@]}" -gt 0 ]]; then
    local code
    code="$(curl -sS -o /dev/null -w '%{http_code}' "${AUTH_HEADER[@]}" "$API/api/ping" || echo 000)"
    if [[ "$code" == "200" ]]; then
      echo "[TOKEN] Existing token is valid."
      return 0
    fi
  fi

  # 3) Generate a new token
  echo "[TOKEN] Generating a new token…"
  local gen
  gen="$(curl -sS -X POST "$API/api/auth/generate" || echo '{}')"
  local new_tok expires
  new_tok="$(jq -r '.token // empty' <<<"$gen" 2>/dev/null || true)"
  expires="$(jq -r '.expires_at // empty' <<<"$gen" 2>/dev/null || true)"
  if [[ -n "$new_tok" ]]; then
    if [[ -n "$expires" ]]; then
      printf '{ "token": "%s", "expires": %s }\n' "$new_tok" "$expires" >"$TOKEN_FILE"
    else
      printf '{ "token": "%s" }\n' "$new_tok" >"$TOKEN_FILE"
    fi
    echo "[TOKEN] Token written to $TOKEN_FILE"
    set_auth_header
    return 0
  fi

  echo "[TOKEN] Failed to generate token; continuing without Authorization header."
  AUTH_HEADER=()
  return 0
}

# ---------- 0) Run tests ----------
TEST_DIR="$ROOT/test"
TEST_SCRIPT="$TEST_DIR/test_api.sh"
LOG_DIR="$TEST_DIR"
LOG_FILE="$LOG_DIR/test_api.log"

# Make sure token is valid before starting tests (test script също прави ensure за всяка стъпка)
ensure_token

if [[ -x "$TEST_SCRIPT" ]]; then
  echo "[TEST] Running API tests..."
  mkdir -p "$LOG_DIR"
  set +e
  "$TEST_SCRIPT" | tee -a "$LOG_FILE"
  TEST_RC=${PIPESTATUS[0]}
  set -e
  echo "[TEST] Exit code: $TEST_RC"
  if (( TEST_RC != 0 )); then
    echo "Some tests FAILED. See log: $LOG_FILE"
    read -rp "Continue with backup anyway? (y/n): " CONT
    if [[ ! "$CONT" =~ ^[Yy]$ ]]; then
      echo "Aborting backup due to failed tests."
      exit 1
    fi
  else
    echo "All tests passed. Log: $LOG_FILE"
  fi
else
  echo "[TEST] No test script found at: $TEST_SCRIPT"
  read -rp "Skip tests and continue? (y/n): " SKIP
  if [[ ! "$SKIP" =~ ^[Yy]$ ]]; then
    echo "Aborting."
    exit 1
  fi
fi

# ---------- 1) Meta / inputs ----------
DEFAULT_TAG="v$(date +%Y.%m.%d)"
read -rp "Enter tag version (default: $DEFAULT_TAG): " TAG
TAG="${TAG:-$DEFAULT_TAG}"
TS="$(date +%Y%m%d_%H%M%S)"
DEST="_backups/$TS"
mkdir -p "$DEST"

echo
echo "Tag: $TAG"
echo "Timestamp: $TS"
echo "Backup folder: $DEST"
echo

# ---------- 2) Commit ----------
read -rp "Commit all changes? (y/n): " DO_COMMIT
if [[ "$DO_COMMIT" =~ ^[Yy]$ ]]; then
  git add -A
  if ! git diff --cached --quiet; then
    read -rp "Commit message (default: 'Backup: stable state ($TS)'): " COMMIT_MSG
    COMMIT_MSG="${COMMIT_MSG:-Backup: stable state ($TS)}"
    git commit -m "$COMMIT_MSG"
  else
    echo "No staged changes to commit."
  fi
else
  echo "Skipping commit."
fi

# ---------- 3) Tag ----------
read -rp "Create or update tag '$TAG'? (y/n): " DO_TAG
if [[ "$DO_TAG" =~ ^[Yy]$ ]]; then
  if git rev-parse "$TAG" >/dev/null 2>&1; then
    echo "Tag $TAG already exists."
    read -rp "Delete and recreate tag? (y/n): " RETAG
    if [[ "$RETAG" =~ ^[Yy]$ ]]; then
      git tag -d "$TAG" || true
      git push --delete origin "$TAG" || true
      git tag -a "$TAG" -m "Stable snapshot $TAG ($TS)"
    else
      echo "Keeping existing tag."
    fi
  else
    git tag -a "$TAG" -m "Stable snapshot $TAG ($TS)"
  fi
else
  echo "Skipping tagging."
fi

# ---------- 4) Push ----------
read -rp "Push current branch and tags to GitHub? (y/n): " DO_PUSH
if [[ "$DO_PUSH" =~ ^[Yy]$ ]]; then
  BR="$(git rev-parse --abbrev-ref HEAD)"
  git push origin "$BR" --tags
else
  echo "Skipping push."
fi

# ---------- 5) Local snapshot ----------
read -rp "Create local backup snapshot? (y/n): " DO_BACKUP
if [[ "$DO_BACKUP" =~ ^[Yy]$ ]]; then
  git archive --format=tar.gz -o "$DEST/repo_${TAG}_$TS.tgz" HEAD
  rsync -av --delete "$ROOT/backend/data/" "$DEST/data/" 2>/dev/null || true
  if [[ -d "$TEST_DIR" ]]; then
    rsync -av "$TEST_DIR/" "$DEST/test/" 2>/dev/null || true
  fi
  [[ -f "$LOG_FILE" ]] && cp "$LOG_FILE" "$DEST/" || true

  cat > "$DEST/README.txt" <<EON
Snapshot at: $(date)
Tag: $TAG
Repo archive: repo_${TAG}_$TS.tgz
Data path: $DEST/data
Tests folder: $DEST/test
Test log (if present): $(basename "$LOG_FILE")
EON
  echo "Local backup created at: $DEST"
else
  echo "Skipping local snapshot."
fi

echo "=== Done ==="
