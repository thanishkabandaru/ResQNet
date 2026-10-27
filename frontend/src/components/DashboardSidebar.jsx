import { useEffect } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import "./DashboardSidebar.css";

const USER_NAV_ITEMS = [
  {
    key: "dashboard",
    label: "Dashboard",
    to: "/dashboard",
    hash: "",
    icon: (
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <rect width="7" height="9" x="3" y="3" rx="1" />
        <rect width="7" height="5" x="14" y="3" rx="1" />
        <rect width="7" height="9" x="14" y="12" rx="1" />
        <rect width="7" height="5" x="3" y="16" rx="1" />
      </svg>
    ),
    isActive: (pathname, hash) =>
      pathname === "/dashboard" && hash !== "#my-reports",
  },
  {
    key: "report",
    label: "Report Emergency",
    to: "/report",
    hash: "",
    icon: (
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
        <line x1="12" y1="9" x2="12" y2="13" />
        <line x1="12" y1="17" x2="12.01" y2="17" />
      </svg>
    ),
    isActive: (pathname) => pathname === "/report",
  },
  {
    key: "my-reports",
    label: "My Reports",
    to: "/dashboard",
    hash: "#my-reports",
    icon: (
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="16" y1="13" x2="8" y2="13" />
        <line x1="16" y1="17" x2="8" y2="17" />
        <polyline points="10 9 9 9 8 9" />
      </svg>
    ),
    isActive: (pathname, hash) =>
      pathname === "/dashboard" && hash === "#my-reports",
  },
];

const RESPONDER_NAV_ITEMS = [
  {
    key: "dashboard",
    label: "Dashboard",
    to: "/responder",
    hash: "",
    icon: (
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <rect width="7" height="9" x="3" y="3" rx="1" />
        <rect width="7" height="5" x="14" y="3" rx="1" />
        <rect width="7" height="9" x="14" y="12" rx="1" />
        <rect width="7" height="5" x="3" y="16" rx="1" />
      </svg>
    ),
    isActive: (pathname, hash) =>
      pathname === "/responder" && hash !== "#analytics",
  },
  {
    key: "reports",
    label: "Reports",
    to: "/responder/reports",
    hash: "",
    icon: (
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="16" y1="13" x2="8" y2="13" />
        <line x1="16" y1="17" x2="8" y2="17" />
        <polyline points="10 9 9 9 8 9" />
      </svg>
    ),
    isActive: (pathname, hash) =>
      pathname === "/responder/reports" &&
      hash !== "#department-routing" &&
      hash !== "#incident-map",
  },
  {
    key: "intelligence",
    label: "Incident Intelligence",
    to: "/responder/intelligence",
    hash: "",
    icon: (
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
        <circle cx="12" cy="12" r="3" />
      </svg>
    ),
    isActive: (pathname, hash) =>
      (pathname === "/responder/intelligence" ||
        pathname.startsWith("/responder/reports/")) &&
      hash !== "#incident-map",
  },
  {
    key: "incident-map",
    label: "Incident Map",
    to: "/responder/intelligence",
    hash: "#incident-map",
    icon: (
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6" />
        <line x1="8" y1="2" x2="8" y2="18" />
        <line x1="16" y1="6" x2="16" y2="22" />
      </svg>
    ),
    isActive: (_, hash) => hash === "#incident-map",
  },
  {
    key: "department-routing",
    label: "Department Routing",
    to: "/responder/reports",
    hash: "#department-routing",
    icon: (
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <circle cx="6" cy="19" r="3" />
        <path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15" />
        <polyline points="18 2 21 5 18 8" />
      </svg>
    ),
    isActive: (_, hash) => hash === "#department-routing",
  },
  {
    key: "analytics",
    label: "Analytics",
    to: "/responder",
    hash: "#analytics",
    icon: (
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <line x1="18" y1="20" x2="18" y2="10" />
        <line x1="12" y1="20" x2="12" y2="4" />
        <line x1="6" y1="20" x2="6" y2="14" />
      </svg>
    ),
    isActive: (pathname, hash) =>
      pathname === "/responder" && hash === "#analytics",
  },
];

function DashboardSidebar({
  role = "user",
  user = null,
  mobileOpen = false,
  onToggleMobile = () => {},
  onClose = () => {},
}) {
  const location = useLocation();
  const navigate = useNavigate();

  const isResponder = role === "responder" || role === "admin";
  const items = isResponder ? RESPONDER_NAV_ITEMS : USER_NAV_ITEMS;

  const displayName =
    (user?.name && user.name.trim()) ||
    user?.email ||
    (user?.id ? `User #${user.id}` : isResponder ? "Responder" : "User");

  // Determine current active item for mobile bar title
  const activeItem = items.find((item) =>
    item.isActive(location.pathname, location.hash),
  );
  const activeLabel = activeItem ? activeItem.label : "Navigation";

  // Close mobile drawer on Escape key
  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === "Escape" && mobileOpen) {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [mobileOpen, onClose]);

  function handleItemClick(item, event) {
    onClose();

    if (item.hash) {
      // If already on the target page:
      if (location.pathname === item.to) {
        event.preventDefault();
        if (location.hash === item.hash) {
          const targetId = item.hash.slice(1);
          const el = document.getElementById(targetId);
          if (el) {
            el.scrollIntoView({ behavior: "smooth", block: "start" });
          }
        } else {
          navigate(`${item.to}${item.hash}`);
        }
      }
    } else {
      // Plain page link (no hash)
      if (location.pathname === item.to && !location.hash) {
        event.preventDefault();
        window.scrollTo({ top: 0, behavior: "smooth" });
      }
    }
  }

  return (
    <>
      {/* Mobile top navigation bar */}
      <div className="dashboard-mobile-bar" aria-label="Dashboard mobile toolbar">
        <button
          type="button"
          className="mobile-nav-toggle"
          onClick={onToggleMobile}
          aria-label="Toggle navigation menu"
          aria-expanded={mobileOpen}
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
          <span>Dashboard Menu</span>
        </button>
        <div className="mobile-active-label">
          <span className="mobile-active-dot" aria-hidden="true" />
          <span>{activeLabel}</span>
        </div>
      </div>

      {/* Backdrop for mobile drawer */}
      {mobileOpen && (
        <div
          className="sidebar-backdrop"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Left Sidebar */}
      <aside
        className={`dashboard-sidebar ${mobileOpen ? "is-open" : ""}`}
        aria-label={isResponder ? "Responder navigation" : "User navigation"}
      >
        <div className="sidebar-content-wrap">
          <div className="sidebar-header">
            <div className="sidebar-portal-badge">
              <span className="sidebar-portal-indicator" aria-hidden="true" />
              <span className="sidebar-portal-text">
                {isResponder ? "Responder Portal" : "User Portal"}
              </span>
            </div>
            <button
              type="button"
              className="sidebar-close-button"
              onClick={onClose}
              aria-label="Close navigation menu"
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>

          <nav className="sidebar-nav-container">
            <ul className="sidebar-nav">
              {items.map((item) => {
                const active = item.isActive(
                  location.pathname,
                  location.hash,
                );
                return (
                  <li className="sidebar-nav-item" key={item.key}>
                    <Link
                      to={`${item.to}${item.hash}`}
                      className={`sidebar-nav-link ${active ? "is-active" : ""}`}
                      onClick={(e) => handleItemClick(item, e)}
                      aria-current={active ? "page" : undefined}
                    >
                      <span className="sidebar-nav-icon">{item.icon}</span>
                      <span className="sidebar-nav-label">{item.label}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>
        </div>

        <div className="sidebar-footer">
          <div className="sidebar-user-card">
            <div className="sidebar-user-avatar" aria-hidden="true">
              {(displayName[0] || "U").toUpperCase()}
            </div>
            <div className="sidebar-user-info">
              <strong className="sidebar-user-name" title={displayName}>
                {displayName}
              </strong>
              <span className="sidebar-user-role">
                {isResponder ? "Responder" : "Citizen User"}
              </span>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}

export default DashboardSidebar;
