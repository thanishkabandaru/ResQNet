from flask import session

from database import get_db_connection


def get_logged_in_user():
    user_id = session.get("user_id")
    if isinstance(user_id, bool) or not isinstance(user_id, int):
        return None

    connection = get_db_connection()
    try:
        user = connection.execute(
            "SELECT id, name, email, role FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        connection.close()

    return dict(user) if user else None


def check_responder_access(user_id):
    connection = get_db_connection()
    try:
        user = connection.execute(
            "SELECT role FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        connection.close()

    if user is None:
        return False, False

    return True, user["role"] in {"responder", "admin"}
