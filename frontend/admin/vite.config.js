import { resolve } from "node:path";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const REPO_ROOT = resolve(__dirname, "../..");

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, REPO_ROOT, "");

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@mateassist/ui": resolve(__dirname, "../packages/ui/src"),
        "@": resolve(__dirname, "src")
      }
    },
    server: {
      port: Number(env.ADMIN_PORT) || 5174,
      // See the portal config and amendment A-007: Vite's default `localhost`
      // binds ::1 only, which tenant subdomains cannot reach.
      host: true,
      proxy: {
        "/api": {
          target: `http://127.0.0.1:${env.DJANGO_PORT || 8000}`,
          // Must match the portal: see the note there. The admin host resolves
          // to no tenant anyway, so this surface would work either way - which
          // is exactly why the bug hid here and only showed up on the portal.
          changeOrigin: false
        }
      }
    },
    build: {
      outDir: "dist",
      sourcemap: mode !== "production"
    }
  };
});
