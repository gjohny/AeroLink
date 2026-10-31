
import { useState } from "react";
import { registerUser } from "../authApi";

export default function Register({ onSuccess, onNavigate }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    if (password.length < 12) {
      setError("Password must be at least 12 characters.");
      return;
    }

    setLoading(true);

    try {
      const data = await registerUser(name, email, password);
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
            <circle cx="10" cy="8" r="4" />
            <path d="M3 21v-2a7 7 0 0 1 14 0v2" />
            <path d="M19 8v6M16 11h6" />
          </svg>
        </div>

        <h1>Create Your Account</h1>
        <p className="auth-subtitle">
          Start your personalized travel experience.
        </p>

        <form onSubmit={handleSubmit}>
          <label htmlFor="register-name">Full Name</label>
          <div className="auth-input-wrap">
            <span className="auth-input-icon" aria-hidden="true">♙</span>
            <input
              id="register-name"
              type="text"
              placeholder="Enter your full name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="name"
              maxLength={100}
              required
            />
          </div>

          <label htmlFor="register-email">Email Address</label>
          <div className="auth-input-wrap">
            <span className="auth-input-icon" aria-hidden="true">✉</span>
            <input
              id="register-email"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              maxLength={255}
              required
            />
          </div>

          <label htmlFor="register-password">Password</label>
          <div className="auth-input-wrap">
            <span className="auth-input-icon" aria-hidden="true">♢</span>
            <input
              id="register-password"
              type="password"
              placeholder="At least 12 characters"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              minLength={12}
              required
            />
          </div>

          <label htmlFor="register-confirm">Confirm Password</label>
          <div className="auth-input-wrap">
            <span className="auth-input-icon" aria-hidden="true">♢</span>
            <input
              id="register-confirm"
              type="password"
              placeholder="Re-enter your password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              autoComplete="new-password"
              required
            />
          </div>

          {error && <p className="auth-error" role="alert">{error}</p>}

          <button className="auth-submit" type="submit" disabled={loading}>
            {loading ? "Creating account..." : "Create Account"}
          </button>
        </form>

        <p className="auth-footer">
          Already have an account?{" "}
          <a
            href="/login"
            onClick={(event) => {
              event.preventDefault();
              onNavigate("/login");
            }}
          >
            Login
          </a>
        </p>
      </div>
    </section>
  );
}
