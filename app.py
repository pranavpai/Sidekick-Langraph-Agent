# Gradio web interface framework for building interactive ML demos
import asyncio

import gradio as gr

# Import authentication and memory management
from auth_manager import auth_manager
from config import APP_THEME, APP_TITLE, ensure_directories
from memory_manager import memory_manager

# Import the main Sidekick agent class
from sidekick import Sidekick

# Global state for managing authenticated sessions
active_sidekicks = {}

# Global browser manager to prevent multiple Chrome instances
class BrowserManager:
    def __init__(self):
        self.shared_browser = None
        self.shared_playwright = None
        self.reference_count = 0

    async def get_browser(self):
        """Get or create a shared browser instance"""
        if self.shared_browser is None:
            from playwright.async_api import async_playwright
            print("🌐 Creating shared browser instance...")
            self.shared_playwright = await async_playwright().start()
            self.shared_browser = await self.shared_playwright.chromium.launch(headless=False)
            print("✅ Shared browser instance created")

        self.reference_count += 1
        print(f"📊 Browser reference count: {self.reference_count}")
        return self.shared_browser, self.shared_playwright

    async def release_browser(self):
        """Release browser reference and cleanup if no more references"""
        if self.reference_count > 0:
            self.reference_count -= 1
            print(f"📊 Browser reference count: {self.reference_count}")

        # Only close browser when all references are released
        if self.reference_count == 0 and self.shared_browser:
            print("🔄 Closing shared browser instance...")
            try:
                await self.shared_browser.close()
                if self.shared_playwright:
                    await self.shared_playwright.stop()
            except Exception as e:
                print(f"⚠️ Error closing browser: {e}")
            finally:
                self.shared_browser = None
                self.shared_playwright = None
            print("✅ Shared browser instance closed")

# Global browser manager instance
browser_manager = BrowserManager()

# Async initialization function for Sidekick agent with user context
async def setup_sidekick(username=None, conversation_id=None):
    try:
        print(f"Initializing Sidekick agent... User: {username}, Conversation: {conversation_id}")

        # Get shared browser instance
        shared_browser, shared_playwright = await browser_manager.get_browser()

        # Create new Sidekick instance with user context
        sidekick = Sidekick(username=username, conversation_id=conversation_id)
        # Initialize all agent components (LLMs, tools, graph) with shared browser
        await sidekick.setup(shared_browser=shared_browser, shared_playwright=shared_playwright)

        # Store in active sessions if authenticated
        if username and conversation_id:
            session_key = f"{username}_{conversation_id}"
            active_sidekicks[session_key] = sidekick

        print("Sidekick agent initialized successfully!")
        return sidekick
    except Exception as e:
        print(f"Error initializing Sidekick agent: {e}")
        import traceback
        traceback.print_exc()
        return None

# Legacy setup function for backward compatibility
async def setup():
    return await setup_sidekick()

# Generate clarifying questions for user input
# First phase of two-phase processing workflow
async def generate_clarifying_questions(sidekick, message, success_criteria, chatbot):
    import time
    start_time = time.time()
    print(f"\n❓ [QUESTIONS] Starting generate_clarifying_questions at {time.strftime('%H:%M:%S')}")

    try:
        # Validate inputs
        if not message or not message.strip():
            print("❌ [QUESTIONS] No message provided")
            return ["Please provide a message first", "", ""], gr.update(visible=True), gr.update(visible=False)

        if not sidekick:
            print("❌ [QUESTIONS] Sidekick agent not available")
            return [
                "❌ Agent not initialized. Please try one of the following:",
                "• Click 'New Conversation' to create a fresh conversation",
                "• Try logging out and back in if the issue persists"
            ], gr.update(visible=True), gr.update(visible=False)

        # Log input details
        print(f"📝 [QUESTIONS] Message length: {len(message)} chars")
        print(f"📝 [QUESTIONS] Message preview: {message[:100]}...")
        print(f"📝 [QUESTIONS] Success criteria: {success_criteria[:50] if success_criteria else 'None'}...")

        # Generate 3 clarifying questions using the agent
        print("🤖 [QUESTIONS] Calling sidekick.generate_clarifying_questions...")
        questions = await sidekick.generate_clarifying_questions(message.strip(), success_criteria or "")

        # Log the generated questions
        end_time = time.time()
        print(f"✅ [QUESTIONS] Generated {len(questions)} questions in {end_time - start_time:.2f}s:")
        for i, question in enumerate(questions):
            print(f"  Q{i+1}: {question}")

        # Return questions to display in UI
        return questions, gr.update(visible=True), gr.update(visible=False)
    except Exception as e:
        error_time = time.time()
        print(f"❌ [QUESTIONS] Error after {error_time - start_time:.2f}s: {e}")
        import traceback
        traceback.print_exc()
        return [
            f"❌ Error generating questions: {e!s}",
            "• Try using 'Go Directly!' instead",
            "• Or reset the conversation and try again"
        ], gr.update(visible=True), gr.update(visible=False)

# Main message processing function with clarifying answers
# Second phase of processing workflow that includes clarifying context
async def process_with_clarifying(sidekick, message, success_criteria, chatbot, q1_answer, q2_answer, q3_answer, clarifying_questions, username, conversation_id):
    import time
    start_time = time.time()
    print(f"\n🔍 [CLARIFYING] Starting process_with_clarifying at {time.strftime('%H:%M:%S')}")

    try:
        # Validate critical inputs first
        if not sidekick:
            print("❌ [CLARIFYING] Error: Sidekick agent is None")
            error_message = {"role": "assistant", "content": "❌ Error: Sidekick agent not initialized. Please reset the conversation and try again."}
            return [error_message], None, gr.update(visible=False), gr.update(visible=True)

        if not message or not message.strip():
            print("❌ [CLARIFYING] Error: Message is empty")
            error_message = {"role": "assistant", "content": "❌ Error: Please provide a message to process."}
            return [error_message], sidekick, gr.update(visible=False), gr.update(visible=True)

        # Log input parameters
        print(f"📝 [CLARIFYING] Original message length: {len(message) if message else 0}")
        print(f"📝 [CLARIFYING] Success criteria: {success_criteria[:100] if success_criteria else 'None'}...")
        print(f"📝 [CLARIFYING] Questions available: {len(clarifying_questions) if clarifying_questions else 0}")
        print(f"📝 [CLARIFYING] Chatbot history type: {type(chatbot)}, length: {len(chatbot) if hasattr(chatbot, '__len__') else 'N/A'}")
        print(f"📝 [CLARIFYING] Sidekick object type: {type(sidekick)}")

        # Ensure chatbot is a list
        if not isinstance(chatbot, list):
            print("⚠️ [CLARIFYING] Converting chatbot to list")
            chatbot = []

        # Combine original message with clarifying answers
        clarifying_context = ""
        print("📝 [CLARIFYING] Processing clarifying questions...")
        print(f"📝 [CLARIFYING] Available questions: {len(clarifying_questions) if clarifying_questions else 0}")

        if clarifying_questions and len(clarifying_questions) >= 3:
            answers = [q1_answer, q2_answer, q3_answer]
            answered_questions = []

            # Log all questions first
            print("❓ [CLARIFYING] All 3 generated questions:")
            for i, question in enumerate(clarifying_questions[:3]):
                print(f"  Q{i+1}: {question}")

            # Log all answers
            print("💬 [CLARIFYING] User's answers:")
            for i, (question, answer) in enumerate(zip(clarifying_questions[:3], answers, strict=False)):
                if answer and answer.strip():
                    answered_questions.append(f"Q{i+1}: {question}\nA{i+1}: {answer.strip()}")
                    print(f"  ✅ A{i+1}: '{answer.strip()}'")
                else:
                    print(f"  ⏸️ A{i+1}: [No answer provided]")

            if answered_questions:
                clarifying_context = "\n\nClarifying Questions and Answers:\n" + "\n\n".join(answered_questions)
                print(f"📋 [CLARIFYING] Created clarifying context with {len(answered_questions)} answered questions")
                print(f"📏 [CLARIFYING] Clarifying context length: {len(clarifying_context)} chars")
            else:
                print("⚠️ [CLARIFYING] No answers provided, proceeding without clarifying context")
        else:
            print(f"⚠️ [CLARIFYING] Insufficient questions available ({len(clarifying_questions) if clarifying_questions else 0}), skipping clarifying context")

        # Enhance the original message with clarifying context
        enhanced_message = message + clarifying_context
        print(f"📏 [CLARIFYING] Enhanced message total length: {len(enhanced_message)}")
        print(f"📄 [CLARIFYING] Enhanced message preview: {enhanced_message[:200]}...")

        # Log before calling run_superstep
        pre_superstep_time = time.time()
        print(f"🚀 [CLARIFYING] Calling run_superstep at {time.strftime('%H:%M:%S')} (prep took {pre_superstep_time - start_time:.2f}s)")

        # Run the complete agent workflow with enhanced context
        # Pass both original message (for storage) and enhanced message (for LLM processing)
        # Add Gradio-specific timeout protection (120 seconds)
        print("⏱️ [CLARIFYING] Starting run_superstep with 120s timeout protection...")
        try:
            results = await asyncio.wait_for(
                sidekick.run_superstep(enhanced_message, success_criteria, chatbot, original_message=message),
                timeout=120  # 2 minutes timeout to prevent Gradio connection issues
            )
        except TimeoutError:
            print("⏰ [CLARIFYING] run_superstep timed out after 120s, falling back...")
            raise Exception("Processing timed out after 2 minutes")

        # Log completion
        end_time = time.time()
        print(f"✅ [CLARIFYING] run_superstep completed at {time.strftime('%H:%M:%S')} (took {end_time - pre_superstep_time:.2f}s)")
        print(f"🎯 [CLARIFYING] Total process_with_clarifying time: {end_time - start_time:.2f}s")
        print(f"📊 [CLARIFYING] Results type: {type(results)}, length: {len(results) if hasattr(results, '__len__') else 'N/A'}")

        # Validate results
        if not isinstance(results, list):
            print(f"⚠️ [CLARIFYING] Converting results to list, was: {type(results)}")
            results = []

        # Refresh conversation dropdown to show updated title if it was auto-updated
        try:
            refreshed_conv_choices, _ = await refresh_conversation_list(username, conversation_id)
            conversation_dropdown_update = gr.update(choices=refreshed_conv_choices, value=conversation_id)
            print(f"🔄 [CLARIFYING] Refreshed dropdown with {len(refreshed_conv_choices)} choices")
        except Exception as e:
            print(f"⚠️ [CLARIFYING] Error refreshing dropdown: {e}")
            conversation_dropdown_update = gr.update()
        
        # FIXED: Proper return format matching Gradio event handler expectations
        # [chatbot, sidekick, clarifying_section, main_controls, conversation_list]
        return results, sidekick, gr.update(visible=False), gr.update(visible=True), conversation_dropdown_update

    except Exception as e:
        error_time = time.time()
        print(f"❌ [CLARIFYING] Error at {time.strftime('%H:%M:%S')} (after {error_time - start_time:.2f}s): {e}")
        import traceback
        traceback.print_exc()

                # CIRCUIT BREAKER: Fall back to direct processing if clarifying workflow fails
        if sidekick:  # Only try fallback if sidekick exists
            print("🔄 [CLARIFYING] Attempting fallback to direct processing...")
            try:
                fallback_start = time.time()
                # Try direct processing with original message as fallback
                # Use original message for both parameters since we're bypassing clarifying
                fallback_results = await sidekick.run_superstep(message, success_criteria, chatbot, original_message=message)
                fallback_end = time.time()
                print(f"✅ [CLARIFYING] Fallback successful in {fallback_end - fallback_start:.2f}s")

                # Ensure fallback_results is a list
                if not isinstance(fallback_results, list):
                    fallback_results = []

                # Add notification about fallback to the beginning of new messages
                if len(fallback_results) > len(chatbot):
                    new_messages = fallback_results[len(chatbot):]
                    notification = {"role": "assistant", "content": "⚠️ Clarifying questions workflow encountered issues, processed your request directly instead."}
                    enhanced_results = chatbot + [notification] + new_messages
                else:
                    enhanced_results = fallback_results

                # Refresh conversation dropdown for fallback case too
                try:
                    refreshed_conv_choices, _ = await refresh_conversation_list(username, conversation_id)
                    conversation_dropdown_update = gr.update(choices=refreshed_conv_choices, value=conversation_id)
                    print(f"🔄 [CLARIFYING] Fallback refreshed dropdown with {len(refreshed_conv_choices)} choices")
                except Exception as e:
                    print(f"⚠️ [CLARIFYING] Error refreshing dropdown in fallback: {e}")
                    conversation_dropdown_update = gr.update()
                
                return enhanced_results, sidekick, gr.update(visible=False), gr.update(visible=True), conversation_dropdown_update

            except Exception as fallback_error:
                print(f"❌ [CLARIFYING] Fallback also failed: {fallback_error}")
                import traceback
                traceback.print_exc()
        else:
            print("❌ [CLARIFYING] No sidekick available for fallback")

        # Final error state - ensure proper format
        # Try to refresh conversation dropdown even on error
        try:
            refreshed_conv_choices, _ = await refresh_conversation_list(username, conversation_id)
            conversation_dropdown_update = gr.update(choices=refreshed_conv_choices, value=conversation_id)
        except:
            conversation_dropdown_update = gr.update()
            
        error_message = {"role": "assistant", "content": "❌ Error: Processing failed. Please try resetting the conversation or logging out and back in."}
        error_history = chatbot + [error_message] if isinstance(chatbot, list) else [error_message]
        return error_history, sidekick, gr.update(visible=False), gr.update(visible=True), conversation_dropdown_update

# Original process_message function for direct processing (skip clarifying questions)
async def process_message_direct(sidekick, message, success_criteria, chatbot, username, conversation_id):
    import time
    start_time = time.time()
    print(f"\n🔄 [DIRECT] Starting process_message_direct at {time.strftime('%H:%M:%S')}")

    try:
        # Validate critical inputs first
        if not sidekick:
            print("❌ [DIRECT] Error: Sidekick agent is None")
            error_message = {"role": "assistant", "content": "❌ Error: Sidekick agent not initialized. Please reset the conversation and try again."}
            return [error_message], None

        if not message or not message.strip():
            print("❌ [DIRECT] Error: Message is empty")
            error_message = {"role": "assistant", "content": "❌ Error: Please provide a message to process."}
            return [error_message], sidekick

        # Log input parameters
        print(f"📝 [DIRECT] Message length: {len(message) if message else 0}")
        print(f"📝 [DIRECT] Success criteria: {success_criteria[:100] if success_criteria else 'None'}...")
        print(f"📄 [DIRECT] Message preview: {message[:200] if message else 'None'}...")
        print(f"📝 [DIRECT] Sidekick object type: {type(sidekick)}")

        # Ensure chatbot is a list
        if not isinstance(chatbot, list):
            print("⚠️ [DIRECT] Converting chatbot to list")
            chatbot = []

        # Run the complete agent workflow (worker-evaluator pattern)
        print(f"🚀 [DIRECT] Calling run_superstep at {time.strftime('%H:%M:%S')}")
        # For direct processing, message is both the LLM input and storage input (no enhancement)
        results = await sidekick.run_superstep(message, success_criteria, chatbot, original_message=message)

        # Log completion
        end_time = time.time()
        print(f"✅ [DIRECT] Completed at {time.strftime('%H:%M:%S')} (took {end_time - start_time:.2f}s)")
        print(f"📊 [DIRECT] Results type: {type(results)}, length: {len(results) if hasattr(results, '__len__') else 'N/A'}")

        # Validate results
        if not isinstance(results, list):
            print(f"⚠️ [DIRECT] Converting results to list, was: {type(results)}")
            results = []

        # Refresh conversation dropdown to show updated title if it was auto-updated
        try:
            refreshed_conv_choices, _ = await refresh_conversation_list(username, conversation_id)
            conversation_dropdown_update = gr.update(choices=refreshed_conv_choices, value=conversation_id)
            print(f"🔄 [DIRECT] Refreshed dropdown with {len(refreshed_conv_choices)} choices")
        except Exception as e:
            print(f"⚠️ [DIRECT] Error refreshing dropdown: {e}")
            conversation_dropdown_update = gr.update()
        
        # Return updated chat history, agent state, and refreshed conversation dropdown
        return results, sidekick, conversation_dropdown_update

    except Exception as e:
        error_time = time.time()
        print(f"❌ [DIRECT] Error at {time.strftime('%H:%M:%S')} (after {error_time - start_time:.2f}s): {e}")
        import traceback
        traceback.print_exc()

        # Ensure chatbot is a list for error handling
        if not isinstance(chatbot, list):
            chatbot = []

        # Try to refresh conversation dropdown even on error
        try:
            refreshed_conv_choices, _ = await refresh_conversation_list(username, conversation_id)
            conversation_dropdown_update = gr.update(choices=refreshed_conv_choices, value=conversation_id)
        except:
            conversation_dropdown_update = gr.update()
        
        # Return error state
        error_message = {"role": "assistant", "content": f"❌ Error: Processing failed. Please try resetting the conversation. Details: {e!s}"}
        error_history = chatbot + [error_message]
        return error_history, sidekick, conversation_dropdown_update

# Clear chat display function - only clears UI, preserves conversation history in DB
# This gives users a clean visual interface without losing their data
async def clear_chat_display(username=None, conversation_id=None):
    """Clear chat display and conversation history from database"""
    print(f"\n🧹 [CLEAR_DISPLAY] Clearing chat display and history for user: {username}, conversation: {conversation_id[:8] if conversation_id else 'None'}...")

    conversation_dropdown_update = gr.update()  # Default no change
    
    if username and conversation_id:
        # Actually clear the conversation history from the database
        try:
            result = memory_manager.clear_conversation_history(conversation_id, username)
            if result["success"]:
                print("✅ [CLEAR_DISPLAY] Conversation history cleared from database")
                
                # CRITICAL: Remove Sidekick instance from memory cache to prevent toggle behavior
                session_key = f"{username}_{conversation_id}"
                if session_key in active_sidekicks:
                    # Properly cleanup the Sidekick instance
                    try:
                        active_sidekicks[session_key].cleanup()
                        print(f"🧹 [CLEAR_DISPLAY] Cleaned up Sidekick instance for {session_key}")
                    except Exception as cleanup_error:
                        print(f"⚠️ [CLEAR_DISPLAY] Error during Sidekick cleanup: {cleanup_error}")
                    
                    # Remove from cache
                    del active_sidekicks[session_key]
                    print(f"🗑️ [CLEAR_DISPLAY] Removed Sidekick from cache: {session_key}")
                else:
                    print(f"ℹ️ [CLEAR_DISPLAY] No cached Sidekick found for {session_key}")
                
                # Refresh dropdown to show updated state (title reset to default, 0 messages)
                try:
                    refreshed_conv_choices, _ = await refresh_conversation_list(username, conversation_id)
                    conversation_dropdown_update = gr.update(choices=refreshed_conv_choices, value=conversation_id)
                    print(f"🔄 [CLEAR_DISPLAY] Refreshed dropdown after clear with {len(refreshed_conv_choices)} choices")
                except Exception as e:
                    print(f"⚠️ [CLEAR_DISPLAY] Error refreshing dropdown after clear: {e}")
                    conversation_dropdown_update = gr.update()
            else:
                print(f"⚠️ [CLEAR_DISPLAY] Failed to clear history: {result['error']}")
        except Exception as e:
            print(f"❌ [CLEAR_DISPLAY] Error clearing history: {e}")
    else:
        print("⚠️ [CLEAR_DISPLAY] No username/conversation_id provided, only clearing UI")

    print("✅ [CLEAR_DISPLAY] Chat display cleared")

    # Return empty UI values and updated conversation dropdown
    return (
        "",                         # Clear message input
        "",                         # Clear success criteria input
        [],                         # Clear chatbot display
        "",                         # Clear Q1 answer
        "",                         # Clear Q2 answer
        "",                         # Clear Q3 answer
        gr.update(visible=False),   # Hide clarifying section
        gr.update(visible=True),    # Show main controls
        conversation_dropdown_update # Updated conversation dropdown
    )

# Helper function to update clarifying questions display
def update_question_displays(questions):
    """Update the question display components with generated questions"""
    if not questions or len(questions) < 3:
        return gr.update(value=""), gr.update(value=""), gr.update(value="")

    return (
        gr.update(value=f"**Question 1:** {questions[0]}"),
        gr.update(value=f"**Question 2:** {questions[1]}"),
        gr.update(value=f"**Question 3:** {questions[2]}")
    )

# Enhanced generate clarifying questions with UI updates
async def generate_and_display_questions(sidekick, message, success_criteria, chatbot):
    """Generate clarifying questions and update UI to show them"""
    try:
        questions, show_clarifying, hide_main = await generate_clarifying_questions(sidekick, message, success_criteria, chatbot)
        q1_update, q2_update, q3_update = update_question_displays(questions)
        return questions, show_clarifying, hide_main, q1_update, q2_update, q3_update, "", "", ""
    except Exception as e:
        print(f"Error in generate_and_display_questions: {e}")
        error_questions = [f"Error: {e!s}", "", ""]
        q1_update, q2_update, q3_update = update_question_displays(error_questions)
        return error_questions, gr.update(visible=True), gr.update(visible=False), q1_update, q2_update, q3_update, "", "", ""

# Resource cleanup callback for Gradio state management
# Called automatically when agent state is deleted or interface closes
def free_resources(sidekick):
    print("Cleaning up")
    try:
        # Clean up agent resources
        if sidekick:
            sidekick.cleanup()

        # Release browser reference
        asyncio.create_task(browser_manager.release_browser())

    except Exception as e:
        print(f"Exception during cleanup: {e}")


# Authentication and conversation management functions
async def handle_login(username: str, password: str):
    """Handle user login"""
    if not username or not password:
        return "", "", "Please enter both username and password", gr.update(visible=True), gr.update(visible=False), [], "", None

    result = auth_manager.login_user(username, password)
    if result["success"]:
        # Load user's conversations
        conversations = memory_manager.get_user_conversations(username)
        conv_choices = []

        for conv in conversations:
            # Truncate title if too long for better display
            title = conv.title
            if len(title) > 40:
                title = title[:37] + "..."

            # Enhanced display format with better readability
            display_name = f"📝 {title} • {conv.message_count} msgs • {conv.last_updated.strftime('%m/%d %H:%M')}"
            conv_choices.append((display_name, conv.id))

        # Create initial conversation if none exist
        if not conversations:
            conv_result = memory_manager.create_conversation(username)
            if conv_result["success"]:
                conversations = memory_manager.get_user_conversations(username)
                for conv in conversations:
                    # Truncate title if too long for better display
                    title = conv.title
                    if len(title) > 40:
                        title = title[:37] + "..."

                    # Enhanced display format with better readability
                    display_name = f"📝 {title} • {conv.message_count} msgs • {conv.last_updated.strftime('%m/%d %H:%M')}"
                    conv_choices.append((display_name, conv.id))

        selected_conv_id = conv_choices[0][1] if conv_choices else ""

        # Initialize Sidekick agent for the selected conversation
        sidekick_agent = None
        if selected_conv_id:
            try:
                sidekick_agent = await setup_sidekick(username, selected_conv_id)
                print(f"✅ Sidekick agent initialized for user {username}, conversation {selected_conv_id}")
            except Exception as e:
                print(f"⚠️ Warning: Could not initialize Sidekick agent: {e}")

        return (
            result["token"],
            result["username"],
            f"✅ {result['message']}",
            gr.update(visible=False),  # Hide login
            gr.update(visible=True),   # Show chat
            safe_dropdown_update(conv_choices, selected_conv_id),  # Safe dropdown update
            selected_conv_id,
            sidekick_agent
        )
    return "", "", f"❌ {result['error']}", gr.update(visible=True), gr.update(visible=False), [], "", None

async def handle_register(username: str, password: str, confirm_password: str):
    """Handle user registration"""
    if not username or not password or not confirm_password:
        return "", "", "Please fill in all fields", gr.update(visible=True), gr.update(visible=False), [], "", None

    if password != confirm_password:
        return "", "", "❌ Passwords do not match", gr.update(visible=True), gr.update(visible=False), [], "", None

    result = auth_manager.register_user(username, password)
    if result["success"]:
        # Create initial conversation
        conv_result = memory_manager.create_conversation(username)
        conv_choices = []
        selected_conv_id = ""

        if conv_result["success"]:
            conversations = memory_manager.get_user_conversations(username)
            for conv in conversations:
                # Truncate title if too long for better display
                title = conv.title
                if len(title) > 40:
                    title = title[:37] + "..."

                # Enhanced display format with better readability
                display_name = f"📝 {title} • {conv.message_count} msgs • {conv.last_updated.strftime('%m/%d %H:%M')}"
                conv_choices.append((display_name, conv.id))
            selected_conv_id = conv_choices[0][1] if conv_choices else ""

        # Initialize Sidekick agent for the new conversation
        sidekick_agent = None
        if selected_conv_id:
            try:
                sidekick_agent = await setup_sidekick(username, selected_conv_id)
                print(f"✅ Sidekick agent initialized for new user {username}, conversation {selected_conv_id}")
            except Exception as e:
                print(f"⚠️ Warning: Could not initialize Sidekick agent: {e}")

        return (
            result["token"],
            result["username"],
            f"✅ {result['message']}",
            gr.update(visible=False),  # Hide login
            gr.update(visible=True),   # Show chat
            safe_dropdown_update(conv_choices, selected_conv_id),  # Safe dropdown update
            selected_conv_id,
            sidekick_agent
        )
    return "", "", f"❌ {result['error']}", gr.update(visible=True), gr.update(visible=False), [], "", None

def handle_logout(token: str):
    """Handle user logout"""
    auth_manager.logout_user(token)
    return "", "", "✅ Logged out successfully", gr.update(visible=True), gr.update(visible=False), [], "", None, []

async def handle_conversation_change(username: str, conversation_id: str):
    """Handle conversation selection change with simplified logic"""
    print(f"\n🔄 [CONV_CHANGE] Starting conversation change for user: {username}")

    if not username:
        print("❌ [CONV_CHANGE] No username provided")
        return None, []

    if not conversation_id:
        print("❌ [CONV_CHANGE] No conversation ID provided")
        return None, []

    # Since we removed allow_custom_value, conversation_id should be a simple string
    # If it's not, something went wrong with the dropdown configuration
    if not isinstance(conversation_id, str):
        print(f"⚠️ [CONV_CHANGE] Unexpected conversation_id type: {type(conversation_id)}, value: {conversation_id}")
        # Try to convert to string as fallback
        conversation_id = str(conversation_id)

    print(f"🎯 [CONV_CHANGE] Switching to conversation: {conversation_id[:8]}...")

    # Setup or get existing Sidekick for this conversation
    session_key = f"{username}_{conversation_id}"

    if session_key in active_sidekicks:
        sidekick = active_sidekicks[session_key]
        print(f"✅ [CONV_CHANGE] Found existing Sidekick for session: {session_key}")
    else:
        print(f"🆕 [CONV_CHANGE] Creating new Sidekick for session: {session_key}")
        sidekick = await setup_sidekick(username, conversation_id)
        if sidekick:
            print("✅ [CONV_CHANGE] Successfully created Sidekick")
        else:
            print("❌ [CONV_CHANGE] Failed to create Sidekick")

    # Load conversation history
    if sidekick:
        try:
            history = await sidekick.get_conversation_history()
            print(f"📚 [CONV_CHANGE] Loaded {len(history)} messages from conversation history")
            return sidekick, history
        except Exception as e:
            print(f"❌ [CONV_CHANGE] Error loading conversation history: {e}")
            return sidekick, []

    print("❌ [CONV_CHANGE] No sidekick available, returning empty state")
    return None, []

async def handle_new_conversation(username: str):
    """Handle new conversation creation with full UI reset"""
    print(f"\n🆕 [NEW_CONV] Creating new conversation for {username}")

    result = memory_manager.create_conversation(username)
    if result["success"]:
        conversation_id = result["conversation_id"]
        print(f"✅ [NEW_CONV] Created conversation: {conversation_id[:8]}...")

        # Setup fresh Sidekick for new conversation
        sidekick = await setup_sidekick(username, conversation_id)
        print("✅ [NEW_CONV] Initialized Sidekick agent")

        # Refresh conversation list with new conversation selected
        conv_choices, _ = await refresh_conversation_list(username, conversation_id)
        print(f"✅ [NEW_CONV] Refreshed conversation list with {len(conv_choices)} items")

        # Return all UI components in reset state
        return (
            safe_dropdown_update(conv_choices, conversation_id),  # Safe dropdown update
            conversation_id,        # Selected conversation ID
            sidekick,              # Fresh Sidekick agent
            [],                    # Empty chat history
            "✅ New conversation created - ready for your first message!",  # Status message
            "",                    # Clear message input
            "",                    # Clear success criteria input
            "",                    # Clear Q1 answer
            "",                    # Clear Q2 answer
            "",                    # Clear Q3 answer
            gr.update(visible=False),  # Hide clarifying section
            gr.update(visible=True)    # Show main controls
        )

    print(f"❌ [NEW_CONV] Failed to create conversation: {result['error']}")
    return [], "", None, [], f"❌ {result['error']}", "", "", "", "", "", gr.update(visible=False), gr.update(visible=True)

async def handle_clear_memory(username: str):
    """Clear all user memory and create a fresh conversation"""
    if not username:
        return [], "", None, [], "❌ No user logged in"

    # Clear all memory
    result = memory_manager.delete_all_user_memory(username)
    if result["success"]:
        # Create a new conversation after clearing memory
        conv_result = memory_manager.create_conversation(username)
        if conv_result["success"]:
            conversation_id = conv_result["conversation_id"]

            # Initialize new Sidekick for the fresh conversation
            try:
                sidekick = await setup_sidekick(username, conversation_id)

                # Refresh conversation list
                conv_choices, _ = await refresh_conversation_list(username, conversation_id)

                return safe_dropdown_update(conv_choices, conversation_id), conversation_id, sidekick, [], f"✅ {result['message']} - New conversation created"
            except Exception as e:
                print(f"Error initializing sidekick after memory clear: {e}")
                return [], "", None, [], f"⚠️ Memory cleared but failed to initialize agent: {e}"
        else:
            return [], "", None, [], f"⚠️ Memory cleared but failed to create new conversation: {conv_result['error']}"

    return [], "", None, [], f"❌ {result['error']}"

# Helper function for safe dropdown updates
def safe_dropdown_update(choices, target_value):
    """Safely update dropdown with value validation to prevent Gradio errors"""
    if not choices:
        return gr.update(choices=[], value=None)
    
    # Extract values from choices tuples for validation
    valid_values = [choice[1] if isinstance(choice, tuple) else choice for choice in choices]
    
    # Only set value if it exists in choices
    if target_value and target_value in valid_values:
        print(f"✅ [DROPDOWN] Setting valid value: {target_value[:8] if target_value else 'None'}...")
        return gr.update(choices=choices, value=target_value)
    else:
        # Set to first choice if no valid target
        default_value = choices[0][1] if choices and isinstance(choices[0], tuple) else None
        print(f"⚠️ [DROPDOWN] Target value not in choices, using default: {default_value[:8] if default_value else 'None'}...")
        return gr.update(choices=choices, value=default_value)

# Helper function to refresh conversation list
async def refresh_conversation_list(username: str, selected_conversation_id: str = None):
    """Refresh conversation list with updated titles"""
    try:
        print(f"🔄 [REFRESH_LIST] Starting refresh for user: {username}, selected: {selected_conversation_id[:8] if selected_conversation_id else 'None'}...")
        
        conversations = memory_manager.get_user_conversations(username)
        conv_choices = []

        print(f"🔄 [REFRESH_LIST] Found {len(conversations)} conversations for {username}")

        for i, conv in enumerate(conversations):
            # Truncate title if too long for better display
            title = conv.title
            if len(title) > 40:
                title = title[:37] + "..."

            # Enhanced display format with better readability
            display_name = f"📝 {title} • {conv.message_count} msgs • {conv.last_updated.strftime('%m/%d %H:%M')}"
            conv_choices.append((display_name, conv.id))

            print(f"  🔄 [REFRESH_LIST] {i+1}. ID: {conv.id[:8]}... | Title: '{conv.title}' | Messages: {conv.message_count}")

        # If no specific conversation selected, use the first one
        if not selected_conversation_id and conv_choices:
            selected_conversation_id = conv_choices[0][1]
            print(f"✅ [REFRESH_LIST] Auto-selected conversation: {selected_conversation_id[:8]}...")
        elif selected_conversation_id:
            print(f"✅ [REFRESH_LIST] Using specified conversation: {selected_conversation_id[:8]}...")
        else:
            print(f"⚠️ [REFRESH_LIST] No conversations available or selected")

        print(f"📋 [REFRESH_LIST] Created {len(conv_choices)} dropdown choices")
        return conv_choices, selected_conversation_id
    except Exception as e:
        print(f"❌ [REFRESH_LIST] Error refreshing conversation list: {e}")
        import traceback
        traceback.print_exc()
        return [], selected_conversation_id or ""

# Gradio interface definition with authentication
with gr.Blocks(title=APP_TITLE, theme=gr.themes.Default(primary_hue=APP_THEME)) as ui:
    # Ensure required directories exist
    ensure_directories()

    # Global state management
    session_token = gr.State("")
    current_username = gr.State("")
    current_conversation_id = gr.State("")
    sidekick = gr.State(None, delete_callback=free_resources)
    clarifying_questions = gr.State([])

    # Login section (visible initially)
    with gr.Column(visible=True) as login_section:
        gr.Markdown("# 🔐 Sidekick Login")
        gr.Markdown("Please login or register to access your personal Sidekick agent with persistent memory.")

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

    # Chat section (hidden initially)
    with gr.Column(visible=False) as chat_section:
        # Header with user info and logout
        with gr.Row():
            gr.Markdown("## 💬 Sidekick Personal Co-Worker")
            with gr.Column(scale=1):
                user_info = gr.Markdown("")
                logout_button = gr.Button("🚪 Logout", variant="secondary", size="sm")

        with gr.Row():
            # Conversation sidebar
            with gr.Column(scale=1, min_width=250):
                gr.Markdown("### 💬 Conversations")
                new_conversation_btn = gr.Button("➕ New Conversation", variant="primary")
                conversation_list = gr.Dropdown(
                    label="Previous Conversations",
                    choices=[],
                    value=None,
                    interactive=True,
                    allow_custom_value=True,  # Safety measure to prevent value rejection
                    info="Click to select a conversation",
                    show_label=True
                )

                gr.Markdown("### 🧠 Memory")
                clear_memory_btn = gr.Button("🗑️ Delete All Conversations", variant="stop")
                memory_status = gr.Markdown("", visible=False)

            # Main chat interface
            with gr.Column(scale=3):
                # Chat display area
                chatbot = gr.Chatbot(label="Sidekick", height=400, type="messages")

                # Input area for user messages and success criteria
                with gr.Group():
                    with gr.Row():
                        message = gr.Textbox(show_label=False, placeholder="Your request to the Sidekick")
                    with gr.Row():
                        success_criteria = gr.Textbox(show_label=False, placeholder="What are your success criteria?")

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
                        reset_button = gr.Button("🧹 Clear Chat Display", variant="secondary")
                        clarify_button = gr.Button("❓ Ask Clarifying Questions First", variant="secondary")
                        go_button = gr.Button("🚀 Go Directly!", variant="primary")

    # Event handlers for authentication
    login_button.click(
        handle_login,
        inputs=[login_username, login_password],
        outputs=[
            session_token, current_username, login_message,
            login_section, chat_section, conversation_list, current_conversation_id, sidekick
        ]
    )

    register_button.click(
        handle_register,
        inputs=[register_username, register_password, register_password_confirm],
        outputs=[
            session_token, current_username, register_message,
            login_section, chat_section, conversation_list, current_conversation_id, sidekick
        ]
    )

    # Allow Enter key in password fields
    login_password.submit(
        handle_login,
        inputs=[login_username, login_password],
        outputs=[
            session_token, current_username, login_message,
            login_section, chat_section, conversation_list, current_conversation_id, sidekick
        ]
    )

    register_password_confirm.submit(
        handle_register,
        inputs=[register_username, register_password, register_password_confirm],
        outputs=[
            session_token, current_username, register_message,
            login_section, chat_section, conversation_list, current_conversation_id, sidekick
        ]
    )

    # Logout handler
    logout_button.click(
        handle_logout,
        inputs=[session_token],
        outputs=[
            session_token, current_username, login_message,
            login_section, chat_section, conversation_list, current_conversation_id, sidekick, chatbot
        ]
    )

    # Update user info when username changes
    current_username.change(
        lambda username: f"**Logged in as:** {username}" if username else "",
        inputs=[current_username],
        outputs=[user_info]
    )

    # Conversation management
    new_conversation_btn.click(
        handle_new_conversation,
        inputs=[current_username],
        outputs=[
            conversation_list, current_conversation_id, sidekick, chatbot, memory_status,
            message, success_criteria, q1_answer, q2_answer, q3_answer,
            clarifying_section, main_controls
        ]
    )

    conversation_list.change(
        handle_conversation_change,
        inputs=[current_username, conversation_list],
        outputs=[sidekick, chatbot]
    ).then(
        lambda username, conv_id: conv_id,  # Extract just the conversation ID
        inputs=[current_username, conversation_list],
        outputs=[current_conversation_id]
    )

    # Memory management
    clear_memory_btn.click(
        handle_clear_memory,
        inputs=[current_username],
        outputs=[conversation_list, current_conversation_id, sidekick, chatbot, memory_status]
    )

    # Chat event handlers (same as before but adapted)
    clarify_button.click(
        generate_and_display_questions,
        [sidekick, message, success_criteria, chatbot],
        [clarifying_questions, clarifying_section, main_controls, q1_display, q2_display, q3_display, q1_answer, q2_answer, q3_answer],
        concurrency_limit=2
    )

    continue_button.click(
        process_with_clarifying,
        [sidekick, message, success_criteria, chatbot, q1_answer, q2_answer, q3_answer, clarifying_questions, current_username, current_conversation_id],
        [chatbot, sidekick, clarifying_section, main_controls, conversation_list],
        concurrency_limit=1
    )

    skip_clarifying_button.click(
        process_message_direct,
        [sidekick, message, success_criteria, chatbot, current_username, current_conversation_id],
        [chatbot, sidekick, conversation_list]
    ).then(
        lambda: (gr.update(visible=False), gr.update(visible=True)),
        [],
        [clarifying_section, main_controls]
    )

    go_button.click(process_message_direct, [sidekick, message, success_criteria, chatbot, current_username, current_conversation_id], [chatbot, sidekick, conversation_list])

    message.submit(process_message_direct, [sidekick, message, success_criteria, chatbot, current_username, current_conversation_id], [chatbot, sidekick, conversation_list])

    success_criteria.submit(process_message_direct, [sidekick, message, success_criteria, chatbot, current_username, current_conversation_id], [chatbot, sidekick, conversation_list])

    reset_button.click(
        clear_chat_display,
        [current_username, current_conversation_id],
        [message, success_criteria, chatbot, q1_answer, q2_answer, q3_answer, clarifying_section, main_controls, conversation_list]
    )

# Configure Gradio queue to prevent browser timeouts for long-running operations
# This switches from HTTP POST to Server-Side Events (SSE) protocol
ui.queue(
    default_concurrency_limit=5,  # Allow up to 5 concurrent operations
    max_size=20                   # Queue up to 20 requests
)

# Launch the Gradio interface in the default web browser
# Creates a local web server for the chat interface
ui.launch(inbrowser=True)
