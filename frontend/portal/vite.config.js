import { resolve } from "node:path";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const REPO_ROOT = resolve(__dirname, "../..");

export default defineConfig(({ mode }) => {
  // Read the repo-root .env with no prefix filter so ports come from the same
  // contract that drives Django and docker compose. Only VITE_* values are ever
  // exposed to client code; these are used for dev-server config only.
  const env = loadEnv(mode, REPO_ROOT, "");

  return {
    plugins: [react()],
    resolve: {
      alias: {
        // Consume the shared package as SOURCE rather than a built artifact:
        // no build step to keep in sync, and edits to a primitive hot-reload
        // in both apps immediately.
        "@mateassist/ui": resolve(__dirname, "../packages/ui/src"),
        "@": resolve(__dirname, "src")
      }
    },
    server: {
      port: Number(env.PORTAL_PORT) || 5175,
      // Bind every interface rather than Vite's default `localhost`, which
      // listens on ::1 ONLY. Tenant subdomains (D-021) are resolved by browsers
      // to IPv4 127.0.0.1, so an ::1-only server is unreachable at
      // netswitch.localhost. See amendment A-007.
      host: true,
      // Proxying keeps dev same-origin, mirroring production where one proxy
      // fronts both the SPA and the API. It also means the httpOnly refresh
      // cookie (D-032) behaves in dev exactly as it will in prod.
      proxy: {
        "/api": {
          target: `http://127.0.0.1:${env.DJANGO_PORT || 8000}`,
          changeOrigin: true
        }
      }
    },
    build: {
      outDir: "dist",
      sourcemap: mode !== "production"
    }
  };
});
