import { useEffect, useState } from "react";

export type AuthUser = {
  authenticated: true;
  accountId: string;
  name: string;
  avatar: string | null;
};

type AuthState = {
  authUser: AuthUser | null;
  resolved: boolean;
};

let cachedAuthUser: AuthUser | null | undefined;
let authRequest: Promise<AuthUser | null> | null = null;

function fetchAuthUser() {
  if (!authRequest) {
    authRequest = fetch("/api/auth/me")
      .then(async (response) => response.ok ? response.json() : null)
      .then((payload) => payload?.authenticated ? payload as AuthUser : null)
      .catch(() => null)
      .then((user) => {
        cachedAuthUser = user;
        return user;
      });
  }
  return authRequest;
}

export function useAuthUser(): AuthState {
  const [state, setState] = useState<AuthState>({
    authUser: cachedAuthUser ?? null,
    resolved: cachedAuthUser !== undefined,
  });

  useEffect(() => {
    let disposed = false;
    fetchAuthUser().then((authUser) => {
      if (!disposed) setState({ authUser, resolved: true });
    });
    return () => {
      disposed = true;
    };
  }, []);

  return state;
}
