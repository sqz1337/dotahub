import { UserRound } from "lucide-react";
import { defaultProfileAccountId, type Page } from "../data";
import { useAuthUser } from "../auth/useAuthUser";

const navItems: { label: string; href: string; page?: Page }[] = [
  { label: "Dashboard", href: "/dashboard/", page: "dashboard" },
  { label: "Players", href: "/players/", page: "players" },
  { label: "Profile", href: "/profile/", page: "profile" },
  { label: "Achievements", href: "/dashboard/" },
  { label: "Hall of Fame", href: "/dashboard/" },
];

export function Header({ activePage }: { activePage: Page }) {
  const { authUser } = useAuthUser();
  const authResult = new URLSearchParams(window.location.search).get("auth");
  const profileHref = `/profile/${authUser?.accountId ?? defaultProfileAccountId}`;

  const authNotice = authResult === "not_registered"
    ? "Вашего профиля пока нет на сайте — вход недоступен."
    : authResult === "failed"
      ? "Не удалось подтвердить вход через Steam. Попробуйте ещё раз."
      : null;

  return (
    <header className="site-header">
      <a className="brand" href="/dashboard/">
        <span className="brand-mark" aria-hidden="true">
          <span />
          <span />
          <span />
          <span />
        </span>
        <span>KASTEMS HUB</span>
      </a>

      <nav className="nav-links" aria-label="Primary navigation">
        {navItems.map((item) => (
          <a key={item.label} aria-current={item.page === activePage ? "page" : undefined} href={item.page === "profile" ? profileHref : item.href}>
            {item.label}
          </a>
        ))}
      </nav>
      <div className="header-auth">
        {authUser ? (
          <a className="profile-link" href={`/profile/${authUser.accountId}`} aria-label={`Open ${authUser.name}'s profile`} title={authUser.name}>
            {authUser.avatar ? <img src={authUser.avatar} alt="" /> : <UserRound aria-hidden="true" />}
          </a>
        ) : (
          <a className="steam-login" href="/auth/steam">
            <UserRound aria-hidden="true" />
            Sign in through Steam
          </a>
        )}
      </div>
      {authNotice ? <p className="auth-notice" role="alert">{authNotice}</p> : null}
    </header>
  );
}
