import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";
import { createReadStream, existsSync, readFileSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL(".", import.meta.url));

function loadLocalEnv() {
  const envPath = join(ROOT, ".env");
  if (!existsSync(envPath)) return;
  for (const line of readFileSync(envPath, "utf8").split(/\r?\n/)) {
    const match = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
    if (!match || process.env[match[1]] !== undefined) continue;
    process.env[match[1]] = match[2].replace(/^(["'])(.*)\1$/, "$2");
  }
}

loadLocalEnv();

const PORT = Number(process.env.PORT ?? 3001);
const PUBLIC_ORIGIN = (process.env.PUBLIC_ORIGIN ?? "http://127.0.0.1:5173").replace(/\/$/, "");
const IS_PRODUCTION = process.env.NODE_ENV === "production";
const SESSION_SECRET = process.env.AUTH_SESSION_SECRET ?? (IS_PRODUCTION ? "" : randomBytes(32).toString("hex"));
const STEAM_OPENID_URL = "https://steamcommunity.com/openid/login";
const STEAM_ID_OFFSET = 76561197960265728n;
const SESSION_COOKIE = "dotahub_session";
const STATE_COOKIE = "dotahub_openid_state";

if (!SESSION_SECRET) {
  throw new Error("AUTH_SESSION_SECRET must be set when NODE_ENV=production.");
}

function encode(value) {
  return Buffer.from(JSON.stringify(value)).toString("base64url");
}

function sign(value) {
  return createHmac("sha256", SESSION_SECRET).update(value).digest("base64url");
}

function makeToken(value) {
  const body = encode(value);
  return `${body}.${sign(body)}`;
}

function readToken(token) {
  if (!token || !token.includes(".")) return null;
  const [body, signature] = token.split(".");
  const expected = sign(body);
  if (signature.length !== expected.length || !timingSafeEqual(Buffer.from(signature), Buffer.from(expected))) return null;
  try {
    const payload = JSON.parse(Buffer.from(body, "base64url").toString("utf8"));
    return payload.exp > Date.now() ? payload : null;
  } catch {
    return null;
  }
}

function parseCookies(request) {
  return Object.fromEntries(
    String(request.headers.cookie ?? "")
      .split(";")
      .map((part) => part.trim().split(/=(.*)/s, 2))
      .filter(([key]) => key)
      .map(([key, value]) => [key, decodeURIComponent(value ?? "")]),
  );
}

function cookie(name, value, maxAge = 0) {
  const parts = [`${name}=${encodeURIComponent(value)}`, "Path=/", "HttpOnly", "SameSite=Lax"];
  if (IS_PRODUCTION) parts.push("Secure");
  if (maxAge) parts.push(`Max-Age=${maxAge}`);
  return parts.join("; ");
}

function clearCookie(name) {
  return cookie(name, "", 0) + "; Max-Age=0";
}

function redirect(response, location, cookies = []) {
  response.writeHead(302, { Location: location, "Set-Cookie": cookies });
  response.end();
}

function sendJson(response, status, payload) {
  response.writeHead(status, { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" });
  response.end(JSON.stringify(payload));
}

function trackedPlayer(accountId) {
  const dashboardPath = join(ROOT, "data", "dashboard.json");
  if (!existsSync(dashboardPath)) return null;
  const dashboard = JSON.parse(readFileSync(dashboardPath, "utf8"));
  return dashboard.players?.find((player) => Number(player.accountId) === Number(accountId)) ?? null;
}

function steamLoginUrl(returnTo) {
  const query = new URLSearchParams({
    "openid.ns": "http://specs.openid.net/auth/2.0",
    "openid.mode": "checkid_setup",
    "openid.return_to": returnTo,
    "openid.realm": PUBLIC_ORIGIN,
    "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
    "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
  });
  return `${STEAM_OPENID_URL}?${query}`;
}

async function verifySteamAssertion(url) {
  const params = new URLSearchParams(url.searchParams);
  params.set("openid.mode", "check_authentication");
  const response = await fetch(STEAM_OPENID_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: params,
  });
  const verification = await response.text();
  if (!response.ok || !/^is_valid:true$/m.test(verification)) return null;
  const claimedId = url.searchParams.get("openid.claimed_id") ?? "";
  const match = claimedId.match(/^https?:\/\/steamcommunity\.com\/openid\/id\/(\d{17})\/?$/);
  return match?.[1] ?? null;
}

const mimeTypes = {
  ".css": "text/css; charset=utf-8", ".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
  ".svg": "image/svg+xml", ".woff2": "font/woff2",
};

function serveStatic(request, response, pathname) {
  const requested = pathname === "/" ? "/dashboard/" : pathname;
  const file = requested.endsWith("/") ? `${requested}index.html` : requested;
  const candidate = normalize(join(ROOT, "dist", file));
  const distRoot = normalize(join(ROOT, "dist"));
  if (!candidate.startsWith(distRoot) || !existsSync(candidate)) {
    response.writeHead(404);
    response.end("Not found");
    return;
  }
  response.writeHead(200, { "Content-Type": mimeTypes[extname(candidate)] ?? "application/octet-stream" });
  createReadStream(candidate).pipe(response);
}

createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", PUBLIC_ORIGIN);
  const cookies = parseCookies(request);

  if (request.method === "GET" && url.pathname === "/auth/steam") {
    const state = randomBytes(24).toString("base64url");
    const stateToken = makeToken({ state, exp: Date.now() + 10 * 60_000 });
    const returnTo = new URL("/auth/steam/return", PUBLIC_ORIGIN);
    returnTo.searchParams.set("state", state);
    redirect(response, steamLoginUrl(returnTo.toString()), [cookie(STATE_COOKIE, stateToken, 600)]);
    return;
  }

  if (request.method === "GET" && url.pathname === "/auth/steam/return") {
    const state = readToken(cookies[STATE_COOKIE]);
    if (!state || state.state !== url.searchParams.get("state")) {
      redirect(response, "/dashboard/?auth=failed", [clearCookie(STATE_COOKIE)]);
      return;
    }
    try {
      const steamId64 = await verifySteamAssertion(url);
      if (!steamId64) {
        redirect(response, "/dashboard/?auth=failed", [clearCookie(STATE_COOKIE)]);
        return;
      }
      const accountId = (BigInt(steamId64) - STEAM_ID_OFFSET).toString();
      const player = trackedPlayer(accountId);
      if (!player) {
        redirect(response, "/dashboard/?auth=not_registered", [clearCookie(STATE_COOKIE), clearCookie(SESSION_COOKIE)]);
        return;
      }
      const session = makeToken({ steamId64, accountId, exp: Date.now() + 7 * 24 * 60 * 60_000 });
      redirect(response, "/dashboard/?auth=success", [cookie(SESSION_COOKIE, session, 7 * 24 * 60 * 60), clearCookie(STATE_COOKIE)]);
    } catch {
      redirect(response, "/dashboard/?auth=failed", [clearCookie(STATE_COOKIE)]);
    }
    return;
  }

  if (request.method === "GET" && url.pathname === "/api/auth/me") {
    const session = readToken(cookies[SESSION_COOKIE]);
    const player = session && trackedPlayer(session.accountId);
    if (!session || !player) {
      sendJson(response, 401, { authenticated: false });
      return;
    }
    sendJson(response, 200, {
      authenticated: true,
      accountId: session.accountId,
      name: player.name,
      avatar: player.avatar,
    });
    return;
  }

  if (request.method === "POST" && url.pathname === "/auth/logout") {
    response.writeHead(204, { "Set-Cookie": clearCookie(SESSION_COOKIE) });
    response.end();
    return;
  }

  serveStatic(request, response, url.pathname);
}).listen(PORT, "127.0.0.1", () => {
  console.log(`DotaHub auth server listening on http://127.0.0.1:${PORT}`);
});
