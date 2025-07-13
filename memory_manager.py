# Memory manager for Sidekick agent with SQLite long-term storage
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

# Import AsyncSqliteSaver for persistent SQLite memory
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from config import (
    DEFAULT_CONVERSATION_TITLE,
    ERROR_MESSAGES,
    MAX_CONVERSATIONS_PER_USER,
    SIDEKICK_DB_PATH,
    SUCCESS_MESSAGES,
    THREAD_ID_FORMAT,
    ensure_directories,
)


@dataclass
class Conversation:
    """Conversation data structure"""
    id: str
    thread_id: str
    username: str
    title: str
    created_at: datetime
    last_updated: datetime
    message_count: int = 0

class MemoryManager:
    """Manages SQLite-based memory storage and conversation management"""

    def __init__(self):
        ensure_directories()
        self._checkpointer: AsyncSqliteSaver | None = None
        self._connection = None
        self._init_database()

    def _init_database(self):
        """Initialize the conversations database"""
        with sqlite3.connect(SIDEKICK_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT UNIQUE NOT NULL,
                    username TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    message_count INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversations_username 
                ON conversations(username)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversations_last_updated 
                ON conversations(last_updated)
            """)
            conn.commit()

    async def get_checkpointer(self):
        """Get or create checkpointer instance"""
        if self._checkpointer is None:
            # AsyncSqliteSaver.from_conn_string returns an async context manager
            # We need to manage the connection lifecycle differently
            import aiosqlite

            # Create a persistent connection
            self._connection = await aiosqlite.connect(str(SIDEKICK_DB_PATH))
            self._checkpointer = AsyncSqliteSaver(self._connection)

            # Initialize the checkpointer tables
            await self._checkpointer.setup()
            print("✅ Using SQLite checkpointer for persistent memory")
        return self._checkpointer

    def _generate_conversation_id(self) -> str:
        """Generate unique conversation ID"""
        return str(uuid.uuid4())

    def _format_thread_id(self, username: str, conversation_id: str) -> str:
        """Format thread ID for user isolation"""
        return THREAD_ID_FORMAT.format(username=username, conversation_id=conversation_id)

    def _parse_thread_id(self, thread_id: str) -> tuple[str, str]:
        """Parse thread ID to extract username and conversation ID"""
        try:
            parts = thread_id.split('_')
            if len(parts) >= 3 and parts[0] == 'user':
                username = parts[1]
                conversation_id = '_'.join(parts[2:])
                return username, conversation_id
        except Exception:
            pass
        raise ValueError(f"Invalid thread ID format: {thread_id}")

    def _generate_conversation_title(self, message: str) -> str:
        """Generate a simple conversation title from first 50 chars of user message"""
        if not message or not message.strip():
            return DEFAULT_CONVERSATION_TITLE

        # Clean the message - remove extra whitespace and normalize
        cleaned_message = re.sub(r'\s+', ' ', message.strip())
        
        # Remove clarifying questions context if present
        if "\n\nClarifying Questions and Answers:" in cleaned_message:
            cleaned_message = cleaned_message.split("\n\nClarifying Questions and Answers:")[0].strip()

        # Simple approach: take first 50 characters
        if len(cleaned_message) <= 50:
            title = cleaned_message
        else:
            # Truncate at word boundary if possible
            truncated = cleaned_message[:50]
            last_space = truncated.rfind(' ')
            if last_space > 30:  # Only truncate at word boundary if reasonable
                title = truncated[:last_space] + "..."
            else:
                title = truncated + "..."

        # Capitalize first letter
        if title:
            title = title[0].upper() + title[1:] if len(title) > 1 else title.upper()

        # Fallback to default if somehow empty
        return title if title and title.strip() else DEFAULT_CONVERSATION_TITLE

    def create_conversation(self, username: str, title: str = None) -> dict[str, Any]:
        """Create a new conversation for user"""
        try:
            # Check conversation limit
            if self.get_user_conversation_count(username) >= MAX_CONVERSATIONS_PER_USER:
                return {"success": False, "error": ERROR_MESSAGES["conversation_limit"]}

            conversation_id = self._generate_conversation_id()
            thread_id = self._format_thread_id(username, conversation_id)
            title = title or DEFAULT_CONVERSATION_TITLE

            with sqlite3.connect(SIDEKICK_DB_PATH) as conn:
                conn.execute("""
                    INSERT INTO conversations (id, thread_id, username, title)
                    VALUES (?, ?, ?, ?)
                """, (conversation_id, thread_id, username, title))
                conn.commit()

            return {
                "success": True,
                "conversation_id": conversation_id,
                "thread_id": thread_id,
                "title": title
            }

        except Exception as e:
            return {"success": False, "error": f"Failed to create conversation: {e!s}"}

    def get_user_conversations(self, username: str) -> list[Conversation]:
        """Get all conversations for a user"""
        try:
            with sqlite3.connect(SIDEKICK_DB_PATH) as conn:
                cursor = conn.execute("""
                    SELECT id, thread_id, username, title, created_at, last_updated, message_count
                    FROM conversations 
                    WHERE username = ? 
                    ORDER BY last_updated DESC
                """, (username,))

                conversations = []
                for row in cursor.fetchall():
                    conversations.append(Conversation(
                        id=row[0],
                        thread_id=row[1],
                        username=row[2],
                        title=row[3],
                        created_at=datetime.fromisoformat(row[4]),
                        last_updated=datetime.fromisoformat(row[5]),
                        message_count=row[6]
                    ))

                return conversations

        except Exception as e:
            print(f"Error getting user conversations: {e}")
            return []

    def get_conversation(self, conversation_id: str, username: str) -> Conversation | None:
        """Get specific conversation for user"""
        try:
            with sqlite3.connect(SIDEKICK_DB_PATH) as conn:
                cursor = conn.execute("""
                    SELECT id, thread_id, username, title, created_at, last_updated, message_count
                    FROM conversations 
                    WHERE id = ? AND username = ?
                """, (conversation_id, username))

                row = cursor.fetchone()
                if row:
                    return Conversation(
                        id=row[0],
                        thread_id=row[1],
                        username=row[2],
                        title=row[3],
                        created_at=datetime.fromisoformat(row[4]),
                        last_updated=datetime.fromisoformat(row[5]),
                        message_count=row[6]
                    )

        except Exception as e:
            print(f"Error getting conversation: {e}")
        return None

    def update_conversation(self, conversation_id: str, username: str,
                           title: str = None, increment_messages: bool = False) -> bool:
        """Update conversation metadata"""
        try:
            with sqlite3.connect(SIDEKICK_DB_PATH) as conn:
                if title and increment_messages:
                    conn.execute("""
                        UPDATE conversations 
                        SET title = ?, last_updated = CURRENT_TIMESTAMP, message_count = message_count + 1
                        WHERE id = ? AND username = ?
                    """, (title, conversation_id, username))
                elif title:
                    conn.execute("""
                        UPDATE conversations 
                        SET title = ?, last_updated = CURRENT_TIMESTAMP
                        WHERE id = ? AND username = ?
                    """, (title, conversation_id, username))
                elif increment_messages:
                    conn.execute("""
                        UPDATE conversations 
                        SET last_updated = CURRENT_TIMESTAMP, message_count = message_count + 1
                        WHERE id = ? AND username = ?
                    """, (conversation_id, username))
                else:
                    conn.execute("""
                        UPDATE conversations 
                        SET last_updated = CURRENT_TIMESTAMP
                        WHERE id = ? AND username = ?
                    """, (conversation_id, username))

                conn.commit()
                return conn.total_changes > 0

        except Exception as e:
            print(f"Error updating conversation: {e}")
            return False

    def clear_conversation_history(self, conversation_id: str, username: str) -> dict[str, Any]:
        """Clear all messages from a conversation while keeping the conversation record"""
        try:
            print(f"🧹 [CLEAR_HISTORY] Starting clear for conversation: {conversation_id[:8]}... user: {username}")
            
            conversation = self.get_conversation(conversation_id, username)
            if not conversation:
                print(f"❌ [CLEAR_HISTORY] Conversation not found: {conversation_id}")
                return {"success": False, "error": "Conversation not found"}

            print(f"🧹 [CLEAR_HISTORY] Found conversation with thread_id: {conversation.thread_id}")

            with sqlite3.connect(SIDEKICK_DB_PATH) as conn:
                # Check current checkpoint count before clearing
                cursor = conn.execute("SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (conversation.thread_id,))
                checkpoint_count_before = cursor.fetchone()[0]
                print(f"🧹 [CLEAR_HISTORY] Found {checkpoint_count_before} checkpoints to clear")

                # Check current writes count before clearing  
                cursor = conn.execute("SELECT COUNT(*) FROM writes WHERE thread_id = ?", (conversation.thread_id,))
                writes_count_before = cursor.fetchone()[0]
                print(f"🧹 [CLEAR_HISTORY] Found {writes_count_before} writes to clear")

                # Reset conversation to default state: title, message count, and timestamp
                conn.execute("""
                    UPDATE conversations 
                    SET title = ?, message_count = 0, last_updated = CURRENT_TIMESTAMP
                    WHERE id = ? AND username = ?
                """, (DEFAULT_CONVERSATION_TITLE, conversation_id, username))

                # Delete associated checkpoints (this clears the message history)
                checkpoints_deleted = conn.execute("""
                    DELETE FROM checkpoints 
                    WHERE thread_id = ?
                """, (conversation.thread_id,)).rowcount

                # Delete associated writes (LangGraph state changes)
                writes_deleted = conn.execute("""
                    DELETE FROM writes 
                    WHERE thread_id = ?
                """, (conversation.thread_id,)).rowcount

                conn.commit()

                print(f"✅ [CLEAR_HISTORY] Deleted {checkpoints_deleted} checkpoints and {writes_deleted} writes")
                print(f"✅ [CLEAR_HISTORY] Reset title to '{DEFAULT_CONVERSATION_TITLE}' and message count to 0")
                print(f"✅ [CLEAR_HISTORY] Conversation history cleared successfully")

            return {
                "success": True, 
                "message": "Conversation history cleared successfully",
                "conversation_id": conversation_id,
                "username": username
            }

        except Exception as e:
            print(f"❌ [CLEAR_HISTORY] Error clearing conversation history: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": f"Failed to clear conversation history: {e!s}"}

    def delete_conversation(self, conversation_id: str, username: str) -> dict[str, Any]:
        """Delete a specific conversation and its checkpoints"""
        try:
            conversation = self.get_conversation(conversation_id, username)
            if not conversation:
                return {"success": False, "error": "Conversation not found"}

            # Delete conversation record
            with sqlite3.connect(SIDEKICK_DB_PATH) as conn:
                conn.execute("""
                    DELETE FROM conversations 
                    WHERE id = ? AND username = ?
                """, (conversation_id, username))

                # Delete associated checkpoints
                conn.execute("""
                    DELETE FROM checkpoints 
                    WHERE thread_id = ?
                """, (conversation.thread_id,))

                conn.commit()

            return {"success": True, "message": SUCCESS_MESSAGES["conversation_deleted"]}

        except Exception as e:
            return {"success": False, "error": f"Failed to delete conversation: {e!s}"}

    def delete_all_user_memory(self, username: str) -> dict[str, Any]:
        """Delete all conversations and memory for a user"""
        try:
            # Get all user thread IDs
            conversations = self.get_user_conversations(username)
            thread_ids = [conv.thread_id for conv in conversations]

            with sqlite3.connect(SIDEKICK_DB_PATH) as conn:
                # Delete all conversations
                conn.execute("DELETE FROM conversations WHERE username = ?", (username,))

                # Delete all associated checkpoints
                if thread_ids:
                    placeholders = ','.join(['?'] * len(thread_ids))
                    conn.execute(f"DELETE FROM checkpoints WHERE thread_id IN ({placeholders})", thread_ids)

                conn.commit()

            return {"success": True, "message": SUCCESS_MESSAGES["memory_cleared"]}

        except Exception as e:
            return {"success": False, "error": f"Failed to clear memory: {e!s}"}

    def auto_title_conversation(self, conversation_id: str, username: str, message: str) -> bool:
        """Auto-generate and update conversation title based on first message"""
        try:
            print(f"🏷️ [AUTO_TITLE] Starting auto-title for conversation {conversation_id[:8]}... for user {username}")
            print(f"🏷️ [AUTO_TITLE] Message preview: {message[:100] if message else 'None'}...")
            
            # Check if conversation still has default title
            conversation = self.get_conversation(conversation_id, username)
            if not conversation:
                print(f"⚠️ [AUTO_TITLE] Conversation not found: {conversation_id}")
                return False
                
            print(f"🏷️ [AUTO_TITLE] Current title: '{conversation.title}'")
            
            if conversation.title != DEFAULT_CONVERSATION_TITLE:
                print(f"🏷️ [AUTO_TITLE] Conversation already has custom title, skipping")
                return False  # Already has a custom title

            # Generate new title from message
            new_title = self._generate_conversation_title(message)
            print(f"🏷️ [AUTO_TITLE] Generated new title: '{new_title}'")

            # Update conversation with new title
            success = self.update_conversation(conversation_id, username, title=new_title)
            if success:
                print(f"✅ [AUTO_TITLE] Successfully updated conversation title to: '{new_title}'")
            else:
                print(f"❌ [AUTO_TITLE] Failed to update conversation title")
            
            return success

        except Exception as e:
            print(f"❌ [AUTO_TITLE] Error auto-titling conversation: {e}")
            import traceback
            traceback.print_exc()
            return False

    def get_user_conversation_count(self, username: str) -> int:
        """Get number of conversations for user"""
        try:
            with sqlite3.connect(SIDEKICK_DB_PATH) as conn:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM conversations WHERE username = ?",
                    (username,)
                )
                return cursor.fetchone()[0]
        except Exception:
            return 0

    def get_total_conversations(self) -> int:
        """Get total number of conversations in system"""
        try:
            with sqlite3.connect(SIDEKICK_DB_PATH) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM conversations")
                return cursor.fetchone()[0]
        except Exception:
            return 0

    async def cleanup_orphaned_checkpoints(self) -> int:
        """Clean up checkpoints without corresponding conversations"""
        try:
            with sqlite3.connect(SIDEKICK_DB_PATH) as conn:
                # Find orphaned thread_ids
                cursor = conn.execute("""
                    SELECT DISTINCT c.thread_id 
                    FROM checkpoints c
                    LEFT JOIN conversations conv ON c.thread_id = conv.thread_id
                    WHERE conv.thread_id IS NULL
                """)
                orphaned_thread_ids = [row[0] for row in cursor.fetchall()]

                # Delete orphaned checkpoints
                if orphaned_thread_ids:
                    placeholders = ','.join(['?'] * len(orphaned_thread_ids))
                    result = conn.execute(
                        f"DELETE FROM checkpoints WHERE thread_id IN ({placeholders})",
                        orphaned_thread_ids
                    )
                    conn.commit()
                    return result.rowcount

                return 0

        except Exception as e:
            print(f"Error cleaning up orphaned checkpoints: {e}")
            return 0

    async def close(self):
        """Close the SQLite connection and cleanup"""
        if self._connection:
            await self._connection.close()
            self._connection = None
            self._checkpointer = None
            print("✅ SQLite connection closed")

# Global memory manager instance
memory_manager = MemoryManager()
