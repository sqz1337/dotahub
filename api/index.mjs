import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";
import { readFileSync } from "node:fs";

const dashboard = JSON.parse(readFileSync(new URL("../data/dashboard.json", import.meta.url), "utf8"));
const profileDefaults = JSON.parse(readFileSync(new URL("../data/profile-overrides.json", import.meta.url), "utf8"));

const STEAM_OPENID_URL = "https://steamcommunity.com/openid/login";
const STEAM_ID_OFFSET = 76561197960265728n;
const SESSION_COOKIE = "dotahub_session";
const STATE_COOKIE = "dotahub_openid_state";
const PROFILE_COOKIE = "dotahub_profile_overrides";

function sessionSecret() {
  return process.env.AUTH_SESSION_SECRET ?? "";
}

function requestOrigin(request) {
  if (process.env.PUBLIC_ORIGIN) return process.env.PUBLIC_ORIGIN.replace(/\/$/, "");
  const forwardedProto = String(request.headers["x-forwarded-proto"] ?? "https").split(",")[0].trim();
  const forwardedHost = String(request.headers["x-forwarded-host"] ?? request.headers.host ?? "dotahub.vercel.app").split(",")[0].trim();
  return `${forwardedProto}://${forwardedHost}`;
}

function encode(value) {
  return Buffer.from(JSON.stringify(value)).toString("base64url");
}

function sign(value) {
  return createHmac("sha256", sessionSecret()).update(value).digest("base64url");
}

function makeToken(value) {
  const body = encode(value);
  return `${body}.${sign(body)}`;
}

function readToken(token) {
  if (!sessionSecret() || !token || !token.includes(".")) return null;
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
  const parts = [`${name}=${encodeURIComponent(value)}`, "Path=/", "HttpOnly", "SameSite=Lax", "Secure"];
  if (maxAge) parts.push(`Max-Age=${maxAge}`);
  return parts.join("; ");
}

function clearCookie(name) {
  return `${cookie(name, "")}; Max-Age=0`;
}

function redirect(response, location, cookies = []) {
  if (cookies.length) response.setHeader("Set-Cookie", cookies);
  response.statusCode = 302;
  response.setHeader("Location", location);
  response.end();
}

function sendJson(response, status, payload, cookies = []) {
  if (cookies.length) response.setHeader("Set-Cookie", cookies);
  response.statusCode = status;
  response.setHeader("Content-Type", "application/json; charset=utf-8");
  response.setHeader("Cache-Control", "no-store");
  response.end(JSON.stringify(payload));
}

function trackedPlayer(accountId) {
  return dashboard.players?.find((player) => Number(player.accountId) === Number(accountId)) ?? null;
}

async function readJson(request) {
  if (request.body && typeof request.body === "object" && !Buffer.isBuffer(request.body)) return request.body;
  if (typeof request.body === "string" || Buffer.isBuffer(request.body)) return JSON.parse(String(request.body) || "{}");
  let body = "";
  for await (const chunk of request) {
    body += chunk;
    if (body.length > 10_000) throw new Error("Request body too large");
  }
  return JSON.parse(body || "{}");
}

function steamLoginUrl(origin, returnTo) {
  const query = new URLSearchParams({
    "openid.ns": "http://specs.openid.net/auth/2.0",
    "openid.mode": "checkid_setup",
    "openid.return_to": returnTo,
    "openid.realm": origin,
    "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
    "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
  });
  return `${STEAM_OPENID_URL}?${query}`;
}

async function verifySteamAssertion(url) {
  const params = new URLSearchParams(url.searchParams);
  params.delete("route");
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

function normalizedRoute(url) {
  const rewritten = url.searchParams.get("route");
  return rewritten ? `/${rewritten.replace(/^\/+/, "")}` : url.pathname;
}

export default async function handler(request, response) {
  const origin = requestOrigin(request);
  const url = new URL(request.url ?? "/", origin);
  const route = normalizedRoute(url);
  const cookies = parseCookies(request);

  if (!sessionSecret()) {
    sendJson(response, 503, { error: "Server authentication is not configured" });
    return;
  }

  if (request.method === "GET" && route === "/auth/steam") {
    const state = randomBytes(24).toString("base64url");
    const stateToken = makeToken({ state, exp: Date.now() + 10 * 60_000 });
    const returnTo = new URL("/auth/steam/return", origin);
    returnTo.searchParams.set("state", state);
    redirect(response, steamLoginUrl(origin, returnTo.toString()), [cookie(STATE_COOKIE, stateToken, 600)]);
    return;
  }

  if (request.method === "GET" && route === "/auth/steam/return") {
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

  if (request.method === "GET" && route === "/api/auth/me") {
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

  const profileMatch = route.match(/^\/api\/profiles\/(\d+)$/);
  if (request.method === "GET" && profileMatch) {
    const player = trackedPlayer(profileMatch[1]);
    if (!player) {
      sendJson(response, 404, { error: "Profile not found" });
      return;
    }
    const session = readToken(cookies[SESSION_COOKIE]);
    const saved = readToken(cookies[PROFILE_COOKIE]);
    const privateOverrides = session?.accountId === profileMatch[1] && saved?.accountId === profileMatch[1]
      ? saved.overrides
      : null;
    sendJson(response, 200, {
      accountId: String(player.accountId),
      overrides: privateOverrides ?? profileDefaults[String(player.accountId)] ?? {},
    });
    return;
  }

  if (request.method === "POST" && route === "/api/profile") {
    const session = readToken(cookies[SESSION_COOKIE]);
    if (!session || !trackedPlayer(session.accountId)) {
      sendJson(response, 401, { error: "Authentication required" });
      return;
    }
    try {
      const input = await readJson(request);
      const matches = Number(input.matches);
      const firstMatchAt = String(input.firstMatchAt ?? "");
      const showcase = Array.isArray(input.showcase) ? input.showcase.map(String) : ["mmr", "wins"];
      const allowedShowcase = new Set(["mmr", "wins", "matches", "firstMatch"]);
      if (!Number.isInteger(matches) || matches < 0 || matches > 1_000_000 || !/^\d{4}-\d{2}-\d{2}$/.test(firstMatchAt)) {
        sendJson(response, 400, { error: "Invalid profile fields" });
        return;
      }
      if (showcase.length !== 2 || showcase.some((stat) => !allowedShowcase.has(stat))) {
        sendJson(response, 400, { error: "Invalid showcase stats" });
        return;
      }
      const overrides = { matches, firstMatchAt, showcase };
      const saved = makeToken({ accountId: session.accountId, overrides, exp: Date.now() + 365 * 24 * 60 * 60_000 });
      sendJson(response, 200, { accountId: session.accountId, overrides }, [cookie(PROFILE_COOKIE, saved, 365 * 24 * 60 * 60)]);
    } catch {
      sendJson(response, 400, { error: "Invalid request" });
    }
    return;
  }

  if (request.method === "POST" && route === "/auth/logout") {
    response.statusCode = 204;
    response.setHeader("Set-Cookie", clearCookie(SESSION_COOKIE));
    response.end();
    return;
  }

  sendJson(response, 404, { error: "Not found" });
}
