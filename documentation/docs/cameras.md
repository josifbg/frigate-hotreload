# Cameras

Cameras are defined under the `cameras` object where each key is a camera ID (`cam1`, `garage`, etc.).

## Common operations

### Clone
```bash
TOKEN="$(cat backend/data/auth_token.txt 2>/dev/null || true)"
curl -s ${TOKEN:+-H "Authorization: Bearer $TOKEN"} -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:8080/api/cameras/clone \
  -d '{"source_key":"cam1","target_key":"cam_new","overwrite":false,"apply":true}' | jq .
```

### Delete
```bash
curl -s ${TOKEN:+-H "Authorization: Bearer $TOKEN"} -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:8080/api/cameras/delete \
  -d '{"key":"cam_new","apply":true}' | jq .
```

### Reorder
```bash
ORDER=$(curl -s ${TOKEN:+-H "Authorization: Bearer $TOKEN"} http://127.0.0.1:8080/api/config | jq -c '{order:(.cameras|keys|reverse), apply:true}')
curl -s ${TOKEN:+-H "Authorization: Bearer $TOKEN"} -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:8080/api/cameras/reorder \
  -d "$ORDER" | jq .
```

### Bulk delete
```bash
curl -s ${TOKEN:+-H "Authorization: Bearer $TOKEN"} -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:8080/api/cameras/bulk_delete \
  -d '{"keys":["camA","camB"],"apply":true}' | jq .
```

## UI helpers
- **Clone from selected** button duplicates configuration to a new camera ID.
- **Drag to reorder** the list; click **Apply** to persist order.
- **Select all + Delete selected** removes multiple cameras at once.
