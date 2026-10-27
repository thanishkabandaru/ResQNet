"""Comprehensive tests for Government Data integration, provenance, duplicate prevention,
APIs, authorization, source failure handling, and area recommendation logic.
"""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

import database
from app import app
from database import get_db_connection, initialize_database
from government_data import (
    DEFAULT_NCRB_CSV_PATH,
    MORTH_PROVENANCE,
    NCRB_PROVENANCE,
    get_government_data_summary,
    import_official_government_data,
    query_government_records,
    validate_and_parse_ncrb_csv,
)
from intelligence import build_incident_intelligence
from werkzeug.security import generate_password_hash


class GovernmentDataUnitTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_gov.db"
        self._orig_db_path = database.DATABASE_PATH
        database.DATABASE_PATH = self.db_path
        initialize_database()

    def tearDown(self):
        database.DATABASE_PATH = self._orig_db_path
        self.temp_dir.cleanup()

    def test_government_data_parsing_and_validation(self):
        # Valid minimal CSV
        valid_csv = (
            "Sl. No.,State/Ut/,Road Accidents - Cases,Road Accidents - Injured,"
            "Road Accidents - Died,Railway Accidents - Cases,Railway Accidents - Injured,"
            "Railway Accidents - Died,Railway Crossing Accidents - Cases,"
            "Railway Crossing Accidents - Injured,Railway Crossing Accidents - Died,"
            "Total Traffic Accidents - Cases,Total Traffic Accidents - Injured,"
            "Total Traffic Accidents - Died\n"
            "1,Andhra Pradesh,19949,20409,8137,1125,0,1143,4,0,4,21078,20409,9284\n"
            "88,Vijayawada,1522,1416,373,0,0,0,0,0,0,1522,1416,373\n"
        )
        records = validate_and_parse_ncrb_csv(valid_csv)
        self.assertEqual(len(records), 24)  # 2 rows * 12 metrics

        ap_records = [r for r in records if r["state"] == "Andhra Pradesh" and r["city"] is None]
        self.assertEqual(len(ap_records), 12)
        road_cases = next(r for r in ap_records if r["category"] == "Road Accidents" and r["metric"] == "Cases Reported")
        self.assertEqual(road_cases["value"], 19949)
        self.assertEqual(road_cases["geographic_level"], "State")

        vja_records = [r for r in records if r["city"] == "Vijayawada"]
        self.assertEqual(len(vja_records), 12)
        vja_cases = next(r for r in vja_records if r["category"] == "Road Accidents" and r["metric"] == "Cases Reported")
        self.assertEqual(vja_cases["value"], 1522)
        self.assertEqual(vja_cases["state"], "Andhra Pradesh")
        self.assertEqual(vja_cases["geographic_level"], "City")

    def test_malformed_csv_columns_rejected(self):
        bad_csv = "Sl. No.,State/Ut/,Some Random Column\n1,Andhra Pradesh,100\n"
        with self.assertRaises(ValueError) as ctx:
            validate_and_parse_ncrb_csv(bad_csv)
        self.assertIn("Missing required columns", str(ctx.exception))

    def test_negative_values_rejected(self):
        negative_csv = (
            "Sl. No.,State/Ut/,Road Accidents - Cases,Road Accidents - Injured,"
            "Road Accidents - Died,Railway Accidents - Cases,Railway Accidents - Injured,"
            "Railway Accidents - Died,Railway Crossing Accidents - Cases,"
            "Railway Crossing Accidents - Injured,Railway Crossing Accidents - Died,"
            "Total Traffic Accidents - Cases,Total Traffic Accidents - Injured,"
            "Total Traffic Accidents - Died\n"
            "1,Andhra Pradesh,-5,20409,8137,1125,0,1143,4,0,4,21078,20409,9284\n"
        )
        with self.assertRaises(ValueError) as ctx:
            validate_and_parse_ncrb_csv(negative_csv)
        self.assertIn("negative count", str(ctx.exception))

    def test_import_and_duplicate_prevention(self):
        # 1st import
        conn = get_db_connection()
        try:
            res1 = import_official_government_data(connection=conn)
            self.assertEqual(res1["status"], "success")
            self.assertEqual(res1["imported_count"], 1116)
            self.assertEqual(res1["total_stored"], 1116)

            # 2nd import must not duplicate
            res2 = import_official_government_data(connection=conn)
            self.assertEqual(res2["status"], "success")
            self.assertEqual(res2["imported_count"], 0)
            self.assertEqual(res2["total_stored"], 1116)

            # Query check
            ap_recs = query_government_records(
                connection=conn, state="Andhra Pradesh", category="Road Accidents"
            )
            self.assertGreater(len(ap_recs), 0)
            for r in ap_recs:
                self.assertEqual(r["source_name"], "National Crime Records Bureau (NCRB)")
                self.assertEqual(r["license"], "Government Open Data License - India (GODL-India)")
        finally:
            conn.close()

    def test_missing_government_data_summary(self):
        conn = get_db_connection()
        try:
            summary = get_government_data_summary(connection=conn)
            self.assertFalse(summary["available"])
            self.assertIn("not yet imported", summary["message"])
        finally:
            conn.close()

    def test_provenance_and_metadata_preserved(self):
        self.assertEqual(NCRB_PROVENANCE["source_name"], "National Crime Records Bureau (NCRB)")
        self.assertEqual(NCRB_PROVENANCE["department"], "Ministry of Home Affairs")
        self.assertEqual(NCRB_PROVENANCE["dataset_year"], 2023)
        self.assertIn("NCRB_ADSI_2023_Table_1A.2_2.csv", NCRB_PROVENANCE["dataset_file_url"])
        self.assertEqual(MORTH_PROVENANCE["source_name"], "Ministry of Road Transport and Highways (MoRTH)")
        self.assertIn("9709bed2-7ac4-43b2-87d9-05f01910b07b", MORTH_PROVENANCE["api_url"])


class GovernmentApiAndAreaIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_api_gov.db"
        self._orig_db_path = database.DATABASE_PATH
        database.DATABASE_PATH = self.db_path
        initialize_database()

        self.client = app.test_client()
        conn = get_db_connection()
        try:
            # Create user and responder
            conn.execute(
                "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
                ("Citizen One", "citizen@example.com", generate_password_hash("pass123"), "user"),
            )
            conn.execute(
                "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
                ("Official Responder", "resp@example.com", generate_password_hash("pass123"), "responder"),
            )
            conn.commit()
            self.user_id = conn.execute("SELECT id FROM users WHERE email='citizen@example.com'").fetchone()[0]
            self.resp_id = conn.execute("SELECT id FROM users WHERE email='resp@example.com'").fetchone()[0]

            # Import government data into test db
            import_official_government_data(connection=conn)
        finally:
            conn.close()

    def tearDown(self):
        database.DATABASE_PATH = self._orig_db_path
        self.temp_dir.cleanup()

    def test_government_data_api_authorization(self):
        # Unauthenticated request
        res = self.client.get("/api/responder/government-data")
        self.assertEqual(res.status_code, 401)

        # Citizen user request (forbidden)
        with self.client.session_transaction() as sess:
            sess["user_id"] = self.user_id
        res = self.client.get("/api/responder/government-data")
        self.assertEqual(res.status_code, 403)

        # Responder request (success)
        with self.client.session_transaction() as sess:
            sess["user_id"] = self.resp_id
        res = self.client.get("/api/responder/government-data")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "success")
        self.assertTrue(data["summary"]["available"])
        self.assertEqual(data["summary"]["andhra_pradesh"]["road_accident_cases"], 19949.0)
        self.assertEqual(data["summary"]["cities"]["Vijayawada"]["road_accident_cases"], 1522.0)
        self.assertGreater(len(data["records"]), 0)

    def test_area_recommendation_and_observed_problem_detection(self):
        now = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
        current = {
            "id": 10,
            "emergency_type": "Accident",
            "priority": "High",
            "status": "Received",
            "latitude": 17.385,
            "longitude": 78.4867,
            "created_at": "2026-10-05 12:00:00",
        }
        nearby_accidents = [
            {
                "id": i,
                "emergency_type": "Accident",
                "priority": "High",
                "status": "Resolved",
                "latitude": 17.385 + i * 0.0001,
                "longitude": 78.4867,
                "created_at": f"2026-10-0{i} 10:00:00",
            }
            for i in range(1, 4)
        ]
        conn = get_db_connection()
        try:
            intel = build_incident_intelligence(
                current, [current, *nearby_accidents], radius_km=1.0, now=now, db_connection=conn
            )
            self.assertEqual(intel["observed_local_problem"], "Repeated road-safety incidents")
            self.assertIn("road-safety assessment", intel["recommendation"])
            self.assertEqual(intel["evidence_strength"], "Moderate")
            self.assertIn("Local ResQNet Evidence", intel["combined_evidence"]["local_resqnet_layer"]["title"])
            self.assertTrue(intel["combined_evidence"]["government_historical_layer"]["available"])
            self.assertIn("19,949", intel["combined_evidence"]["government_historical_layer"]["context_description"])
        finally:
            conn.close()

    def test_fire_safety_observed_problem_detection(self):
        now = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
        current = {
            "id": 20,
            "emergency_type": "Fire",
            "priority": "High",
            "status": "Received",
            "latitude": 17.385,
            "longitude": 78.4867,
            "created_at": "2026-10-05 12:00:00",
        }
        nearby_fire = [
            {
                "id": i,
                "emergency_type": "Fire",
                "priority": "High",
                "status": "Resolved",
                "latitude": 17.385 + i * 0.0001,
                "longitude": 78.4867,
                "created_at": f"2026-10-0{i} 10:00:00",
            }
            for i in range(1, 4)
        ]
        conn = get_db_connection()
        try:
            intel = build_incident_intelligence(
                current, [current, *nearby_fire], radius_km=1.0, now=now, db_connection=conn
            )
            self.assertEqual(intel["observed_local_problem"], "Repeated fire-related incidents")
            self.assertIn("fire-safety and electrical-safety assessment", intel["recommendation"])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
