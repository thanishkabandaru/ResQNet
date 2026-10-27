import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import ReportMap from "../components/ReportMap.jsx";

const ROUTING_DEPARTMENTS = [
  "Medical / Ambulance",
  "Fire & Rescue",
  "Police",
  "Road & Traffic",
  "Other Emergency Services",
];

const SIMULATED_DESTINATIONS = [
  { department: "Medical / Ambulance", name: "Simulated Medical Point 1", latitude: 17.385, longitude: 78.4867 },
  { department: "Medical / Ambulance", name: "Simulated Medical Point 2", latitude: 17.405, longitude: 78.4767 },
  { department: "Medical / Ambulance", name: "Simulated Medical Point 3", latitude: 17.365, longitude: 78.5067 },
  { department: "Fire & Rescue", name: "Simulated Fire & Rescue Point 1", latitude: 17.39, longitude: 78.4667 },
  { department: "Fire & Rescue", name: "Simulated Fire & Rescue Point 2", latitude: 17.415, longitude: 78.4967 },
  { department: "Fire & Rescue", name: "Simulated Fire & Rescue Point 3", latitude: 17.36, longitude: 78.4767 },
  { department: "Police", name: "Simulated Police Point 1", latitude: 17.375, longitude: 78.4967 },
  { department: "Police", name: "Simulated Police Point 2", latitude: 17.4, longitude: 78.5067 },
  { department: "Police", name: "Simulated Police Point 3", latitude: 17.355, longitude: 78.4667 },
  { department: "Road & Traffic", name: "Simulated Road & Traffic Point 1", latitude: 17.395, longitude: 78.4867 },
  { department: "Road & Traffic", name: "Simulated Road & Traffic Point 2", latitude: 17.37, longitude: 78.4667 },
  { department: "Road & Traffic", name: "Simulated Road & Traffic Point 3", latitude: 17.41, longitude: 78.4667 },
  { department: "Other Emergency Services", name: "Simulated Other Services Point 1", latitude: 17.38, longitude: 78.4567 },
  { department: "Other Emergency Services", name: "Simulated Other Services Point 2", latitude: 17.42, longitude: 78.4867 },
  { department: "Other Emergency Services", name: "Simulated Other Services Point 3", latitude: 17.35, longitude: 78.4967 },
];

function hasValidLocation(latitude, longitude) {
  return (
    Number.isFinite(latitude) &&
    Number.isFinite(longitude) &&
    latitude >= -90 &&
    latitude <= 90 &&
    longitude >= -180 &&
    longitude <= 180
  );
}

function formatConfidence(confidence) {
  return Number.isFinite(confidence) && confidence >= 0 && confidence <= 1
    ? `${Math.round(confidence * 100)}%`
    : "Unavailable";
}

function formatReportDateTime(timestamp) {
  const utcTimestamp = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(timestamp)
    ? `${timestamp.replace(" ", "T")}Z`
    : timestamp;
  const date = new Date(utcTimestamp);
  if (Number.isNaN(date.getTime())) {
    return "Unavailable";
  }

  const parts = new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
    timeZone: "Asia/Kolkata",
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  return `${values.day} ${values.month} ${values.year}, ${values.hour}:${values.minute} ${values.dayPeriod.toUpperCase()} IST`;
}

function distanceInKilometres(latitude, longitude, destination) {
  const radians = (degrees) => (degrees * Math.PI) / 180;
  const latitudeDifference = radians(destination.latitude - latitude);
  const longitudeDifference = radians(destination.longitude - longitude);
  const haversine =
    Math.sin(latitudeDifference / 2) ** 2 +
    Math.cos(radians(latitude)) *
      Math.cos(radians(destination.latitude)) *
      Math.sin(longitudeDifference / 2) ** 2;
  return 6371.0088 * 2 * Math.atan2(Math.sqrt(haversine), Math.sqrt(1 - haversine));
}

function statusBadgeClass(status) {
  return `responder-report-badge status-${status.toLowerCase().replaceAll(" ", "-")}`;
}

function BreakdownChart({ title, entries }) {
  const values = Object.entries(entries);
  const maximum = Math.max(...values.map(([, count]) => count), 1);
  return (
    <div className="analytics-breakdown">
      <h3>{title}</h3>
      <ul className="analytics-chart-list">
        {values.map(([label, count]) => (
          <li key={label} title={`${label}: ${count} reports`}>
            <span className="analytics-chart-label">{label}</span>
            <span className="analytics-chart-track" aria-hidden="true">
              <i style={{ width: `${count ? Math.max(3, count / maximum * 100) : 0}%` }} />
            </span>
            <strong>{count}</strong>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ResponderDashboard({ showReports = false }) {
  let user = null;
  try {
    user = JSON.parse(localStorage.getItem("resqnetUser"));
  } catch {
    user = null;
  }

  if (!user) {
    return (
      <main className="page-main content-width">
        <div className="empty-state">
          <h3>Please log in to access the responder dashboard.</h3>
          <Link className="button button-primary" to="/login">
            Go to login
          </Link>
        </div>
      </main>
    );
  }

  if (user.role !== "responder" && user.role !== "admin") {
    return (
      <main className="page-main content-width">
        <div className="empty-state">
          <h3>Access denied</h3>
          <p>This area is available only to authorized responders.</p>
          <Link to="/dashboard">Back to your dashboard</Link>
        </div>
      </main>
    );
  }

  return <AuthorizedResponderDashboard user={user} showReports={showReports} />;
}

function AuthorizedResponderDashboard({ user, showReports }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [reports, setReports] = useState([]);
  const [loadState, setLoadState] = useState("loading");
  const [updatingReportId, setUpdatingReportId] = useState(null);
  const [statusMessages, setStatusMessages] = useState({});
  const [selectedDepartments, setSelectedDepartments] = useState({});
  const [selectedDestinations, setSelectedDestinations] = useState({});
  const [routingReportId, setRoutingReportId] = useState(null);
  const [routingMessages, setRoutingMessages] = useState({});

  const analytics = reports.reduce(
    (counts, report) => {
      counts.totalReports += 1;
      if (report.status === "Resolved") {
        counts.resolvedReports += 1;
      } else {
        counts.activeReports += 1;
      }
      if (report.priority === "High") {
        counts.highPriorityReports += 1;
      }
      if (hasValidLocation(report.latitude, report.longitude)) {
        counts.reportsWithLocation += 1;
      }
      if (report.image_attached || report.video_attached) {
        counts.reportsWithEvidence += 1;
      }

      if (Object.hasOwn(counts.priorities, report.priority)) {
        counts.priorities[report.priority] += 1;
      }
      if (Object.hasOwn(counts.categories, report.emergency_type)) {
        counts.categories[report.emergency_type] += 1;
      }
      if (Object.hasOwn(counts.statuses, report.status)) {
        counts.statuses[report.status] += 1;
      }
      return counts;
    },
    {
      totalReports: 0,
      activeReports: 0,
      resolvedReports: 0,
      highPriorityReports: 0,
      reportsWithLocation: 0,
      reportsWithEvidence: 0,
      priorities: { High: 0, Medium: 0, Low: 0 },
      categories: {
        "Medical Emergency": 0,
        Accident: 0,
        Fire: 0,
        "Road Hazard": 0,
        Crime: 0,
        Theft: 0,
        "Missing Person": 0,
        "Natural Disaster": 0,
        "Building Collapse": 0,
        "Electrical Emergency": 0,
        "Gas Leak": 0,
        "Other Emergency": 0,
      },
      statuses: {
        Received: 0,
        Assigned: 0,
        "In Progress": 0,
        Resolved: 0,
      },
    },
  );

  useEffect(() => {
    const controller = new AbortController();

    async function loadReports() {
      try {
        const response = await fetch(
          `/api/responder/reports/${user.id}`,
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
          setLoadState("error");
          return;
        }

        setReports(result.reports);
        setSelectedDepartments(
          Object.fromEntries(
            result.reports
              .filter((report) => report.route_department)
              .map((report) => [report.id, report.route_department]),
          ),
        );
        setSelectedDestinations(
          Object.fromEntries(
            result.reports
              .filter((report) => report.route_destination)
              .map((report) => [report.id, report.route_destination]),
          ),
        );
        setLoadState("loaded");
      } catch (error) {
        if (error.name !== "AbortError") {
          setLoadState("error");
        }
      }
    }

    loadReports();
    return () => controller.abort();
  }, [user.id]);

  useEffect(() => {
    if (!location.hash) {
      return;
    }
    const targetId = location.hash.slice(1);
    if (!showReports && targetId === "analytics") {
      const el = document.getElementById("analytics");
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
      }
      return;
    }
    if (showReports && targetId === "department-routing") {
      const firstDetails = document.querySelector(".responder-report-details");
      if (firstDetails instanceof HTMLDetailsElement) {
        firstDetails.open = true;
      }
      setTimeout(() => {
        const el =
          document.getElementById("department-routing") ||
          document.querySelector(".department-routing");
        if (el) {
          el.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }, 50);
      return;
    }
    if (showReports) {
      const reportDetails = document.getElementById(targetId);
      if (reportDetails instanceof HTMLDetailsElement) {
        reportDetails.open = true;
        reportDetails.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }
  }, [location.hash, reports, showReports]);

  async function sendToSelectedLocation(report) {
    const department = selectedDepartments[report.id] || report.route_department;
    const destinationName =
      selectedDestinations[report.id] || report.route_destination;
    if (!department || !destinationName) {
      return;
    }

    setRoutingReportId(report.id);
    setRoutingMessages((messages) => ({ ...messages, [report.id]: "" }));
    try {
      const response = await fetch(
        `/api/responder/reports/${report.id}/routing`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({
            user_id: user.id,
            department,
            destination: destinationName,
          }),
        },
      );
      const result = await response.json();
      if (!response.ok) {
        setRoutingMessages((messages) => ({
          ...messages,
          [report.id]: result.message || "Unable to save prototype routing.",
        }));
        return;
      }

      setReports((currentReports) =>
        currentReports.map((currentReport) =>
          currentReport.id === report.id
            ? {
                ...currentReport,
                route_department: result.routing.department,
                route_destination: result.routing.destination,
                route_status: result.routing.status,
              }
            : currentReport,
        ),
      );
      setRoutingMessages((messages) => ({
        ...messages,
        [report.id]: "",
      }));
    } catch {
      setRoutingMessages((messages) => ({
        ...messages,
        [report.id]: "Unable to save prototype routing.",
      }));
    } finally {
      setRoutingReportId(null);
    }
  }

  async function updateReportStatus(report) {
    const requestedStatus = {
      Received: "Assigned",
      Assigned: "In Progress",
      "In Progress": "Resolved",
    }[report.status];

    if (!requestedStatus) {
      return;
    }

    setUpdatingReportId(report.id);
    setStatusMessages((currentMessages) => ({
      ...currentMessages,
      [report.id]: "",
    }));

    try {
      const response = await fetch(
        `/api/responder/reports/${report.id}/status`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({
            user_id: user.id,
            status: requestedStatus,
          }),
        },
      );
      const result = await response.json();

      if (!response.ok) {
        setStatusMessages((currentMessages) => ({
          ...currentMessages,
          [report.id]: "Unable to update report status.",
        }));
        return;
      }

      setReports((currentReports) =>
        currentReports.map((currentReport) =>
          currentReport.id === report.id
            ? { ...currentReport, status: result.report.status }
            : currentReport,
        ),
      );

      const successMessage = {
        Assigned: "Report assigned successfully.",
        "In Progress": "Response started.",
        Resolved: "Report marked as resolved.",
      }[result.report.status];
      setStatusMessages((currentMessages) => ({
        ...currentMessages,
        [report.id]: successMessage,
      }));
    } catch {
      setStatusMessages((currentMessages) => ({
        ...currentMessages,
        [report.id]: "Unable to update report status.",
      }));
    } finally {
      setUpdatingReportId(null);
    }
  }

  const responderDisplayName =
    (user?.name && user.name.trim()) || "Responder";

  return (
    <main className="page-main content-width">
      <div className="page-heading">
        <span className="eyebrow">Responder workspace</span>
        <h1>{showReports ? "Emergency Reports" : `Welcome, ${responderDisplayName}`}</h1>
        <p>
          {showReports
            ? "Review reports received from all users."
            : "Monitor active incidents, intelligence, locations, and response activity."}
        </p>
      </div>

      {!showReports && loadState === "loaded" && (
        <section id="analytics" className="responder-analytics" aria-label="Report analytics">
          <div className="analytics-summary">
            <div className="analytics-metric">
              <span>Total Reports</span>
              <strong>{analytics.totalReports}</strong>
            </div>
            <div className="analytics-metric">
              <span>Active Reports</span>
              <strong>{analytics.activeReports}</strong>
            </div>
            <div className="analytics-metric">
              <span>Resolved Reports</span>
              <strong>{analytics.resolvedReports}</strong>
            </div>
            <div className="analytics-metric">
              <span>High Priority Reports</span>
              <strong>{analytics.highPriorityReports}</strong>
            </div>
            <div className="analytics-metric">
              <span>Reports With Location</span>
              <strong>{analytics.reportsWithLocation}</strong>
            </div>
            <div className="analytics-metric">
              <span>Reports With Evidence</span>
              <strong>{analytics.reportsWithEvidence}</strong>
            </div>
          </div>
          <div className="analytics-breakdowns">
            <BreakdownChart title="Category Overview (12 Categories)" entries={analytics.categories} />
            <BreakdownChart title="Priority Overview" entries={analytics.priorities} />
            <BreakdownChart title="Status Overview" entries={analytics.statuses} />
          </div>

          <div className="dashboard-section recent-incidents-section" style={{ marginTop: "2rem" }}>
            <div className="section-title-row">
              <div>
                <h2>Recent Incidents</h2>
                <p>Click any incident to inspect report details, routing, and intelligence.</p>
              </div>
              <Link className="button button-outline" to="/responder/reports">
                View All Reports ({reports.length})
              </Link>
            </div>
            <div className="intelligence-table-wrap">
              <table className="intelligence-table">
                <thead>
                  <tr>
                    <th>Report #</th>
                    <th>Category</th>
                    <th>Priority</th>
                    <th>Location Availability</th>
                    <th>Status</th>
                    <th>Date / Time</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {reports.slice(0, 8).map((report) => (
                    <tr key={report.id}>
                      <td><strong>#{report.id}</strong></td>
                      <td>{report.emergency_type}</td>
                      <td>
                        <span className={`intelligence-priority-tag priority-${report.priority.toLowerCase()}`}>
                          {report.priority}
                        </span>
                      </td>
                      <td>
                        {hasValidLocation(report.latitude, report.longitude)
                          ? `Lat: ${Number(report.latitude).toFixed(3)}, Lon: ${Number(report.longitude).toFixed(3)}`
                          : "Not shared"}
                      </td>
                      <td>
                        <span className={statusBadgeClass(report.status)}>
                          {report.status}
                        </span>
                      </td>
                      <td>{formatReportDateTime(report.created_at)}</td>
                      <td>
                        <Link
                          className="button button-small button-outline"
                          to={`/responder/reports#report-${report.id}`}
                        >
                          View Details
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}

      {!showReports && loadState === "loading" && (
        <div className="empty-state">
          <p>Loading emergency reports...</p>
        </div>
      )}

      {!showReports && loadState === "error" && (
        <div className="empty-state" role="alert">
          <p>Unable to load emergency reports. Please try again.</p>
        </div>
      )}

      {showReports && (
        <section className="dashboard-section responder-reports-section">
          <div className="section-title-row">
            <div>
              <h2>Emergency Reports</h2>
              <p>Review incoming reports and their response status.</p>
            </div>
          </div>
          {loadState === "loading" && (
            <div className="empty-state">
              <p>Loading emergency reports...</p>
            </div>
          )}

          {loadState === "error" && (
            <div className="empty-state" role="alert">
              <p>Unable to load emergency reports. Please try again.</p>
            </div>
          )}

          {loadState === "loaded" && reports.length === 0 && (
            <div className="empty-state">
              <span className="empty-icon" aria-hidden="true">—</span>
              <h3>No Emergency Reports</h3>
              <p>New emergency reports will appear here when they are received.</p>
            </div>
          )}

          {loadState === "loaded" && reports.length > 0 && (
            <div className="responder-report-list">
              {reports.map((report) => (
              <article className="form-card responder-report-card" key={report.id}>
                <Link
                  className="button button-outline responder-intelligence-link"
                  to={`/responder/reports/${report.id}/intelligence`}
                >
                  Incident Intelligence
                </Link>
                <details
                  className="responder-report-details"
                  id={`report-${report.id}`}
                >
                  <summary className="responder-report-summary">
                    <div className="responder-report-summary-main">
                      <strong>#{report.id}</strong>
                      <span>{report.emergency_type}</span>
                      <span>{report.priority}</span>
                      <span className={statusBadgeClass(report.status)}>{report.status}</span>
                    </div>
                    <div className="responder-report-summary-meta">
                      <span>{report.reporter_name}</span>
                      <time>{formatReportDateTime(report.created_at)}</time>
                    </div>
                    <p className="responder-report-preview">{report.description}</p>
                  </summary>

                <section className="responder-report-section" aria-label="ML Analysis">
                  <h4>ML Summary</h4>
                  <dl className="responder-report-ml">
                    <div>
                      <dt>Emergency Category</dt>
                      <dd>{report.emergency_type}</dd>
                    </div>
                    <div>
                      <dt>Category Confidence</dt>
                      <dd>{formatConfidence(report.category_confidence)}</dd>
                    </div>
                    <div>
                      <dt>{report.priority_source === "ml" ? "ML Priority" : "Priority (existing/default)"}</dt>
                      <dd>{report.priority}</dd>
                    </div>
                    <div>
                      <dt>Priority Confidence</dt>
                      <dd>{formatConfidence(report.priority_confidence)}</dd>
                    </div>
                  </dl>
                </section>

                <section className="responder-report-section" aria-label="Incident Description">
                  <h4>Incident Description</h4>
                  <p className="responder-incident-description">{report.description}</p>
                </section>

                <section className="responder-report-section" aria-label="Evidence">
                  <h4>Evidence</h4>
                  {report.image_attached ? (
                    <img
                      className="responder-evidence-photo"
                      src={`/api/responder/reports/${report.id}/image`}
                      alt={`Evidence photo for emergency report ${report.id}`}
                      loading="lazy"
                    />
                  ) : (
                    <p>No photo attached</p>
                  )}
                  {report.video_attached && (
                    <video
                      className="responder-evidence-photo"
                      src={`/api/responder/reports/${report.id}/video`}
                      controls
                      preload="metadata"
                      aria-label={`Evidence video for emergency report ${report.id}`}
                    />
                  )}
                </section>

                <section className="responder-report-section" aria-label="Emergency Location">
                  <h4>Emergency Location</h4>
                  {hasValidLocation(report.latitude, report.longitude) ? (
                    <>
                      <ReportMap
                        latitude={report.latitude}
                        longitude={report.longitude}
                      />
                      <a
                        className="button button-outline"
                        href={`https://www.google.com/maps?q=${report.latitude},${report.longitude}`}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        Open in Google Maps
                      </a>
                    </>
                  ) : (
                    <p>Location unavailable</p>
                  )}
                </section>

                <section
                  id={report.id === reports[0]?.id ? "department-routing" : undefined}
                  className="responder-report-section"
                  aria-label="Department Routing"
                >
                  <h4>Department Routing</h4>
                  <div className="department-routing">
                  <label className="field">
                    <span>Department</span>
                    <select
                      value={
                        selectedDepartments[report.id] ||
                        report.route_department ||
                        ""
                      }
                      onChange={(event) =>
                        {
                          setSelectedDepartments((currentDepartments) => ({
                            ...currentDepartments,
                            [report.id]: event.target.value,
                          }));
                          setSelectedDestinations((currentDestinations) => ({
                            ...currentDestinations,
                            [report.id]: "",
                          }));
                        }
                      }
                    >
                      <option value="" disabled>
                        Select a department
                      </option>
                      {ROUTING_DEPARTMENTS.map((department) => (
                        <option key={department} value={department}>
                          {department}
                        </option>
                      ))}
                    </select>
                  </label>
                  <p>Prototype / Simulated locations — not real stations.</p>
                  {!hasValidLocation(report.latitude, report.longitude) ? (
                    <p>Nearby routing is unavailable because this report has no valid GPS location.</p>
                  ) : (
                    (selectedDepartments[report.id] || report.route_department) && (
                      <div role="radiogroup" aria-label="Select one simulated location">
                        {SIMULATED_DESTINATIONS
                          .filter(
                            (destination) =>
                              destination.department ===
                              (selectedDepartments[report.id] ||
                                report.route_department),
                          )
                          .map((destination) => ({
                            ...destination,
                            distance: distanceInKilometres(
                              report.latitude,
                              report.longitude,
                              destination,
                            ),
                          }))
                          .sort((first, second) => first.distance - second.distance)
                          .map((destination) => (
                            <label
                              key={destination.name}
                              style={{ display: "block", margin: "8px 0" }}
                            >
                              <input
                                type="radio"
                                name={`route-${report.id}`}
                                value={destination.name}
                                checked={
                                  (selectedDestinations[report.id] ||
                                    report.route_destination) ===
                                  destination.name
                                }
                                onChange={() =>
                                  setSelectedDestinations((currentDestinations) => ({
                                    ...currentDestinations,
                                    [report.id]: destination.name,
                                  }))
                                }
                              />{" "}
                              {destination.name} — {destination.distance.toFixed(2)} km
                            </label>
                          ))}
                      </div>
                    )
                  )}
                  <button
                    className="button button-outline"
                    type="button"
                    onClick={() => sendToSelectedLocation(report)}
                    disabled={
                      !hasValidLocation(report.latitude, report.longitude) ||
                      !(selectedDepartments[report.id] || report.route_department) ||
                      !(selectedDestinations[report.id] || report.route_destination) ||
                      routingReportId === report.id
                    }
                  >
                    {routingReportId === report.id
                      ? "Saving simulation..."
                      : "Send to Selected Location"}
                  </button>
                  <p>
                    Prototype Simulation only. No external service is contacted.
                  </p>
                  {report.route_status === "Sent" &&
                    report.route_department &&
                    report.route_destination && (
                      <p role="status">
                        Sent to {report.route_department} — {report.route_destination}
                      </p>
                    )}
                  {routingMessages[report.id] && (
                    <p role="alert">{routingMessages[report.id]}</p>
                  )}
                  </div>
                </section>

                <section className="responder-report-section responder-response-status" aria-label="Response Status">
                  <h4>Response Status</h4>
                  <p><strong>Current status:</strong> <span className={statusBadgeClass(report.status)}>{report.status}</span></p>
                  {report.status !== "Resolved" && (
                    <button
                      className="button button-primary"
                      type="button"
                      onClick={() => updateReportStatus(report)}
                      disabled={updatingReportId === report.id}
                    >
                      {updatingReportId === report.id
                        ? "Updating status..."
                        : {
                            Received: "Assign",
                            Assigned: "Start Response",
                            "In Progress": "Mark Resolved",
                          }[report.status]}
                    </button>
                  )}
                  {statusMessages[report.id] && (
                    <p role="status">{statusMessages[report.id]}</p>
                  )}
                </section>
                </details>
              </article>
              ))}
            </div>
          )}
        </section>
      )}
    </main>
  );
}

export default ResponderDashboard;
