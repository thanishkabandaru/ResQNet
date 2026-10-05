import sqlite3
import tempfile
import unittest
from pathlib import Path

import database
from app import app
from database import get_db_connection, initialize_database
from ml_models import (
    PRIORITY_LABELS,
    _read_priority_dataset,
    evaluate_priority_model,
    load_models,
    predict_category,
    predict_priority,
)
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC


class PriorityModelTests(unittest.TestCase):
    def test_priority_pipeline_and_held_out_metrics(self):
        _, priority_model = load_models()
        self.assertIs(priority_model, load_models()[1])
        metrics = evaluate_priority_model()

        self.assertIsInstance(priority_model.named_steps["tfidf"], TfidfVectorizer)
        self.assertIsInstance(priority_model.named_steps["classifier"], LinearSVC)
        self.assertEqual(metrics["training_examples"] + metrics["test_examples"], 120)
        for name in ("accuracy", "precision_macro", "recall_macro", "f1_macro"):
            self.assertGreaterEqual(metrics[name], 0)
            self.assertLessEqual(metrics[name], 1)

        descriptions, priorities = _read_priority_dataset()
        self.assertEqual(len(descriptions), 120)
        self.assertEqual({label: priorities.count(label) for label in PRIORITY_LABELS},
                         {"Low": 40, "Medium": 40, "High": 40})
        self.assertEqual(
            predict_priority(
                "Person is unconscious and unable to breathe after collapsing"
            ),
            "High",
        )
        self.assertEqual(
            predict_priority("A small scrape stopped bleeding and the person feels well"),
            "Low",
        )
        self.assertEqual(
            predict_priority(
                "A small kitchen fire is contained but the room is smoky"
            ),
            "Medium",
        )
        self.assertEqual(
            predict_category("chest pain and shortness of breath"),
            "Medical Emergency",
        )
        self.assertEqual(
            predict_category("a building is on fire with smoke spreading"),
            "Fire",
        )
        self.assertEqual(
            predict_category("multiple vehicles collided on the highway"),
            "Accident",
        )


class ReportPriorityIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_database_path = database.DATABASE_PATH
        cls.temp_directory = tempfile.TemporaryDirectory()
        app.config.update(TESTING=True)

    @classmethod
    def tearDownClass(cls):
        database.DATABASE_PATH = cls.original_database_path
        cls.temp_directory.cleanup()

    def setUp(self):
        database.DATABASE_PATH = (
            Path(self.temp_directory.name) / f"test-{self._testMethodName}.db"
        )
        initialize_database()
        self.user_client = app.test_client()
        self.user = self._register_and_login(
            self.user_client, "reporter@example.test", "Project User"
        )

    def test_authentication_duplicate_registration_and_input_validation(self):
        user_response = self.user_client.get("/api/health")
        self.assertEqual(user_response.status_code, 200)

        registration_response = app.test_client().post(
            "/api/register",
            json={
                "name": "Second Test User",
                "email": "second-reporter@example.test",
                "password": "TestPassword123",
            },
        )
        self.assertEqual(registration_response.status_code, 201)
        self.assertNotIn("password_hash", registration_response.get_json())

        duplicate = self.user_client.post(
            "/api/register",
            json={
                "name": "Duplicate",
                "email": "reporter@example.test",
                "password": "TestPassword123",
            },
        )
        self.assertEqual(duplicate.status_code, 409)

        bad_login = app.test_client().post(
            "/api/login",
            json={"email": "reporter@example.test", "password": "wrong"},
        )
        self.assertEqual(bad_login.status_code, 401)
        correct_login = app.test_client().post(
            "/api/login",
            json={
                "email": "reporter@example.test",
                "password": "TestPassword123",
            },
        )
        self.assertEqual(correct_login.status_code, 200)
        self.assertNotIn("password_hash", correct_login.get_json())
        self.assertNotIn("password_hash", self.user)
        self.assertEqual(self.user["role"], "user")
        second_user_client = app.test_client()
        second_user_client.post(
            "/api/login",
            json={
                "email": "second-reporter@example.test",
                "password": "TestPassword123",
            },
        )
        self.assertEqual(
            second_user_client.get(
                f"/api/reports/user/{self.user['id']}"
            ).status_code,
            403,
        )

        missing_description = self.user_client.post(
            "/api/reports",
            json={"user_id": self.user["id"], "description": "  "},
        )
        self.assertEqual(missing_description.status_code, 400)

        invalid_type = self.user_client.post(
            "/api/reports",
            json={
                "user_id": self.user["id"],
                "description": "A reported emergency requiring assessment",
                "emergency_type": "Imaginary Category",
            },
        )
        self.assertEqual(invalid_type.status_code, 400)

    def tearDown(self):
        connection = get_db_connection()
        try:
            connection.execute("DELETE FROM emergency_reports")
            connection.execute("DELETE FROM users")
            connection.commit()
        finally:
            connection.close()

    def _register_and_login(self, client, email, name):
        registration = client.post(
            "/api/register",
            json={"name": name, "email": email, "password": "TestPassword123"},
        )
        self.assertEqual(registration.status_code, 201)
        login = client.post(
            "/api/login",
            json={"email": email, "password": "TestPassword123"},
        )
        self.assertEqual(login.status_code, 200)
        return login.get_json()["user"]

    def test_admin_role_is_authorized_for_responder_dashboard(self):
        admin = self._register_and_login(
            app.test_client(), "admin@example.test", "Project Admin"
        )
        connection = get_db_connection()
        try:
            connection.execute(
                "UPDATE users SET role = 'admin' WHERE id = ?",
                (admin["id"],),
            )
            connection.commit()
        finally:
            connection.close()

        admin_client = app.test_client()
        admin = self._register_responder_login_for_email(
            admin_client, "admin@example.test"
        )
        response = admin_client.get(f"/api/responder/reports/{admin['id']}")
        self.assertEqual(response.status_code, 200)

    def _register_responder_login_for_email(self, client, email):
        login = client.post(
            "/api/login",
            json={"email": email, "password": "TestPassword123"},
        )
        self.assertEqual(login.status_code, 200)
        return login.get_json()["user"]

    def test_api_storage_authorization_map_data_and_status_workflow(self):
        self.assertEqual(self.user_client.get("/api/health").status_code, 200)
        self.assertEqual(self.user_client.get("/api/db-test").status_code, 200)

        test_reports = (
            (
                "Person is unconscious and unable to breathe after collapsing",
                "High",
                12.34,
                56.78,
            ),
            (
                "A small kitchen fire is contained but the room is smoky",
                "Medium",
                None,
                None,
            ),
            (
                "A small scrape stopped bleeding and the person feels well",
                "Low",
                None,
                None,
            ),
        )
        created_reports = {}
        for description, expected_priority, latitude, longitude in test_reports:
            report_data = {"user_id": self.user["id"], "description": description}
            if latitude is not None:
                report_data.update(latitude=latitude, longitude=longitude)
            submitted = self.user_client.post("/api/reports", json=report_data)
            self.assertEqual(submitted.status_code, 201)
            submitted_data = submitted.get_json()
            self.assertEqual(
                submitted_data["predicted_priority"], expected_priority
            )
            self.assertEqual(submitted_data["priority_source"], "ml")
            created_reports[expected_priority] = submitted_data["report_id"]

        self.assertEqual(len(set(created_reports.values())), 3)
        high_report_id = created_reports["High"]
        connection = get_db_connection()
        try:
            stored_reports = connection.execute(
                """
                SELECT id, priority, priority_source, latitude, longitude, status
                FROM emergency_reports
                """
            ).fetchall()
        finally:
            connection.close()
        stored_by_id = {report["id"]: report for report in stored_reports}
        for priority, report_id in created_reports.items():
            self.assertEqual(stored_by_id[report_id]["priority"], priority)
            self.assertEqual(stored_by_id[report_id]["priority_source"], "ml")
        self.assertEqual(
            (
                stored_by_id[high_report_id]["latitude"],
                stored_by_id[high_report_id]["longitude"],
            ),
            (12.34, 56.78),
        )
        self.assertEqual(stored_by_id[high_report_id]["status"], "Received")

        user_reports = self.user_client.get(
            f"/api/reports/user/{self.user['id']}"
        ).get_json()["reports"]
        self.assertEqual(
            [report["id"] for report in user_reports],
            sorted((report["id"] for report in user_reports), reverse=True),
        )
        high_user_report = next(
            report for report in user_reports if report["id"] == high_report_id
        )
        self.assertEqual(high_user_report["priority_source"], "ml")
        self.assertEqual(high_user_report["location_shared"], 1)
        self.assertNotIn("latitude", high_user_report)
        self.assertNotIn("longitude", high_user_report)
        self.assertEqual(
            self.user_client.get(
                f"/api/responder/reports/{self.user['id']}"
            ).status_code,
            403,
        )
        self.assertEqual(
            app.test_client().get(
                f"/api/responder/reports/{self.user['id']}"
            ).status_code,
            401,
        )

        responder_client = app.test_client()
        responder = self._register_and_login(
            responder_client, "responder@example.test", "Project Responder"
        )
        connection = get_db_connection()
        try:
            connection.execute(
                "UPDATE users SET role = 'responder' WHERE id = ?",
                (responder["id"],),
            )
            connection.commit()
        finally:
            connection.close()
        responder_client.post("/api/logout")
        responder = self._register_responder_login(responder_client)

        responder_reports = responder_client.get(
            f"/api/responder/reports/{responder['id']}"
        ).get_json()["reports"]
        report = next(
            item for item in responder_reports if item["id"] == high_report_id
        )
        self.assertEqual(report["priority"], "High")
        self.assertEqual(report["priority_source"], "ml")
        self.assertEqual((report["latitude"], report["longitude"]), (12.34, 56.78))

        invalid_skip = responder_client.patch(
            f"/api/responder/reports/{high_report_id}/status",
            json={"user_id": responder["id"], "status": "In Progress"},
        )
        self.assertEqual(invalid_skip.status_code, 400)
        for status in ("Assigned", "In Progress", "Resolved"):
            response = responder_client.patch(
                f"/api/responder/reports/{high_report_id}/status",
                json={"user_id": responder["id"], "status": status},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["report"]["status"], status)

        after_resolved = responder_client.patch(
            f"/api/responder/reports/{high_report_id}/status",
            json={"user_id": responder["id"], "status": "Assigned"},
        )
        self.assertEqual(after_resolved.status_code, 400)
        user_reports_after_resolution = self.user_client.get(
            f"/api/reports/user/{self.user['id']}"
        ).get_json()["reports"]
        resolved_user_report = next(
            item for item in user_reports_after_resolution
            if item["id"] == high_report_id
        )
        self.assertEqual(resolved_user_report["status"], "Resolved")
        self.assertEqual(resolved_user_report["priority"], "High")
        self.assertEqual(
            resolved_user_report["emergency_type"], "Medical Emergency"
        )
        self.assertEqual(resolved_user_report["location_shared"], 1)

    def _register_responder_login(self, client):
        login = client.post(
            "/api/login",
            json={
                "email": "responder@example.test",
                "password": "TestPassword123",
            },
        )
        self.assertEqual(login.status_code, 200)
        return login.get_json()["user"]


class DatabaseMigrationTests(unittest.TestCase):
    def test_existing_reports_receive_default_priority_source(self):
        original_database_path = database.DATABASE_PATH
        try:
            with tempfile.TemporaryDirectory() as temp_directory:
                database.DATABASE_PATH = Path(temp_directory) / "legacy.db"
                connection = sqlite3.connect(database.DATABASE_PATH)
                try:
                    connection.executescript(
                        """
                        CREATE TABLE users (
                            id INTEGER PRIMARY KEY,
                            name TEXT NOT NULL,
                            email TEXT NOT NULL UNIQUE,
                            password_hash TEXT NOT NULL,
                            role TEXT NOT NULL,
                            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
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
                            id, user_id, emergency_type, description, priority
                        ) VALUES (1, 1, 'Other', 'Existing report', 'Medium');
                        """
                    )
                    connection.commit()
                finally:
                    connection.close()

                initialize_database()
                connection = get_db_connection()
                try:
                    migrated = connection.execute(
                        "SELECT priority_source FROM emergency_reports WHERE id = 1"
                    ).fetchone()
                finally:
                    connection.close()
                self.assertEqual(migrated["priority_source"], "default")
        finally:
            database.DATABASE_PATH = original_database_path


if __name__ == "__main__":
    unittest.main()
