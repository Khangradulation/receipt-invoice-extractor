# Frontend

React 19 + TypeScript + Vite + Tailwind CSS v4, TanStack Query for server state, React Router,
Firebase Auth (email/password) and Recharts.

## Pages

| Route | Page | Data |
|-------|------|------|
| `/login`, `/register` | Sign in / create account / password reset | Firebase Auth |
| `/` | Overview: spending, transactions, success rate, review count, recent documents | `analytics/overview`, `documents`, `review` |
| `/upload` | Drag and drop, client checks, SHA-256, signed-URL upload with progress, live status | `documents/upload-url`, `documents/{id}/status` |
| `/documents` | All documents, status filter, "load more" (cursor paging) | `documents` |
| `/documents/:id` | Original file (signed URL; PDF/image), extracted data, validation, history | `documents/{id}`, `documents/{id}/file` |
| `/review` | Review queue | `review` |
| `/review/:id` | File side by side with editable fields; failed fields highlighted; save, approve, reject; duplicate acknowledgement; correction history | `review/{id}` (+ PATCH, approve, reject) |
| `/analytics` | Cards, monthly chart, categories, merchants, receipts vs. invoices, success and review rates; date range and currency picker | `analytics/*` |
| `/settings` | Account, password reset, upload limits, API status | Firebase, `health` |

Every page has loading, empty and error states. Heavier pages (analytics, review editor, document
details, upload) are code-split.

## Auth

`AuthProvider` subscribes to Firebase `onIdTokenChanged` and registers a token provider with the
API client. Every request sends `Authorization: Bearer <ID token>`; after a 401 the client
refreshes the token once and retries. Signing out clears the query cache, so the next user never
sees cached data. Routes other than `/login` and `/register` sit behind `RequireAuth`.

Firebase web config (`VITE_FIREBASE_*`) is public by design: it identifies the project. Security
comes from the backend verifying ID tokens and checking document ownership.

## Configuration

| Variable | Purpose |
|----------|---------|
| `VITE_API_BASE_URL` | API origin; empty means same origin (the dev proxy forwards `/api`) |
| `VITE_API_PROXY_TARGET` | Dev proxy target (default `http://localhost:8080`) |
| `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID`, `VITE_FIREBASE_APP_ID` | Firebase web app config |

## Firebase setup (done once per project)

1. Add Firebase to the GCP project (Firebase Management API `projects/{id}:addFirebase`).
2. Create a web app and read its config (`webApps.create`, `webApps/{id}/config`).
3. Initialise Auth (`identityPlatform:initializeAuth`), enable the email/password provider, and add
   `localhost` (plus the deployed frontend domain later) to the authorised domains.

These calls are scripted in Phase 11 (Terraform). The live project was configured on 2026-11-10.

## Tests

`npm test` (Vitest + Testing Library, jsdom): 36 tests, covering the API client (token, refresh on
401, query strings, error mapping), review-form diffing, sign-in/registration/redirects, the upload
flow, document listing and paging, document details and 404, the review workflow (highlighting,
save → approve, refused approval, reject reason), and dashboard/analytics rendering. API calls
are stubbed per test; fixtures live in `src/test/fixtures.ts` and are never imported by
application code.
