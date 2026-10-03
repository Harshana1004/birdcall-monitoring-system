import { useState } from "react";

import {
  Link,
  useLocation,
  useNavigate,
} from "react-router-dom";

import { errorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import Logo from "../components/Logo";
import { Alert } from "../components/ui";


function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);


  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      await login({ email: email.trim(), password });
      navigate(location.state?.from?.pathname ?? "/", { replace: true });
    } catch (requestError) {
      setError(errorMessage(requestError, "Could not sign in."));
      setIsSubmitting(false);
    }
  }


  return (
    <main className="auth-page">
      <div className="auth-card">
        <div className="auth-brand">
          <Logo size={56} />
          <div>
            <h1>
              Avian<span className="brand-accent">Acoustics</span>
            </h1>
            <p>Sign in to see what your devices are hearing.</p>
          </div>
        </div>

        <form className="form" onSubmit={handleSubmit}>
          <Alert>{error}</Alert>

          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              className="input"
              type="email"
              autoComplete="email"
              required
              autoFocus
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              className="input"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>

          <button
            type="submit"
            className="button button-primary"
            disabled={isSubmitting}
          >
            {isSubmitting ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="auth-footer">
          New here? <Link to="/register" state={location.state}>Create an account</Link>
        </p>
      </div>
    </main>
  );
}


export default LoginPage;
