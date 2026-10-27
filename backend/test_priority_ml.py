import io
import sqlite3
import tempfile
import unittest
from pathlib import Path

import database
from app import app
from database import get_db_connection, initialize_database
from ml_models import (
    CATEGORY_LABELS,
    PRIORITY_LABELS,
    _load_confidence_models,
    _read_category_dataset,
    _read_priority_dataset,
    evaluate_priority_model,
    load_models,
    predict_category,
    predict_category_confidence,
    predict_priority,
    predict_priority_confidence,
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

    def test_category_model_supports_all_twelve_categories(self):
        _, categories = _read_category_dataset()
        self.assertEqual(set(categories), set(CATEGORY_LABELS))
        self.assertEqual(len(categories), 2400)
        self.assertEqual(
            {label: categories.count(label) for label in CATEGORY_LABELS},
            {label: 200 for label in CATEGORY_LABELS},
        )

        examples = (
            (
                "A person has disappeared and cannot be located by family members",
                "Missing Person",
            ),
            (
                "A large tree has fallen across the road and is blocking traffic",
                "Road Hazard",
            ),
            ("A building is on fire and smoke is spreading", "Fire"),
            ("Two vehicles collided and people are injured", "Accident"),
            ("A person has severe chest pain and difficulty breathing", "Medical Emergency"),
            ("A wallet was stolen from a person's bag", "Theft"),
            (
                "Someone entered a house illegally and threatened the occupants",
                "Crime",
            ),
            ("There is a strong smell of cooking gas and a suspected gas leak", "Gas Leak"),
            (
                "An electrical wire has fallen onto the street and is sparking",
                "Electrical Emergency",
            ),
            (
                "A building has collapsed after structural failure",
                "Building Collapse",
            ),
            (
                "Heavy flooding has affected the surrounding area",
                "Natural Disaster",
            ),
            (
                "An unusual emergency that does not match the other categories",
                "Other Emergency",
            ),
            ("tree on the road", "Road Hazard"),
            ("there is a tree on the road", "Road Hazard"),
            ("fallen tree blocking traffic", "Road Hazard"),
            ("vehicle crashed into a road barrier", "Accident"),
            ("patient has chest pain", "Medical Emergency"),
            ("large fire in a building", "Fire"),
            ("person has disappeared", "Missing Person"),
            ("wallet stolen from bag", "Theft"),
            ("gas smell coming from kitchen", "Gas Leak"),
            ("electric wire is sparking on the road", "Electrical Emergency"),
            ("building collapsed", "Building Collapse"),
            ("flood water entered the street", "Natural Disaster"),
        )
        for description, expected in examples:
            with self.subTest(description=description):
                prediction = predict_category(description)
                self.assertEqual(prediction, expected)
                confidence = predict_category_confidence(description, prediction)
                self.assertIsInstance(confidence, float)
                self.assertGreaterEqual(confidence, 0)
                self.assertLessEqual(confidence, 1)

    def test_calibrated_confidence_uses_existing_model_labels(self):
        cases = (
            (
                "chest pain and shortness of breath",
                predict_category,
                predict_category_confidence,
            ),
            (
                "Person is unconscious and unable to breathe after collapsing",
                predict_priority,
                predict_priority_confidence,
            ),
        )
        for description, predict, predict_confidence in cases:
            with self.subTest(predictor=predict.__name__):
                prediction = predict(description)
                confidence = predict_confidence(description, prediction)
                category_calibrator, priority_calibrator = _load_confidence_models()
                calibrated_model = (
                    category_calibrator
                    if predict is predict_category
                    else priority_calibrator
                )
                expected_confidence = calibrated_model.predict_proba([description])[0][
                    list(calibrated_model.classes_).index(prediction)
                ]
                self.assertIsInstance(confidence, float)
                self.assertGreaterEqual(confidence, 0)
                self.assertLessEqual(confidence, 1)
                self.assertAlmostEqual(confidence, expected_confidence)
                self.assertEqual(predict(description), prediction)


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
        database_response = self.user_client.get("/api/db-test")
        self.assertEqual(database_response.status_code, 200)

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
        login_client = app.test_client()
        correct_login = login_client.post(
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
        session_cookie = correct_login.headers["Set-Cookie"]
        self.assertIn("expires=", session_cookie.lower())
        self.assertIn("HttpOnly", session_cookie)
        self.assertIn("SameSite=Lax", session_cookie)
        current_user = login_client.get("/api/me")
        self.assertEqual(current_user.status_code, 200)
        self.assertEqual(current_user.get_json()["user"]["id"], self.user["id"])
        self.assertEqual(current_user.headers["Cache-Control"], "no-store")
        self.assertNotIn("password_hash", current_user.get_json()["user"])
        logout = login_client.post("/api/logout")
        self.assertEqual(logout.status_code, 200)
        self.assertEqual(login_client.get("/api/me").status_code, 401)
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

        report_without_evidence = self.user_client.post(
            "/api/reports",
            json={
                "user_id": self.user["id"],
                "description": "A reported emergency requiring assessment",
                "latitude": 12.34,
                "longitude": 56.78,
            },
        )
        self.assertEqual(report_without_evidence.status_code, 400)
        self.assertIn("either a photo or a video", report_without_evidence.get_json()["message"])

        report_with_evidence = self.submit_evidence_report(
            "A reported emergency requiring assessment",
            latitude=12.34,
            longitude=56.78,
        )
        self.assertEqual(report_with_evidence.status_code, 201)
        self.assertIn("predicted_category", report_with_evidence.get_json())

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
            submitted = self.submit_evidence_report(
                description,
                latitude=latitude or 12.34,
                longitude=longitude or 56.78,
            )
            self.assertEqual(submitted.status_code, 201)
            submitted_data = submitted.get_json()
            self.assertEqual(
                submitted_data["predicted_priority"], expected_priority
            )
            self.assertGreaterEqual(submitted_data["category_confidence"], 0)
            self.assertLessEqual(submitted_data["category_confidence"], 1)
            self.assertGreaterEqual(submitted_data["priority_confidence"], 0)
            self.assertLessEqual(submitted_data["priority_confidence"], 1)
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
        self.assertEqual(
            (high_user_report["latitude"], high_user_report["longitude"]),
            (12.34, 56.78),
        )
        self.assertGreaterEqual(high_user_report["category_confidence"], 0)
        self.assertLessEqual(high_user_report["category_confidence"], 1)
        self.assertGreaterEqual(high_user_report["priority_confidence"], 0)
        self.assertLessEqual(high_user_report["priority_confidence"], 1)
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
        self.assertGreaterEqual(report["category_confidence"], 0)
        self.assertLessEqual(report["category_confidence"], 1)
        self.assertGreaterEqual(report["priority_confidence"], 0)
        self.assertLessEqual(report["priority_confidence"], 1)
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
        connection = get_db_connection()
        try:
            resolved_timestamp = connection.execute(
                "SELECT resolved_at FROM emergency_reports WHERE id = ?",
                (high_report_id,),
            ).fetchone()["resolved_at"]
        finally:
            connection.close()
        self.assertIsNotNone(resolved_timestamp)
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

    def submit_evidence_report(self, description, latitude, longitude):
        return self.user_client.post(
            "/api/reports/with-image",
            data={
                "user_id": str(self.user["id"]),
                "description": description,
                "latitude": str(latitude),
                "longitude": str(longitude),
                "video": (io.BytesIO(b"test video"), "evidence.webm", "video/webm"),
            },
            content_type="multipart/form-data",
        )


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
