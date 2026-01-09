# Changelog

## 2026-01-09 — Minimal frontend MVP

- Fix: clean duplicate React import in `src/App.tsx`.
- Feat: add `StatusCard` (`frontend/src/components/StatusCard.tsx`) — small reusable card UI.
- Feat: add `TableList` (`frontend/src/components/TableList.tsx`) — simple tabular renderer.
- Fix: clean and improve `frontend/src/pages/AssetsPage.tsx` to use the fetch helper and `TableList`.
- Feat: centralize API client in `frontend/src/lib/api.ts` (added `fetchRootJson` for `/health` and `/version`).
- Change: `frontend/src/components/Health.tsx` and `frontend/src/components/Assets.tsx` now use centralized fetch helpers and `StatusCard`.
- Add: `frontend/.env` with `VITE_API_URL=/api` to set default API base for Vite.

All changes are intentionally small and focused on a minimal MVP UI that consumes the backend `health`, `version`, `/api/assets`, `/api/risk`, and `/api/scenarios` endpoints.
