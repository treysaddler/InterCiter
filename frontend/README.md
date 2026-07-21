# InterCiter frontend

The InterCiter web UI: a **React + TypeScript + Vite** single-page app built on the
**U.S. Web Design System** via [`@trussworks/react-uswds`](https://github.com/trussworks/react-uswds).
It is a client of the InterCiter `/v1` API and holds no state of record.

See the design and rationale in [../docs/ui-design.md](../docs/ui-design.md)
(stack decision §3, USWDS mapping §4, information architecture §5, screens §6,
user stories §8, auth/session §11).

## Prerequisites

- Node (see `.nvmrc`) and npm
- The backend running locally on `http://localhost:8000` for live data
  (`cd ../backend && uv run interciter serve --reload`)

## Develop

```sh
npm install
npm run dev        # http://localhost:5173  (proxies /v1 and /health to :8000)
```

## Build & check

```sh
npm run typecheck  # tsc, no emit
npm run build      # tsc -b && vite build  ->  dist/
npm run preview    # serve the production build
```

## Layout

```
src/
  main.tsx            App bootstrap (Router + USWDS styles)
  App.tsx             Route map (mirrors docs/ui-design.md §5)
  api/
    client.ts         Fetch wrapper; same-origin, credentials: 'include' (BFF cookie)
    types.ts          Hand DTOs (to be replaced by an OpenAPI-generated client)
  components/
    AppShell.tsx      USWDS header/banner/nav/footer + <Outlet/>
    PageFocus.tsx     Route-change focus management (a11y)
    PageHeading.tsx   Focus target heading
  pages/              One stub per route; each names the /v1 endpoints it will use
  styles/styles.scss  USWDS Sass entry + InterCiter token-based custom styles
```

## Notes

- **Auth (docs/ui-design.md §11):** the browser never stores the raw API token.
  Requests are same-origin with `credentials: 'include'`; the backend BFF session
  layer (a login→cookie exchange, cookie auth alongside the existing Bearer header,
  CSRF) is not built yet.
- **USWDS assets:** fonts and images are copied from `@uswds/uswds` into the build
  by `vite-plugin-static-copy`; the Sass entry points theme paths at `/fonts` and
  `/img`.
- **Accessibility is an acceptance criterion, not a phase** — keep USWDS components,
  keyboard parity, and route-change focus intact.
