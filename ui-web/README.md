# Router Mission Control UI

Next.js frontend shell for `router-architecture`.

## Run

1. Start the Python API:

```bash
cd /Users/hwitzthum/router-architecture
router-api
```

2. Start the UI:

```bash
cd /Users/hwitzthum/router-architecture/ui-web
npm install
npm run dev
```

## Environment

- `NEXT_PUBLIC_ROUTER_API_BASE` (optional, default `http://localhost:8001`)

Example:

```bash
NEXT_PUBLIC_ROUTER_API_BASE=http://localhost:8001 npm run dev
```
