import { useEffect, useRef, useState } from "react";
import "./EvidencePhotoCapture.css";

const MAX_PHOTO_SIZE = 8 * 1024 * 1024;
const MAX_PHOTO_DIMENSION = 1600;

async function preparePhoto(file) {
  if (!["image/jpeg", "image/png"].includes(file.type)) {
    throw new Error("Choose a JPEG or PNG image.");
  }
  if (file.size > MAX_PHOTO_SIZE) {
    throw new Error("The image must be 8 MB or smaller.");
  }

  if (typeof createImageBitmap !== "function") {
    return file;
  }

  const bitmap = await createImageBitmap(file);
  try {
    const scale = Math.min(
      1,
      MAX_PHOTO_DIMENSION / Math.max(bitmap.width, bitmap.height),
    );
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const context = canvas.getContext("2d");
    if (!context) {
      throw new Error("Unable to prepare this image. Please choose another.");
    }
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);

    const compressedBlob = await new Promise((resolve, reject) => {
      canvas.toBlob(
        (blob) => {
          if (blob) {
            resolve(blob);
          } else {
            reject(new Error("Unable to prepare this image. Please try another."));
          }
        },
        "image/jpeg",
        0.85,
      );
    });
    if (compressedBlob.size > MAX_PHOTO_SIZE) {
      throw new Error("The prepared image is larger than 8 MB.");
    }

    return new File([compressedBlob], "evidence-photo.jpg", {
      type: "image/jpeg",
      lastModified: Date.now(),
    });
  } finally {
    bitmap.close();
  }
}

function EvidencePhotoCapture({ onPhotoChange }) {
  const fileInputRef = useRef(null);
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const cameraRequestRef = useRef(0);
  const [cameraStream, setCameraStream] = useState(null);
  const [photo, setPhoto] = useState(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [cameraMessage, setCameraMessage] = useState("");
  const [isPreparing, setIsPreparing] = useState(false);

  useEffect(() => {
    if (!cameraStream || !videoRef.current) {
      return undefined;
    }

    videoRef.current.srcObject = cameraStream;
    videoRef.current.play().catch(() => {
      setCameraMessage("Unable to start the camera preview. Try uploading an image instead.");
    });
    return () => {
      if (videoRef.current) {
        videoRef.current.srcObject = null;
      }
    };
  }, [cameraStream]);

  useEffect(() => {
    if (!photo) {
      setPreviewUrl("");
      return undefined;
    }

    const objectUrl = URL.createObjectURL(photo);
    setPreviewUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [photo]);

  useEffect(
    () => () => {
      cameraRequestRef.current += 1;
      streamRef.current?.getTracks().forEach((track) => track.stop());
    },
    [],
  );

  function stopCamera() {
    cameraRequestRef.current += 1;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setCameraStream(null);
  }

  async function openCamera() {
    setCameraMessage("");
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraMessage("Camera access is unavailable in this browser. You can upload an image instead.");
      return;
    }

    const requestId = cameraRequestRef.current + 1;
    cameraRequestRef.current = requestId;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: false,
      });
      if (requestId !== cameraRequestRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      setCameraStream(stream);
    } catch (error) {
      if (requestId !== cameraRequestRef.current) {
        return;
      }
      const permissionDenied =
        error.name === "NotAllowedError" || error.name === "PermissionDeniedError";
      const cameraUnavailable =
        error.name === "NotFoundError" ||
        error.name === "NotReadableError" ||
        error.name === "OverconstrainedError";
      setCameraMessage(
        permissionDenied
          ? "Camera permission was denied. You can still upload an image instead."
          : cameraUnavailable
            ? "Camera is unavailable. You can still upload an image instead."
            : "Unable to open the camera. You can still upload an image instead.",
      );
    }
  }

  async function acceptPhoto(file) {
    if (!file) {
      return;
    }

    setCameraMessage("");
    setIsPreparing(true);
    try {
      const preparedPhoto = await preparePhoto(file);
      setPhoto(preparedPhoto);
      onPhotoChange(preparedPhoto);
      stopCamera();
    } catch (error) {
      setCameraMessage(error.message);
    } finally {
      setIsPreparing(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  }

  async function capturePhoto() {
    const video = videoRef.current;
    if (!video || !video.videoWidth || !video.videoHeight) {
      setCameraMessage("The camera is not ready yet. Please wait and try again.");
      return;
    }

    const scale = Math.min(
      1,
      MAX_PHOTO_DIMENSION / Math.max(video.videoWidth, video.videoHeight),
    );
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
    canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
    const context = canvas.getContext("2d");
    if (!context) {
      setCameraMessage("Unable to capture this photo. Please use the upload option.");
      return;
    }
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(
      async (blob) => {
        if (!blob) {
          setCameraMessage("Unable to capture this photo. Please try again.");
          return;
        }
        const capturedPhoto = new File([blob], "camera-evidence.jpg", {
          type: "image/jpeg",
          lastModified: Date.now(),
        });
        await acceptPhoto(capturedPhoto);
      },
      "image/jpeg",
      0.85,
    );
  }

  function removePhoto() {
    setPhoto(null);
    onPhotoChange(null);
  }

  return (
    <div className="evidence-photo">
      <div className="evidence-photo-heading">
        <strong>Evidence photo</strong>
        <span>Optional · JPEG or PNG · maximum 8 MB</span>
      </div>

      {previewUrl && (
        <div className="evidence-photo-preview">
          <img src={previewUrl} alt="Preview of the evidence photo" />
          <button className="button button-outline" type="button" onClick={removePhoto}>
            Remove photo
          </button>
        </div>
      )}

      {cameraStream && (
        <div className="evidence-camera">
          <video ref={videoRef} autoPlay playsInline muted aria-label="Camera preview" />
          <div className="evidence-photo-actions">
            <button
              className="button button-primary"
              type="button"
              onClick={capturePhoto}
              disabled={isPreparing}
            >
              Capture photo
            </button>
            <button className="button button-outline" type="button" onClick={stopCamera}>
              Close camera
            </button>
          </div>
        </div>
      )}

      <div className="evidence-photo-actions">
        {!cameraStream && (
          <button className="button button-outline" type="button" onClick={openCamera}>
            {photo ? "Retake photo" : "Open camera"}
          </button>
        )}
        <button
          className="button button-outline"
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={isPreparing}
        >
          {photo ? "Choose another image" : "Upload an image"}
        </button>
        <input
          ref={fileInputRef}
          className="evidence-photo-input"
          type="file"
          accept="image/jpeg,image/png"
          onChange={(event) => acceptPhoto(event.target.files?.[0])}
          aria-label="Upload an evidence image"
        />
      </div>

      {isPreparing && <p className="evidence-photo-message">Preparing image...</p>}
      {cameraMessage && (
        <p className="evidence-photo-message error" role="alert">
          {cameraMessage}
        </p>
      )}
    </div>
  );
}

export default EvidencePhotoCapture;
