import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

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
  const [user] = useState(getLoggedInUser);
  const [reports, setReports] = useState([]);
  const [loadState, setLoadState] = useState(user ? "loading" : "logged-out");
  const [errorMessage, setErrorMessage] = useState("");

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
          <h1>Welcome to your dashboard</h1>
          <p>View the status and details of reports you have submitted.</p>
        </div>
        <Link className="button button-primary" to="/report">
          Report Emergency
        </Link>
      </section>

      <section className="dashboard-section">
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
                {report.reported_emergency_type && (
                  <p><strong>Selected Emergency Type:</strong> {report.reported_emergency_type}</p>
                )}
                <p><strong>Emergency Type:</strong> {report.emergency_type}</p>
                <p><strong>Description:</strong> {report.description}</p>
                <p><strong>Date/time:</strong> {new Date(report.created_at).toLocaleString()}</p>
                <p>
                  <strong>
                    {report.priority_source === "ml"
                      ? "Priority (ML Prediction):"
                      : "Priority (existing/default value):"}
                  </strong>{" "}
                  {report.priority}
                </p>
                <p><strong>Status:</strong> {report.status}</p>
                <p>
                  <strong>Location shared:</strong>{" "}
                  {report.location_shared ? "Yes" : "No"}
                </p>
                <p>
                  <strong>Evidence photo:</strong>{" "}
                  {report.image_attached ? "Attached" : "No image attached"}
                </p>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

export default Dashboard;
