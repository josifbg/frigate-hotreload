# Examples

## Minimal single camera
```json
{
  "mqtt": {"host": "mqtt", "port": 1883, "topic_prefix": "frigate"},
  "cameras": {
    "front": {
      "name": "Front",
      "enabled": true,
      "ffmpeg": {"url": "rtsp://user:pass@host/stream", "width": 1920, "height": 1080, "fps": 15},
      "zones": []
    }
  }
}
```

## Two cameras with different FPS and retention
```json
{
  "mqtt": {"host": "mqtt", "port": 1883},
  "cameras": {
    "door": {
      "name": "Door",
      "enabled": true,
      "ffmpeg": {"url": "rtsp://user:pass@door/stream", "width": 2560, "height": 1440, "fps": 20},
      "retention": {"mode": "motion", "detection_days": 5, "recording_days": 2}
    },
    "yard": {
      "name": "Yard",
      "enabled": true,
      "ffmpeg": {"url": "rtsp://user:pass@yard/stream", "width": 1920, "height": 1080, "fps": 10},
      "detection": {"score_threshold": 0.55}
    }
  }
}
```

## Bulk clone via API (shell)
```bash
TOKEN="$(cat backend/data/auth_token.txt 2>/dev/null || true)"
for n in 2 3 4; do
  curl -s ${TOKEN:+-H "Authorization: Bearer $TOKEN"} -H 'Content-Type: application/json' \
    -X POST http://127.0.0.1:8080/api/cameras/clone \
    -d "{\"source_key\":\"front\",\"target_key\":\"front_$n\",\"overwrite\":false,\"apply\":true}" | jq -r '.ok'
done
```
