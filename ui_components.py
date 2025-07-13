# UI components for Sidekick agent authentication and memory management
from typing import Any

import gradio as gr

from auth_manager import auth_manager
from config import (
    CHAT_TITLE,
    LOGIN_TITLE,
)
from memory_manager import memory_manager


def create_login_interface() -> gr.Blocks:
    """Create the login/register interface"""

    with gr.Blocks(title=LOGIN_TITLE) as login_interface:
        gr.Markdown(f"# {LOGIN_TITLE}")
        gr.Markdown("Please login or register to access your personal Sidekick agent.")

        with gr.Tab("Login"):
            with gr.Column():
                login_username = gr.Textbox(
                    label="Username",
                    placeholder="Enter your username",
                    max_lines=1
                )
                login_password = gr.Textbox(
                    label="Password",
                    placeholder="Enter your password",
                    type="password",
                    max_lines=1
                )
                login_button = gr.Button("Login", variant="primary")
                login_message = gr.Markdown("")

        with gr.Tab("Register"):
            with gr.Column():
                register_username = gr.Textbox(
                    label="Username",
                    placeholder="Choose a username (3-50 characters)",
                    max_lines=1
                )
                register_password = gr.Textbox(
                    label="Password",
                    placeholder="Choose a password (minimum 6 characters)",
                    type="password",
                    max_lines=1
                )
                register_password_confirm = gr.Textbox(
                    label="Confirm Password",
                    placeholder="Confirm your password",
                    type="password",
                    max_lines=1
                )
                register_button = gr.Button("Register", variant="primary")
                register_message = gr.Markdown("")

        # Hidden state for session management
        session_token = gr.State("")
        current_username = gr.State("")

        def handle_login(username: str, password: str):
            """Handle user login"""
            if not username or not password:
                return "", "", "Please enter both username and password", "", ""

            result = auth_manager.login_user(username, password)
            if result["success"]:
                return (
                    result["token"],
                    result["username"],
                    f"✅ {result['message']}",
                    "",
                    ""
                )
            return "", "", f"❌ {result['error']}", "", ""

        def handle_register(username: str, password: str, confirm_password: str):
            """Handle user registration"""
            if not username or not password or not confirm_password:
                return "", "", "", "", "Please fill in all fields"

            if password != confirm_password:
                return "", "", "", "", "❌ Passwords do not match"

            result = auth_manager.register_user(username, password)
            if result["success"]:
                return (
                    result["token"],
                    result["username"],
                    "",
                    "",
                    f"✅ {result['message']}"
                )
            return "", "", "", "", f"❌ {result['error']}"

        # Event handlers
        login_button.click(
            handle_login,
            inputs=[login_username, login_password],
            outputs=[session_token, current_username, login_message, register_message, register_message]
        )

        register_button.click(
            handle_register,
            inputs=[register_username, register_password, register_password_confirm],
            outputs=[session_token, current_username, login_message, login_message, register_message]
        )

        # Allow Enter key in password fields to submit
        login_password.submit(
            handle_login,
            inputs=[login_username, login_password],
            outputs=[session_token, current_username, login_message, register_message, register_message]
        )

        register_password_confirm.submit(
            handle_register,
            inputs=[register_username, register_password, register_password_confirm],
            outputs=[session_token, current_username, login_message, login_message, register_message]
        )

    return login_interface, session_token, current_username

def create_conversation_sidebar(username: str) -> tuple[gr.Column, gr.State, gr.State]:
    """Create conversation management sidebar"""

    with gr.Column(scale=1, min_width=250) as sidebar:
        gr.Markdown("### 💬 Conversations")

        # New conversation button
        new_conversation_btn = gr.Button("➕ New Conversation", variant="primary")

        # Conversation list
        conversation_list = gr.Dropdown(
            label="Previous Conversations",
            choices=[],
            value=None,
            interactive=True
        )

        # Conversation controls
        with gr.Row():
            delete_conversation_btn = gr.Button("🗑️ Delete", variant="stop", size="sm")
            rename_conversation_btn = gr.Button("✏️ Rename", size="sm")

        # Memory management
        gr.Markdown("### 🧠 Memory")
        clear_all_memory_btn = gr.Button("🗑️ Clear All Memory", variant="stop")

        # User info
        gr.Markdown("### 👤 Account")
        user_info = gr.Markdown(f"**Logged in as:** {username}")
        logout_btn = gr.Button("🚪 Logout", variant="secondary")

        # Status messages
        sidebar_status = gr.Markdown("", visible=False)

    # State variables
    current_conversation_id = gr.State("")
    conversations_data = gr.State([])

    def load_conversations(username: str):
        """Load user's conversations"""
        try:
            conversations = memory_manager.get_user_conversations(username)
            choices = []
            data = []

            for conv in conversations:
                # Format display name with date and message count
                display_name = f"{conv.title} ({conv.message_count} msgs) - {conv.last_updated.strftime('%m/%d %H:%M')}"
                choices.append((display_name, conv.id))
                data.append({
                    "id": conv.id,
                    "title": conv.title,
                    "created_at": conv.created_at.isoformat(),
                    "last_updated": conv.last_updated.isoformat(),
                    "message_count": conv.message_count
                })

            return gr.update(choices=choices, value=None), data, ""

        except Exception as e:
            return gr.update(choices=[], value=None), [], f"Error loading conversations: {e!s}"

    def create_new_conversation(username: str):
        """Create a new conversation"""
        try:
            result = memory_manager.create_conversation(username)
            if result["success"]:
                # Reload conversations
                conversations = memory_manager.get_user_conversations(username)
                choices = []
                data = []

                for conv in conversations:
                    display_name = f"{conv.title} ({conv.message_count} msgs) - {conv.last_updated.strftime('%m/%d %H:%M')}"
                    choices.append((display_name, conv.id))
                    data.append({
                        "id": conv.id,
                        "title": conv.title,
                        "created_at": conv.created_at.isoformat(),
                        "last_updated": conv.last_updated.isoformat(),
                        "message_count": conv.message_count
                    })

                return (
                    gr.update(choices=choices, value=result["conversation_id"]),
                    result["conversation_id"],
                    data,
                    "✅ New conversation created"
                )
            return gr.update(), "", [], f"❌ {result['error']}"

        except Exception as e:
            return gr.update(), "", [], f"❌ Error creating conversation: {e!s}"

    def delete_conversation(username: str, conversation_id: str):
        """Delete selected conversation"""
        if not conversation_id:
            return gr.update(), "", [], "❌ No conversation selected"

        try:
            result = memory_manager.delete_conversation(conversation_id, username)
            if result["success"]:
                # Reload conversations
                conversations = memory_manager.get_user_conversations(username)
                choices = []
                data = []

                for conv in conversations:
                    display_name = f"{conv.title} ({conv.message_count} msgs) - {conv.last_updated.strftime('%m/%d %H:%M')}"
                    choices.append((display_name, conv.id))
                    data.append({
                        "id": conv.id,
                        "title": conv.title,
                        "created_at": conv.created_at.isoformat(),
                        "last_updated": conv.last_updated.isoformat(),
                        "message_count": conv.message_count
                    })

                return (
                    gr.update(choices=choices, value=None),
                    "",
                    data,
                    f"✅ {result['message']}"
                )
            return gr.update(), conversation_id, [], f"❌ {result['error']}"

        except Exception as e:
            return gr.update(), conversation_id, [], f"❌ Error deleting conversation: {e!s}"

    def clear_all_memory(username: str):
        """Clear all user memory"""
        try:
            result = memory_manager.delete_all_user_memory(username)
            if result["success"]:
                return (
                    gr.update(choices=[], value=None),
                    "",
                    [],
                    f"✅ {result['message']}"
                )
            return gr.update(), "", [], f"❌ {result['error']}"

        except Exception as e:
            return gr.update(), "", [], f"❌ Error clearing memory: {e!s}"

    # Event handlers (to be connected in main app)
    sidebar_events = {
        "load_conversations": load_conversations,
        "create_new_conversation": create_new_conversation,
        "delete_conversation": delete_conversation,
        "clear_all_memory": clear_all_memory,
        "components": {
            "new_conversation_btn": new_conversation_btn,
            "conversation_list": conversation_list,
            "delete_conversation_btn": delete_conversation_btn,
            "clear_all_memory_btn": clear_all_memory_btn,
            "logout_btn": logout_btn,
            "sidebar_status": sidebar_status
        }
    }

    return sidebar, current_conversation_id, conversations_data, sidebar_events

def create_chat_interface() -> tuple[gr.Column, dict[str, gr.Component]]:
    """Create the main chat interface"""

    with gr.Column(scale=3) as chat_interface:
        gr.Markdown(f"# {CHAT_TITLE}")

        # Chat display area
        chatbot = gr.Chatbot(
            label="Sidekick",
            height=400,
            type="messages",
            show_copy_button=True
        )

        # Input area
        with gr.Group():
            with gr.Row():
                message = gr.Textbox(
                    show_label=False,
                    placeholder="Your request to the Sidekick",
                    scale=4,
                    max_lines=3
                )
            with gr.Row():
                success_criteria = gr.Textbox(
                    show_label=False,
                    placeholder="What are your success criteria?",
                    scale=4,
                    max_lines=2
                )

        # Clarifying questions section (initially hidden)
        with gr.Group(visible=False) as clarifying_section:
            gr.Markdown("### Clarifying Questions")
            gr.Markdown("*Please answer any questions that would help improve the response (optional):*")
            with gr.Column():
                q1_display = gr.Markdown("")
                q1_answer = gr.Textbox(label="Your answer (optional)", placeholder="Type your answer here...")
                q2_display = gr.Markdown("")
                q2_answer = gr.Textbox(label="Your answer (optional)", placeholder="Type your answer here...")
                q3_display = gr.Markdown("")
                q3_answer = gr.Textbox(label="Your answer (optional)", placeholder="Type your answer here...")
            with gr.Row():
                continue_button = gr.Button("Continue with Processing", variant="primary")
                skip_clarifying_button = gr.Button("Skip Questions", variant="secondary")

        # Main control buttons
        with gr.Group(visible=True) as main_controls:
            with gr.Row():
                reset_button = gr.Button("🔄 Reset", variant="stop")
                clarify_button = gr.Button("❓ Ask Clarifying Questions First", variant="secondary")
                go_button = gr.Button("🚀 Go Directly!", variant="primary")

        # Status area
        status_message = gr.Markdown("", visible=False)

    # Return components for event handling
    components = {
        "chatbot": chatbot,
        "message": message,
        "success_criteria": success_criteria,
        "clarifying_section": clarifying_section,
        "main_controls": main_controls,
        "q1_display": q1_display,
        "q1_answer": q1_answer,
        "q2_display": q2_display,
        "q2_answer": q2_answer,
        "q3_display": q3_display,
        "q3_answer": q3_answer,
        "continue_button": continue_button,
        "skip_clarifying_button": skip_clarifying_button,
        "reset_button": reset_button,
        "clarify_button": clarify_button,
        "go_button": go_button,
        "status_message": status_message
    }

    return chat_interface, components

def validate_session(token: str) -> tuple[bool, str]:
    """Validate user session"""
    if not token:
        return False, ""

    session = auth_manager.validate_session(token)
    if session:
        return True, session.username
    return False, ""

def logout_user(token: str) -> dict[str, Any]:
    """Logout user and invalidate session"""
    if token:
        return auth_manager.logout_user(token)
    return {"success": True, "message": "Logged out"}
