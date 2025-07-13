# Authentication manager for Sidekick agent
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import bcrypt

from config import (
    BCRYPT_ROUNDS,
    ERROR_MESSAGES,
    PASSWORD_MIN_LENGTH,
    SESSION_TIMEOUT_HOURS,
    SUCCESS_MESSAGES,
    USERNAME_MAX_LENGTH,
    USERNAME_MIN_LENGTH,
    USERS_DB_PATH,
    ensure_directories,
)


@dataclass
class User:
    """User data structure"""
    id: int
    username: str
    created_at: datetime
    last_login: datetime | None = None

@dataclass
class Session:
    """Session data structure"""
    token: str
    user_id: int
    username: str
    created_at: datetime
    expires_at: datetime

class AuthManager:
    """Handles user authentication and session management"""

    def __init__(self):
        ensure_directories()
        self._init_database()
        self._active_sessions: dict[str, Session] = {}

    def _init_database(self):
        """Initialize the users database"""
        with sqlite3.connect(USERS_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            """)
            conn.commit()

    def _hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode('utf-8')

    def _verify_password(self, password: str, hashed: str) -> bool:
        """Verify password against hash"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

    def _validate_username(self, username: str) -> str | None:
        """Validate username format"""
        if len(username) < USERNAME_MIN_LENGTH:
            return ERROR_MESSAGES["username_too_short"]
        if len(username) > USERNAME_MAX_LENGTH:
            return ERROR_MESSAGES["username_too_long"]
        if not username.replace('_', '').replace('-', '').isalnum():
            return "Username can only contain letters, numbers, underscores, and hyphens"
        return None

    def _validate_password(self, password: str) -> str | None:
        """Validate password format"""
        if len(password) < PASSWORD_MIN_LENGTH:
            return ERROR_MESSAGES["password_too_short"]
        return None

    def _generate_session_token(self) -> str:
        """Generate secure session token"""
        return secrets.token_urlsafe(32)

    def _create_session(self, user_id: int, username: str) -> str:
        """Create new session for user"""
        token = self._generate_session_token()
        created_at = datetime.now()
        expires_at = created_at + timedelta(hours=SESSION_TIMEOUT_HOURS)

        session = Session(
            token=token,
            user_id=user_id,
            username=username,
            created_at=created_at,
            expires_at=expires_at
        )

        self._active_sessions[token] = session
        return token

    def _cleanup_expired_sessions(self):
        """Remove expired sessions"""
        now = datetime.now()
        expired_tokens = [
            token for token, session in self._active_sessions.items()
            if session.expires_at < now
        ]
        for token in expired_tokens:
            del self._active_sessions[token]

    def register_user(self, username: str, password: str) -> dict[str, Any]:
        """Register a new user"""
        try:
            # Validate input
            username_error = self._validate_username(username)
            if username_error:
                return {"success": False, "error": username_error}

            password_error = self._validate_password(password)
            if password_error:
                return {"success": False, "error": password_error}

            # Check if username exists
            with sqlite3.connect(USERS_DB_PATH) as conn:
                cursor = conn.execute("SELECT id FROM users WHERE username = ?", (username,))
                if cursor.fetchone():
                    return {"success": False, "error": ERROR_MESSAGES["username_exists"]}

                # Create user
                password_hash = self._hash_password(password)
                cursor = conn.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, password_hash)
                )
                user_id = cursor.lastrowid
                conn.commit()

            # Create session
            token = self._create_session(user_id, username)

            return {
                "success": True,
                "message": SUCCESS_MESSAGES["register"],
                "token": token,
                "username": username
            }

        except Exception as e:
            return {"success": False, "error": f"Registration failed: {e!s}"}

    def login_user(self, username: str, password: str) -> dict[str, Any]:
        """Authenticate user and create session"""
        try:
            with sqlite3.connect(USERS_DB_PATH) as conn:
                cursor = conn.execute(
                    "SELECT id, password_hash FROM users WHERE username = ?",
                    (username,)
                )
                user_data = cursor.fetchone()

                if not user_data or not self._verify_password(password, user_data[1]):
                    return {"success": False, "error": ERROR_MESSAGES["invalid_credentials"]}

                user_id = user_data[0]

                # Update last login
                conn.execute(
                    "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
                    (user_id,)
                )
                conn.commit()

            # Create session
            token = self._create_session(user_id, username)

            return {
                "success": True,
                "message": SUCCESS_MESSAGES["login"],
                "token": token,
                "username": username
            }

        except Exception as e:
            return {"success": False, "error": f"Login failed: {e!s}"}

    def validate_session(self, token: str) -> Session | None:
        """Validate session token and return session if valid"""
        self._cleanup_expired_sessions()

        session = self._active_sessions.get(token)
        if session and session.expires_at > datetime.now():
            return session
        return None

    def get_user(self, username: str) -> User | None:
        """Get user by username"""
        try:
            with sqlite3.connect(USERS_DB_PATH) as conn:
                cursor = conn.execute(
                    "SELECT id, username, created_at, last_login FROM users WHERE username = ?",
                    (username,)
                )
                data = cursor.fetchone()

                if data:
                    return User(
                        id=data[0],
                        username=data[1],
                        created_at=datetime.fromisoformat(data[2]),
                        last_login=datetime.fromisoformat(data[3]) if data[3] else None
                    )
        except Exception:
            pass
        return None

    def logout_user(self, token: str) -> dict[str, Any]:
        """Logout user by invalidating session"""
        if token in self._active_sessions:
            del self._active_sessions[token]
            return {"success": True, "message": SUCCESS_MESSAGES["logout"]}
        return {"success": False, "error": "Session not found"}

    def get_active_sessions_count(self) -> int:
        """Get number of active sessions"""
        self._cleanup_expired_sessions()
        return len(self._active_sessions)

    def get_user_count(self) -> int:
        """Get total number of registered users"""
        try:
            with sqlite3.connect(USERS_DB_PATH) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM users")
                return cursor.fetchone()[0]
        except Exception:
            return 0

# Global auth manager instance
auth_manager = AuthManager()
