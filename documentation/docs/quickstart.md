# Quickstart

## 1) Run the backend
```bash
cd backend
source .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && source .venv/bin/activate)
pip install -U pip "fastapi" "uvicorn[standard]" "pydantic>=2" "watchfiles"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```
Serves API at `/api/*`, UI at `/ui/`.

## 2) Open the UI
http://127.0.0.1:8080/ui/

## 3) Optional auth
```bash
curl -s -X POST http://127.0.0.1:8080/api/auth/generate | jq .
# token is saved to backend/data/auth_token.txt
```

## 4) Sanity checks
```bash
curl -s http://127.0.0.1:8080/api/ping | jq .
TOKEN="$(cat backend/data/auth_token.txt 2>/dev/null || true)"
curl -s ${TOKEN:+-H "Authorization: Bearer $TOKEN"} http://127.0.0.1:8080/api/config | jq .
```

## 5) Edit & apply
- Use UI forms
- **Preview (dry)** → check diff
- **Apply** → instant hot reload
- **Undo** → restore latest backup
