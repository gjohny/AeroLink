
import { useState } from "react";
import { loginUser } from "../authApi";

export default function Login({ onSuccess, onNavigate }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      const data = await loginUser(email, password);
      onSuccess(data.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="auth-page">
      <div className="auth-card">
        <div className="auth-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none">
            <rect x="5" y="10" width="14" height="11" rx="2" />
            <path d="M8 10V7a4 4 0 0 1 8 0v3" />
            <path d="M12 14v3" />
          </svg>
        </div>

        <h1>Welcome Back</h1>
        <p className="auth-subtitle">
          Login to continue planning your next adventure.
        </p>

        <form onSubmit={handleSubmit}>
          <label htmlFor="login-email">Email Address</label>
          <div className="auth-input-wrap">
            <span className="auth-input-icon" aria-hidden="true">✉</span>
            <input
              id="login-email"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
            />
          </div>

          <label htmlFor="login-password">Password</label>
          <div className="auth-input-wrap">
            <span className="auth-input-icon" aria-hidden="true">♢</span>
            <input
              id="login-password"
              type="password"
              placeholder="Enter your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>

          {error && <p className="auth-error" role="alert">{error}</p>}

          <button className="auth-submit" type="submit" disabled={loading}>
            {loading ? "Logging in..." : "Login"}
          </button>
        </form>

        <p className="auth-footer">
          Don't have an account?{" "}
          <a
            href="/register"
            onClick={(event) => {
              event.preventDefault();
              onNavigate("/register");
            }}
          >
            Create Account
          </a>
        </p>
      </div>
    </section>
  );
}
