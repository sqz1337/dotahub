import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

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
  plugins: [react(), profileRewrite()],
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
