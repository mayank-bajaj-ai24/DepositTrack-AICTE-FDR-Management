# DepositTrack web

Next.js app for officers, institutions and auditors. Screens follow the taste-skill
"achromatic ledger" app style (see the comment at the top of `src/app/globals.css`).

```bash
cp .env.example .env.local   # API and Keycloak URLs
npm install
npm run dev                  # http://localhost:3000
npm run lint && npx tsc --noEmit && npm run build
```

UI text is in `src/i18n/en.json` and `src/i18n/hi.json` (Hindi needs review by a fluent speaker).
