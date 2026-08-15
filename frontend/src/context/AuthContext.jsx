import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { apiRequest, ApiError } from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState({ status: "checking", user: null, accessToken: null });
  const accessTokenRef = useRef(null);
  const refreshPromiseRef = useRef(null);

  useEffect(() => {
    accessTokenRef.current = auth.accessToken;
  }, [auth.accessToken]);

  const completeSession = useCallback(async (accessToken, userFromResponse = null) => {
    const user = userFromResponse || (await apiRequest("/auth/me", { accessToken })).user;
    accessTokenRef.current = accessToken;
    setAuth({ status: "authenticated", user, accessToken });
    return user;
  }, []);

  const refresh = useCallback(async () => {
    if (refreshPromiseRef.current) return refreshPromiseRef.current;
    refreshPromiseRef.current = (async () => {
      try {
        const session = await apiRequest("/auth/refresh", { method: "POST", csrf: true });
        if (!session?.access_token) throw new ApiError("Your session has ended. Please sign in again.", { status: 401 });
        await completeSession(session.access_token);
        return session.access_token;
      } catch (error) {
        accessTokenRef.current = null;
        setAuth({ status: "anonymous", user: null, accessToken: null });
        throw error;
      } finally {
        refreshPromiseRef.current = null;
      }
    })();
    return refreshPromiseRef.current;
  }, [completeSession]);

  useEffect(() => {
    refresh().catch(() => {
      // An absent refresh cookie simply means this is a new browser session.
    });
  }, [refresh]);

  const request = useCallback(
    async (path, options = {}) => {
      const attempt = (token) => apiRequest(path, { ...options, accessToken: token || undefined });
      try {
        return await attempt(accessTokenRef.current);
      } catch (error) {
        if (error?.status === 401 && !options.skipRefresh) {
          const token = await refresh();
          return attempt(token);
        }
        throw error;
      }
    },
    [refresh]
  );

  const login = useCallback(
    async ({ email, password }) => {
      const response = await apiRequest("/auth/login", { method: "POST", body: { email, password } });
      if (!response?.access_token) throw new ApiError("We could not sign you in. Please try again.");
      await completeSession(response.access_token, response.user);
      return response.user;
    },
    [completeSession]
  );

  const logout = useCallback(async () => {
    try {
      await apiRequest("/auth/logout", { method: "POST", csrf: true });
    } finally {
      accessTokenRef.current = null;
      setAuth({ status: "anonymous", user: null, accessToken: null });
    }
  }, []);

  const value = {
    ...auth,
    request,
    login,
    logout,
    refresh
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider.");
  return context;
}
