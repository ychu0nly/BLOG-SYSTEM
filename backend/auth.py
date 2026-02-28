from utils import hash_password
from backend.storage import load_users, save_users
from backend.session_manager import create_session 

def register_user(username: str, password: str) -> tuple[bool, str]:
    users = load_users()
    if username in users:
        return False, "用户名已存在"
    users[username] = hash_password(password)
    save_users(users)
    return True, ""

def authenticate_user(username: str, password: str) -> tuple[bool, str]:
    users = load_users()
    if username in users and users[username] == hash_password(password):
        return True, create_session(username)
    return False, ""