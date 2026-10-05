import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
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

function ResponderDashboard() {
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

  return <AuthorizedResponderDashboard user={user} />;
}

function AuthorizedResponderDashboard({ user }) {
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
      priorities: { High: 0, Medium: 0, Low: 0 },
      categories: {
        "Medical Emergency": 0,
        Accident: 0,
        Fire: 0,
        Other: 0,
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

  return (
    <main className="page-main content-width">
      <div className="page-heading">
        <span className="eyebrow">Responder workspace</span>
        <h1>Responder Dashboard</h1>
        <p>Incoming emergency reports are listed below.</p>
      </div>

      {loadState === "loaded" && (
        <section className="responder-analytics" aria-label="Report analytics">
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
          </div>
          <div className="analytics-breakdowns">
            <div className="analytics-breakdown">
              <h3>Priority</h3>
              <dl>
                {Object.entries(analytics.priorities).map(([priority, count]) => (
                  <div key={priority}>
                    <dt>{priority}</dt>
                    <dd>{count}</dd>
                  </div>
                ))}
              </dl>
            </div>
            <div className="analytics-breakdown">
              <h3>Emergency Categories</h3>
              <dl>
                {Object.entries(analytics.categories).map(([category, count]) => (
                  <div key={category}>
                    <dt>{category}</dt>
                    <dd>{count}</dd>
                  </div>
                ))}
              </dl>
            </div>
            <div className="analytics-breakdown">
              <h3>Status</h3>
              <dl>
                {Object.entries(analytics.statuses).map(([status, count]) => (
                  <div key={status}>
                    <dt>{status}</dt>
                    <dd>{count}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </div>
        </section>
      )}

      <section className="dashboard-section">
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
          <div>
            {reports.map((report) => (
              <article className="form-card report-card" key={report.id}>
                <h3>Report #{report.id}</h3>
                <p><strong>Reporter:</strong> {report.reporter_name}</p>
                {report.reported_emergency_type && (
                  <p><strong>User-selected type:</strong> {report.reported_emergency_type}</p>
                )}
                <p><strong>Emergency Type (ML Classification):</strong> {report.emergency_type}</p>
                <p><strong>Category confidence:</strong> {formatConfidence(report.category_confidence)}</p>
                <p><strong>Description:</strong> {report.description}</p>
                <h4>Evidence Photo</h4>
                {report.image_attached ? (
                  <img
                    className="responder-evidence-photo"
                    src={`/api/responder/reports/${report.id}/image`}
                    alt={`Evidence photo for emergency report ${report.id}`}
                    loading="lazy"
                  />
                ) : (
                  <p>No image attached</p>
                )}
                <p><strong>Date/time:</strong> {new Date(report.created_at).toLocaleString()}</p>
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
                  <strong>Location:</strong>{" "}
                  {hasValidLocation(report.latitude, report.longitude)
                    ? "Location available"
                    : "Location unavailable"}
                </p>
                <h4>Emergency Location</h4>
                {hasValidLocation(report.latitude, report.longitude) ? (
                  <>
                    <p>Reported location</p>
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
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

export default ResponderDashboard;
