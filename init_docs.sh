#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/josifbg/Documents/VSCode/frigate-hotreload"
cd "$ROOT"

# ---------- helpers ----------
ask_yn() {
  local q="$1"
  local def="${2:-y}"   # default y|n
  local prompt=" (y/n) "
  [[ "$def" == "y" ]] && prompt=" (Y/n) " || prompt=" (y/N) "
  while true; do
    read -rp "$q$prompt" ans || true
    ans="${ans:-$def}"
    case "$ans" in
      y|Y) return 0 ;;
      n|N) return 1 ;;
      *) echo "Please answer y or n." ;;
    esac
  done
}

banner() { echo; echo "== $* =="; }

# ---------- detect GitHub origin ----------
GH_URL="$(git remote get-url origin 2>/dev/null || echo '')"
if [[ "$GH_URL" =~ github.com[:/](.+)/(.+)(\.git)?$ ]]; then
  GH_USER="${BASH_REMATCH[1]}"
  GH_REPO="${BASH_REMATCH[2]%%.git}"
else
  banner "GitHub remote not detected automatically"
  read -rp "Enter your GitHub username: " GH_USER
  read -rp "Enter your GitHub repository name: " GH_REPO
fi
echo "Using GH_USER=$GH_USER, GH_REPO=$GH_REPO"

# ---------- ensure documentation skeleton ----------
banner "Prepare documentation/ structure"
if [[ -d documentation && -f documentation/mkdocs.yml ]]; then
  echo "Found existing MkDocs config: documentation/mkdocs.yml"
  if ask_yn "Append/overwrite starter pages if missing?" "y"; then
    :
  else
    echo "Skipping content bootstrap."
    SKIP_CONTENT=1
  fi
else
  if ask_yn "Create MkDocs skeleton in documentation/ ?" "y"; then
    mkdir -p documentation/docs
    cat > documentation/mkdocs.yml <<YAML
site_name: Frigate Hot-Reload
site_url: https://$GH_USER.github.io/$GH_REPO/
repo_url: https://github.com/$GH_USER/$GH_REPO
theme:
  name: material
  language: en
  features:
    - navigation.instant
    - navigation.tracking
    - content.code.copy
    - search.highlight
    - search.suggest
nav:
  - Overview: index.md
  - Quickstart: quickstart.md
  - Installation: install.md
  - Configuration: configuration.md
  - Cameras: cameras.md
  - API: api.md
  - UI: ui.md
  - Troubleshooting: troubleshooting.md
  - Changelog: changelog.md
  - Roadmap: roadmap.md
markdown_extensions:
  - admonition
  - codehilite
  - toc:
      permalink: true
YAML
  else
    echo "Aborted."
    exit 1
  fi
fi

# ---------- seed pages (only if not present) ----------
if [[ "${SKIP_CONTENT:-0}" -eq 0 ]]; then
  banner "Seed initial pages (only create if missing)"
  mkdir -p documentation/docs
  create_if_missing() {
    local path="$1"; shift
    if [[ -f "documentation/docs/$path" ]]; then
      echo "keep  documentation/docs/$path"
    else
      echo "write documentation/docs/$path"
      cat > "documentation/docs/$path" <<'MD'
'"$@"'
MD
    fi
  }

  create_if_missing index.md '# Frigate Hot-Reload
Fast, UI-first configuration editing for Frigate — no restarts, instant apply, backups/rollback, and token-based auth.'
  create_if_missing quickstart.md '# Quickstart
1. Start backend (FastAPI/Uvicorn).
2. Open the UI at `/ui/`.
3. Generate an auth token, paste it in the UI if needed.
4. Edit config, use **Dry Run** to preview, then **Apply**.
5. Use **Backups/Undo** to revert recent changes.'
  create_if_missing install.md '# Installation
- **macOS (dev)**: Python 3.11+, `uvicorn`, `fastapi`.
- **Run**: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8080`
- **UI**: open `http://127.0.0.1:8080/ui/`.
- **Token**: POST `/api/auth/generate`, then include `Authorization: Bearer <token>`.'
  create_if_missing configuration.md '# Configuration
- JSON-based config persisted on disk.
- **Dry Run** previews diffs; **Apply** saves and broadcasts changes (no restart).
- Backups (max 5), rollback, import/export supported.'
  create_if_missing cameras.md '# Cameras
- Add / Clone from selected / Delete / Bulk delete.
- Drag & drop to reorder.
- Undo banner for last destructive actions.
- Presets and “advanced JSON override” supported.'
  create_if_missing api.md '# API
- `GET /api/config`, `POST /api/config/validate`, `POST /api/config/apply?dry=true|false`
- `POST /api/config/import`, `GET /api/config/export`
- `GET /api/config/backups`, `POST /api/config/rollback`
- `POST /api/cameras/clone`, `/delete`, `/bulk_delete`, `/reorder`, `/set`
- `POST /api/auth/generate`, `GET /api/auth/status`, `POST /api/auth/disable`
- `GET /ws` (events)'
  create_if_missing ui.md '# UI
- Sidebar camera list with checkboxes and "Select all".
- Buttons: Add, Clone from selected, Delete, Bulk delete, Reorder (drag), Undo.
- Auth token indicator & actions; Import/Export config.'
  create_if_missing troubleshooting.md '# Troubleshooting
- **403**: Missing/invalid token → generate via `/api/auth/generate`.
- **500 on import**: Validate first via `/api/config/validate`.
- **Port busy**: Another instance on :8080 → stop it or change port.'
  create_if_missing changelog.md '# Changelog
This mirrors project CHANGELOG. Keep versions and dates aligned.'
  create_if_missing roadmap.md '# Roadmap
- Phase 1: Live-apply config (done)
- Phase 2: Cameras CRUD (done)
- Phase 3: Auth, backups, undo (done)
- Phase 4: Documentation site (ongoing)'
fi

# ---------- GH Pages workflow ----------
banner "GitHub Pages workflow"
if [[ -f .github/workflows/gh-pages.yml ]]; then
  echo "Workflow already exists: .github/workflows/gh-pages.yml"
else
  if ask_yn "Create GH Pages workflow for auto-deploy on push?" "y"; then
    mkdir -p .github/workflows
    cat > .github/workflows/gh-pages.yml <<'YAML'
name: Deploy Docs
on:
  push:
    branches: [ "main" ]
    paths:
      - "documentation/**"
      - ".github/workflows/gh-pages.yml"
permissions:
  contents: read
  pages: write
  id-token: write
jobs:
  build-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.x"
      - run: pip install mkdocs-material
      - run: mkdocs build --site-dir site
        working-directory: documentation
      - uses: actions/upload-pages-artifact@v3
        with:
          path: documentation/site
      - uses: actions/deploy-pages@v4
YAML
  else
    echo "Skipping workflow creation."
  fi
fi

# ---------- Commit & push ----------
banner "Git commit & push"
if ask_yn "Commit documentation changes now?" "y"; then
  git add documentation .github/workflows/gh-pages.yml 2>/dev/null || true
  if ! git diff --cached --quiet; then
    read -rp "Commit message (default: 'docs: bootstrap site & workflow'): " MSG
    MSG="${MSG:-docs: bootstrap site & workflow}"
    git commit -m "$MSG"
  else
    echo "No staged changes."
  fi
  if ask_yn "Push to GitHub now (current branch + tags)?" "y"; then
    BR="$(git rev-parse --abbrev-ref HEAD)"
    git push origin "$BR"
    echo "Pushed to origin/$BR."
    echo "After first push, check GitHub → Settings → Pages → Build & deployment = GitHub Actions."
  else
    echo "Skipping push."
  fi
else
  echo "Skipping commit & push."
fi

# ---------- Local preview ----------
banner "Local preview (optional)"
if ask_yn "Run local preview server with mkdocs serve?" "n"; then
  # optional lightweight venv
  if ask_yn "Create a local venv (.docs-venv) and install mkdocs-material?" "y"; then
    python3 -m venv .docs-venv
    source .docs-venv/bin/activate
    pip install --upgrade pip
    pip install mkdocs-material
  else
    echo "Assuming mkdocs is already installed globally."
  fi
  cd documentation
  echo "Starting local server on http://127.0.0.1:8000 … Ctrl+C to stop."
  mkdocs serve
else
  echo "Preview skipped. You can run later:"
  echo "  python3 -m venv .docs-venv && source .docs-venv/bin/activate && pip install mkdocs-material"
  echo "  cd documentation && mkdocs serve"
fi

echo
echo "✅ Done."
