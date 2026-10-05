import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

function Login() {
  const location = useLocation();
  const navigate = useNavigate();
  const [message, setMessage] = useState(location.state?.message || "");
  const [messageType, setMessageType] = useState(location.state?.message ? "success" : "");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setMessage("");
    setIsSubmitting(true);

    const formData = new FormData(event.currentTarget);
    const email = formData.get("email").trim();
    const password = formData.get("password");

    try {
      const response = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ email, password }),
      });
      const result = await response.json();

      if (!response.ok) {
        setMessageType("error");
        setMessage(result.message || "Login failed. Please check your credentials.");
        return;
      }

      const user = {
        id: result.user.id,
        name: result.user.name,
        email: result.user.email,
        role: result.user.role,
      };
      localStorage.setItem("resqnetUser", JSON.stringify(user));
      navigate("/dashboard");
    } catch {
      setMessageType("error");
      setMessage("Unable to connect to ResQNet. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-page content-width">
      <section className="form-card auth-card">
        <span className="eyebrow">Welcome back</span>
        <h1>Login to ResQNet</h1>
        <p className="form-intro">
          Sign in to view your emergency reports and updates.
        </p>
        <form onSubmit={handleSubmit}>
          <label className="field">
            <span>Email</span>
            <input type="email" name="email" placeholder="you@example.com" autoComplete="email" required />
          </label>
          <label className="field">
            <span>Password</span>
            <div style={{ position: "relative" }}>
              <input
                type={showPassword ? "text" : "password"}
                name="password"
                placeholder="Enter your password"
                autoComplete="current-password"
                style={{ paddingRight: 42 }}
                required
              />
              <button
                type="button"
                aria-label={showPassword ? "Hide password" : "Show password"}
                aria-pressed={showPassword}
                onClick={() => setShowPassword((visible) => !visible)}
                style={{
                  position: "absolute",
                  top: "50%",
                  right: 10,
                  transform: "translateY(-50%)",
                  border: 0,
                  padding: 4,
                  background: "transparent",
                  color: "inherit",
                  cursor: "pointer",
                }}
              >
                <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
                  <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z" fill="none" stroke="currentColor" strokeWidth="2" />
                  <circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" strokeWidth="2" />
                  {showPassword && <path d="m4 4 16 16" stroke="currentColor" strokeWidth="2" />}
                </svg>
              </button>
            </div>
          </label>
          {message && (
            <p className={`form-message ${messageType}`} role="alert">
              {message}
            </p>
          )}
          <button className="button button-primary button-full" type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Logging in..." : "Login"}
          </button>
        </form>
        <p className="form-switch">
          Don&apos;t have an account? <Link to="/register">Create Account</Link>
        </p>
      </section>
    </main>
  );
}

export default Login;
