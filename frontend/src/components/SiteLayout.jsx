import { useEffect, useState } from "react";
import { Link, Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

function getStoredUser() {
  try {
    return JSON.parse(localStorage.getItem("resqnetUser"));
  } catch {
    return null;
  }
}

import DashboardSidebar from "./DashboardSidebar.jsx";

function SiteLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [user, setUser] = useState(getStoredUser);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState("");
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);

  useEffect(() => {
    setUser(getStoredUser());
    setIsMobileNavOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    let isMounted = true;
    async function validateSession() {
      const storedUser = getStoredUser();
      if (!storedUser) {
        return;
      }
      try {
        const response = await fetch("/api/me", {
          credentials: "same-origin",
        });
        if (!isMounted) return;
        if (response.ok) {
          const result = await response.json();
          localStorage.setItem("resqnetUser", JSON.stringify(result.user));
          setUser(result.user);
        } else if (response.status === 401) {
          localStorage.removeItem("resqnetUser");
          setUser(null);
          const isProtected =
            location.pathname.startsWith("/dashboard") ||
            location.pathname.startsWith("/report") ||
            location.pathname.startsWith("/responder");
          if (isProtected) {
            navigate("/login", {
              replace: true,
              state: { message: "Your session has expired. Please log in again." },
            });
          }
        }
      } catch {
        // Network or server unreachable on startup; do not clear prematurely
      }
    }
    validateSession();
    return () => {
      isMounted = false;
    };
  }, [location.pathname, navigate]);

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

  const isResponderRoute = location.pathname.startsWith("/responder");
  const isUserDashboardRoute =
    location.pathname === "/dashboard" || location.pathname === "/report";

  const showResponderSidebar =
    canAccessResponder && (isResponderRoute || isUserDashboardRoute);
  const showUserSidebar =
    Boolean(user && !canAccessResponder && isUserDashboardRoute);
  const showSidebar = showResponderSidebar || showUserSidebar;

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
            {!user && <NavLink to="/">Home</NavLink>}
            {canAccessResponder ? (
              <>
                <NavLink to="/responder">Dashboard</NavLink>
                <NavLink to="/responder/reports">Reports</NavLink>
                <NavLink to="/responder/intelligence">Intelligence</NavLink>
              </>
            ) : (
              <>
                <NavLink to="/report">Report Emergency</NavLink>
                <NavLink to="/dashboard">My Dashboard</NavLink>
              </>
            )}
          </nav>

          {user ? (
            <button
              className="button button-outline header-login"
              type="button"
              onClick={handleLogout}
              disabled={isLoggingOut}
            >
              {isLoggingOut
                ? "Logging out..."
                : canAccessResponder
                  ? "Logout"
                  : "Log out"}
            </button>
          ) : (
            <Link className="button button-outline header-login" to="/login">
              Login
            </Link>
          )}
        </div>
      </header>

      {logoutError && <p className="content-width form-message error" role="alert">{logoutError}</p>}
      {location.pathname === "/" && user ? (
        <Navigate
          to={canAccessResponder ? "/responder" : "/dashboard"}
          replace
        />
      ) : showSidebar ? (
        <div className="dashboard-shell">
          <DashboardSidebar
            role={canAccessResponder ? "responder" : "user"}
            user={user}
            mobileOpen={isMobileNavOpen}
            onToggleMobile={() => setIsMobileNavOpen((open) => !open)}
            onClose={() => setIsMobileNavOpen(false)}
          />
          <div className="dashboard-main-area">
            <Outlet />
          </div>
        </div>
      ) : (
        <Outlet />
      )}

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
