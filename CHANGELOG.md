# Changelog
All notable changes to this project will be documented in this file.

## [Unreleased]
- Default camera template (UI + API)
- Bulk edit by field (UI + API)
- Mock worker lifecycle & health checks
- Auth tokens & roles; audit log
- Docker compose; CI; docs

## [0.2.0] — 2025-08-10
### Added
- Clone UX: **Clone from selected**, **Clone + Apply**, **Bulk clone** (list/range, Overwrite).
- UI improvements for camera editor and raw JSON.
- Backups with max 5 files (FIFO) and rollback/reset from UI.

### Fixed
- WebSocket reconnect and basic stability tweaks.

## [0.1.0] — 2025-08-10
### Added
- Initial FastAPI backend for config (get/apply/preview/reset/export/import).
- Minimal UI served at `/ui` with JSON editor and form.
