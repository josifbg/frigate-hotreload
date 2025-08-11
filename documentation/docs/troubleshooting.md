# Troubleshooting

## 403 Forbidden (API)
- Auth is enabled but the request is missing/has a wrong token.
- Fix: include the header `Authorization: Bearer <token>` or disable auth via `POST /api/auth/disable` (temporary).

## Import returns 200 but with `"note":"fallback_apply"`
- The backend could not safely hot-apply. It saved the JSON to disk and returned success.
- Verify the config in UI, then **Apply** to confirm.

## WebSocket disconnects
- UI shows a brief disconnect on refresh; this is normal. Persistent 403 → check token.

## Diff shows no changes
- You may be doing a dry-run with identical content. Tweak a field and retry.

## Where are backups?
- `backend/data/backups/` (rolling, default max 5). Use **Undo** in the UI to restore the latest.
