import { resolve } from "node:path";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const REPO_ROOT = resolve(__dirname, "../..");

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, REPO_ROOT, "");

  // The admin panel is served under a path, not a host (D-147):
  //
  //     mateassist.site/platform_admin   the panel
  //     mateassist.site/                 reserved for the marketing site
  //
  // It cannot move to a subdomain: `IsPlatformOwner` refuses any request that
  // resolves to a tenant, and every subdomain of the base domain does. So the
  // platform surface has to live on the apex, and the apex root belongs to
  // marketing.
  //
  // `base` rewrites every asset URL at build time. Without it the bundle asks
  // for /assets/index-*.js, which on the apex is the marketing site's territory
  // and 404s - a blank page with no error in the console.
  //
  // Left at "/" in dev so the Vite server still works at localhost:5174.
  const base = mode === "production" ? "/platform_admin/" : "/";

  return {
    base,
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
