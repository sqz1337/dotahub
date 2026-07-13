import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { copyFileSync, cpSync, mkdirSync } from "node:fs";
import { basename, resolve } from "node:path";

const legacyEntryPattern = /^\/(?:index\.html|cards\.html)?(?:\?.*)?$/;

// The public app always starts at /dashboard/. The old card-editor HTML files
// stay in the repository as development references, but are not website routes.
function dashboardEntryRedirect(): Plugin {
  return {
    name: "dashboard-entry-redirect",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!req.url || !legacyEntryPattern.test(req.url)) return next();
        res.statusCode = 302;
        res.setHeader("Location", "/dashboard/");
        res.end();
      });
    },
    configurePreviewServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!req.url || !legacyEntryPattern.test(req.url)) return next();
        res.statusCode = 302;
        res.setHeader("Location", "/dashboard/");
        res.end();
      });
    },
  };
}

// Pretty entity URLs share the same React entrypoint as their directory page.
function entityRewrite(): Plugin {
  const rewrite = (req: { url?: string }, _res: unknown, next: () => void) => {
    if (req.url && /^\/profile\/\d+\/?($|\?)/.test(req.url)) req.url = "/profile/";
    if (req.url && /^\/matches\/\d+\/?($|\?)/.test(req.url)) req.url = "/matches/";
    next();
  };
  return {
    name: "entity-id-rewrite",
    configureServer(server) {
      server.middlewares.use(rewrite);
    },
    configurePreviewServer(server) {
      server.middlewares.use(rewrite);
    },
  };
}

// Absolute /assets/... URLs are used throughout the UI. Vite only copies
// imported files by default, so copy the small runtime subset explicitly.
function runtimeAssets(): Plugin {
  return {
    name: "runtime-assets",
    writeBundle(options) {
      const outputRoot = resolve(String(options.dir ?? "dist"), "assets");
      mkdirSync(outputRoot, { recursive: true });
      cpSync(resolve("assets/ranks"), resolve(outputRoot, "ranks"), { recursive: true });
      cpSync(resolve("assets/players"), resolve(outputRoot, "players"), { recursive: true });
      cpSync(resolve("assets/backgrounds"), resolve(outputRoot, "backgrounds"), { recursive: true });
      copyFileSync(resolve("assets/radiance.ttf"), resolve(outputRoot, "radiance.ttf"));

      const templates = ["ancient", "archon", "divine", "immortal", "legend"];
      const templateRoot = resolve(outputRoot, "card-templates");
      mkdirSync(templateRoot, { recursive: true });
      for (const template of templates) {
        const source = resolve("assets/card-templates", `${template}_card_transparent.png`);
        copyFileSync(source, resolve(templateRoot, basename(source)));
      }
    },
  };
}

export default defineConfig({
  plugins: [dashboardEntryRedirect(), react(), entityRewrite(), runtimeAssets()],
  server: {
    proxy: {
      "/auth": "http://127.0.0.1:3001",
      "/api": "http://127.0.0.1:3001",
    },
  },
  build: {
    rollupOptions: {
      input: {
        dashboard: "dashboard/index.html",
        players: "players/index.html",
        profile: "profile/index.html",
        matches: "matches/index.html",
      },
    },
  },
});
