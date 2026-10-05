import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

function getStoredUser() {
  try {
    return JSON.parse(localStorage.getItem("resqnetUser"));
  } catch {
    return null;
  }
}

function SiteLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [user, setUser] = useState(getStoredUser);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState("");

  useEffect(() => {
    setUser(getStoredUser());
  }, [location.pathname]);

  const canAccessResponder =
    user?.role === "responder" || user?.role === "admin";

  async function handleLogout() {
    setIsLoggingOut(true);
    setLogoutError("");
    try {
      const response = await fetch("/api/logout", {
        method: "POST",
        credentials: "same-origin",
      });
      if (!response.ok) {
        throw new Error("Logout request failed");
      }
      localStorage.removeItem("resqnetUser");
      setUser(null);
      navigate("/");
    } catch {
      setLogoutError("Unable to log out. Please try again.");
    } finally {
      setIsLoggingOut(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="site-header">
        <div className="header-inner">
          <Link className="brand" to="/" aria-label="ResQNet home">
            <span className="brand-mark" aria-hidden="true">
              R
            </span>
            <span>ResQNet</span>
          </Link>

          <nav className="main-nav" aria-label="Main navigation">
            <NavLink to="/">Home</NavLink>
            <NavLink to="/report">Report Emergency</NavLink>
            <NavLink to="/dashboard">My Dashboard</NavLink>
            {canAccessResponder && <NavLink to="/responder">Responder</NavLink>}
          </nav>

          {user ? (
            <button
              className="button button-outline header-login"
              type="button"
              onClick={handleLogout}
              disabled={isLoggingOut}
            >
              {isLoggingOut ? "Logging out..." : "Log out"}
            </button>
          ) : (
            <Link className="button button-outline header-login" to="/login">
              Login
            </Link>
          )}
        </div>
      </header>

      {logoutError && <p className="content-width form-message error" role="alert">{logoutError}</p>}
      <Outlet />

      <footer className="site-footer">
        <div className="content-width footer-inner">
          <span>ResQNet</span>
          <span>Academic prototype · Not connected to emergency services</span>
        </div>
      </footer>
    </div>
  );
}

export default SiteLayout;
