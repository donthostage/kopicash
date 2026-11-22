# Kopicash React/Vite Implementation Plan

> **For agentic workers:** Migrate independently scoped screens, then integrate and verify them together. Track progress with the checkboxes below.

**Goal:** Replace the browser UI with a React/TypeScript application while preserving the latest local Kopicash flows.

**Architecture:** `advisor/frontend` is the Vite project. Existing styles and artwork are inputs, not a second JavaScript application. Hash navigation and a same-origin, typed fetch client connect the React components to the unchanged FastAPI endpoints.

**Tech Stack:** React, TypeScript strict mode, Vite, FastAPI, Nginx, Chromium.

- [ ] Platform: `frontend/package.json`, `tsconfig.json`, `vite.config.ts`, `index.html`, `src/api.ts`, and `src/main.tsx`. Build using `npm ci` and `npm run build`. `api<T>(path: string, init?: RequestInit): Promise<T>` handles JSON, 204 and typed HTTP errors. Vite dev binds `127.0.0.1:18746`, proxying `/api` and `/healthz` to `127.0.0.1:18745`.
- [ ] Auth and shell: migrate welcome, login/registration/guest, home, theme, hash navigation, logout and header/sidebar controls. Assert guest entry shows the home navigation and reload preserves the guest session. Keep the old entry points operational until release verification.
- [ ] Wallet: `src/Wallet.tsx` migrates carousel, selection, add/import/delete, settings, limits and category editor. Reuse current API contracts; test delete updates carousel without navigation, received above limit is rejected and repeated demo creation adds a unique card.
- [ ] Checkout: `src/Checkout.tsx` migrates category/amount, recommendations and purchase capture. Test category change keeps amount and recalculates; double submission cannot duplicate a purchase.
- [ ] Cashback: `src/Cashback.tsx` migrates summaries, month selection, history and both plans; `src/CashbackEditor.tsx` migrates manual terms and OCR review. Verify repeat plan inputs use cached results, changed inputs recalculate, and OCR does not send a real external request during tests.
- [ ] Production: multi-stage `frontend/Dockerfile`, Nginx SPA fallback, unchanged API proxy, PWA assets with cache migration. Build and run migrated Playwright checks on mobile and desktop plus existing FastAPI suite. Switch local `18745` only after parity checks pass. No push or deployment.
