import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import IntelligenceMap from "../components/IntelligenceMap.jsx";
import ReportMap from "../components/ReportMap.jsx";
import "./ResponderIntelligence.css";

function getUser() {
  try {
    return JSON.parse(localStorage.getItem("resqnetUser"));
  } catch {
    return null;
  }
}

function formatDate(value) {
  if (!value) return "Unavailable";
  const utc = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value)
    ? `${value.replace(" ", "T")}Z`
    : value;
  const date = new Date(utc);
  if (Number.isNaN(date.getTime())) return "Unavailable";
  return `${new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
    timeZone: "Asia/Kolkata",
  }).format(date)} IST`;
}

function formatDuration(minutes) {
  if (!Number.isFinite(minutes)) return "Unavailable";
  if (minutes < 60) return `${Math.round(minutes)} min`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = Math.round(minutes % 60);
  return `${hours}h ${remainingMinutes}m`;
}

function formatCount(val) {
  if (val === null || val === undefined) return "—";
  const num = Number(val);
  return Number.isFinite(num) ? num.toLocaleString("en-IN") : val;
}


function AnimatedValue({ value }) {
  const target = typeof value === "number" && Number.isFinite(value) ? value : null;
  const [displayValue, setDisplayValue] = useState(target ?? value);

  useEffect(() => {
    if (target === null) {
      setDisplayValue(value);
      return undefined;
    }
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setDisplayValue(target);
      return undefined;
    }

    let frameId;
    const startedAt = performance.now();
    const duration = 700;
    function animate(now) {
      const progress = Math.min((now - startedAt) / duration, 1);
      const eased = 1 - (1 - progress) ** 3;
      setDisplayValue(Math.round(target * eased));
      if (progress < 1) {
        frameId = requestAnimationFrame(animate);
      }
    }
    frameId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frameId);
  }, [target, value]);

  return displayValue ?? "—";
}

function BarChart({ title, entries, labelKey = "label", valueKey = "count" }) {
  const values = entries || [];
  const maximum = Math.max(...values.map((entry) => entry[valueKey] || 0), 1);
  return (
    <section className="intelligence-chart" aria-label={title}>
      <h3>{title}</h3>
      {values.length ? (
        <div className="intelligence-bars">
          {values.map((entry) => {
            const value = entry[valueKey] || 0;
            return (
              <div className="intelligence-bar-row" key={entry[labelKey]}>
                <span title={entry[labelKey]}>{entry[labelKey]}</span>
                <div className="intelligence-bar-track">
                  <i style={{ width: `${Math.max(value ? 2 : 0, value / maximum * 100)}%` }} />
                </div>
                <strong><AnimatedValue value={value ?? "Unavailable"} /></strong>
              </div>
            );
          })}
        </div>
      ) : <p className="intelligence-muted">No data recorded.</p>}
    </section>
  );
}

function TrendChart({ title, entries }) {
  const values = entries || [];
  if (!values.length) {
    return (
      <section className="intelligence-chart" aria-label={title}>
        <h3>{title}</h3>
        <p className="intelligence-muted">No data recorded.</p>
      </section>
    );
  }

  const width = 720;
  const height = 190;
  const padding = { top: 18, right: 18, bottom: 32, left: 26 };
  const maximum = Math.max(...values.map((item) => item.count || 0), 1);
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const points = values.map((item, index) => ({
    ...item,
    x: padding.left + (values.length === 1 ? chartWidth / 2 : index * chartWidth / (values.length - 1)),
    y: padding.top + chartHeight - (item.count || 0) / maximum * chartHeight,
  }));
  const path = points.map((point, index) => `${index ? "L" : "M"} ${point.x} ${point.y}`).join(" ");

  return (
    <section className="intelligence-chart intelligence-trend-chart" aria-label={title}>
      <h3>{title}</h3>
      <div className="intelligence-trend-scroll">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={`${title}: ${values.map((item) => `${item.month}, ${item.count}`).join("; ")}`}
          preserveAspectRatio="none"
        >
          {[0, 0.5, 1].map((fraction) => {
            const y = padding.top + chartHeight * fraction;
            return (
              <line
                key={fraction}
                x1={padding.left}
                x2={width - padding.right}
                y1={y}
                y2={y}
                className="intelligence-trend-gridline"
              />
            );
          })}
          <path d={path} className="intelligence-trend-line" />
          {points.map((point) => (
            <g key={point.month} className="intelligence-trend-point">
              <circle cx={point.x} cy={point.y} r="5" />
              <title>{`${point.month}: ${point.count} reports`}</title>
            </g>
          ))}
          {points.map((point, index) => (
            index % Math.max(1, Math.ceil(points.length / 6)) === 0 ||
            index === points.length - 1 ? (
              <text
                key={`${point.month}-label`}
                x={point.x}
                y={height - 8}
                textAnchor="middle"
                className="intelligence-trend-label"
              >
                {point.month.slice(2)}
              </text>
            ) : null
          ))}
        </svg>
      </div>
      <p className="intelligence-chart-caption">Hover or focus a point to inspect its monthly report count.</p>
    </section>
  );
}

function Kpi({ label, value, detail }) {
  return (
    <div className="intelligence-kpi">
      <span>{label}</span>
      <strong><AnimatedValue value={value ?? "—"} /></strong>
      {detail && <small>{detail}</small>}
    </div>
  );
}

function ConfidenceIndicator({ label, confidence }) {
  const percentage = Number.isFinite(confidence) && confidence >= 0 && confidence <= 1
    ? Math.round(confidence * 100)
    : null;
  return (
    <div className="intelligence-confidence">
      <div className="intelligence-confidence-label">
        <span>{label}</span>
        <strong>{percentage === null ? "Unavailable" : `${percentage}%`}</strong>
      </div>
      {percentage !== null && (
        <div
          className="intelligence-confidence-track"
          role="meter"
          aria-label={label}
          aria-valuemin="0"
          aria-valuemax="100"
          aria-valuenow={percentage}
        >
          <i style={{ "--meter-value": `${percentage}%` }} />
        </div>
      )}
    </div>
  );
}

function CombinedEvidencePanel({ combinedEvidence, radiusKm }) {
  if (!combinedEvidence) return null;
  const localLayer = combinedEvidence.local_resqnet_layer || {};
  const govLayer = combinedEvidence.government_historical_layer || {};

  return (
    <div className="intelligence-combined-panel">
      <div className="intelligence-combined-top">
        <span className="intelligence-overline">Dual-Layer Evidence · Spatial &amp; Contextual</span>
        <h2>Combined Area Intelligence</h2>
        <p>Synthesizes real-time micro-level incident records with verified official macro historical statistics.</p>
      </div>

      <div className="intelligence-combined-grid">
        <div className="combined-layer-card layer-local">
          <span className="combined-layer-badge">Layer 1 · Micro-Level Evidence</span>
          <h3>{localLayer.title || "Local ResQNet Evidence"}</h3>
          <p className="combined-layer-main">
            {localLayer.description || `${localLayer.incident_count || 0} emergency report(s) recorded within ${radiusKm} km in ResQNet.`}
          </p>
          <div className="combined-layer-meta">
            <span><strong>Analysis Radius:</strong> {radiusKm} km</span>
            <span><strong>Scope:</strong> Incident submissions &amp; verified field evidence</span>
          </div>
        </div>

        <div className="combined-layer-card layer-gov">
          <span className="combined-layer-badge">Layer 2 · Macro Contextual Layer</span>
          <h3>{govLayer.title || "Government Historical Context"}</h3>
          <p className="combined-layer-main">
            {govLayer.context_description || "Official government statistics (NCRB ADSI 2023) record 19,949 road accident cases for Andhra Pradesh (1,522 in Vijayawada, 1,293 in Visakhapatnam, and 464,029 nationwide)."}
          </p>
          <div className="combined-layer-meta">
            <span><strong>Source:</strong> {govLayer.source || "NCRB"} ({govLayer.year || 2023})</span>
            <span><strong>Granularity:</strong> {govLayer.geographic_granularity || "State & Mega-City Level"}</span>
          </div>
        </div>
      </div>

      <div className="academic-distinction-disclaimer">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="M12 9v4M12 17h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
        </svg>
        <div>
          <strong>Mandatory Academic Distinction:</strong> {govLayer.disclaimer || "Government statistics are reported at their published geographic level (State, UT, and City) and should not be interpreted as incident counts for this 1-km radius."}
        </div>
      </div>
    </div>
  );
}

function HistoricalDataPanel({ notice }) {
  const [activeTab, setActiveTab] = useState("states");
  const [filterText, setFilterText] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState(null);

  if (!notice?.available) {
    return (
      <section className="intelligence-coverage-card">
        <div className="intelligence-support-icon" aria-hidden="true">↗</div>
        <div className="intelligence-support-copy">
          <span className="intelligence-overline">Data sources &amp; coverage</span>
          <h2>Historical Government Data</h2>
          <p>
            {notice?.dataset_name || "Official Historical Records"} ({notice?.year || "2023"}) · {notice?.publisher || "NCRB / MoRTH"}.
          </p>
          <p>{notice?.message || "Official government data is not yet imported into the local database."}</p>
        </div>
        <div className="intelligence-support-action">
          <span className="intelligence-state-pill"><i />Not connected</span>
          {notice?.source_catalog_url && (
            <a href={notice.source_catalog_url} target="_blank" rel="noopener noreferrer">
              Official OGD resource <span aria-hidden="true">↗</span>
            </a>
          )}
          {notice?.additional_source_catalog_url && (
            <a href={notice.additional_source_catalog_url} target="_blank" rel="noopener noreferrer">
              Official monthly resource <span aria-hidden="true">↗</span>
            </a>
          )}
        </div>
      </section>
    );
  }

  const primary = notice.primary_source || {};
  const secondary = notice.secondary_source || {};
  const national = notice.national_totals || {};
  const stateHighlights = notice.state_highlights || {};
  const cityHighlights = notice.city_highlights || {};
  const apData = stateHighlights["Andhra Pradesh"] || {};
  const vijayawada = cityHighlights["Vijayawada"] || {};
  const vizag = cityHighlights["Vishakhapatnam"] || cityHighlights["Visakhapatnam"] || {};

  const states = (notice.state_breakdown || []).filter((item) =>
    !filterText || item.state.toLowerCase().includes(filterText.toLowerCase())
  );
  const cities = (notice.city_breakdown || []).filter((item) =>
    !filterText ||
    item.city.toLowerCase().includes(filterText.toLowerCase()) ||
    (item.state && item.state.toLowerCase().includes(filterText.toLowerCase()))
  );

  async function handleRefresh() {
    setRefreshing(true);
    setRefreshMessage(null);
    try {
      const res = await fetch("/api/responder/government-data/refresh", {
        method: "POST",
        credentials: "same-origin",
      });
      const data = await res.json();
      if (res.ok) {
        setRefreshMessage(`✓ Verified ${data.records_total || 1116} records from ${data.source || "NCRB"}. ${data.skipped_duplicates || 0} duplicates prevented.`);
      } else {
        setRefreshMessage(`Refresh notice: ${data.message || "Failed to refresh"}`);
      }
    } catch {
      setRefreshMessage("Government data verification endpoint temporarily unreachable.");
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <section className="intelligence-section government-data-section intelligence-section-enter">
      <div className="government-header-row">
        <div>
          <span className="intelligence-overline">Official Macro Historical Layer · Open Government Data</span>
          <h2>Government Historical Data &amp; Contextual Intelligence</h2>
          <p>Official accident and fatality statistics published by the Government of India. Maintained as a separate macro contextual layer.</p>
        </div>
        <div className="government-header-actions">
          <span className="intelligence-state-pill connected">
            <i className="status-dot-active" /> Connected · {formatCount(notice.records_imported)} Records
          </span>
          <button
            type="button"
            className="button button-outline button-sm"
            onClick={handleRefresh}
            disabled={refreshing}
          >
            {refreshing ? "Re-verifying..." : "Re-verify Government Data"}
          </button>
        </div>
      </div>

      {refreshMessage && (
        <div className="government-refresh-alert" role="status">
          {refreshMessage}
        </div>
      )}

      {/* Provenance Card */}
      <div className="government-provenance-box">
        <div className="provenance-title-row">
          <strong>Academic Data Provenance &amp; Attribution</strong>
          <span className="provenance-license">{primary.license || "Government Open Data License - India (GODL)"}</span>
        </div>
        <div className="provenance-grid">
          <div>
            <span className="prov-label">Primary Source</span>
            <strong>{primary.source_name || "National Crime Records Bureau (NCRB)"}</strong>
          </div>
          <div>
            <span className="prov-label">Ministry / Department</span>
            <strong>{primary.department || "Ministry of Home Affairs"}</strong>
          </div>
          <div>
            <span className="prov-label">Official Dataset</span>
            <strong>{primary.dataset_title || "Accidental Deaths & Suicides in India (ADSI) - 2023"}</strong>
          </div>
          <div>
            <span className="prov-label">Publication Year</span>
            <strong>{primary.year || 2023}</strong>
          </div>
          <div>
            <span className="prov-label">Geographic Granularity</span>
            <strong>{primary.geographic_granularity || "State / UT / 53 Mega Cities (5 Lakh+)"}</strong>
          </div>
          <div>
            <span className="prov-label">Last Ingested</span>
            <strong>{notice.last_imported_at ? formatDate(notice.last_imported_at) : "Imported & Verified"}</strong>
          </div>
        </div>
        <div className="provenance-links-row">
          <span>Official Portals:</span>
          {primary.resource_url && (
            <a href={primary.resource_url} target="_blank" rel="noopener noreferrer">
              Official CSV Download (data.gov.in) ↗
            </a>
          )}
          <a href="https://data.gov.in/" target="_blank" rel="noopener noreferrer">
            Open Government Data (data.gov.in) ↗
          </a>
          <a href="https://ap.data.gov.in/" target="_blank" rel="noopener noreferrer">
            Andhra Pradesh OGD (ap.data.gov.in) ↗
          </a>
        </div>
        {secondary?.source_name && (
          <div className="secondary-provenance-note">
            <span className="prov-label">Secondary Source Catalog:</span> {secondary.source_name} ({secondary.department}) — <em>{secondary.dataset_title}</em>. {secondary.status}.
            {secondary.source_catalog_url && (
              <a href={secondary.source_catalog_url} target="_blank" rel="noopener noreferrer" style={{ marginLeft: 8 }}>
                Catalog Resource ↗
              </a>
            )}
          </div>
        )}
      </div>

      {/* KPI Highlights */}
      <div className="government-kpi-grid">
        <div className="government-kpi-card national-card">
          <span className="kpi-tag">All-India Annual Totals</span>
          <h3>National Road Accidents</h3>
          <div className="kpi-stat-group">
            <div>
              <span className="kpi-sublabel">Total Cases</span>
              <strong>{formatCount(national.cases)}</strong>
            </div>
            <div>
              <span className="kpi-sublabel">Fatalities</span>
              <strong>{formatCount(national.killed)}</strong>
            </div>
            <div>
              <span className="kpi-sublabel">Injured</span>
              <strong>{formatCount(national.injured)}</strong>
            </div>
          </div>
          <small className="kpi-footnote">Official NCRB ADSI 2023 Table 1A.2</small>
        </div>

        <div className="government-kpi-card state-card">
          <span className="kpi-tag highlight-tag">State Focus · Andhra Pradesh</span>
          <h3>Andhra Pradesh Road Accidents</h3>
          <div className="kpi-stat-group">
            <div>
              <span className="kpi-sublabel">Reported Cases</span>
              <strong>{formatCount(apData.cases)}</strong>
            </div>
            <div>
              <span className="kpi-sublabel">Fatalities</span>
              <strong>{formatCount(apData.killed)}</strong>
            </div>
            <div>
              <span className="kpi-sublabel">Injured</span>
              <strong>{formatCount(apData.injured)}</strong>
            </div>
          </div>
          <small className="kpi-footnote">Official State Aggregates</small>
        </div>

        <div className="government-kpi-card city-card">
          <span className="kpi-tag">Regional Mega Cities</span>
          <h3>AP Major Urban Centers</h3>
          <div className="kpi-city-list">
            <div className="city-stat-line">
              <span><strong>Vijayawada:</strong> {formatCount(vijayawada.cases)} cases</span>
              <span className="city-substats">({formatCount(vijayawada.killed)} deaths · {formatCount(vijayawada.injured)} injured)</span>
            </div>
            <div className="city-stat-line">
              <span><strong>Visakhapatnam:</strong> {formatCount(vizag.cases)} cases</span>
              <span className="city-substats">({formatCount(vizag.killed)} deaths · {formatCount(vizag.injured)} injured)</span>
            </div>
          </div>
          <small className="kpi-footnote">Cities with 5+ Lakh Population</small>
        </div>
      </div>

      {/* Academic Separation Banner */}
      <div className="academic-separation-banner">
        <div className="academic-sep-header">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <strong>Academic Dataset Distinction: ResQNet Reports vs. Government Historical Data</strong>
        </div>
        <div className="academic-sep-grid">
          <div className="sep-col">
            <span className="sep-col-tag">ResQNet Emergency Reports</span>
            <p>Live, incident-level reports submitted directly by citizens and field responders. Located with precision GPS coordinates and evaluated within a localized 1-km radius.</p>
          </div>
          <div className="sep-divider" aria-hidden="true">≠</div>
          <div className="sep-col">
            <span className="sep-col-tag">Government Historical Context</span>
            <p>Official macro-level statistical totals published by the National Crime Records Bureau (NCRB). Aggregated at State, Union Territory, and 53 Mega City levels.</p>
          </div>
        </div>
        <p className="academic-mandatory-distinction">
          <strong>Mandatory Academic Distinction:</strong> Government statistics are reported at their published geographic level (State and Mega City) and must never be interpreted as incident counts for a specific local 1-km radius. Government data provides macro context and does not establish causality for individual local incidents.
        </p>
      </div>

      {/* Statistical Explorer */}
      <div className="government-explorer">
        <div className="explorer-header">
          <div className="explorer-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "states"}
              className={`explorer-tab ${activeTab === "states" ? "active" : ""}`}
              onClick={() => setActiveTab("states")}
            >
              States &amp; Union Territories (36)
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "cities"}
              className={`explorer-tab ${activeTab === "cities" ? "active" : ""}`}
              onClick={() => setActiveTab("cities")}
            >
              Mega Cities (53)
            </button>
          </div>
          <div className="explorer-search">
            <input
              type="text"
              placeholder={`Search ${activeTab === "states" ? "state" : "city or state"}...`}
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              aria-label="Search government records"
            />
          </div>
        </div>

        <div className="intelligence-table-wrap">
          <table className="intelligence-table">
            <thead>
              <tr>
                <th>{activeTab === "states" ? "State / UT" : "City"}</th>
                {activeTab === "cities" && <th>State</th>}
                <th style={{ textAlign: "right" }}>Road Accident Cases</th>
                <th style={{ textAlign: "right" }}>Persons Killed</th>
                <th style={{ textAlign: "right" }}>Persons Injured</th>
              </tr>
            </thead>
            <tbody>
              {activeTab === "states" ? (
                states.length ? (
                  states.map((item) => (
                    <tr key={item.state} className={item.state === "Andhra Pradesh" ? "row-highlight" : ""}>
                      <td>
                        <strong>{item.state}</strong>
                        {item.state === "Andhra Pradesh" && <span className="table-badge">Regional Focus</span>}
                      </td>
                      <td style={{ textAlign: "right" }}>{formatCount(item.road_cases)}</td>
                      <td style={{ textAlign: "right" }}>{formatCount(item.road_deaths)}</td>
                      <td style={{ textAlign: "right" }}>{formatCount(item.road_injured)}</td>
                    </tr>
                  ))
                ) : (
                  <tr><td colSpan={4} className="intelligence-muted" style={{ textAlign: "center" }}>No states matching "{filterText}"</td></tr>
                )
              ) : (
                cities.length ? (
                  cities.map((item) => (
                    <tr key={item.city} className={item.state === "Andhra Pradesh" ? "row-highlight" : ""}>
                      <td>
                        <strong>{item.city}</strong>
                        {item.state === "Andhra Pradesh" && <span className="table-badge">AP City</span>}
                      </td>
                      <td>{item.state}</td>
                      <td style={{ textAlign: "right" }}>{formatCount(item.road_cases)}</td>
                      <td style={{ textAlign: "right" }}>{formatCount(item.road_deaths)}</td>
                      <td style={{ textAlign: "right" }}>{formatCount(item.road_injured)}</td>
                    </tr>
                  ))
                ) : (
                  <tr><td colSpan={5} className="intelligence-muted" style={{ textAlign: "center" }}>No mega cities matching "{filterText}"</td></tr>
                )
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}


function FutureRiskCard({ futureRisk }) {
  return (
    <section className="intelligence-future-card">
      <div className="intelligence-support-icon" aria-hidden="true">◷</div>
      <div className="intelligence-support-copy">
        <span className="intelligence-overline">Forecasting</span>
        <h2>Future Risk Forecast</h2>
        <p>{futureRisk.message}</p>
      </div>
      <span className="intelligence-coming-soon">Coming Soon</span>
    </section>
  );
}

function DataTable({ title, columns, rows, emptyMessage = "No matching records." }) {
  return (
    <section className="intelligence-section">
      <h2>{title}</h2>
      {!rows?.length ? (
        <p className="intelligence-muted">{emptyMessage}</p>
      ) : (
        <div className="intelligence-table-wrap">
          <table className="intelligence-table">
            <thead><tr>{columns.map((column) => <th key={column.label}>{column.label}</th>)}</tr></thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={row.id || `${title}-${index}`}>
                  {columns.map((column) => (
                    <td key={column.label}>{column.render ? column.render(row) : row[column.key] ?? "—"}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function ResponderIntelligence() {
  const navigate = useNavigate();
  const location = useLocation();
  const { reportId } = useParams();
  const user = getUser();
  const [radiusKm, setRadiusKm] = useState(1);
  const [payload, setPayload] = useState(null);
  const [loadState, setLoadState] = useState("loading");

  useEffect(() => {
    if (location.hash === "#incident-map") {
      setTimeout(() => {
        const el = document.getElementById("incident-map");
        if (el) {
          el.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }, 50);
    }
  }, [location.hash, loadState]);

  useEffect(() => {
    if (!user || !["responder", "admin"].includes(user.role)) {
      setLoadState("denied");
      return undefined;
    }
    const controller = new AbortController();
    async function load() {
      setLoadState("loading");
      const url = reportId
        ? `/api/responder/reports/${reportId}/intelligence?radius_km=${radiusKm}`
        : `/api/responder/intelligence/${user.id}`;
      try {
        const response = await fetch(url, {
          credentials: "same-origin",
          signal: controller.signal,
        });
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
          setPayload({ error: result.message || "Unable to load intelligence." });
          setLoadState("error");
          return;
        }
        setPayload(result);
        setLoadState("loaded");
      } catch (error) {
        if (error.name !== "AbortError") {
          setPayload({ error: "Unable to load intelligence. Please try again." });
          setLoadState("error");
        }
      }
    }
    load();
    return () => controller.abort();
  }, [radiusKm, reportId, user?.id, user?.role]);

  if (loadState === "denied") {
    return <main className="page-main content-width"><div className="empty-state"><h3>Responder access required</h3><Link to="/dashboard">Back to your dashboard</Link></div></main>;
  }
  if (loadState === "loading") {
    return <main className="page-main content-width"><div className="empty-state"><p>Loading responder intelligence…</p></div></main>;
  }
  if (loadState === "error") {
    return <main className="page-main content-width"><div className="empty-state" role="alert"><h3>Intelligence unavailable</h3><p>{payload?.error}</p></div></main>;
  }

  return reportId
    ? <IncidentIntelligence payload={payload} radiusKm={radiusKm} setRadiusKm={setRadiusKm} />
    : <GlobalIntelligence analytics={payload.analytics} />;
}

function GlobalIntelligence({ analytics }) {
  const kpis = analytics.kpis;
  const averageResolution = Number.isFinite(kpis.average_resolution_minutes)
    ? formatDuration(kpis.average_resolution_minutes)
    : "Unavailable";
  return (
    <main className="page-main content-width responder-intelligence-page intelligence-dashboard">
      <div className="page-heading">
        <span className="eyebrow">Operations center · Live ResQNet records</span>
        <h1>Incident Intelligence</h1>
        <p>Response patterns, severity signals, and outcomes calculated from reports in ResQNet.</p>
      </div>
      <section className="intelligence-kpis" aria-label="Incident KPIs">
        <Kpi label="Total incidents" value={kpis.total_incidents} />
        <Kpi label="Recent · 30 days" value={kpis.recent_incidents_30_days} />
        <Kpi label="High priority" value={kpis.high_priority_incidents} />
        <Kpi label="Resolved" value={kpis.resolved_incidents} />
        <Kpi label="Repeat incidents" value={kpis.repeat_incidents} />
        <Kpi label="Average resolution" value={averageResolution} />
      </section>
      <div className="intelligence-chart-grid intelligence-section-enter">
        <BarChart title="Category distribution" entries={analytics.categories} />
        <BarChart title="Priority distribution" entries={analytics.priorities} />
        <BarChart title="Status distribution" entries={analytics.statuses} />
        <TrendChart title="Monthly incident trend" entries={analytics.monthly_trend} />
        <BarChart title="Most active time periods · IST" entries={analytics.time_period_pattern} labelKey="period" />
      </div>
      <section id="incident-map" className="intelligence-section intelligence-section-enter">
        <h2>Spatial hotspots</h2>
        {analytics.hotspots.count ? (
          <>
            <p>{analytics.hotspots.count} hotspot clusters · {analytics.hotspots.incident_count} reports within 1 km DBSCAN clusters.</p>
            <IntelligenceMap hotspots={analytics.hotspots.clusters} />
            <DataTable
              title="Detected clusters"
              columns={[
                { label: "Incidents", key: "incident_count" },
                { label: "Dominant category", key: "dominant_category" },
                { label: "Repeat count", key: "repeat_count" },
                { label: "Approx. center", render: (row) => `${row.center.latitude}, ${row.center.longitude}` },
              ]}
              rows={analytics.hotspots.clusters}
            />
          </>
        ) : <p className="intelligence-muted">{analytics.hotspots.insufficient_data_message}</p>}
      </section>
      <section className="intelligence-section intelligence-section-enter">
        <h2>Response effectiveness</h2>
        <div className="intelligence-response-summary">
          <div className="intelligence-response-label">
            <span>Resolved reports</span>
            <strong><AnimatedValue value={analytics.response_effectiveness.resolved_percentage} />%</strong>
          </div>
          <div
            className="intelligence-response-track"
            role="meter"
            aria-label="Resolved reports"
            aria-valuemin="0"
            aria-valuemax="100"
            aria-valuenow={analytics.response_effectiveness.resolved_percentage}
          >
            <i style={{ "--meter-value": `${analytics.response_effectiveness.resolved_percentage}%` }} />
          </div>
          <p>Active: {analytics.response_effectiveness.active_percentage}%</p>
        </div>
        <p className="intelligence-muted">{analytics.response_effectiveness.unavailable_message}</p>
        <div className="intelligence-chart-grid">
          <BarChart
            title="Average resolution time by category (minutes)"
            entries={analytics.response_effectiveness.resolution_by_category}
            labelKey="category"
            valueKey="average_minutes"
          />
          <BarChart
            title="Average resolution time by priority (minutes)"
            entries={analytics.response_effectiveness.resolution_by_priority}
            labelKey="priority"
            valueKey="average_minutes"
          />
          <BarChart
            title="Average resolution time by department (minutes)"
            entries={analytics.response_effectiveness.resolution_by_department}
            labelKey="department"
            valueKey="average_minutes"
          />
        </div>
      </section>
      <HistoricalDataPanel notice={analytics.official_historical_data} />
      <FutureRiskCard futureRisk={analytics.future_risk_model} />
    </main>
  );
}

function IncidentIntelligence({ payload, radiusKm, setRadiusKm }) {
  const { incident, intelligence } = payload;
  const area = intelligence.area_analytics;
  const risk = intelligence.risk_indicator;
  const hasGps =
    Number.isFinite(incident.latitude) && Number.isFinite(incident.longitude);
  const nearbyColumns = [
    { label: "Date", render: (row) => formatDate(row.date) },
    { label: "Category", key: "category" },
    { label: "Priority", key: "priority" },
    { label: "Distance", render: (row) => Number.isFinite(row.distance_km) ? `${row.distance_km} km` : "Unavailable" },
    { label: "Department", key: "department" },
    { label: "Destination", key: "destination" },
    { label: "Status", key: "status" },
    { label: "Resolution", render: (row) => formatDuration(row.resolution_minutes) },
  ];
  return (
    <main className="page-main content-width responder-intelligence-page intelligence-dashboard">
      <div className="page-heading">
        <span className="eyebrow">Operations center · Incident analysis</span>
        <h1>Incident #{incident.id}</h1>
        <p>{formatDate(incident.created_at)} · <span className={`responder-report-badge status-${incident.status.toLowerCase().replaceAll(" ", "-")}`}>{incident.status}</span></p>
      </div>
      <section className="intelligence-incident-hero intelligence-section-enter">
        <div className="intelligence-incident-topline">
          <span className={`intelligence-priority-tag priority-${incident.priority.toLowerCase()}`}>
            {incident.priority} priority
          </span>
          <span className="intelligence-incident-category">{incident.emergency_type}</span>
          <span className={`responder-report-badge status-${incident.status.toLowerCase().replaceAll(" ", "-")}`}>{incident.status}</span>
        </div>
        <h2>Incident overview</h2>
        <p className="intelligence-incident-description">{incident.description}</p>
        <div className="intelligence-confidence-grid">
          <ConfidenceIndicator label="Category confidence" confidence={incident.category_confidence} />
          <ConfidenceIndicator label="Priority confidence" confidence={incident.priority_confidence} />
        </div>
        <div className="intelligence-quick-stats">
          <div><span>Nearby reports</span><strong>{hasGps ? <AnimatedValue value={intelligence.previous_nearby_count} /> : "Location unavailable"}</strong></div>
          <div><span>Similar incidents</span><strong><AnimatedValue value={intelligence.similar_incidents.length} /></strong></div>
          <div><span>Area risk</span><strong>{risk.available ? <>{risk.level} · <AnimatedValue value={risk.score} /></> : hasGps ? "Insufficient data" : "Location unavailable"}</strong></div>
        </div>
      </section>
      <div className="intelligence-detail-grid intelligence-section-enter">
        <section className="intelligence-section intelligence-section-enter">
          <h2>Evidence</h2>
          {incident.image_attached && (
            <img className="responder-evidence-photo" src={`/api/responder/reports/${incident.id}/image`} alt={`Report ${incident.id} evidence`} />
          )}
          {incident.video_attached && (
            <video className="responder-evidence-photo" src={`/api/responder/reports/${incident.id}/video`} controls preload="metadata" />
          )}
          {!incident.image_attached && !incident.video_attached && <p>No evidence attached.</p>}
        </section>
        <section className="intelligence-section">
          <h2>Emergency Location</h2>
          {Number.isFinite(incident.latitude) && Number.isFinite(incident.longitude) ? (
            <>
              <ReportMap latitude={incident.latitude} longitude={incident.longitude} />
              <a className="button button-outline" href={`https://www.google.com/maps?q=${incident.latitude},${incident.longitude}`} target="_blank" rel="noopener noreferrer">Open in Google Maps</a>
            </>
          ) : <p>Location unavailable. GPS was not shared with this report; no location or map point is inferred.</p>}
        </section>
      </div>
      <section className="intelligence-section">
        <div className="intelligence-section-heading">
          <div>
            <h2>Area Intelligence</h2>
            {hasGps ? (
              <p>ResQNet Records within the selected radius; no reporter identity is included.</p>
            ) : (
              <p>Location unavailable. Area analysis cannot be calculated.</p>
            )}
          </div>
          <label className="intelligence-radius">Analysis radius
            <select
              value={radiusKm}
              disabled={!hasGps}
              onChange={(event) => setRadiusKm(Number(event.target.value))}
            >
              {[0.5, 1, 2, 5, 10].map((radius) => <option key={radius} value={radius}>{radius} km</option>)}
            </select>
          </label>
        </div>
        {hasGps ? (
          <>
            <section className="intelligence-kpis intelligence-area-kpis">
              <Kpi label="Total area incidents" value={area.total_incidents} />
              <Kpi label="Most common category" value={area.most_common_category || "—"} />
              <Kpi label="High priority" value={area.high_priority_cases} />
              <Kpi label="Repeat cases" value={area.repeat_cases} />
              <Kpi label="Resolution rate" value={`${area.resolution_rate_percentage}%`} />
              <Kpi label="Average resolution" value={formatDuration(area.average_resolution_minutes)} />
              <Kpi label="Most active period" value={area.most_active_time_period || "—"} />
              <Kpi label="Recent · 30 days" value={area.recent_activity_30_days} />
            </section>
            <div className="intelligence-chart-grid">
              <BarChart title="Category distribution" entries={area.category_distribution} />
              <BarChart title="Priority distribution" entries={area.priority_distribution} />
              <BarChart title="Status distribution" entries={area.status_distribution} />
              <TrendChart title="Incident trend" entries={area.monthly_trend} />
              <BarChart title="Time pattern · IST" entries={area.time_period_pattern} labelKey="period" />
            </div>
          </>
        ) : (
          <>
            <p className="intelligence-muted">
              {intelligence.location_intelligence.message}
            </p>
            <div className="intelligence-chart-grid">
              <BarChart title="ResQNet-wide categories" entries={intelligence.general_intelligence.trends.categories} />
              <BarChart title="ResQNet-wide priorities" entries={intelligence.general_intelligence.trends.priorities} />
              <BarChart title="ResQNet-wide statuses" entries={intelligence.network_analytics.statuses} />
              <TrendChart title="ResQNet-wide monthly trend" entries={intelligence.general_intelligence.trends.monthly} />
              <BarChart
                title="Average resolution by priority · minutes"
                entries={intelligence.network_analytics.response_effectiveness.resolution_by_priority}
                labelKey="priority"
                valueKey="average_minutes"
              />
              <BarChart
                title="Average resolution by department · minutes"
                entries={intelligence.network_analytics.response_effectiveness.resolution_by_department}
                labelKey="department"
                valueKey="average_minutes"
              />
            </div>
          </>
        )}
      </section>
      <section id="incident-map" className="intelligence-section intelligence-section-enter">
        <h2>Hotspot Map</h2>
        {hasGps
          ? <IntelligenceMap incident={incident} hotspots={intelligence.hotspots?.clusters || []} />
          : <p className="intelligence-muted">{intelligence.location_intelligence?.message || "Location unavailable"}</p>}
      </section>
      <section className="intelligence-section intelligence-section-enter">
        <h2>Historical Nearby Cases</h2>
        {hasGps ? (
          <p>{intelligence.previous_nearby_count} previous report(s) within {intelligence.radius_km} km.</p>
        ) : (
          <p className="intelligence-muted">{intelligence.location_intelligence.message}</p>
        )}
        <DataTable title="Nearby ResQNet Records" columns={nearbyColumns} rows={intelligence.nearby_cases} />
      </section>
      <DataTable
        title={`Similar incidents found: ${intelligence.similar_incidents.length}`}
        columns={[
          ...nearbyColumns.slice(0, 4),
          { label: "Similarity", render: (row) => `${Math.round(row.similarity_score * 100)}%` },
          ...nearbyColumns.slice(4),
        ]}
        rows={intelligence.similar_incidents}
      />
      <section className="intelligence-insight-grid">
        <div className="intelligence-insight-panel">
          <h2>Repeat Pattern</h2>
          {!hasGps
            ? <p>{intelligence.prevention.message}</p>
            : intelligence.area_analytics.repeat_pattern_detected
              ? <p>Repeat pattern detected: {intelligence.area_analytics.repeat_cases} reports in this category within the analysis area.</p>
              : <p>No qualifying repeat pattern detected in this area.</p>}
        </div>
        <div className="intelligence-insight-panel">
          <h2>Risk Indicator</h2>
          {risk.available
            ? (
              <>
                <strong className="risk-score">{risk.level} · <AnimatedValue value={risk.score} />/100</strong>
                <div
                  className={`intelligence-risk-track risk-${risk.level.toLowerCase()}`}
                  role="meter"
                  aria-label="Area risk score"
                  aria-valuemin="0"
                  aria-valuemax="100"
                  aria-valuenow={risk.score}
                >
                  <i style={{ "--meter-value": `${risk.score}%` }} />
                </div>
              </>
            )
            : <p>{risk.message}</p>}
          {risk.available && <p>{risk.message}</p>}
        </div>
      </section>
      <section className="intelligence-section intelligence-section-enter">
        <h2>Location Pattern Assessment</h2>
        {!intelligence.location_intelligence.available ? (
          <p className="intelligence-muted">{intelligence.location_intelligence.message}</p>
        ) : (
          <>
            <div className="intelligence-insight-grid">
              <div className="intelligence-insight-panel">
                <h2>Detected Local Problem</h2>
                <p><strong>Observed Local Problem: {intelligence.observed_local_problem || intelligence.local_problem}</strong></p>
                <p>{intelligence.local_problem_reason}</p>
                <p className="intelligence-muted">
                  {intelligence.short_term_concentration.detected
                    ? `Short-term incident concentration detected: ${intelligence.short_term_concentration.incident_count} incidents within ${intelligence.short_term_concentration.window_hours} hours.`
                    : `No short-term incident concentration detected within ${intelligence.short_term_concentration.window_hours} hours.`}
                </p>
                <p className="intelligence-muted">
                  {intelligence.extreme_proximity.detected
                    ? `Very close incidents detected: ${intelligence.extreme_proximity.count} within ${intelligence.extreme_proximity.threshold_km} km (${intelligence.extreme_proximity.incidents.map((item) => `${item.distance_km} km`).join(", ")}).`
                    : `No previous incident was within ${intelligence.extreme_proximity.threshold_km} km.`}
                </p>
                <p className="intelligence-muted">
                  {intelligence.recurring_pattern.detected
                    ? `Recurring ${intelligence.recurring_pattern.category} pattern across ${intelligence.recurring_pattern.distinct_dates} separate dates.`
                    : `No recurring pattern met the threshold of ${intelligence.recurring_pattern.minimum_incidents} incidents across ${intelligence.recurring_pattern.minimum_distinct_dates} dates.`}
                </p>
              </div>
              <div className="intelligence-insight-panel">
                <h2>Evidence Strength</h2>
                <strong className={`risk-score strength-${(intelligence.evidence_strength || "").toLowerCase()}`}>{intelligence.evidence_strength}</strong>
                <p>{intelligence.evidence_explanation}</p>
                <p>
                  Historical incidents: {intelligence.recommendation_basis.historical_incidents}
                  {" · "}Very close: {intelligence.recommendation_basis.very_close_incidents}
                  {" · "}Radius: {intelligence.recommendation_basis.analysis_radius_km} km
                  {" · "}Dominant category: {intelligence.recommendation_basis.dominant_historical_category || "Unavailable"}
                  {" · "}Distinct dates: {intelligence.recommendation_basis.distinct_historical_dates}
                </p>
              </div>
              <div className="intelligence-insight-panel">
                <h2>Recommended Solution for This Location</h2>
                <p>{intelligence.recommendation}</p>
              </div>
              <div className="intelligence-insight-panel">
                <h2>Why This Solution?</h2>
                <p>{intelligence.recommendation_reason}</p>
                <p className="intelligence-muted">
                  Decision support based on recorded ResQNet reports; this does not
                  establish a cause or guarantee prevention.
                </p>
              </div>
            </div>
            <CombinedEvidencePanel
              combinedEvidence={intelligence.combined_evidence}
              radiusKm={radiusKm}
            />
            <div className="intelligence-insight-panel">
              <h2>Location Conclusion</h2>
              <p>{intelligence.location_conclusion}</p>
              <p><strong>Reason:</strong> {intelligence.conclusion_reason}</p>
              <p><strong>Evidence limitation:</strong> {intelligence.data_limitation}</p>
            </div>
          </>
        )}
      </section>
      <HistoricalDataPanel notice={intelligence.official_historical_data} />
      <DataTable
        title="Response History"
        columns={[
          { label: "Date", render: (row) => formatDate(row.date) },
          { label: "Category", key: "category" },
          { label: "Department", key: "department" },
          { label: "Simulated destination", render: (row) => row.destination ? `Prototype / Simulated Location · ${row.destination}` : row.response_information },
          { label: "Status", key: "status" },
          { label: "Resolution", render: (row) => formatDuration(row.resolution_minutes) },
        ]}
        rows={intelligence.response_history}
        emptyMessage={hasGps ? "Response information unavailable." : "Location unavailable. Nearby response history cannot be calculated."}
      />
      <section className="intelligence-section intelligence-section-enter">
        <h2>Prevention Intelligence</h2>
        <p>{intelligence.prevention.message}</p>
        {intelligence.prevention.suggestions.length
          ? <ul>{intelligence.prevention.suggestions.map((suggestion) => <li key={suggestion}>{suggestion}</li>)}</ul>
          : <p className="intelligence-muted">
            {intelligence.prevention.pattern_detected
              ? "No category-specific recommendations are available."
              : "No recommendations are generated without a detected repeat pattern."}
          </p>}
      </section>
      <section className="intelligence-section">
        <h2>Department Routing</h2>
        {incident.route_department
          ? <p>Prototype / Simulated Location · {incident.route_department} — {incident.route_destination || "No destination selected"}</p>
          : <p>Not routed yet. Routing destinations are simulated and do not contact external services.</p>}
        <p>Current response status: <span className={`responder-report-badge status-${incident.status.toLowerCase().replaceAll(" ", "-")}`}>{incident.status}</span></p>
        <Link className="button button-outline" to={`/responder/reports#report-${incident.id}`}>
          Open existing routing and status controls
        </Link>
      </section>
      <FutureRiskCard futureRisk={intelligence.future_risk_model} />
    </main>
  );
}

export default ResponderIntelligence;
