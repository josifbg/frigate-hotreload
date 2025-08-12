#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/josifbg/Documents/VSCode/frigate-hotreload"
cd "$ROOT"

echo "=== Backup Script (with tests) ==="

# ---------- 0) Run tests ----------
TEST_DIR="$ROOT/test"
TEST_SCRIPT="$TEST_DIR/test_api.sh"
LOG_DIR="$TEST_DIR"
LOG_FILE="$LOG_DIR/test_api.log"

if [[ -x "$TEST_SCRIPT" ]]; then
  echo "[TEST] Running API tests..."
  # осигуряване на папка за логове
  mkdir -p "$LOG_DIR"
  # пускаме тестовете (те сами пишат в $LOG_FILE; осигуряваме и дублиране към конзолата)
  # ако тестовият скрипт връща код ≠0, ще хванем това и ще питаме дали да продължим
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
  # архив на кода
  git archive --format=tar.gz -o "$DEST/repo_${TAG}_$TS.tgz" HEAD
  # конфигурации/данни
  rsync -av --delete backend/data/ "$DEST/data/" 2>/dev/null || true
  # тестове и логове
  if [[ -d "$TEST_DIR" ]]; then
    rsync -av "$TEST_DIR/" "$DEST/test/" 2>/dev/null || true
  fi
  [[ -f "$LOG_FILE" ]] && cp "$LOG_FILE" "$DEST/" || true

  # кратък опис
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
