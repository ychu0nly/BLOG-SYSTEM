import hashlib
import time

sessions = {}  # session_id -> username

def create_session(username: str) -> str:
    session_id = hashlib.md5(str(time.time()).encode()).hexdigest()
    sessions[session_id] = username
    return session_id

def get_user_by_session(session_id: str) -> str | None:
    return sessions.get(session_id)

def destroy_session(session_id: str):
    sessions.pop(session_id, None)