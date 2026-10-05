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
                status TEXT NOT NULL DEFAULT 'Received',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            );
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
        if "route_department" not in report_columns:
            connection.execute(
                "ALTER TABLE emergency_reports ADD COLUMN route_department TEXT"
            )
        if "route_destination" not in report_columns:
            connection.execute(
                "ALTER TABLE emergency_reports ADD COLUMN route_destination TEXT"
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
