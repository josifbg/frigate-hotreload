# FAQ

### Do I need to restart after config changes?
No. The backend applies changes live. If a safe hot-apply is not possible, the import will still save the JSON and return with a `note: "fallback_apply"`.

### Where is the config stored?
`backend/data/config.json`. Backups are in `backend/data/backups/`.

### How do I recover after a bad change?
Use **Undo** in the UI (restores latest backup). You can also import a known-good JSON via **Import**.

### Why do I get 403 Forbidden?
Auth is enabled and the request is missing or has a wrong token. Use:
```
Authorization: Bearer <token>
```
Generate a token via `POST /api/auth/generate`.

### Can I bulk delete cameras?
Yes: use the UI checkboxes with **Delete selected**, or the API `POST /api/cameras/bulk_delete`.

### How do I reorder cameras?
Drag-and-drop in the UI, then **Apply**. Or POST to `/api/cameras/reorder` with the desired `order` array.
