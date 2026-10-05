import { Link } from "react-router-dom";

function Home() {
  return (
    <main>
      <section className="hero content-width">
        <div className="hero-copy">
          <span className="eyebrow">A connected community is a safer one</span>
          <h1>Emergency Reporting &amp; Response Network</h1>
          <p className="hero-description">
            ResQNet is a platform concept for sharing emergency reports and
            helping response teams stay informed. Submit a report and follow
            its progress in one place.
          </p>
          <div className="hero-actions">
            <Link className="button button-primary" to="/report">
              Report Emergency
              <span aria-hidden="true">→</span>
            </Link>
            <Link className="button button-outline" to="/login">
              Login
            </Link>
          </div>
          <p className="prototype-note">
            Academic prototype only. For real emergencies, contact your local
            emergency services.
          </p>
        </div>
        <div className="hero-panel" aria-label="ResQNet service overview">
          <div className="hero-panel-icon" aria-hidden="true">
            +
          </div>
          <p className="panel-label">RESQNET</p>
          <h2>Help starts with being heard.</h2>
          <p>
            Share the details responders need, with a clear place to track your
            report.
          </p>
          <div className="panel-divider" />
          <div className="panel-status">
            <span className="status-dot" />
            <span>Ready to receive a report</span>
          </div>
        </div>
      </section>

      <section className="intro-strip">
        <div className="content-width intro-inner">
          <span className="intro-symbol" aria-hidden="true">
            i
          </span>
          <p>
            ResQNet is a student project and does not alert real emergency
            services.
          </p>
          <Link to="/dashboard">Explore your dashboard <span aria-hidden="true">→</span></Link>
        </div>
      </section>
    </main>
  );
}

export default Home;
