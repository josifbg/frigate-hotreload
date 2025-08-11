# Configuration

This project stores configuration as JSON at `backend/data/config.json`. The UI edits the same structure in-memory and applies changes without restart.

## Top-level keys
- `mqtt`: broker settings
- `cameras`: object whose keys are camera IDs (e.g., `cam1`, `front_door`)

### mqtt
```json
{
  "host": "mqtt",
  "port": 1883,
  "user": null,
  "password": null,
  "topic_prefix": "frigate"
}
```

### cameras[*]
Each camera entry supports the following fields:

```json
{
  "name": "Front Yard",
  "enabled": true,
  "ffmpeg": {
    "url": "rtsp://user:pass@host:554/Streaming/Channels/101",
    "hwaccel": null,
    "width": 1920,
    "height": 1080,
    "fps": 15
  },
  "onvif": {
    "host": "http://host:8000",
    "user": "user",
    "pass": "pass"
  },
  "zones": [],
  "detection": {
    "score_threshold": 0.6,
    "iou_threshold": 0.45
  },
  "retention": {
    "mode": "motion",
    "detection_days": 5,
    "recording_days": 2,
    "pre_capture_sec": 3,
    "post_capture_sec": 3
  }
}
```

> Note: All fields are optional unless your specific camera requires them. Unknown keys are preserved on round-trip.

## Backups
On each successful **Apply**, a copy of `config.json` is saved to `backend/data/backups/`. The default retention is 5 files. The **Undo** button restores the latest backup.

## Import/Export
- **Export**: `GET /api/config/export` → current JSON
- **Import**: `POST /api/config/import` with raw JSON. If a safe hot-apply is not possible, the backend will persist the file and return a `note: "fallback_apply"`.
