# UI Guide

Open http://127.0.0.1:8080/ui/

## Features
- Full config editing in browser
- Apply without restart; Dry-run preview
- Clone camera; Drag-and-drop reorder
- Bulk delete with checkboxes
- Undo (restore from latest backup)
- Optional token auth (banner warns if missing)

## Import/Export
- Export downloads current JSON
- Import replaces config; if safe apply fails, backend saves file and marks `"note":"fallback_apply"`
