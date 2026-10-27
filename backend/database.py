import sqlite3
from pathlib import Path


DATABASE_PATH = Path(__file__).resolve().parent / "resqnet.db"


def get_db_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database():
    connection = get_db_connection()
    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'responder', 'admin')),
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS emergency_reports (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                emergency_type TEXT NOT NULL,
                description TEXT NOT NULL,
                latitude REAL,
                longitude REAL,
                priority TEXT NOT NULL DEFAULT 'Medium',
                priority_source TEXT NOT NULL DEFAULT 'default'
                    CHECK (priority_source IN ('default', 'ml')),
                reported_emergency_type TEXT,
                image_filename TEXT,
                video_filename TEXT,
                status TEXT NOT NULL DEFAULT 'Received',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                resolved_at DATETIME,
                FOREIGN KEY (user_id) REFERENCES users (id)
            );

            CREATE TABLE IF NOT EXISTS historical_dataset_imports (
                id INTEGER PRIMARY KEY,
                source TEXT NOT NULL,
                dataset_name TEXT NOT NULL,
                dataset_url TEXT NOT NULL,
                geographic_level TEXT NOT NULL,
                period_start TEXT,
                period_end TEXT,
                imported_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                import_method TEXT NOT NULL,
                imported_record_count INTEGER NOT NULL CHECK (imported_record_count >= 0),
                import_notes TEXT
            );

            CREATE TABLE IF NOT EXISTS government_historical_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_identifier TEXT NOT NULL UNIQUE,
                source_name TEXT NOT NULL,
                department TEXT NOT NULL,
                dataset_title TEXT NOT NULL,
                dataset_year INTEGER NOT NULL,
                state TEXT,
                district TEXT,
                city TEXT,
                geographic_level TEXT NOT NULL,
                category TEXT NOT NULL,
                metric TEXT NOT NULL,
                value REAL NOT NULL,
                unit TEXT NOT NULL DEFAULT 'count',
                source_url TEXT NOT NULL,
                license TEXT NOT NULL,
                imported_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_gov_geo ON government_historical_data(geographic_level, state, city);
            CREATE INDEX IF NOT EXISTS idx_gov_cat ON government_historical_data(category, metric);
            """
        )
        report_columns = {
            column["name"]
            for column in connection.execute(
                "PRAGMA table_info(emergency_reports)"
            ).fetchall()
        }
        if "priority_source" not in report_columns:
            connection.execute(
                """
                ALTER TABLE emergency_reports
                ADD COLUMN priority_source TEXT NOT NULL DEFAULT 'default'
                    CHECK (priority_source IN ('default', 'ml'))
                """
            )
        if "reported_emergency_type" not in report_columns:
            connection.execute(
                "ALTER TABLE emergency_reports ADD COLUMN reported_emergency_type TEXT"
            )
        if "image_filename" not in report_columns:
            connection.execute(
                "ALTER TABLE emergency_reports ADD COLUMN image_filename TEXT"
            )
        if "video_filename" not in report_columns:
            connection.execute(
                "ALTER TABLE emergency_reports ADD COLUMN video_filename TEXT"
            )
        if "route_department" not in report_columns:
            connection.execute(
                "ALTER TABLE emergency_reports ADD COLUMN route_department TEXT"
            )
        if "route_destination" not in report_columns:
            connection.execute(
                "ALTER TABLE emergency_reports ADD COLUMN route_destination TEXT"
            )
        if "resolved_at" not in report_columns:
            connection.execute(
                "ALTER TABLE emergency_reports ADD COLUMN resolved_at DATETIME"
            )
        if "route_status" not in report_columns:
            connection.execute(
                """
                ALTER TABLE emergency_reports
                ADD COLUMN route_status TEXT NOT NULL DEFAULT 'Not sent'
                """
            )
        connection.commit()
    finally:
        connection.close()
