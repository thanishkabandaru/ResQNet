import { useState } from "react";
import { Link } from "react-router-dom";
import EvidencePhotoCapture from "../components/EvidencePhotoCapture.jsx";

function Report() {
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState("");
  const [prediction, setPrediction] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [location, setLocation] = useState(null);
  const [locationMessage, setLocationMessage] = useState("");
  const [isGettingLocation, setIsGettingLocation] = useState(false);
  const [photo, setPhoto] = useState(null);

  function shareLocation() {
    if (!navigator.geolocation) {
      setLocationMessage("Location sharing is not supported by this browser.");
      return;
    }

    setIsGettingLocation(true);
    setLocationMessage("");
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        setLocation({
          latitude: coords.latitude,
          longitude: coords.longitude,
        });
        setLocationMessage("Location ready to include with your report.");
        setIsGettingLocation(false);
      },
      (error) => {
        const locationErrors = {
          1: "Location permission was denied. You can still submit without it.",
          2: "Your location is currently unavailable. You can still submit without it.",
          3: "Location request timed out. You can still submit without it.",
        };
        setLocation(null);
        setLocationMessage(
          locationErrors[error.code] || "Unable to get your location.",
        );
        setIsGettingLocation(false);
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 },
    );
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setMessage("");
    const form = event.currentTarget;

    let user;
    try {
      user = JSON.parse(localStorage.getItem("resqnetUser"));
    } catch {
      user = null;
    }

    if (!user || !Number.isInteger(user.id) || user.id <= 0) {
      setMessageType("error");
      setMessage("Please log in before submitting an emergency report.");
      return;
    }

    const formData = new FormData(form);
    const description = formData.get("description").trim();

    setPrediction(null);
    setIsSubmitting(true);
    try {
      const report = new FormData();
      report.append("user_id", String(user.id));
      report.append("emergency_type", formData.get("emergency_type"));
      report.append("description", description);
      if (location) {
        report.append("latitude", String(location.latitude));
        report.append("longitude", String(location.longitude));
      }
      if (photo) {
        report.append("image", photo);
      }

      const response = await fetch("/api/reports/with-image", {
        method: "POST",
        credentials: "same-origin",
        body: report,
      });
      const result = await response.json();

      if (!response.ok) {
        setMessageType("error");
        setMessage(result.message || "Unable to submit your report. Please try again.");
        return;
      }

      form.reset();
      setPhoto(null);
      setLocation(null);
      setLocationMessage("");
      setPrediction({
        category: result.predicted_category,
        priority: result.predicted_priority,
      });
      setMessageType("success");
      setMessage(result.message || "Emergency report submitted successfully.");
    } catch {
      setMessageType("error");
      setMessage("Unable to connect to ResQNet. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="page-main content-width">
      <div className="page-heading">
        <span className="eyebrow">Emergency reporting</span>
        <h1>Report an emergency</h1>
        <p>Share the details below to submit an emergency report.</p>
      </div>

      <section className="form-card report-card">
        <form onSubmit={handleSubmit}>
          <div className="info-box">
            <strong>Category Detection</strong>
            <p>Your selected category is stored separately. The existing text model still classifies the description.</p>
          </div>
          <label className="field">
            <span>Emergency type</span>
            <select name="emergency_type" defaultValue="" required>
              <option value="" disabled>Select a category</option>
              <option value="Medical Emergency">Medical Emergency</option>
              <option value="Accident">Accident</option>
              <option value="Fire">Fire</option>
              <option value="Other">Other</option>
            </select>
          </label>
          <label className="field">
            <span>Emergency description</span>
            <textarea
              name="description"
              rows="5"
              placeholder="Describe what is happening and any important details... (The system will automatically classify the emergency type)"
              required
            />
          </label>
          <EvidencePhotoCapture onPhotoChange={setPhoto} />
          <div className="location-box">
            <div>
              <strong>Location</strong>
              <p>{locationMessage || "Location is optional. Share it to help responders."}</p>
            </div>
            <button
              className="button button-outline"
              type="button"
              onClick={shareLocation}
              disabled={isGettingLocation}
            >
              {isGettingLocation
                ? "Getting location..."
                : location
                  ? "Update My Location"
                  : "Share My Location"}
            </button>
          </div>
          {message && (
            <p className={`form-message ${messageType}`} role="alert">
              {message}
              {messageType === "error" && message.includes("log in") && (
                <>
                  {" "}
                  <Link to="/login">Go to login</Link>
                </>
              )}
            </p>
          )}
          {prediction && (
            <div className="info-box" role="status">
              <strong>Text ML result</strong>
              <p>Classification: {prediction.category}</p>
              <p>Priority: {prediction.priority}</p>
            </div>
          )}
          <button className="button button-primary button-full" type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Submitting..." : "Submit Report"}
          </button>
          <p className="form-disclaimer">
            This academic prototype does not contact real emergency services.
          </p>
        </form>
      </section>
      <p className="back-link">
        <Link to="/">← Back to home</Link>
      </p>
    </main>
  );
}

export default Report;
