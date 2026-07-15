# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react/README.md) uses [Babel](https://babeljs.io/) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type aware lint rules:

- Configure the top-level `parserOptions` property like this:

```js
export default tseslint.config({
  languageOptions: {
    // other options...
    parserOptions: {
      project: ['./tsconfig.node.json', './tsconfig.backend.json'],
      tsconfigRootDir: import.meta.dirname,
    },
  },
})
```

- Replace `tseslint.configs.recommended` to `tseslint.configs.recommendedTypeChecked` or `tseslint.configs.strictTypeChecked`
- Optionally add `...tseslint.configs.stylisticTypeChecked`
- Install [eslint-plugin-react](https://github.com/jsx-eslint/eslint-plugin-react) and update the config:

```js
// eslint.config.js
import react from 'eslint-plugin-react'

export default tseslint.config({
  // Set the react version
  settings: { react: { version: '18.3' } },
  plugins: {
    // Add the react plugin
    react,
  },
  rules: {
    // other rules...
    // Enable its recommended rules
    ...react.configs.recommended.rules,
    ...react.configs['jsx-runtime'].rules,
  },
})
```

---

## Local Development (Testing Mode)

Set `TESTING=true` in the root `.env` to run TuneBox without a real Plex server.
The backend uses mock data (10 artists × 6 albums × 15 tracks) and a mock player.

### Day-to-day dev workflow

```bash
# 1. Ensure TESTING=true is in root .env
echo "TESTING=true" >> ../.env

# 2. Start Redis (required for queue operations)
docker compose up redis -d

# 3. Start the backend
cd .. && uv run uvicorn backend.main:app --reload

# 4. Start the frontend (separate terminal)
cd frontend && npm run dev
```

On **first load**, the setup wizard appears — but the mock PIN flow is instant:

1. Enter any username / jukebox name and click **Connect to Plex**
2. The PIN shows as `MOCK` — visit the mock-claim URL or just wait (auto-claims in testing mode)
3. Select the mock server and click **Save & Finish Setup**
4. You land on the dashboard in **admin mode** — all navigation and queue features work

On every **subsequent load** the wizard is skipped automatically (admin token is persisted).

### Testing the setup wizard flow

Force the wizard at any time by adding `?wizard` to the URL:

```
http://localhost:5173/?wizard
```

This clears the stored admin token and guest profile so the wizard runs again. The `?wizard`
param is stripped from the URL immediately so normal navigation is unaffected.

### Full reset

Remove the `ADMIN_TOKEN` value from root `.env` (leave the key, just clear the value)
and clear your browser's `localStorage` for `localhost:5173`.
