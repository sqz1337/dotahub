import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

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

// /profile/<accountId> is a pretty URL for the profile page; serve profile/index.html for it.
function profileRewrite(): Plugin {
  return {
    name: "profile-id-rewrite",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        if (req.url && /^\/profile\/\d+\/?($|\?)/.test(req.url)) req.url = "/profile/";
        next();
      });
    },
  };
}

export default defineConfig({
  plugins: [dashboardEntryRedirect(), react(), profileRewrite()],
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
      },
    },
  },
});
