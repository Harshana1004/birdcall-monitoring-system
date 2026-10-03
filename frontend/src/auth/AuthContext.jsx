import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import * as authApi from "../api/authApi";
import {
  AUTH_EXPIRED_EVENT,
  clearStoredToken,
  getStoredToken,
  setStoredToken,
} from "../api/client";


const AuthContext = createContext(null);


export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);

  // "loading" while a stored token is being checked, then
  // "authenticated" or "anonymous".
  const [status, setStatus] = useState(
    getStoredToken() ? "loading" : "anonymous"
  );


  useEffect(() => {
    if (!getStoredToken()) {
      return;
    }

    let cancelled = false;

    authApi
      .getMe()
      .then((me) => {
        if (!cancelled) {
          setUser(me);
          setStatus("authenticated");
        }
      })
      .catch(() => {
        if (!cancelled) {
          clearStoredToken();
          setUser(null);
          setStatus("anonymous");
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);


  useEffect(() => {
    function handleExpired() {
      setUser(null);
      setStatus("anonymous");
    }

    window.addEventListener(AUTH_EXPIRED_EVENT, handleExpired);

    return () =>
      window.removeEventListener(AUTH_EXPIRED_EVENT, handleExpired);
  }, []);


  const acceptSession = useCallback((session) => {
    setStoredToken(session.access_token);
    setUser(session.user);
    setStatus("authenticated");

    return session.user;
  }, []);


  const login = useCallback(
    async (credentials) => acceptSession(await authApi.login(credentials)),
    [acceptSession]
  );


  const register = useCallback(
    async (details) => acceptSession(await authApi.register(details)),
    [acceptSession]
  );


  const logout = useCallback(() => {
    clearStoredToken();
    setUser(null);
    setStatus("anonymous");
  }, []);


  const value = useMemo(
    () => ({
      user,
      status,
      isAdmin: Boolean(user?.is_admin),
      login,
      register,
      logout,
      setUser,
    }),
    [user, status, login, register, logout]
  );


  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}


export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth must be used inside <AuthProvider>.");
  }

  return context;
}
