import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import ReportMap from "../components/ReportMap.jsx";

function formatConfidence(confidence) {
  const value = toFiniteNumber(confidence);
  return value !== null && value >= 0 && value <= 1
    ? `${Math.round(value * 100)}%`
    : "Unavailable";
}

function toFiniteNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function formatReportDateTime(timestamp) {
  const utcTimestamp = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(timestamp)
    ? `${timestamp.replace(" ", "T")}Z`
    : timestamp;
  return new Date(utcTimestamp).toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
  });
}

function getLoggedInUser() {
  try {
    const user = JSON.parse(localStorage.getItem("resqnetUser"));
    if (user && Number.isInteger(user.id) && user.id > 0) {
      return user;
    }
  } catch {
    return null;
  }

  return null;
}

function Dashboard() {
  const navigate = useNavigate();
  const location = useLocation();
  const [user] = useState(getLoggedInUser);
  const [reports, setReports] = useState([]);
  const [loadState, setLoadState] = useState(user ? "loading" : "logged-out");
  const [errorMessage, setErrorMessage] = useState("");

  const userDisplayName =
    (user?.name && user.name.trim()) ||
    user?.email ||
    (user?.id ? `User #${user.id}` : "User");

  useEffect(() => {
    if (location.hash === "#my-reports") {
      const el = document.getElementById("my-reports");
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }
  }, [location.hash, loadState]);

  useEffect(() => {
    if (!user) {
      return undefined;
    }

    const controller = new AbortController();

    async function loadReports() {
      try {
        const response = await fetch(
          `/api/reports/user/${user.id}`,
          { signal: controller.signal, credentials: "same-origin" },
        );
        const result = await response.json();

        if (!response.ok) {
          if (response.status === 401) {
            localStorage.removeItem("resqnetUser");
            navigate("/login", {
              replace: true,
              state: { message: "Your session has expired. Please log in again." },
            });
            return;
          }
          setErrorMessage(result.message || "Unable to load your emergency reports.");
          setLoadState("error");
          return;
        }

        setReports(result.reports);
        setLoadState("loaded");
      } catch (error) {
        if (error.name !== "AbortError") {
          setErrorMessage("Unable to load your emergency reports. Please try again later.");
          setLoadState("error");
        }
      }
    }

    loadReports();
    return () => controller.abort();
  }, [user]);

  return (
    <main className="page-main content-width">
      <section className="dashboard-welcome">
        <div>
          <span className="eyebrow">User dashboard</span>
          <h1>Welcome, {userDisplayName}</h1>
          <p>Monitor your emergency reports and their current status.</p>
        </div>
        <Link className="button button-primary" to="/report">
          Report Emergency
        </Link>
      </section>

      <section id="my-reports" className="dashboard-section">
        <div className="section-title-row">
          <div>
            <h2>My Emergency Reports</h2>
            <p>View the status and details of reports you have submitted.</p>
          </div>
        </div>

        {loadState === "logged-out" && (
          <div className="empty-state">
            <h3>Please log in to view your reports</h3>
            <p>Your emergency reports are available after you log in.</p>
            <Link to="/login">Go to login <span aria-hidden="true">→</span></Link>
          </div>
        )}

        {loadState === "loading" && (
          <div className="empty-state">
            <p>Loading your emergency reports...</p>
          </div>
        )}

        {loadState === "error" && (
          <div className="empty-state" role="alert">
            <h3>Reports could not be loaded</h3>
            <p>{errorMessage}</p>
          </div>
        )}

        {loadState === "loaded" && reports.length === 0 && (
          <div className="empty-state">
            <span className="empty-icon" aria-hidden="true">—</span>
            <h3>No emergency reports yet</h3>
            <p>Reports you submit will appear here.</p>
            <Link to="/report">Create a report <span aria-hidden="true">→</span></Link>
          </div>
        )}

        {loadState === "loaded" && reports.length > 0 && (
          <div>
            {reports.map((report) => (
              <article className="form-card report-card" key={report.id}>
                <h3>Report #{report.id}</h3>
                <p><strong>Emergency Category:</strong> {report.emergency_type}</p>
                <p><strong>Category confidence:</strong> {formatConfidence(report.category_confidence)}</p>
                <p><strong>Description:</strong> {report.description}</p>
                <p><strong>Date/time:</strong> {formatReportDateTime(report.created_at)}</p>
                <p>
                  <strong>
                    {report.priority_source === "ml"
                      ? "Priority (ML Prediction):"
                      : "Priority (existing/default value):"}
                  </strong>{" "}
                  {report.priority}
                </p>
                <p><strong>Priority confidence:</strong> {formatConfidence(report.priority_confidence)}</p>
                <p><strong>Status:</strong> {report.status}</p>
                <p>
                  <strong>Location shared:</strong>{" "}
                  {report.location_shared ? "Yes" : "No"}
                </p>
                <h4>Emergency Location</h4>
                <ReportMap
                  latitude={toFiniteNumber(report.latitude)}
                  longitude={toFiniteNumber(report.longitude)}
                />
                <p>
                  <strong>Evidence photo:</strong>{" "}
                  {report.image_attached ? "Attached" : "No image attached"}
                </p>
                {report.image_attached && (
                  <img
                    className="responder-evidence-photo"
                    src={`/api/reports/user/${user.id}/${report.id}/image`}
                    alt={`Evidence photo for emergency report ${report.id}`}
                    loading="lazy"
                  />
                )}
                {report.video_attached && (
                  <>
                    <h4>Evidence video</h4>
                    <video
                      className="responder-evidence-photo"
                      src={`/api/reports/user/${user.id}/${report.id}/video`}
                      controls
                      preload="metadata"
                    >
                      Your browser does not support video playback.
                    </video>
                  </>
                )}
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

export default Dashboard;
