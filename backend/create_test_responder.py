import os

from werkzeug.security import generate_password_hash

from database import get_db_connection


TEST_NAME = "ResQNet Test Responder"
TEST_EMAIL = os.environ.get("RESQNET_TEST_RESPONDER_EMAIL")
TEST_PASSWORD = os.environ.get("RESQNET_TEST_RESPONDER_PASSWORD")


def create_test_responder():
    if not TEST_EMAIL or not TEST_PASSWORD:
        raise ValueError(
            "Set RESQNET_TEST_RESPONDER_EMAIL and "
            "RESQNET_TEST_RESPONDER_PASSWORD to create the development test account."
        )

    connection = get_db_connection()
    try:
        existing_user = connection.execute(
            "SELECT id FROM users WHERE email = ?",
            (TEST_EMAIL.strip(),),
        ).fetchone()
        if existing_user:
            print(f"Test responder already exists: {TEST_EMAIL.strip()}")
            return

        connection.execute(
            """
            INSERT INTO users (name, email, password_hash, role)
            VALUES (?, ?, ?, 'responder')
            """,
            (
                TEST_NAME,
                TEST_EMAIL.strip(),
                generate_password_hash(TEST_PASSWORD),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    print(f"Created development test responder: {TEST_EMAIL.strip()}")


if __name__ == "__main__":
    create_test_responder()
