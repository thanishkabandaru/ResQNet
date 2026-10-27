import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import database
from app import app
from database import get_db_connection, initialize_database
from intelligence import (
    build_global_intelligence,
    build_incident_intelligence,
    haversine_km,
    parse_utc,
)
from werkzeug.security import generate_password_hash


class IntelligenceCalculationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)

    def test_haversine_and_utc_parser_use_real_coordinates_and_times(self):
        self.assertAlmostEqual(haversine_km(0, 0, 0, 1), 111.195, places=2)
        self.assertEqual(
            parse_utc("2026-10-05 12:00:00"),
            datetime(2026, 10, 5, 12, tzinfo=timezone.utc),
        )
        self.assertIsNone(parse_utc("not-a-date"))

    def test_global_analytics_and_dbscan_use_report_records(self):
        reports = [
            {
                "id": report_id,
                "emergency_type": "Accident",
                "priority": "High" if report_id == 1 else "Medium",
                "status": "Resolved" if report_id == 1 else "Received",
                "latitude": 17.385 + report_id * 0.0002,
                "longitude": 78.4867,
                "created_at": (self.now - timedelta(days=report_id)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "resolved_at": (
                    (self.now - timedelta(days=report_id) + timedelta(minutes=45))
                    .strftime("%Y-%m-%d %H:%M:%S")
                    if report_id == 1 else None
                ),
            }
            for report_id in range(1, 5)
        ]
        analytics = build_global_intelligence(reports, now=self.now)
        self.assertEqual(analytics["kpis"]["total_incidents"], 4)
        self.assertEqual(analytics["kpis"]["high_priority_incidents"], 1)
        self.assertEqual(analytics["kpis"]["average_resolution_minutes"], 45)
        self.assertEqual(analytics["hotspots"]["count"], 1)
        self.assertEqual(analytics["hotspots"]["incident_count"], 4)
        self.assertEqual(analytics["kpis"]["repeat_incidents"], 4)
        self.assertFalse(analytics["official_historical_data"]["available"])
        self.assertFalse(analytics["future_risk_model"]["available"])

    def test_area_analytics_similarity_risk_and_recommendations_are_dynamic(self):
        report_time = self.now.strftime("%Y-%m-%d %H:%M:%S")
        report = {
            "id": 10,
            "emergency_type": "Fire",
            "priority": "High",
            "status": "Received",
            "latitude": 17.385,
            "longitude": 78.4867,
            "created_at": report_time,
            "resolved_at": None,
        }
        previous = [
            {
                "id": index,
                "emergency_type": "Fire",
                "priority": "High",
                "status": "Resolved" if index == 1 else "Assigned",
                "latitude": 17.385 + index * 0.0002,
                "longitude": 78.4867,
                "created_at": (
                    self.now - timedelta(days=index)
                ).strftime("%Y-%m-%d %H:%M:%S"),
                "resolved_at": (
                    (self.now - timedelta(days=index) + timedelta(minutes=30))
                    .strftime("%Y-%m-%d %H:%M:%S")
                    if index == 1 else None
                ),
                "route_department": "Fire & Rescue",
                "route_destination": "Simulated Fire Point",
            }
            for index in range(1, 4)
        ]
        result = build_incident_intelligence(
            report, [report, *previous], radius_km=1, now=self.now
        )
        self.assertEqual(result["previous_nearby_count"], 3)
        self.assertEqual(result["area_analytics"]["total_incidents"], 4)
        self.assertEqual(len(result["similar_incidents"]), 3)
        self.assertEqual(result["area_analytics"]["repeat_cases"], 4)
        self.assertTrue(result["area_analytics"]["repeat_pattern_detected"])
        self.assertTrue(result["risk_indicator"]["available"])
        self.assertEqual(result["risk_indicator"]["score"], 61)
        self.assertEqual(
            result["prevention"]["suggestions"],
            [
                result["recommendation"],
                "Review fire-safety conditions",
                "Review emergency access",
                "Consider a safety inspection",
            ],
        )
        self.assertNotIn("description", result["similar_incidents"][0])
        self.assertNotIn("latitude", result["nearby_cases"][0])
        self.assertEqual(result["response_history"][0]["resolution_minutes"], 30)

    def test_insufficient_data_and_invalid_radius_are_reported(self):
        report = {
            "id": 1,
            "emergency_type": "Accident",
            "priority": "Low",
            "status": "Received",
            "latitude": 17.385,
            "longitude": 78.4867,
            "created_at": "2026-10-05 12:00:00",
        }
        result = build_incident_intelligence(report, [report], now=self.now)
        self.assertFalse(result["risk_indicator"]["available"])
        self.assertEqual(result["risk_indicator"]["message"], "Insufficient historical data.")
        self.assertEqual(result["hotspots"]["message"], "Insufficient data for hotspot detection.")
        with self.assertRaises(ValueError):
            build_incident_intelligence(report, [report], radius_km=0)
        report["latitude"] = None
        no_location = build_incident_intelligence(report, [report], now=self.now)
        self.assertFalse(no_location["risk_indicator"]["available"])

    def test_no_gps_intelligence_keeps_network_trends_and_non_spatial_prevention(self):
        current = {
            "id": 20,
            "emergency_type": "Fire",
            "priority": "High",
            "status": "Received",
            "latitude": None,
            "longitude": None,
            "created_at": self.now.strftime("%Y-%m-%d %H:%M:%S"),
        }
        previous_reports = [
            {
                **current,
                "id": report_id,
                "latitude": None if report_id == 19 else 17.385,
                "longitude": None if report_id == 19 else 78.4867,
                "created_at": (
                    self.now - timedelta(days=report_id - 17)
                ).strftime("%Y-%m-%d %H:%M:%S"),
            }
            for report_id in (17, 18, 19)
        ]

        result = build_incident_intelligence(
            current,
            [*previous_reports, current],
            now=self.now,
        )

        self.assertFalse(result["gps_available"])
        self.assertIsNone(current["latitude"])
        self.assertIsNone(current["longitude"])
        self.assertEqual(result["nearby_cases"], [])
        self.assertFalse(result["risk_indicator"]["available"])
        self.assertIn("Location unavailable", result["hotspots"]["message"])
        self.assertTrue(result["general_intelligence"]["available"])
        self.assertFalse(result["location_intelligence"]["available"])
        self.assertEqual(result["local_problem"], "unavailable")
        self.assertEqual(result["recommendation"], "unavailable")
        self.assertEqual(result["location_conclusion"], "unavailable")
        self.assertEqual(len(result["similar_incidents"]), 3)
        self.assertEqual(len(result["response_history"]), 3)
        self.assertTrue(result["general_intelligence"]["trends"]["monthly"])
        self.assertTrue(result["general_intelligence"]["trends"]["categories"])
        self.assertTrue(result["prevention"]["pattern_detected"])
        self.assertTrue(result["prevention"]["suggestions"])
        self.assertEqual(
            result["network_analytics"]["categories"][
                2
            ]["count"],
            4,
        )
        self.assertEqual(
            sum(item["count"] for item in result["network_analytics"]["monthly_trend"]),
            4,
        )

    def test_location_assessment_detects_extreme_proximity_and_mixed_concentration(self):
        current = {
            "id": 30,
            "emergency_type": "Road Hazard",
            "priority": "Medium",
            "status": "Received",
            "latitude": 16.8118,
            "longitude": 82.2400,
            "created_at": "2026-10-05 12:00:00",
        }
        previous = [
            {
                "id": 31,
                "emergency_type": "Fire",
                "priority": "Medium",
                "status": "Received",
                "latitude": 16.8119,
                "longitude": 82.2400,
                "created_at": "2026-10-05 08:00:00",
            },
            {
                "id": 32,
                "emergency_type": "Fire",
                "priority": "High",
                "status": "Resolved",
                "latitude": 16.8120,
                "longitude": 82.2400,
                "created_at": "2026-10-05 09:00:00",
            },
        ]

        result = build_incident_intelligence(
            current, [current, *previous], radius_km=1, now=self.now
        )

        self.assertTrue(result["short_term_concentration"]["detected"])
        self.assertEqual(result["short_term_concentration"]["incident_count"], 3)
        self.assertTrue(result["short_term_concentration"]["mixed_categories"])
        self.assertTrue(result["extreme_proximity"]["detected"])
        self.assertEqual(result["extreme_proximity"]["count"], 2)
        self.assertTrue(
            all(
                item["distance_km"] <= 0.05
                for item in result["extreme_proximity"]["incidents"]
            )
        )
        self.assertEqual(
            result["local_problem"],
            "Possible recurring local safety/environmental issue",
        )
        self.assertIn("Investigate the location", result["recommendation"])
        self.assertIn("2 previous nearby incident(s)", result["recommendation_reason"])
        self.assertIn("Fire (2)", result["recommendation_reason"])
        self.assertIn("current Road Hazard report", result["recommendation_reason"])
        self.assertEqual(
            result["prevention"]["suggestions"][0],
            result["recommendation"],
        )
        self.assertEqual(result["evidence_strength"], "Limited")
        self.assertIn("2 previous nearby", result["evidence_explanation"])
        self.assertIn("metres", result["recommendation_reason"])
        self.assertIn("short-term concentration", result["location_conclusion"])
        self.assertIn("cannot", result["data_limitation"])

    def test_short_term_concentration_requires_three_incidents_within_24_hours(self):
        current = {
            "id": 40,
            "emergency_type": "Road Hazard",
            "priority": "Low",
            "status": "Received",
            "latitude": 17.0,
            "longitude": 78.0,
            "created_at": "2026-10-05 12:00:00",
        }
        previous = [
            {
                **current,
                "id": 41,
                "emergency_type": "Accident",
                "created_at": "2026-10-04 11:59:00",
            },
            {
                **current,
                "id": 42,
                "emergency_type": "Fire",
                "created_at": "2026-10-02 11:59:00",
            },
        ]

        result = build_incident_intelligence(
            current, [current, *previous], radius_km=1, now=self.now
        )

        self.assertFalse(result["short_term_concentration"]["detected"])
        self.assertEqual(result["short_term_concentration"]["window_hours"], 24)
        self.assertEqual(result["short_term_concentration"]["incident_count"], 1)

    def test_recurring_category_across_dates_and_evidence_strength(self):
        current = {
            "id": 50,
            "emergency_type": "Road Hazard",
            "priority": "Medium",
            "status": "Received",
            "latitude": 17.0,
            "longitude": 78.0,
            "created_at": "2026-10-05 12:00:00",
        }

        def previous_records(count):
            return [
                {
                    **current,
                    "id": 50 + index,
                    "emergency_type": "Accident",
                    "priority": "High",
                    "created_at": (
                        self.now - timedelta(days=index * 30)
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                }
                for index in range(1, count + 1)
            ]

        moderate_history = previous_records(3)
        moderate = build_incident_intelligence(
            current,
            [current, *moderate_history],
            radius_km=1,
            now=self.now,
        )
        self.assertTrue(moderate["recurring_pattern"]["detected"])
        self.assertEqual(moderate["recurring_pattern"]["category"], "Accident")
        self.assertEqual(moderate["recurring_pattern"]["distinct_dates"], 3)
        self.assertEqual(moderate["evidence_strength"], "Moderate")
        self.assertEqual(moderate["local_problem"], "Possible accident-prone pattern")
        self.assertIn("road-safety hazards", moderate["recommendation"])

        strong = build_incident_intelligence(
            current,
            [current, *previous_records(5)],
            radius_km=1,
            now=self.now,
        )
        self.assertTrue(strong["recurring_pattern"]["detected"])
        self.assertEqual(strong["evidence_strength"], "Strong")
        self.assertEqual(strong["recommendation_basis"]["historical_incidents"], 5)

    def test_location_without_short_term_or_recurring_pattern_is_limited(self):
        current = {
            "id": 60,
            "emergency_type": "Road Hazard",
            "priority": "Low",
            "status": "Received",
            "latitude": 17.0,
            "longitude": 78.0,
            "created_at": "2026-10-05 12:00:00",
        }
        previous = [
            {
                **current,
                "id": 61,
                "emergency_type": "Fire",
                "created_at": "2026-10-04 11:59:00",
            },
            {
                **current,
                "id": 62,
                "emergency_type": "Accident",
                "created_at": "2026-10-03 12:00:00",
            },
        ]
        result = build_incident_intelligence(
            current, [current, *previous], radius_km=1, now=self.now
        )
        self.assertEqual(result["evidence_strength"], "Limited")
        self.assertEqual(result["local_problem"], "Insufficient historical evidence")
        self.assertIn("Review the available nearby incident records", result["recommendation"])
        self.assertFalse(result["recurring_pattern"]["detected"])
        self.assertFalse(result["short_term_concentration"]["detected"])


class ResponderIntelligenceApiTests(unittest.TestCase):
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
        database.DATABASE_PATH = Path(self.temp_directory.name) / f"{self._testMethodName}.db"
        initialize_database()
        connection = get_db_connection()
        try:
            cursor = connection.execute(
                """
                INSERT INTO users (name, email, password_hash, role)
                VALUES (?, ?, ?, 'user')
                """,
                ("Intelligence Test", "intelligence-test@example.test", generate_password_hash("TestPassword123")),
            )
            self.user_id = cursor.lastrowid
            cursor = connection.execute(
                """
                INSERT INTO emergency_reports (
                    user_id, emergency_type, description, latitude, longitude,
                    priority, status
                ) VALUES (?, 'Accident', 'Vehicle collision', 17.385, 78.4867, 'High', 'Received')
                """,
                (self.user_id,),
            )
            self.report_id = cursor.lastrowid
            connection.commit()
        finally:
            connection.close()
        self.client = app.test_client()

    def test_intelligence_requires_responder_and_serves_report_detail(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertEqual(self.client.get("/api/db-test").status_code, 200)
        report_intelligence_url = (
            f"/api/responder/reports/{self.report_id}/intelligence"
        )
        self.assertEqual(
            self.client.get(f"/api/responder/intelligence/{self.user_id}").status_code,
            401,
        )
        self.assertEqual(self.client.get(report_intelligence_url).status_code, 401)
        with self.client.session_transaction() as session:
            session["user_id"] = self.user_id
        self.assertEqual(
            self.client.get(f"/api/responder/intelligence/{self.user_id}").status_code,
            403,
        )
        self.assertEqual(self.client.get(report_intelligence_url).status_code, 403)

        connection = get_db_connection()
        try:
            connection.execute(
                "UPDATE users SET role = 'responder' WHERE id = ?",
                (self.user_id,),
            )
            connection.commit()
        finally:
            connection.close()
        response = self.client.get(f"/api/responder/intelligence/{self.user_id}")
        self.assertEqual(response.status_code, 200)
        analytics = response.get_json()["analytics"]
        self.assertEqual(analytics["kpis"]["total_incidents"], 1)
        historical_data = analytics["official_historical_data"]
        self.assertFalse(historical_data["available"])
        self.assertEqual(historical_data["year"], 2023)
        self.assertEqual(
            historical_data["source_catalog_url"],
            "https://ap.data.gov.in/resource/"
            "stateutcity-wise-number-cases-reported-and-persons-injured-and-died-due-traffic-accidents",
        )
        self.assertEqual(
            historical_data["additional_source_catalog_url"],
            "https://delhi.data.gov.in/resource/"
            "stateutcity-wise-and-month-occurrence-wise-number-traffic-accidents-during-2023",
        )
        self.assertIn("HTTP 403", historical_data["message"])
        self.assertIn("HTTP 400", historical_data["message"])
        self.assertIn("transport-level DNS/connection/TLS failure", historical_data["message"])
        self.assertEqual(historical_data["datasets"], [])

        connection = get_db_connection()
        try:
            for days_ago in (1, 2, 3):
                created_at = (
                    datetime.now(timezone.utc) - timedelta(days=days_ago)
                ).strftime("%Y-%m-%d %H:%M:%S")
                connection.execute(
                    """
                    INSERT INTO emergency_reports (
                        user_id, emergency_type, description, latitude, longitude,
                        priority, status, created_at
                    ) VALUES (?, 'Accident', 'Nearby collision', ?, 78.4867,
                              'High', 'Resolved', ?)
                    """,
                    (self.user_id, 17.385 + days_ago * 0.0002, created_at),
                )
            connection.commit()
        finally:
            connection.close()

        detail = self.client.get(
            f"/api/responder/reports/{self.report_id}/intelligence?radius_km=2"
        )
        self.assertEqual(detail.status_code, 200)
        detail_json = detail.get_json()
        self.assertEqual(detail_json["incident"]["id"], self.report_id)
        self.assertGreaterEqual(detail_json["incident"]["category_confidence"], 0)
        self.assertGreaterEqual(detail_json["incident"]["priority_confidence"], 0)
        self.assertEqual(detail_json["intelligence"]["radius_km"], 2)
        self.assertTrue(detail_json["intelligence"]["general_intelligence"]["available"])
        self.assertTrue(detail_json["intelligence"]["location_intelligence"]["available"])
        self.assertEqual(
            detail_json["intelligence"]["location_intelligence"]["status"],
            "available",
        )
        self.assertEqual(detail_json["intelligence"]["previous_nearby_count"], 3)
        self.assertTrue(detail_json["intelligence"]["risk_indicator"]["available"])
        self.assertGreaterEqual(detail_json["intelligence"]["hotspots"]["count"], 1)
        self.assertTrue(detail_json["intelligence"]["general_intelligence"]["trends"]["monthly"])
        self.assertEqual(
            self.client.get(
                f"/api/responder/reports/{self.report_id}/intelligence?radius_km=500"
            ).status_code,
            400,
        )

        # Test report without GPS returns 200 with graceful fallback intelligence
        connection = get_db_connection()
        try:
            cursor = connection.execute(
                """
                INSERT INTO emergency_reports (
                    user_id, emergency_type, description, latitude, longitude,
                    priority, status
                ) VALUES (?, 'Fire', 'Smoke seen in building', NULL, NULL, 'High', 'Received')
                """,
                (self.user_id,),
            )
            no_location_report_id = cursor.lastrowid
            connection.commit()
        finally:
            connection.close()

        no_location_detail = self.client.get(
            f"/api/responder/reports/{no_location_report_id}/intelligence?radius_km=1"
        )
        self.assertEqual(no_location_detail.status_code, 200)
        json_data = no_location_detail.get_json()
        self.assertEqual(json_data["status"], "success")
        self.assertEqual(json_data["incident"]["id"], no_location_report_id)
        self.assertEqual(json_data["incident"]["emergency_type"], "Fire")
        self.assertEqual(json_data["incident"]["priority"], "High")
        self.assertGreaterEqual(json_data["incident"]["category_confidence"], 0)
        self.assertGreaterEqual(json_data["incident"]["priority_confidence"], 0)
        self.assertIsNone(json_data["incident"]["latitude"])
        self.assertIsNone(json_data["incident"]["longitude"])
        self.assertTrue(json_data["intelligence"]["general_intelligence"]["available"])
        self.assertFalse(json_data["intelligence"]["location_intelligence"]["available"])
        self.assertEqual(
            json_data["intelligence"]["location_intelligence"]["status"],
            "unavailable",
        )
        self.assertEqual(
            json_data["intelligence"]["location_intelligence"]["message"],
            "Location unavailable. Nearby incidents, hotspots and area risk "
            "require a valid incident location.",
        )
        self.assertEqual(json_data["intelligence"]["previous_nearby_count"], 0)
        self.assertEqual(json_data["intelligence"]["nearby_cases"], [])
        self.assertFalse(json_data["intelligence"]["risk_indicator"]["available"])
        self.assertFalse(json_data["intelligence"]["gps_available"])
        self.assertIn("Location unavailable", json_data["intelligence"]["analysis_scope"])
        self.assertEqual(len(json_data["intelligence"]["similar_incidents"]), 4)
        self.assertIsNone(
            json_data["intelligence"]["similar_incidents"][0]["distance_km"]
        )
        self.assertNotIn("latitude", json_data["intelligence"]["similar_incidents"][0])
        self.assertNotIn("longitude", json_data["intelligence"]["similar_incidents"][0])
        self.assertTrue(json_data["intelligence"]["general_intelligence"]["trends"]["categories"])
        self.assertTrue(json_data["intelligence"]["general_intelligence"]["trends"]["priorities"])
        self.assertEqual(len(json_data["intelligence"]["response_history"]), 4)
        self.assertTrue(json_data["intelligence"]["prevention"]["suggestions"])
        self.assertEqual(
            json_data["intelligence"]["network_analytics"]["kpis"]["total_incidents"],
            5,
        )
        self.assertEqual(
            sum(
                item["count"]
                for item in json_data["intelligence"]["network_analytics"]["categories"]
            ),
            5,
        )

    def test_api_me_returns_authenticated_user_or_unauthorized(self):
        # Unauthenticated returns 401
        logged_out_client = app.test_client()
        response = logged_out_client.get("/api/me")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["message"], "Please log in")

        # Authenticated returns user information
        with logged_out_client.session_transaction() as session:
            session["user_id"] = self.user_id
        response = logged_out_client.get("/api/me")
        self.assertEqual(response.status_code, 200)
        user_data = response.get_json()["user"]
        self.assertEqual(user_data["id"], self.user_id)
        self.assertEqual(user_data["email"], "intelligence-test@example.test")
        self.assertNotIn("password", user_data)
        self.assertNotIn("password_hash", user_data)


if __name__ == "__main__":
    unittest.main()
