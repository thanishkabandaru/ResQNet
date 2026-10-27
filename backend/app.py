import io
import math
import os
import re
import secrets
import sqlite3
import uuid
import warnings
from datetime import timedelta
from pathlib import Path

from flask import Flask, jsonify, request, send_file, session
from flask_cors import CORS
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.security import check_password_hash, generate_password_hash

from authorization import check_responder_access, get_logged_in_user
from database import get_db_connection, initialize_database
from intelligence import (
    build_global_intelligence,
    build_incident_intelligence,
)
from ml_models import (
    predict_category,
    predict_category_confidence,
    predict_priority,
    predict_priority_confidence,
)

app = Flask(__name__)
@app.route("/")
def home():
    return {
        "status": "success",
        "message": "ResQNet backend is running"
    }
def _resolve_secret_key():
    env_secret = os.environ.get("RESQNET_SECRET_KEY")
    if env_secret:
        return env_secret
    dev_secret_file = Path(__file__).resolve().parent / ".secret_key"
    try:
        if dev_secret_file.is_file():
            secret = dev_secret_file.read_text(encoding="utf-8").strip()
            if secret:
                return secret
        new_secret = secrets.token_hex(32)
        dev_secret_file.write_text(new_secret, encoding="utf-8")
        return new_secret
    except OSError as error:
        raise RuntimeError(
            "Unable to persist the Flask session key. Set RESQNET_SECRET_KEY "
            "to a stable secret before starting ResQNet."
        ) from error


app.config.update(
    SECRET_KEY=_resolve_secret_key(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    SESSION_COOKIE_SECURE=os.environ.get("RESQNET_COOKIE_SECURE", "false").lower()
    == "true",
)
CORS(
    app,
    supports_credentials=True,
    origins=["http://localhost:5173", "http://127.0.0.1:5173"],
)

initialize_database()


@app.after_request
def protect_api_responses(response):
    if request.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers["X-Content-Type-Options"] = "nosniff"
    return response

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_VIDEO_BYTES = 25 * 1024 * 1024
MAX_REPORT_REQUEST_BYTES = MAX_VIDEO_BYTES + 128 * 1024
MAX_IMAGE_PIXELS = 20_000_000
VIDEO_MIME_TYPES = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
}
UPLOADS_DIRECTORY = Path(__file__).resolve().parent / "private_uploads"
SIMULATED_ROUTING_DESTINATIONS = {
    "Medical / Ambulance": {
        "Simulated Medical Point 1",
        "Simulated Medical Point 2",
        "Simulated Medical Point 3",
    },
    "Fire & Rescue": {
        "Simulated Fire & Rescue Point 1",
        "Simulated Fire & Rescue Point 2",
        "Simulated Fire & Rescue Point 3",
    },
    "Police": {
        "Simulated Police Point 1",
        "Simulated Police Point 2",
        "Simulated Police Point 3",
    },
    "Road & Traffic": {
        "Simulated Road & Traffic Point 1",
        "Simulated Road & Traffic Point 2",
        "Simulated Road & Traffic Point 3",
    },
    "Other Emergency Services": {
        "Simulated Other Services Point 1",
        "Simulated Other Services Point 2",
        "Simulated Other Services Point 3",
    },
}


@app.get("/api/health")
def health_check():
    return jsonify(
        {
            "status": "success",
            "message": "ResQNet backend is running",
        }
    )


@app.get("/api/db-test")
def database_test():
    connection = get_db_connection()
    try:
        connection.execute("SELECT 1")
    finally:
        connection.close()

    return jsonify(
        {
            "status": "success",
            "message": "Database connection successful",
        }
    )


@app.post("/api/register")
def register():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "A JSON request body is required"}), 400

    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    if not all(isinstance(value, str) for value in (name, email, password)):
        return jsonify({"status": "error", "message": "Name, email, and password are required"}), 400

    name = name.strip()
    email = email.strip()
    if not name or not email or not password:
        return jsonify({"status": "error", "message": "Name, email, and password are required"}), 400

    connection = get_db_connection()
    try:
        existing_user = connection.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        if existing_user:
            return jsonify({"status": "error", "message": "An account with this email already exists"}), 409

        password_hash = generate_password_hash(password)
        cursor = connection.execute(
            """
            INSERT INTO users (name, email, password_hash, role)
            VALUES (?, ?, ?, 'user')
            """,
            (name, email, password_hash),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        return jsonify({"status": "error", "message": "An account with this email already exists"}), 409
    finally:
        connection.close()

    return jsonify(
        {
            "status": "success",
            "message": "Registration successful",
            "user": {
                "id": cursor.lastrowid,
                "name": name,
                "email": email,
                "role": "user",
            },
        }
    ), 201


@app.post("/api/login")
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "A JSON request body is required"}), 400

    email = data.get("email")
    password = data.get("password")
    if not isinstance(email, str) or not isinstance(password, str) or not email.strip() or not password:
        return jsonify({"status": "error", "message": "Email and password are required"}), 400

    connection = get_db_connection()
    try:
        user = connection.execute(
            "SELECT id, name, email, password_hash, role FROM users WHERE email = ?",
            (email.strip(),),
        ).fetchone()
    finally:
        connection.close()

    if user is None or not check_password_hash(user["password_hash"], password):
        return jsonify({"status": "error", "message": "Invalid email or password"}), 401

    session.clear()
    session["user_id"] = user["id"]
    session.permanent = True

    return jsonify(
        {
            "status": "success",
            "message": "Login successful",
            "user": {
                "id": user["id"],
                "name": user["name"],
                "email": user["email"],
                "role": user["role"],
            },
        }
    ), 200


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify({"status": "success", "message": "Logged out successfully"}), 200


@app.get("/api/me")
def get_current_user():
    current_user = get_logged_in_user()
    if current_user is None:
        return jsonify({"status": "error", "message": "Please log in"}), 401
    return jsonify(
        {
            "status": "success",
            "user": {
                "id": current_user["id"],
                "name": current_user["name"],
                "email": current_user["email"],
                "role": current_user["role"],
            },
        }
    ), 200


@app.post("/api/reports")
def create_report():
    current_user = get_logged_in_user()
    if current_user is None:
        return jsonify({"status": "error", "message": "Please log in to submit a report"}), 401

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "A JSON request body is required"}), 400

    user_id = data.get("user_id")
    description = data.get("description")
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        return jsonify({"status": "error", "message": "A valid user_id is required"}), 400
    if user_id != current_user["id"]:
        return jsonify({"status": "error", "message": "You can only submit reports for your own account"}), 403
    if current_user["role"] != "user":
        return jsonify({"status": "error", "message": "Only user accounts can submit reports"}), 403
    if not isinstance(description, str) or not description.strip():
        return jsonify({"status": "error", "message": "A description is required"}), 400
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    if (latitude is None) != (longitude is None):
        return jsonify(
            {"status": "error", "message": "Latitude and longitude must be provided together"}
        ), 400
    if latitude is not None:
        valid_latitude = (
            isinstance(latitude, (int, float))
            and not isinstance(latitude, bool)
            and math.isfinite(latitude)
            and -90 <= latitude <= 90
        )
        valid_longitude = (
            isinstance(longitude, (int, float))
            and not isinstance(longitude, bool)
            and math.isfinite(longitude)
            and -180 <= longitude <= 180
        )
        if not valid_latitude or not valid_longitude:
            return jsonify(
                {"status": "error", "message": "A valid latitude and longitude are required"}
            ), 400

    return jsonify(
        {
            "status": "error",
            "message": "Please provide either a photo or a video evidence before submitting",
        }
    ), 400


@app.post("/api/reports/with-image")
def create_report_with_image():
    current_user = get_logged_in_user()
    if current_user is None:
        return jsonify({"status": "error", "message": "Please log in to submit a report"}), 401
    if current_user["role"] != "user":
        return jsonify({"status": "error", "message": "Only user accounts can submit reports"}), 403
    if request.content_length and request.content_length > MAX_REPORT_REQUEST_BYTES:
        return jsonify({"status": "error", "message": "The uploaded evidence is too large"}), 413

    form = request.form
    try:
        user_id = int(form.get("user_id", ""))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "A valid user_id is required"}), 400
    if user_id <= 0:
        return jsonify({"status": "error", "message": "A valid user_id is required"}), 400
    if user_id != current_user["id"]:
        return jsonify(
            {"status": "error", "message": "You can only submit reports for your own account"}
        ), 403

    description = form.get("description", "")
    if not description.strip():
        return jsonify({"status": "error", "message": "A description is required"}), 400

    latitude_text = form.get("latitude")
    longitude_text = form.get("longitude")
    if (latitude_text is None) != (longitude_text is None):
        return jsonify(
            {"status": "error", "message": "Latitude and longitude must be provided together"}
        ), 400
    latitude = longitude = None
    if latitude_text is not None:
        try:
            latitude = float(latitude_text)
            longitude = float(longitude_text)
        except (TypeError, ValueError):
            return jsonify(
                {"status": "error", "message": "A valid latitude and longitude are required"}
            ), 400
        if (
            not math.isfinite(latitude)
            or not math.isfinite(longitude)
            or not -90 <= latitude <= 90
            or not -180 <= longitude <= 180
        ):
            return jsonify(
                {"status": "error", "message": "A valid latitude and longitude are required"}
            ), 400

    image_files = [
        file for file in request.files.getlist("image") if file.filename
    ]
    video_files = [
        file for file in request.files.getlist("video") if file.filename
    ]
    evidence_count = len(image_files) + len(video_files)
    if evidence_count == 0:
        return jsonify(
            {
                "status": "error",
                "message": "Please provide either a photo or a video evidence before submitting",
            }
        ), 400
    if evidence_count > 1:
        return jsonify(
            {"status": "error", "message": "Attach exactly one photo or one video, not both"}
        ), 400
    image_file = image_files[0] if image_files else None
    video_file = video_files[0] if video_files else None
    has_image = image_file is not None
    has_video = video_file is not None

    image_bytes = None
    if has_image:
        raw_image = image_file.stream.read(MAX_IMAGE_BYTES + 1)
        if len(raw_image) > MAX_IMAGE_BYTES:
            return jsonify({"status": "error", "message": "The uploaded image is too large"}), 413
        if not raw_image:
            return jsonify({"status": "error", "message": "The uploaded image is empty"}), 400

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw_image)) as source_image:
                    if source_image.format not in {"JPEG", "PNG"}:
                        raise ValueError("Only JPEG and PNG images are supported")
                    if source_image.width * source_image.height > MAX_IMAGE_PIXELS:
                        raise ValueError("The image dimensions are too large")
                    source_image.verify()

                with Image.open(io.BytesIO(raw_image)) as source_image:
                    prepared_image = ImageOps.exif_transpose(source_image)
                    if prepared_image.mode in {"RGBA", "LA"} or "transparency" in prepared_image.info:
                        rgba_image = prepared_image.convert("RGBA")
                        background = Image.new("RGB", rgba_image.size, "white")
                        background.paste(rgba_image, mask=rgba_image.getchannel("A"))
                        prepared_image = background
                    else:
                        prepared_image = prepared_image.convert("RGB")
                    prepared_image.thumbnail(
                        (1600, 1600),
                        Image.Resampling.LANCZOS,
                    )
                    output = io.BytesIO()
                    prepared_image.save(output, format="JPEG", quality=85, optimize=True)
                    image_bytes = output.getvalue()
        except (
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
            UnidentifiedImageError,
            OSError,
            ValueError,
        ):
            return jsonify(
                {
                    "status": "error",
                    "message": "Please upload a valid JPEG or PNG image.",
                }
            ), 400

    video_bytes = None
    video_extension = None
    if has_video:
        video_extension = Path(video_file.filename).suffix.lower()
        if (
            video_extension not in VIDEO_MIME_TYPES
            or video_file.mimetype != VIDEO_MIME_TYPES[video_extension]
        ):
            return jsonify(
                {"status": "error", "message": "Please upload an MP4, WebM, or MOV video"}
            ), 400
        video_bytes = video_file.stream.read(MAX_VIDEO_BYTES + 1)
        if len(video_bytes) > MAX_VIDEO_BYTES:
            return jsonify({"status": "error", "message": "The uploaded video is too large"}), 413
        if not video_bytes:
            return jsonify({"status": "error", "message": "The uploaded video is empty"}), 400

    user_exists = get_db_connection()
    try:
        user = user_exists.execute(
            "SELECT id FROM users WHERE id = ?",
            (current_user["id"],),
        ).fetchone()
    finally:
        user_exists.close()
    if user is None:
        return jsonify({"status": "error", "message": "User not found"}), 404

    ml_category = predict_category(description)
    ml_priority = predict_priority(description)
    category_confidence = predict_category_confidence(description, ml_category)
    priority_confidence = predict_priority_confidence(description, ml_priority)
    image_filename = f"{uuid.uuid4().hex}.jpg" if image_bytes is not None else None
    video_filename = (
        f"{uuid.uuid4().hex}{video_extension}" if video_bytes is not None else None
    )
    image_path = UPLOADS_DIRECTORY / image_filename if image_filename else None
    video_path = UPLOADS_DIRECTORY / video_filename if video_filename else None
    if image_path is not None:
        image_created = False
        try:
            UPLOADS_DIRECTORY.mkdir(parents=True, exist_ok=True)
            with image_path.open("xb") as saved_image:
                image_created = True
                saved_image.write(image_bytes)
        except OSError:
            if image_created:
                image_path.unlink(missing_ok=True)
            return jsonify(
                {"status": "error", "message": "Unable to store the uploaded image"}
            ), 500
    if video_path is not None:
        video_created = False
        try:
            UPLOADS_DIRECTORY.mkdir(parents=True, exist_ok=True)
            with video_path.open("xb") as saved_video:
                video_created = True
                saved_video.write(video_bytes)
        except OSError:
            if video_created:
                video_path.unlink(missing_ok=True)
            if image_path is not None:
                image_path.unlink(missing_ok=True)
            return jsonify(
                {"status": "error", "message": "Unable to store the uploaded video"}
            ), 500

    connection = None
    committed = False
    try:
        connection = get_db_connection()
        cursor = connection.execute(
            """
            INSERT INTO emergency_reports (
                user_id, emergency_type, description,
                latitude, longitude, priority, priority_source, image_filename,
                video_filename
            )
            VALUES (?, ?, ?, ?, ?, ?, 'ml', ?, ?)
            """,
            (
                current_user["id"],
                ml_category,
                description.strip(),
                latitude,
                longitude,
                ml_priority,
                image_filename,
                video_filename,
            ),
        )
        connection.commit()
        committed = True
    finally:
        if connection is not None:
            connection.close()
        if not committed and image_path is not None:
            image_path.unlink(missing_ok=True)
        if not committed and video_path is not None:
            video_path.unlink(missing_ok=True)

    return jsonify(
        {
            "status": "success",
            "message": "Emergency report submitted successfully",
            "report_id": cursor.lastrowid,
            "emergency_type": ml_category,
            "image_attached": image_filename is not None,
            "video_attached": video_filename is not None,
            "description": description.strip(),
            "priority": ml_priority,
            "status": "Received",
            "location_shared": latitude is not None,
            "predicted_category": ml_category,
            "category_confidence": category_confidence,
            "predicted_priority": ml_priority,
            "priority_confidence": priority_confidence,
            "priority_source": "ml",
        }
    ), 201


@app.get("/api/reports/user/<int:user_id>")
def get_user_reports(user_id):
    current_user = get_logged_in_user()
    if current_user is None:
        return jsonify({"status": "error", "message": "Please log in to view reports"}), 401
    if current_user["id"] != user_id:
        return jsonify({"status": "error", "message": "You can only view your own reports"}), 403

    connection = get_db_connection()
    try:
        user = connection.execute(
            "SELECT id FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if user is None:
            return jsonify({"status": "error", "message": "User not found"}), 404

        reports = connection.execute(
            """
            SELECT id, emergency_type, reported_emergency_type, description,
                   latitude, longitude,
                   CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL
                       THEN 1 ELSE 0 END AS location_shared,
                   CASE WHEN image_filename IS NOT NULL THEN 1 ELSE 0 END AS image_attached,
                   CASE WHEN video_filename IS NOT NULL THEN 1 ELSE 0 END AS video_attached,
                   priority, priority_source, status, created_at
            FROM emergency_reports
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (user_id,),
        ).fetchall()
    finally:
        connection.close()

    user_reports = []
    for report in reports:
        report_data = dict(report)
        report_data["category_confidence"] = predict_category_confidence(
            report_data["description"],
            report_data["emergency_type"],
        )
        report_data["priority_confidence"] = predict_priority_confidence(
            report_data["description"],
            report_data["priority"],
        )
        user_reports.append(report_data)

    return jsonify(
        {
            "status": "success",
            "reports": user_reports,
        }
    ), 200


@app.get("/api/reports/user/<int:user_id>/<int:report_id>/image")
def get_user_report_image(user_id, report_id):
    current_user = get_logged_in_user()
    if current_user is None:
        return jsonify({"status": "error", "message": "Please log in"}), 401
    if current_user["id"] != user_id:
        return jsonify({"status": "error", "message": "You can only view your own reports"}), 403

    connection = get_db_connection()
    try:
        report = connection.execute(
            """
            SELECT image_filename FROM emergency_reports
            WHERE id = ? AND user_id = ?
            """,
            (report_id, user_id),
        ).fetchone()
    finally:
        connection.close()

    if report is None or report["image_filename"] is None:
        return jsonify({"status": "error", "message": "Report image not found"}), 404
    image_filename = report["image_filename"]
    if not re.fullmatch(r"[a-f0-9]{32}\.jpg", image_filename):
        return jsonify({"status": "error", "message": "Report image not found"}), 404

    image_path = UPLOADS_DIRECTORY / image_filename
    if not image_path.is_file():
        return jsonify({"status": "error", "message": "Report image not found"}), 404

    response = send_file(
        image_path,
        mimetype="image/jpeg",
        as_attachment=False,
        conditional=True,
        max_age=0,
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/api/reports/user/<int:user_id>/<int:report_id>/video")
def get_user_report_video(user_id, report_id):
    current_user = get_logged_in_user()
    if current_user is None:
        return jsonify({"status": "error", "message": "Please log in"}), 401
    if current_user["id"] != user_id:
        return jsonify({"status": "error", "message": "You can only view your own reports"}), 403

    connection = get_db_connection()
    try:
        report = connection.execute(
            """
            SELECT video_filename FROM emergency_reports
            WHERE id = ? AND user_id = ?
            """,
            (report_id, user_id),
        ).fetchone()
    finally:
        connection.close()

    return send_report_video(report["video_filename"] if report else None)


def send_report_video(video_filename):
    if (
        not video_filename
        or not re.fullmatch(r"[a-f0-9]{32}\.(mp4|webm|mov)", video_filename)
    ):
        return jsonify({"status": "error", "message": "Report video not found"}), 404

    video_path = UPLOADS_DIRECTORY / video_filename
    if not video_path.is_file():
        return jsonify({"status": "error", "message": "Report video not found"}), 404

    extension = Path(video_filename).suffix
    response = send_file(
        video_path,
        mimetype=VIDEO_MIME_TYPES[extension],
        as_attachment=False,
        conditional=True,
        max_age=0,
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/api/responder/access/<int:user_id>")
def responder_access_test(user_id):
    current_user = get_logged_in_user()
    if current_user is None:
        return jsonify({"status": "error", "message": "Please log in"}), 401
    if current_user["id"] != user_id:
        return jsonify({"status": "error", "message": "Responder access required"}), 403

    user_exists, access_granted = check_responder_access(user_id)
    if not user_exists:
        return jsonify({"status": "error", "message": "User not found"}), 404
    if not access_granted:
        return jsonify({"status": "error", "message": "Responder access required"}), 403

    return jsonify(
        {
            "status": "success",
            "message": "Responder access granted",
        }
    ), 200


@app.get("/api/responder/reports/<int:user_id>")
def get_responder_reports(user_id):
    current_user = get_logged_in_user()
    if current_user is None:
        return jsonify({"status": "error", "message": "Please log in"}), 401
    if current_user["id"] != user_id:
        return jsonify({"status": "error", "message": "Responder access required"}), 403

    user_exists, access_granted = check_responder_access(user_id)
    if not user_exists:
        return jsonify({"status": "error", "message": "User not found"}), 404
    if not access_granted:
        return jsonify({"status": "error", "message": "Responder access required"}), 403

    connection = get_db_connection()
    try:
        reports = connection.execute(
            """
            SELECT reports.id, reports.user_id, users.name AS reporter_name,
                   reports.emergency_type, reports.reported_emergency_type,
                   reports.description,
                   reports.latitude, reports.longitude, reports.priority,
                   reports.priority_source,
                   reports.route_department, reports.route_destination,
                   reports.route_status,
                   CASE WHEN reports.image_filename IS NOT NULL THEN 1 ELSE 0 END AS image_attached,
                   CASE WHEN reports.video_filename IS NOT NULL THEN 1 ELSE 0 END AS video_attached,
                   reports.status, reports.created_at
            FROM emergency_reports AS reports
            JOIN users ON users.id = reports.user_id
            ORDER BY reports.created_at DESC, reports.id DESC
            """
        ).fetchall()
    finally:
        connection.close()

    responder_reports = []
    for report in reports:
        report_data = dict(report)
        report_data["category_confidence"] = predict_category_confidence(
            report_data["description"],
            report_data["emergency_type"],
        )
        report_data["priority_confidence"] = predict_priority_confidence(
            report_data["description"],
            report_data["priority"],
        )
        responder_reports.append(report_data)

    return jsonify(
        {
            "status": "success",
            "reports": responder_reports,
        }
    ), 200


def _load_intelligence_reports():
    connection = get_db_connection()
    try:
        rows = connection.execute(
            """
            SELECT id, emergency_type, description, latitude, longitude,
                   priority, route_department, route_destination, status,
                   created_at, resolved_at
            FROM emergency_reports
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()
    finally:
        connection.close()
    return [dict(row) for row in rows]


def _require_responder():
    current_user = get_logged_in_user()
    if current_user is None:
        return None, (jsonify({"status": "error", "message": "Please log in"}), 401)
    if current_user["role"] not in {"responder", "admin"}:
        return None, (
            jsonify({"status": "error", "message": "Responder access required"}),
            403,
        )
    return current_user, None


@app.get("/api/responder/intelligence/<int:user_id>")
def get_responder_intelligence(user_id):
    current_user, error_response = _require_responder()
    if error_response:
        return error_response
    if current_user["id"] != user_id:
        return jsonify({"status": "error", "message": "Responder access required"}), 403

    reports = _load_intelligence_reports()
    connection = get_db_connection()
    try:
        analytics = build_global_intelligence(reports, db_connection=connection)
    finally:
        connection.close()

    return jsonify(
        {
            "status": "success",
            "analytics": analytics,
        }
    ), 200


@app.get("/api/responder/reports/<int:report_id>/intelligence")
def get_report_intelligence(report_id):
    current_user, error_response = _require_responder()
    if error_response:
        return error_response

    try:
        radius_km = float(request.args.get("radius_km", "1"))
    except ValueError:
        return jsonify(
            {"status": "error", "message": "Analysis radius must be a valid number"}
        ), 400
    if not math.isfinite(radius_km) or not 0.1 <= radius_km <= 50:
        return jsonify(
            {"status": "error", "message": "Analysis radius must be between 0.1 and 50 km"}
        ), 400

    reports = _load_intelligence_reports()
    report = next((item for item in reports if item["id"] == report_id), None)
    if report is None:
        return jsonify({"status": "error", "message": "Emergency report not found"}), 404

    connection = get_db_connection()
    try:
        detail = connection.execute(
            """
            SELECT id, emergency_type, description, latitude, longitude,
                   priority, priority_source, status, created_at, resolved_at,
                   route_department, route_destination, route_status,
                   image_filename IS NOT NULL AS image_attached,
                   video_filename IS NOT NULL AS video_attached
            FROM emergency_reports WHERE id = ?
            """,
            (report_id,),
        ).fetchone()
        if detail is None:
            return jsonify({"status": "error", "message": "Emergency report not found"}), 404

        incident = dict(detail)
        incident["category_confidence"] = predict_category_confidence(
            incident["description"], incident["emergency_type"]
        )
        incident["priority_confidence"] = predict_priority_confidence(
            incident["description"], incident["priority"]
        )
        try:
            intelligence = build_incident_intelligence(
                report, reports, radius_km=radius_km, db_connection=connection
            )
        except ValueError as error:
            return jsonify({"status": "error", "message": str(error)}), 400

        return jsonify(
            {
                "status": "success",
                "incident": incident,
                "intelligence": intelligence,
            }
        ), 200
    finally:
        connection.close()


@app.get("/api/responder/government-data")
def get_government_data_api():
    current_user, error_response = _require_responder()
    if error_response:
        return error_response

    geographic_level = request.args.get("geographic_level")
    state = request.args.get("state")
    city = request.args.get("city")
    category = request.args.get("category")
    try:
        limit = min(max(int(request.args.get("limit", "100")), 1), 500)
    except ValueError:
        limit = 100

    connection = get_db_connection()
    try:
        from government_data import get_government_data_summary, query_government_records
        summary = get_government_data_summary(connection)
        records = query_government_records(
            connection=connection,
            geographic_level=geographic_level,
            state=state,
            city=city,
            category=category,
            limit=limit,
        )
        return jsonify({
            "status": "success",
            "summary": summary,
            "records": records,
        }), 200
    finally:
        connection.close()


@app.post("/api/responder/government-data/refresh")
def refresh_government_data_api():
    current_user, error_response = _require_responder()
    if error_response:
        return error_response

    connection = get_db_connection()
    try:
        from government_data import import_official_government_data
        result = import_official_government_data(connection=connection)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Official government data refresh encountered: {str(e)}",
        }), 500
    finally:
        connection.close()


@app.patch("/api/responder/reports/<int:report_id>/routing")
def route_report(report_id):
    current_user = get_logged_in_user()
    if current_user is None:
        return jsonify({"status": "error", "message": "Please log in"}), 401

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "A JSON request body is required"}), 400

    user_id = data.get("user_id")
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        return jsonify({"status": "error", "message": "A valid user_id is required"}), 400
    if user_id != current_user["id"]:
        return jsonify({"status": "error", "message": "Responder access required"}), 403

    user_exists, access_granted = check_responder_access(user_id)
    if not user_exists:
        return jsonify({"status": "error", "message": "User not found"}), 404
    if not access_granted:
        return jsonify({"status": "error", "message": "Responder access required"}), 403

    department = data.get("department")
    destination = data.get("destination")
    if (
        not isinstance(department, str)
        or department not in SIMULATED_ROUTING_DESTINATIONS
        or not isinstance(destination, str)
        or destination not in SIMULATED_ROUTING_DESTINATIONS[department]
    ):
        return jsonify(
            {"status": "error", "message": "Select a valid simulated department location"}
        ), 400

    connection = get_db_connection()
    try:
        report = connection.execute(
            "SELECT id FROM emergency_reports WHERE id = ?",
            (report_id,),
        ).fetchone()
        if report is None:
            return jsonify({"status": "error", "message": "Emergency report not found"}), 404

        connection.execute(
            """
            UPDATE emergency_reports
            SET route_department = ?, route_destination = ?, route_status = 'Sent'
            WHERE id = ?
            """,
            (department, destination, report_id),
        )
        connection.commit()
    finally:
        connection.close()

    return jsonify(
        {
            "status": "success",
            "message": "Prototype routing decision saved",
            "routing": {
                "department": department,
                "destination": destination,
                "status": "Sent",
            },
        }
    ), 200


@app.get("/api/responder/reports/<int:report_id>/image")
def get_report_image(report_id):
    current_user = get_logged_in_user()
    if current_user is None:
        return jsonify({"status": "error", "message": "Please log in"}), 401

    user_exists, access_granted = check_responder_access(current_user["id"])
    if not user_exists:
        return jsonify({"status": "error", "message": "User not found"}), 404
    if not access_granted:
        return jsonify({"status": "error", "message": "Responder access required"}), 403

    connection = get_db_connection()
    try:
        report = connection.execute(
            "SELECT image_filename FROM emergency_reports WHERE id = ?",
            (report_id,),
        ).fetchone()
    finally:
        connection.close()

    if report is None or report["image_filename"] is None:
        return jsonify({"status": "error", "message": "Report image not found"}), 404
    image_filename = report["image_filename"]
    if not re.fullmatch(r"[a-f0-9]{32}\.jpg", image_filename):
        return jsonify({"status": "error", "message": "Report image not found"}), 404

    image_path = UPLOADS_DIRECTORY / image_filename
    if not image_path.is_file():
        return jsonify({"status": "error", "message": "Report image not found"}), 404

    response = send_file(
        image_path,
        mimetype="image/jpeg",
        as_attachment=False,
        conditional=True,
        max_age=0,
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/api/responder/reports/<int:report_id>/video")
def get_report_video(report_id):
    current_user = get_logged_in_user()
    if current_user is None:
        return jsonify({"status": "error", "message": "Please log in"}), 401

    user_exists, access_granted = check_responder_access(current_user["id"])
    if not user_exists:
        return jsonify({"status": "error", "message": "User not found"}), 404
    if not access_granted:
        return jsonify({"status": "error", "message": "Responder access required"}), 403

    connection = get_db_connection()
    try:
        report = connection.execute(
            "SELECT video_filename FROM emergency_reports WHERE id = ?",
            (report_id,),
        ).fetchone()
    finally:
        connection.close()

    return send_report_video(report["video_filename"] if report else None)


@app.patch("/api/responder/reports/<int:report_id>/status")
def update_report_status(report_id):
    current_user = get_logged_in_user()
    if current_user is None:
        return jsonify({"status": "error", "message": "Please log in"}), 401

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "A JSON request body is required"}), 400

    user_id = data.get("user_id")
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        return jsonify({"status": "error", "message": "A valid user_id is required"}), 400
    if user_id != current_user["id"]:
        return jsonify({"status": "error", "message": "Responder access required"}), 403

    user_exists, access_granted = check_responder_access(user_id)
    if not user_exists:
        return jsonify({"status": "error", "message": "User not found"}), 404
    if not access_granted:
        return jsonify({"status": "error", "message": "Responder access required"}), 403

    requested_status = data.get("status")
    allowed_statuses = {"Received", "Assigned", "In Progress", "Resolved"}
    if not isinstance(requested_status, str) or requested_status not in allowed_statuses:
        return jsonify({"status": "error", "message": "Invalid report status"}), 400

    next_status = {
        "Received": "Assigned",
        "Assigned": "In Progress",
        "In Progress": "Resolved",
    }

    connection = get_db_connection()
    try:
        report = connection.execute(
            "SELECT id, status FROM emergency_reports WHERE id = ?",
            (report_id,),
        ).fetchone()
        if report is None:
            return jsonify({"status": "error", "message": "Emergency report not found"}), 404

        if next_status.get(report["status"]) != requested_status:
            return jsonify(
                {
                    "status": "error",
                    "message": f"Report status cannot change from {report['status']} to {requested_status}",
                }
            ), 400

        cursor = connection.execute(
            """
            UPDATE emergency_reports
            SET status = ?,
                resolved_at = CASE
                    WHEN ? = 'Resolved' THEN CURRENT_TIMESTAMP
                    ELSE resolved_at
                END
            WHERE id = ? AND status = ?
            """,
            (requested_status, requested_status, report_id, report["status"]),
        )
        if cursor.rowcount != 1:
            connection.rollback()
            return jsonify(
                {
                    "status": "error",
                    "message": "Report status changed. Please refresh and try again.",
                }
            ), 400
        connection.commit()
    finally:
        connection.close()

    return jsonify(
        {
            "status": "success",
            "message": "Report status updated successfully",
            "report": {
                "id": report_id,
                "status": requested_status,
            },
        }
    ), 200


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
