import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        dashboard: "dashboard/index.html",
        players: "players/index.html",
      },
    },
  },
});
