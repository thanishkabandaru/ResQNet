import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

function Register() {
  const navigate = useNavigate();
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setMessage("");

    const formData = new FormData(event.currentTarget);
    const name = formData.get("name").trim();
    const email = formData.get("email").trim();
    const password = formData.get("password");
    const confirmPassword = formData.get("confirmPassword");

    if (password !== confirmPassword) {
      setMessageType("error");
      setMessage("Passwords do not match.");
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await fetch("/api/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ name, email, password }),
      });
      const result = await response.json();

      if (!response.ok) {
        setMessageType("error");
        setMessage(result.message || "Registration failed. Please try again.");
        return;
      }

      navigate("/login", {
        state: { message: result.message || "Registration successful. Please log in." },
      });
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
        <span className="eyebrow">Get started</span>
        <h1>Create your account</h1>
        <p className="form-intro">
          Create a ResQNet account to keep track of your reports.
        </p>
        <form onSubmit={handleSubmit}>
          <label className="field">
            <span>Name</span>
            <input type="text" name="name" placeholder="Your name" autoComplete="name" required />
          </label>
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
                placeholder="Create a password"
                autoComplete="new-password"
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
          <label className="field">
            <span>Confirm Password</span>
            <div style={{ position: "relative" }}>
              <input
                type={showConfirmPassword ? "text" : "password"}
                name="confirmPassword"
                placeholder="Enter your password again"
                autoComplete="new-password"
                style={{ paddingRight: 42 }}
                required
              />
              <button
                type="button"
                aria-label={showConfirmPassword ? "Hide confirm password" : "Show confirm password"}
                aria-pressed={showConfirmPassword}
                onClick={() => setShowConfirmPassword((visible) => !visible)}
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
                  {showConfirmPassword && <path d="m4 4 16 16" stroke="currentColor" strokeWidth="2" />}
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
            {isSubmitting ? "Registering..." : "Register"}
          </button>
        </form>
        <p className="form-switch">
          Already have an account? <Link to="/login">Login</Link>
        </p>
      </section>
    </main>
  );
}

export default Register;
