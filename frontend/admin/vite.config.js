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
