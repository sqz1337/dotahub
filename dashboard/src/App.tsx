import { DashboardPage } from "./pages/DashboardPage";
import { MatchPage } from "./pages/MatchPage";
import { PlayersPage } from "./pages/PlayersPage";
import { ProfilePage } from "./pages/ProfilePage";
import type { Page } from "./data";

export function App() {
  const page: Page = window.location.pathname.startsWith("/players")
    ? "players"
    : window.location.pathname.startsWith("/matches")
      ? "match"
    : window.location.pathname.startsWith("/profile")
      ? "profile"
      : "dashboard";

  return (
    <main className={`dashboard-shell ${page === "players" ? "players-shell" : ""} ${page === "match" ? "match-shell" : ""} ${page === "profile" ? "profile-shell" : ""}`}>
      {page === "players" ? <PlayersPage /> : page === "match" ? <MatchPage /> : page === "profile" ? <ProfilePage /> : <DashboardPage />}
    </main>
  );
}
