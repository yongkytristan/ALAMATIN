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

Set `NEXT_PUBLIC_API_BASE_URL` to use real `POST /parse` and `POST /validate` endpoints. With no value set, `lib/api.ts` uses typed provisional fixtures. The API boundary is intentionally isolated because the ALM-025/026 schema is not final. Set `NEXT_PUBLIC_HEALTH_AVAILABLE=true` only when a safe health endpoint is actually connected; the health indicator is hidden by default.

## Interaction notes

- Suggestions remain visually marked and cannot be copied until explicitly resolved and revalidated.
- Any component edit preserves the previous value, marks the review as dirty, and disables final copying.
- Raw addresses are kept in React memory only. They are not written to URLs, logs, analytics, local storage, or session storage.
- The interface includes empty, loading, ready, needs-confirmation, invalid, dirty, input-error, and safe API-error states.

## Known limitations

- Fixtures use keyword routing purely for demonstration; address inference and reference lookup belong to the backend.
- Health status is hidden until a health endpoint is connected.
- The provisional API response types must be aligned once ALM-025/026 are frozen.
