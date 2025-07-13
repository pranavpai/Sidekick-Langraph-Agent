# Configuration constants for Sidekick agent with authentication and memory
import os
from pathlib import Path

# Directory paths
PROJECT_ROOT = Path(__file__).parent
MEMORY_DIR = PROJECT_ROOT / "memory"
SANDBOX_DIR = PROJECT_ROOT / "sandbox"

# Database paths
SIDEKICK_DB_PATH = MEMORY_DIR / "sidekick.db"
USERS_DB_PATH = MEMORY_DIR / "users.db"

# Authentication settings
PASSWORD_MIN_LENGTH = 6
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 50
SESSION_TIMEOUT_HOURS = 24

# Security settings
BCRYPT_ROUNDS = 12
SECRET_KEY = os.getenv("SIDEKICK_SECRET_KEY", "default_dev_key_change_in_production")

# Thread ID format for user isolation
THREAD_ID_FORMAT = "user_{username}_{conversation_id}"

# Conversation settings
MAX_CONVERSATIONS_PER_USER = 100
DEFAULT_CONVERSATION_TITLE = "New Conversation"

# Database initialization
def ensure_directories():
    """Ensure required directories exist"""
    MEMORY_DIR.mkdir(exist_ok=True)
    SANDBOX_DIR.mkdir(exist_ok=True)

# UI configuration
APP_TITLE = "Sidekick Personal Co-Worker"
APP_THEME = "emerald"
LOGIN_TITLE = "🔐 Sidekick Login"
CHAT_TITLE = "💬 Sidekick Chat"

# Memory management
ENABLE_MEMORY_ENCRYPTION = os.getenv("ENABLE_MEMORY_ENCRYPTION", "false").lower() == "true"
AES_KEY = os.getenv("LANGGRAPH_AES_KEY")  # For LangGraph encryption

# Error messages
ERROR_MESSAGES = {
    "invalid_credentials": "Invalid username or password",
    "username_exists": "Username already exists",
    "username_too_short": f"Username must be at least {USERNAME_MIN_LENGTH} characters",
    "username_too_long": f"Username must be at most {USERNAME_MAX_LENGTH} characters",
    "password_too_short": f"Password must be at least {PASSWORD_MIN_LENGTH} characters",
    "session_expired": "Session expired, please login again",
    "memory_error": "Error accessing memory database",
    "conversation_limit": f"Maximum {MAX_CONVERSATIONS_PER_USER} conversations allowed",
}

# Success messages
SUCCESS_MESSAGES = {
    "login": "Login successful",
    "register": "Account created successfully",
    "logout": "Logged out successfully",
    "memory_cleared": "All memory cleared successfully",
    "conversation_deleted": "Conversation deleted successfully",
}
