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


const MIN_PASSWORD_LENGTH = 8;


function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);


  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);

    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Use at least ${MIN_PASSWORD_LENGTH} characters for your password.`);
      return;
    }

    if (password !== confirm) {
      setError("The passwords do not match.");
      return;
    }

    setIsSubmitting(true);

    try {
      await register({
        email: email.trim(),
        password,
        displayName: displayName.trim(),
      });
      navigate(location.state?.from?.pathname ?? "/devices", { replace: true });
    } catch (requestError) {
      setError(errorMessage(requestError, "Could not create the account."));
      setIsSubmitting(false);
    }
  }


  return (
    <main className="auth-page">
      <div className="auth-card">
        <div className="auth-brand">
          <Logo size={56} />
          <div>
            <h1>Create your account</h1>
            <p>Then add your monitoring device with its claim code.</p>
          </div>
        </div>

        <form className="form" onSubmit={handleSubmit}>
          <Alert>{error}</Alert>

          <div className="field">
            <label htmlFor="name">Name (optional)</label>
            <input
              id="name"
              className="input"
              autoComplete="name"
              maxLength={120}
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              className="input"
              type="email"
              autoComplete="email"
              required
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
              autoComplete="new-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <span className="field-hint">At least {MIN_PASSWORD_LENGTH} characters.</span>
          </div>

          <div className="field">
            <label htmlFor="confirm">Confirm password</label>
            <input
              id="confirm"
              className="input"
              type="password"
              autoComplete="new-password"
              required
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
            />
          </div>

          <button
            type="submit"
            className="button button-primary"
            disabled={isSubmitting}
          >
            {isSubmitting ? "Creating account…" : "Create account"}
          </button>
        </form>

        <p className="auth-footer">
          Already have an account? <Link to="/login" state={location.state}>Sign in</Link>
        </p>
      </div>
    </main>
  );
}


export default RegisterPage;
