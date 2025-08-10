# Frigate Hot-Reload – Rollout Plan

**Owner:** Josif / Assistant  
**Repo:** `josifbg/frigate-hotreload`  
**Date:** 2025-08-10 (Europe/Sofia)

## Legend
- [x] Done · [ ] Todo · [~] In progress  
- **DoD** = Definition of Done (критерии за приемане)

---

## Phase 0 — Foundations (DONE)
- [x] Minimal FastAPI backend: `/api/config` (get), `/api/config/apply` (dry/apply), `/api/config/reset`, `/api/config/export`, `/api/config/import`.
- [x] WebSocket bus `/ws` + broadcast helper.
- [x] Static UI `/ui` с форма за камера и raw JSON редактор.
- [x] Backups с лимит до 5 (FIFO) + rollback (latest/by name) + reset to disk.
- [x] Clone UX: **Clone from selected**, **Clone + Apply**, **Bulk clone** (list or range, Overwrite).
- **DoD:** API работи локално; UI визуализира и прилага промените без рестарт; бекъпите се режат до 5; клониране работи и през API проверка.

---

## Phase 1 — UX и масови операции (CURRENT)
### 1.1 Default camera template
- [ ] UI: панел „Default template“ (editable JSON/форма) с **Apply template to new cams**.
- [ ] Backend: съхранение на `default_template.json` в `data/` + endpoint `/api/template` (GET/POST).
- [ ] UI: при Add/Clone нова камера – предлага попълване от шаблон (merge: template → fields → existing camera when cloning).
- **DoD:** Нова камера се създава с пресет от шаблон. Шаблонът се променя/съхранява от UI. Валидацията не допуска невалиден JSON.

### 1.2 Масова промяна по поле
- [ ] UI: секция „Bulk edit fields“ – target keys (list/range), избор на полета (URL/FPS/W/H/thresholds/name/enabled) и нови стойности.
- [ ] Backend: `/api/config/bulk_edit` – валидира списък ключове и patch операции.
- [ ] Preview diff преди Apply, Apply като бекъпва и пази лимита.
- **DoD:** Една операция променя избрани полета за N камери, с видим diff и атомично Apply.

### 1.3 Валидации и UX подсказки
- [ ] Inline подсказки за невалидни URL, непопълнени ключове, диапазони.
- [ ] Disabled състояние на бутони при невалидни входни данни.
- **DoD:** Потребителят не може да извърши Apply с очевидно грешни входове; получава конкретни съобщения.

---

## Phase 2 — Process & Hot-Reload Simulation
- [ ] Worker lifecycle (mock): start/stop/reload на камера „worker“ при промени.
- [ ] Health checks (mock): reachability/latency/FPS readout.
- [ ] Event Log панел в UI, stream през WS.
- **DoD:** При промяна по камера се симулира контрол на процес; статусът се вижда live в UI.

---

## Phase 3 — Security & Roles
- [ ] Token-based auth (JWT) или session cookie; Basic остава опция за dev.
- [ ] Роли: Admin / Operator (ограничени операции за Operator).
- [ ] Audit log: кой/кога е приложил промяна (файл + endpoint).
- **DoD:** Защитени Apply/Reset/Bulk; записан audit trail; сесии изтичат коректно.

---

## Phase 4 — Packaging & Integration
- [ ] Dockerfile + docker-compose (dev) с MQTT stub.
- [ ] OpenAPI дооформяне; versioned API prefix `/v1`.
- [ ] План за hook-ове към реален Frigate за истински hot-reload (design doc).
- **DoD:** `docker compose up` стартира системата; документацията описва интеграцията.

---

## Phase 5 — Tests & CI
- [ ] Unit tests (backend): apply/rollback/backups/bulk_edit/template.
- [ ] E2E smoke (UI+API) чрез Playwright или pytest-playwright.
- [ ] GitHub Actions: линт, тест, build артефакти.
- **DoD:** CI зелено; минимален E2E сценарий минава стабилно локално и в CI.

---

## Phase 6 — Docs & Release
- [ ] README с бърз старт + скрийншоти.
- [ ] User guide: конфиг/клониране/бекъпи/rollback.
- [ ] Semantic versioning; CHANGELOG автоматизация; release tags.
- **DoD:** Нов потребител може да стартира за <5 мин; релийз артефакти налични.

---

## Phase 7 — Mobile (iOS)
- [ ] API договор и auth за мобилни клиенти (JWT/OAuth2 refresh flow).
- [ ] Live view опции: HLS/WebRTC (проучване + PoC).
- [ ] Нотификации (APNs) за motion/person/vehicle.
- [ ] SwiftUI клиент: login, cameras list, camera details, settings.
- [ ] Offline кеш + background sync.
- [ ] TestFlight билд, crash/analytics, telemetry opt-in.
- **DoD:** Публичен TestFlight build; стабилна навигация и минимум екраните по-горе.

---

## Tracking & Reporting
- Всички значими промени се логват в `CHANGELOG.md`.
- Всеки завършен таск получава комит/PR с описание и линк към секцията.

## Risks / Notes
- Browser caching за статиките – принудителен рефреш в инструкции.
- Диапазони и bulk операции – require strict validation.
- Security rollout да не блокира dev UX – поддържаме Basic докато не мигрираме напълно.
