# ALAMATIN web

Next.js 16, React 19, and TypeScript implementation of the single-address
review interface.

## Run with the local backend

Start the Python backend from the repository root as described in the main
[README](../README.md). In another terminal:

```bash
cd web
npm ci
cp .env.example .env.local
npm run dev
```

On Windows PowerShell, use:

```powershell
Copy-Item .env.example .env.local
npm run dev
```

Open <http://localhost:3000>. The supplied environment file routes browser
requests through the same-origin `/api` proxy to
<http://127.0.0.1:8000>. The backend therefore needs no CORS configuration.

If the backend uses another origin, change `API_ORIGIN` in `.env.local`.

## Fixture-only demo

To run without a backend, remove `NEXT_PUBLIC_API_BASE_URL` from
`.env.local` or do not create that file. The UI then uses typed synthetic
fixtures. Use one of the “Coba contoh” options and select “Periksa alamat”.

## Tests and production build

```bash
npm test
npm run build
npm start
```

The tests cover the contract, all demo addresses, the valid-address flow, and
the confirmation → dirty → revalidation flow.

## API contract

`NEXT_PUBLIC_API_BASE_URL=/api` enables live requests.
`next.config.ts` proxies them to `API_ORIGIN`, which defaults to
`http://127.0.0.1:8000`.

The request body is:

```json
{
  "document_type": "address_parse_request",
  "schema_version": "1.0.0",
  "request_id": "req_demo_00001",
  "input": {
    "address_text": "Jl. Asia Afrika No. 1, Kel. Braga, Kec. Sumur Bandung, Kota Bandung, Jawa Barat 40111",
    "geocoding_consent": false
  }
}
```

The canonical schema is `contracts/address-api.v1.schema.json`; the frontend
loads it through `address-contract.js`. Do not create a frontend-only copy or
rename `model_score` to `confidence`.

## Privacy and interaction rules

- Raw addresses remain in React memory only.
- They are not written to URLs, logs, analytics, local storage, or session
  storage.
- Suggestions cannot be copied until they are explicitly resolved and
  revalidated.
- Editing a component preserves the previous value, marks the review dirty, and
  disables final copying.
- The UI includes empty, loading, ready, needs-confirmation, invalid, dirty,
  input-error, and safe API-error states.
