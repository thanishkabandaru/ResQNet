import io
import math
import os
import re
import secrets
import sqlite3
import uuid
import warnings
from pathlib import Path

from flask import Flask, jsonify, request, send_file, session
from flask_cors import CORS
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.security import check_password_hash, generate_password_hash

from authorization import check_responder_access, get_logged_in_user
from database import get_db_connection, initialize_database
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
app.config.update(
    SECRET_KEY=os.environ.get("RESQNET_SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("RESQNET_COOKIE_SECURE", "false").lower()
    == "true",
)
CORS(
    app,
    supports_credentials=True,
    origins=["http://localhost:5173", "http://127.0.0.1:5173"],
)

initialize_database()

ALLOWED_EMERGENCY_TYPES = {"Medical Emergency", "Accident", "Fire", "Other"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_REPORT_REQUEST_BYTES = MAX_IMAGE_BYTES + 128 * 1024
MAX_IMAGE_PIXELS = 20_000_000
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
    emergency_type = data.get("emergency_type")
    allowed_types = {"Medical Emergency", "Accident", "Fire", "Other"}

    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        return jsonify({"status": "error", "message": "A valid user_id is required"}), 400
    if user_id != current_user["id"]:
        return jsonify({"status": "error", "message": "You can only submit reports for your own account"}), 403
    if current_user["role"] != "user":
        return jsonify({"status": "error", "message": "Only user accounts can submit reports"}), 403
    if not isinstance(description, str) or not description.strip():
        return jsonify({"status": "error", "message": "A description is required"}), 400
    if emergency_type is not None and (
        not isinstance(emergency_type, str) or emergency_type not in allowed_types
    ):
        return jsonify({"status": "error", "message": "A valid emergency_type is required"}), 400

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

    connection = get_db_connection()
    try:
        user = connection.execute(
            "SELECT id FROM users WHERE id = ?",
            (current_user["id"],),
        ).fetchone()
        if user is None:
            return jsonify({"status": "error", "message": "User not found"}), 404

        # Use ML models to predict category and priority from description
        ml_category = predict_category(description)
        ml_priority = predict_priority(description)
        category_confidence = predict_category_confidence(description, ml_category)
        priority_confidence = predict_priority_confidence(description, ml_priority)

        cursor = connection.execute(
            """
            INSERT INTO emergency_reports (
                user_id, emergency_type, description, latitude, longitude,
                priority, priority_source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                current_user["id"],
                ml_category,
                description.strip(),
                latitude,
                longitude,
                ml_priority,
                "ml",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    return jsonify(
        {
            "status": "success",
            "message": "Emergency report submitted successfully",
            "report_id": cursor.lastrowid,
            "predicted_category": ml_category,
            "category_confidence": category_confidence,
            "predicted_priority": ml_priority,
            "priority_confidence": priority_confidence,
            "priority_source": "ml",
        }
    ), 201


@app.post("/api/reports/with-image")
def create_report_with_image():
    current_user = get_logged_in_user()
    if current_user is None:
        return jsonify({"status": "error", "message": "Please log in to submit a report"}), 401
    if current_user["role"] != "user":
        return jsonify({"status": "error", "message": "Only user accounts can submit reports"}), 403
    if request.content_length and request.content_length > MAX_REPORT_REQUEST_BYTES:
        return jsonify({"status": "error", "message": "The uploaded image is too large"}), 413

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

    emergency_type = form.get("emergency_type")
    if emergency_type not in ALLOWED_EMERGENCY_TYPES:
        return jsonify({"status": "error", "message": "A valid emergency_type is required"}), 400

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

    image_file = request.files.get("image")
    image_bytes = None
    if image_file and image_file.filename:
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
    image_path = UPLOADS_DIRECTORY / image_filename if image_filename else None
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

    connection = None
    committed = False
    try:
        connection = get_db_connection()
        cursor = connection.execute(
            """
            INSERT INTO emergency_reports (
                user_id, emergency_type, reported_emergency_type, description,
                latitude, longitude, priority, priority_source, image_filename
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'ml', ?)
            """,
            (
                current_user["id"],
                ml_category,
                emergency_type,
                description.strip(),
                latitude,
                longitude,
                ml_priority,
                image_filename,
            ),
        )
        connection.commit()
        committed = True
    finally:
        if connection is not None:
            connection.close()
        if not committed and image_path is not None:
            image_path.unlink(missing_ok=True)

    return jsonify(
        {
            "status": "success",
            "message": "Emergency report submitted successfully",
            "report_id": cursor.lastrowid,
            "emergency_type": ml_category,
            "image_attached": image_filename is not None,
            "reported_emergency_type": emergency_type,
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
                   CASE
                       WHEN latitude IS NOT NULL AND longitude IS NOT NULL THEN 1
                       ELSE 0
                   END AS location_shared,
                   CASE WHEN image_filename IS NOT NULL THEN 1 ELSE 0 END AS image_attached,
                   priority, priority_source, status, created_at
            FROM emergency_reports
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (user_id,),
        ).fetchall()
    finally:
        connection.close()

    return jsonify(
        {
            "status": "success",
            "reports": [dict(report) for report in reports],
        }
    ), 200


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
            SET status = ?
            WHERE id = ? AND status = ?
            """,
            (requested_status, report_id, report["status"]),
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
