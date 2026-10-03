import {
  Navigate,
  Outlet,
  useLocation,
} from "react-router-dom";

import { LoadingState } from "../components/ui";
import { useAuth } from "./AuthContext";


/** Signed-in users only; others go to /login and come back after. */
export function RequireAuth() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return (
      <div className="full-page-center">
        <LoadingState label="Signing you in…" />
      </div>
    );
  }

  if (status !== "authenticated") {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <Outlet />;
}


/** Admins only (inside RequireAuth). */
export function RequireAdmin() {
  const { isAdmin } = useAuth();

  return isAdmin ? <Outlet /> : <Navigate to="/" replace />;
}


/** Login/register pages: signed-in users skip straight to the app. */
export function GuestOnly() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return null;
  }

  if (status === "authenticated") {
    const from = location.state?.from?.pathname ?? "/";

    return <Navigate to={from} replace />;
  }

  return <Outlet />;
}
