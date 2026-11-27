# Career Hub web

Next.js frontend for the existing FastAPI service. This first slice covers sign-in, session refresh, sign-out, and the job tracker.

## Development

Use Node.js 24. Copy `.env.example` to `.env.local` and start the existing local FastAPI and database services. Run `npm ci` and `npm run dev` from this directory. Use a synthetic account in the local database.

Use `npm test`, `npm run typecheck`, and `npm run build` to check a change.

## Preview

Set Vercel's root directory to `web/`. Configure a separate `CAREER_HUB_API_ORIGIN` for Preview and Production. Use an isolated API and synthetic data for preview writes. Set `CAREER_HUB_WEB_ORIGIN` to the exact browser origin for the production deployment. Hosted previews accept their Vercel deployment origin by default. Configure the exact preview origin when using a fixed preview alias.

Before production, verify session rotation and revocation with the deployed API, account isolation, and per-client limits through the deployed proxy. The API currently keys some limits by source IP, and this frontend does not authoritatively establish client identity at that proxy boundary.

The same-origin proxy exposes sign-in, refresh, sign-out, profile and tracker routes only. Access and refresh tokens use HttpOnly cookies. The refresh cookie is scoped to `/api/session`, and personalized responses use `private, no-store`.
