# ALAMATIN web

Single-address review UI for ALM-027, implemented with Next.js 16, React 19, and TypeScript. Next.js was selected because it gives the MVP a typed React UI today and a clear path to server-side integration later, while keeping all frontend work inside `web/`.

## Run locally

```bash
cd web
npm install
npm run dev
```

Open <http://localhost:3000>. The UI defaults to provisional, synthetic fixtures so every required state can be demonstrated without a backend. Use the three “Coba contoh” options and then select “Periksa alamat”.

## Production build

```bash
npm run build
npm start
```

## Tests

```bash
npm test
```

The component tests cover the complete valid-address flow and the explicit confirmation → dirty → revalidation flow.

## API integration

Set `NEXT_PUBLIC_API_BASE_URL` to `/api` and the app talks to the backend through the same-origin proxy in `next.config.ts`, so the backend needs no CORS headers. Point `API_ORIGIN` at the API if it is not on `http://127.0.0.1:8000`. The simplest local setup is a `.env.local` holding:

```
NEXT_PUBLIC_API_BASE_URL=/api
NEXT_PUBLIC_HEALTH_AVAILABLE=true
```

Prefer the file over an inline environment variable: a shell that rewrites POSIX paths (Git Bash on Windows) turns `/api` into a Windows path, which is compiled into the bundle and produces a silent fetch failure.

With no value set, `lib/api.ts` uses typed fixtures, routed by exact match against `DEMO_ADDRESSES`. Set `NEXT_PUBLIC_HEALTH_AVAILABLE=true` only when a safe health endpoint is actually connected; the health indicator is hidden by default.

Load the schema through `address-contract.js`, which fetches the canonical
`contracts/address-api.v1.schema.json`. Do not keep a frontend-only copy of the
schema, and do not rename `model_score` to `confidence`: the frozen scope
forbids presenting `model_score` as calibrated confidence.

ALM-025 and ALM-026 are frozen and the alignment is done. The request body must be
`{"document_type": "address_parse_request", "schema_version": "1.0.0",
"request_id": ..., "input": {"address_text": ..., "geocoding_consent": ...}}`;
sending `{"address": ...}` returns HTTP 422 `REQUEST_VALIDATION_ERROR`.

## Interaction notes

- Suggestions remain visually marked and cannot be copied until explicitly resolved and revalidated.
- Any component edit preserves the previous value, marks the review as dirty, and disables final copying.
- Raw addresses are kept in React memory only. They are not written to URLs, logs, analytics, local storage, or session storage.
- The interface includes empty, loading, ready, needs-confirmation, invalid, dirty, input-error, and safe API-error states.

## Known limitations

- Fixtures use keyword routing purely for demonstration; address inference and reference lookup belong to the backend.
- Health status is hidden until a health endpoint is connected.
- The three demo addresses exercise the real backend; each was verified to return a distinct status. Against the fixture path they are matched by exact value, so changing one requires updating it in one place only.
