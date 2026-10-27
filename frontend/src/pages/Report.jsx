import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import EvidencePhotoCapture from "../components/EvidencePhotoCapture.jsx";
import ReportMap from "../components/ReportMap.jsx";

const MAX_VIDEO_SIZE = 25 * 1024 * 1024;
const ALLOWED_VIDEO_TYPES = new Map([
  [".mp4", "video/mp4"],
  [".webm", "video/webm"],
  [".mov", "video/quicktime"],
]);

function isRecentLocation(location, timestamp = Date.now()) {
  if (!location || !Number.isFinite(location.timestamp)) {
    return false;
  }
  const age = timestamp - location.timestamp;
  return age >= 0 && age <= 5 * 60 * 1000;
}

function Report() {
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState("");
  const [prediction, setPrediction] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [location, setLocation] = useState(null);
  const [locationMessage, setLocationMessage] = useState("");
  const [isGettingLocation, setIsGettingLocation] = useState(false);
  const [photo, setPhoto] = useState(null);
  const [video, setVideo] = useState(null);
  const [videoMessage, setVideoMessage] = useState("");
  const videoInputRef = useRef(null);
  const videoPreviewRef = useRef(null);
  const videoStreamRef = useRef(null);
  const videoRecorderRef = useRef(null);
  const videoChunksRef = useRef([]);
  const videoRequestRef = useRef(0);
  const discardRecordingRef = useRef(false);
  const recordingTooLargeRef = useRef(false);
  const [videoCameraStream, setVideoCameraStream] = useState(null);
  const [isRecordingVideo, setIsRecordingVideo] = useState(false);
  const [photoCaptureKey, setPhotoCaptureKey] = useState(0);
  const [videoPreviewUrl, setVideoPreviewUrl] = useState("");

  useEffect(() => {
    if (!video) {
      setVideoPreviewUrl("");
      return undefined;
    }
    const previewUrl = URL.createObjectURL(video);
    setVideoPreviewUrl(previewUrl);
    return () => URL.revokeObjectURL(previewUrl);
  }, [video]);

  useEffect(() => {
    if (videoCameraStream && videoPreviewRef.current) {
      videoPreviewRef.current.srcObject = videoCameraStream;
      videoPreviewRef.current.play().catch(() => {
        setVideoMessage("Unable to start the camera preview. You can upload a video instead.");
      });
    }
    return () => {
      if (videoPreviewRef.current) {
        videoPreviewRef.current.srcObject = null;
      }
    };
  }, [videoCameraStream]);

  useEffect(
    () => () => {
      videoRequestRef.current += 1;
      if (videoRecorderRef.current?.state === "recording") {
        discardRecordingRef.current = true;
        videoRecorderRef.current.stop();
      }
      videoStreamRef.current?.getTracks().forEach((track) => track.stop());
    },
    [],
  );

  function stopVideoCamera() {
    videoRequestRef.current += 1;
    videoStreamRef.current?.getTracks().forEach((track) => track.stop());
    videoStreamRef.current = null;
    setVideoCameraStream(null);
  }

  async function openVideoCamera() {
    setVideoMessage("");
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setVideoMessage("Camera recording is unavailable in this browser. You can upload a video instead.");
      return;
    }

    const requestId = videoRequestRef.current + 1;
    videoRequestRef.current = requestId;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: false,
      });
      if (requestId !== videoRequestRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      videoStreamRef.current = stream;
      setVideoCameraStream(stream);
    } catch (error) {
      if (requestId !== videoRequestRef.current) {
        return;
      }
      const denied =
        error.name === "NotAllowedError" || error.name === "PermissionDeniedError";
      setVideoMessage(
        denied
          ? "Camera permission was denied. You can upload a video instead."
          : "Camera recording is unavailable. You can upload a video instead.",
      );
    }
  }

  function startVideoRecording() {
    const stream = videoStreamRef.current;
    if (!stream) {
      return;
    }
    try {
      const preferredType = [
        "video/webm;codecs=vp9,opus",
        "video/webm;codecs=vp8,opus",
        "video/webm",
      ].find((type) => MediaRecorder.isTypeSupported(type));
      const recorder = new MediaRecorder(
        stream,
        preferredType ? { mimeType: preferredType } : undefined,
      );
      videoChunksRef.current = [];
      discardRecordingRef.current = false;
      recordingTooLargeRef.current = false;
      recorder.ondataavailable = (event) => {
        if (!event.data.size) {
          return;
        }
        videoChunksRef.current.push(event.data);
        const recordedSize = videoChunksRef.current.reduce(
          (size, chunk) => size + chunk.size,
          0,
        );
        if (recordedSize > MAX_VIDEO_SIZE) {
          recordingTooLargeRef.current = true;
          if (recorder.state === "recording") {
            recorder.stop();
          }
        }
      };
      recorder.onstop = () => {
        if (!discardRecordingRef.current) {
          if (recordingTooLargeRef.current) {
            setVideoMessage("The recorded video must be 25 MB or smaller.");
          } else {
            const mimeType = recorder.mimeType || "video/webm";
            const baseMimeType = mimeType.split(";")[0];
            const extension = [...ALLOWED_VIDEO_TYPES].find(
              ([, allowedMimeType]) => allowedMimeType === baseMimeType,
            )?.[0];
            if (!extension) {
              setVideoMessage("This browser's recording format is unsupported. Upload an MP4, WebM, or MOV video instead.");
            } else {
              const recordedVideo = new File(
                [new Blob(videoChunksRef.current, { type: mimeType })],
                `camera-evidence${extension}`,
                { type: baseMimeType, lastModified: Date.now() },
              );
              setVideo(recordedVideo);
              setVideoMessage("");
            }
          }
        }
        videoChunksRef.current = [];
        videoRecorderRef.current = null;
        setIsRecordingVideo(false);
        stopVideoCamera();
      };
      videoRecorderRef.current = recorder;
      recorder.start(1000);
      setVideoMessage("");
      setIsRecordingVideo(true);
    } catch {
      setVideoMessage("Unable to start video recording. You can upload a video instead.");
    }
  }

  function stopVideoRecording() {
    const recorder = videoRecorderRef.current;
    if (recorder?.state === "recording") {
      recorder.stop();
      stopVideoCamera();
    }
  }

  function cancelVideoRecording() {
    discardRecordingRef.current = true;
    const recorder = videoRecorderRef.current;
    if (recorder?.state === "recording") {
      recorder.stop();
    }
    videoChunksRef.current = [];
    videoRecorderRef.current = null;
    setIsRecordingVideo(false);
    stopVideoCamera();
  }

  function removeVideo() {
    setVideo(null);
    setVideoMessage("");
    if (videoInputRef.current) {
      videoInputRef.current.value = "";
    }
  }

  function selectVideo(event) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    const extension = file.name.toLowerCase().match(/\.[^.]+$/)?.[0];
    if (!extension || ALLOWED_VIDEO_TYPES.get(extension) !== file.type) {
      setVideoMessage("Choose an MP4, WebM, or MOV video.");
      event.target.value = "";
      return;
    }
    if (file.size > MAX_VIDEO_SIZE) {
      setVideoMessage("The video must be 25 MB or smaller.");
      event.target.value = "";
      return;
    }

    setVideo(file);
    setVideoMessage("");
  }

  function shareLocation() {
    if (!navigator.geolocation) {
      setLocationMessage("Location sharing is not supported by this browser.");
      return;
    }

    setIsGettingLocation(true);
    setLocationMessage("");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { coords } = position;
        setLocation({
          latitude: coords.latitude,
          longitude: coords.longitude,
          accuracy: coords.accuracy,
          timestamp: position.timestamp,
        });
        setLocationMessage(
          `Location ready · approximately ${Math.round(coords.accuracy)} m accuracy.`,
        );
        setIsGettingLocation(false);
      },
      (error) => {
        const locationErrors = {
          1: "Location permission was denied. You can still submit without GPS.",
          2: "Your location is unavailable right now. You can still submit without GPS.",
          3: "Location request timed out. You can still submit without GPS.",
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

    if (photo && video) {
      setMessageType("error");
      setMessage("Please attach only one photo or video evidence.");
      return;
    }
    if (!photo && !video) {
      setMessageType("error");
      setMessage("Please provide either a photo or a video evidence before submitting.");
      return;
    }
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
    const reportLocation = isRecentLocation(location) ? location : null;
    if (location && !reportLocation) {
      setLocationMessage("This GPS fix is over five minutes old. The report will be submitted without GPS.");
    }

    setPrediction(null);
    setIsSubmitting(true);
    try {
      const report = new FormData();
      report.append("user_id", String(user.id));
      report.append("description", description);
      if (reportLocation) {
        report.append("latitude", String(reportLocation.latitude));
        report.append("longitude", String(reportLocation.longitude));
      }
      if (photo) {
        report.append("image", photo);
      }
      if (video) {
        report.append("video", video);
      }

      const response = await fetch("/api/reports/with-image", {
        method: "POST",
        credentials: "same-origin",
        body: report,
      });
      const result = await response.json();

      if (!response.ok) {
        if (response.status === 401) {
          localStorage.removeItem("resqnetUser");
        }
        setMessageType("error");
        setMessage(result.message || "Unable to submit your report. Please try again.");
        return;
      }

      form.reset();
      setPhoto(null);
      removeVideo();
      setPhotoCaptureKey((key) => key + 1);
      if (videoInputRef.current) {
        videoInputRef.current.value = "";
      }
      setVideoMessage("");
      setLocation(null);
      setLocationMessage("");
      setPrediction({
        category: result.predicted_category,
        priority: result.predicted_priority,
      });
      setMessageType("success");
      setMessage(
        `${result.message || "Emergency report submitted successfully."}${
          location && !reportLocation
            ? " GPS was omitted because the location fix was over five minutes old."
            : ""
        }`,
      );
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
          <label className="field">
            <span>Emergency description</span>
            <textarea
              name="description"
              rows="5"
              placeholder="Describe what is happening and any important details... (The system will automatically classify the emergency type)"
              required
            />
          </label>
          <section className="evidence-choice" aria-label="Evidence">
            <div className="evidence-photo-heading">
              <strong>Evidence <span aria-hidden="true">*</span></strong>
              <span>Required · choose one photo or video</span>
            </div>

            {video ? (
              <div className="evidence-photo-preview evidence-video-preview">
                {videoPreviewUrl && (
                  <video
                    className="responder-evidence-photo"
                    src={videoPreviewUrl}
                    controls
                    preload="metadata"
                    aria-label="Preview of the evidence video"
                  />
                )}
                <div className="evidence-photo-actions">
                  <button className="button button-outline" type="button" onClick={removeVideo}>
                    Retake / Replace video
                  </button>
                  <button
                    className="button button-outline"
                    type="button"
                    onClick={() => {
                      removeVideo();
                      setPhotoCaptureKey((key) => key + 1);
                    }}
                  >
                    Replace with photo
                  </button>
                </div>
              </div>
            ) : photo ? (
              <>
                <EvidencePhotoCapture
                  location={location}
                  key={photoCaptureKey}
                  onPhotoChange={(capturedPhoto) => {
                    if (capturedPhoto) {
                      cancelVideoRecording();
                    }
                    setPhoto(capturedPhoto);
                  }}
                />
                <div className="evidence-photo-message">
                  Video is unavailable while a photo is selected.
                  <div className="evidence-photo-actions">
                    <button
                      className="button button-outline"
                      type="button"
                      onClick={() => {
                        setPhoto(null);
                        setPhotoCaptureKey((key) => key + 1);
                      }}
                    >
                      Replace with video
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <>
                <EvidencePhotoCapture
                  location={location}
                  key={photoCaptureKey}
                  onPhotoChange={(capturedPhoto) => {
                    if (capturedPhoto) {
                      cancelVideoRecording();
                    }
                    setPhoto(capturedPhoto);
                  }}
                />
                {videoCameraStream && (
                  <div className="evidence-camera">
                    <video
                      ref={videoPreviewRef}
                      autoPlay
                      playsInline
                      muted
                      aria-label="Live video camera preview"
                    />
                    <div className="evidence-photo-actions">
                      {isRecordingVideo ? (
                        <>
                          <button
                            className="button button-primary"
                            type="button"
                            onClick={stopVideoRecording}
                          >
                            Stop Recording
                          </button>
                          <button
                            className="button button-outline"
                            type="button"
                            onClick={cancelVideoRecording}
                          >
                            Cancel recording
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            className="button button-primary"
                            type="button"
                            onClick={startVideoRecording}
                          >
                            Start Recording
                          </button>
                          <button
                            className="button button-outline"
                            type="button"
                            onClick={cancelVideoRecording}
                          >
                            Close camera
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                )}
                {!videoCameraStream && (
                  <div className="evidence-photo-actions">
                    <button
                      className="button button-outline"
                      type="button"
                      onClick={openVideoCamera}
                    >
                      Record Video
                    </button>
                    <button
                      className="button button-outline"
                      type="button"
                      onClick={() => videoInputRef.current?.click()}
                    >
                      Upload a video
                    </button>
                    <input
                      ref={videoInputRef}
                      className="evidence-photo-input"
                      type="file"
                      accept="video/mp4,video/webm,video/quicktime,.mp4,.webm,.mov"
                      onChange={selectVideo}
                      aria-label="Upload an evidence video"
                    />
                  </div>
                )}
                <span>MP4, WebM, or MOV · maximum 25 MB</span>
              </>
            )}
            {videoMessage && (
              <p className="evidence-photo-message error" role="alert">{videoMessage}</p>
            )}
          </section>
          <div className="location-box">
            <div>
              <strong>Location</strong>
              <p>
                {locationMessage ||
                  "Optional · share GPS to enable location-based responder intelligence."}
              </p>
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
          {location && (
            <>
              <p className="evidence-photo-message">
                This report will include the location shown. Camera photos captured after sharing GPS also include it in their evidence overlay.
              </p>
              <ReportMap
                latitude={location.latitude}
                longitude={location.longitude}
              />
            </>
          )}
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
              <strong>ML Prediction</strong>
              <p>Emergency Category: {prediction.category}</p>
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
