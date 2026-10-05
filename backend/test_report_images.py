import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from werkzeug.security import generate_password_hash

import app as resqnet_app
import database
from database import get_db_connection, initialize_database


class EvidencePhotoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_database_path = database.DATABASE_PATH
        cls.original_uploads_directory = resqnet_app.UPLOADS_DIRECTORY
        cls.temp_directory = tempfile.TemporaryDirectory()
        resqnet_app.app.config.update(TESTING=True)

    @classmethod
    def tearDownClass(cls):
        database.DATABASE_PATH = cls.original_database_path
        resqnet_app.UPLOADS_DIRECTORY = cls.original_uploads_directory
        cls.temp_directory.cleanup()

    def setUp(self):
        test_directory = Path(self.temp_directory.name) / self._testMethodName
        test_directory.mkdir()
        database.DATABASE_PATH = test_directory / "test.db"
        resqnet_app.UPLOADS_DIRECTORY = test_directory / "private_uploads"
        initialize_database()

        self.user_client = resqnet_app.app.test_client()
        registration = self.user_client.post(
            "/api/register",
            json={
                "name": "Photo Test User",
                "email": "photo-user@example.test",
                "password": "TestPassword123",
            },
        )
        self.assertEqual(registration.status_code, 201)
        login = self.user_client.post(
            "/api/login",
            json={
                "email": "photo-user@example.test",
                "password": "TestPassword123",
            },
        )
        self.assertEqual(login.status_code, 200)
        self.user_id = login.get_json()["user"]["id"]

    def tearDown(self):
        connection = get_db_connection()
        try:
            connection.execute("DELETE FROM emergency_reports")
            connection.execute("DELETE FROM users")
            connection.commit()
        finally:
            connection.close()

    def test_multipart_reports_with_and_without_photo_keep_text_ml_and_private_gps(self):
        with_photo = self.submit_report(
            image=self.png_upload(),
            latitude="12.34",
            longitude="56.78",
        )
        self.assertEqual(with_photo.status_code, 201)
        photo_result = with_photo.get_json()
        self.assertTrue(photo_result["image_attached"])
        self.assertEqual(photo_result["reported_emergency_type"], "Other")
        self.assertEqual(photo_result["emergency_type"], "Fire")
        self.assertEqual(photo_result["status"], "Received")
        self.assertNotIn("latitude", photo_result)
        self.assertNotIn("longitude", photo_result)
        self.assertEqual(photo_result["predicted_category"], "Fire")
        self.assertEqual(photo_result["priority_source"], "ml")

        without_photo = self.submit_report(
            description="A person is unconscious and unable to breathe"
        )
        self.assertEqual(without_photo.status_code, 201)
        self.assertFalse(without_photo.get_json()["image_attached"])
        self.assertIn("predicted_category", without_photo.get_json())
        self.assertIn("predicted_priority", without_photo.get_json())

        connection = get_db_connection()
        try:
            reports = connection.execute(
                """
                SELECT id, emergency_type, reported_emergency_type, image_filename,
                       latitude, longitude, priority, priority_source
                FROM emergency_reports
                ORDER BY id
                """
            ).fetchall()
        finally:
            connection.close()

        self.assertEqual(reports[0]["emergency_type"], "Fire")
        self.assertEqual(reports[0]["reported_emergency_type"], "Other")
        self.assertEqual((reports[0]["latitude"], reports[0]["longitude"]), (12.34, 56.78))
        self.assertRegex(reports[0]["image_filename"], r"^[a-f0-9]{32}\.jpg$")
        self.assertTrue((resqnet_app.UPLOADS_DIRECTORY / reports[0]["image_filename"]).is_file())
        self.assertIsNone(reports[1]["image_filename"])
        self.assertIsNone(reports[1]["latitude"])
        self.assertEqual(reports[0]["priority_source"], "ml")

        user_report = self.user_client.get(
            f"/api/reports/user/{self.user_id}"
        ).get_json()["reports"]
        user_report = next(
            report for report in user_report if report["id"] == photo_result["report_id"]
        )
        self.assertTrue(user_report["image_attached"])
        self.assertEqual(user_report["reported_emergency_type"], "Other")
        self.assertNotIn("image_filename", user_report)
        self.assertNotIn("latitude", user_report)
        self.assertNotIn("longitude", user_report)

    def test_invalid_or_oversized_images_are_rejected(self):
        invalid_image = self.submit_report(
            image=(io.BytesIO(b"not an image"), "evidence.png", "image/png")
        )
        self.assertEqual(invalid_image.status_code, 400)

        oversized_image = self.submit_report(
            image=(
                io.BytesIO(b"x" * (8 * 1024 * 1024 + 1)),
                "large.jpg",
                "image/jpeg",
            )
        )
        self.assertEqual(oversized_image.status_code, 413)

    def test_bad_category_and_incomplete_location_are_rejected(self):
        invalid_category = self.submit_report(emergency_type="Unlisted")
        self.assertEqual(invalid_category.status_code, 400)

        incomplete_location = self.submit_report(latitude="12.34")
        self.assertEqual(incomplete_location.status_code, 400)

    def test_legacy_database_migration_preserves_reports(self):
        original_database_path = database.DATABASE_PATH
        legacy_path = Path(self.temp_directory.name) / "legacy.db"
        try:
            import sqlite3

            connection = sqlite3.connect(legacy_path)
            try:
                connection.executescript(
                    """
                    CREATE TABLE users (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        email TEXT NOT NULL UNIQUE,
                        password_hash TEXT NOT NULL,
                        role TEXT NOT NULL
                    );
                    CREATE TABLE emergency_reports (
                        id INTEGER PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        emergency_type TEXT NOT NULL,
                        description TEXT NOT NULL,
                        latitude REAL,
                        longitude REAL,
                        priority TEXT NOT NULL DEFAULT 'Medium',
                        status TEXT NOT NULL DEFAULT 'Received',
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    INSERT INTO users (id, name, email, password_hash, role)
                    VALUES (1, 'Legacy User', 'legacy@example.test', 'hash', 'user');
                    INSERT INTO emergency_reports (
                        id, user_id, emergency_type, description
                    ) VALUES (1, 1, 'Other', 'Existing report');
                    """
                )
                connection.commit()
            finally:
                connection.close()

            database.DATABASE_PATH = legacy_path
            initialize_database()
            connection = get_db_connection()
            try:
                migrated = connection.execute(
                    """
                    SELECT id, description, priority_source,
                           reported_emergency_type, image_filename
                    FROM emergency_reports WHERE id = 1
                    """
                ).fetchone()
            finally:
                connection.close()
        finally:
            database.DATABASE_PATH = original_database_path

        self.assertEqual(migrated["description"], "Existing report")
        self.assertEqual(migrated["priority_source"], "default")
        self.assertIsNone(migrated["reported_emergency_type"])
        self.assertIsNone(migrated["image_filename"])

    def test_only_authorized_responders_can_retrieve_report_images(self):
        submitted = self.submit_report(image=self.png_upload())
        report_id = submitted.get_json()["report_id"]

        anonymous_response = resqnet_app.app.test_client().get(
            f"/api/responder/reports/{report_id}/image"
        )
        self.assertEqual(anonymous_response.status_code, 401)
        self.assertEqual(
            self.user_client.get(
                f"/api/responder/reports/{report_id}/image"
            ).status_code,
            403,
        )

        connection = get_db_connection()
        try:
            connection.execute(
                """
                INSERT INTO users (name, email, password_hash, role)
                VALUES (?, ?, ?, 'responder')
                """,
                (
                    "Responder",
                    "responder@example.test",
                    generate_password_hash("TestPassword123"),
                ),
            )
            connection.commit()
        finally:
            connection.close()

        responder_client = resqnet_app.app.test_client()
        responder_login = responder_client.post(
            "/api/login",
            json={
                "email": "responder@example.test",
                "password": "TestPassword123",
            },
        )
        self.assertEqual(responder_login.status_code, 200)
        responder_id = responder_login.get_json()["user"]["id"]

        report_list = responder_client.get(
            f"/api/responder/reports/{responder_id}"
        ).get_json()["reports"]
        report = next(item for item in report_list if item["id"] == report_id)
        self.assertTrue(report["image_attached"])
        self.assertEqual(report["reported_emergency_type"], "Other")

        image_response = responder_client.get(
            f"/api/responder/reports/{report_id}/image"
        )
        self.assertEqual(image_response.status_code, 200)
        self.assertEqual(image_response.mimetype, "image/jpeg")
        self.assertEqual(image_response.headers["Cache-Control"], "private, no-store")
        self.assertEqual(image_response.headers["X-Content-Type-Options"], "nosniff")
        with Image.open(io.BytesIO(image_response.data)) as saved_image:
            self.assertEqual(saved_image.format, "JPEG")
        image_response.close()

    def submit_report(
        self,
        image=None,
        latitude=None,
        longitude=None,
        description="A building is on fire and smoke is spreading",
        emergency_type="Other",
    ):
        data = {
            "user_id": str(self.user_id),
            "emergency_type": emergency_type,
            "description": description,
        }
        if latitude is not None:
            data["latitude"] = latitude
        if longitude is not None:
            data["longitude"] = longitude
        if image is not None:
            data["image"] = image
        return self.user_client.post(
            "/api/reports/with-image",
            data=data,
            content_type="multipart/form-data",
        )

    @staticmethod
    def png_upload():
        image_bytes = io.BytesIO()
        Image.new("RGB", (16, 12), color=(220, 30, 30)).save(image_bytes, format="PNG")
        image_bytes.seek(0)
        return image_bytes, "evidence.png", "image/png"


if __name__ == "__main__":
    unittest.main()
