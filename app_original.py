# Gradio web interface framework for building interactive ML demos
import asyncio

import gradio as gr

# Import the main Sidekick agent class
from sidekick import Sidekick


# Async initialization function for Sidekick agent
# Called when Gradio interface loads to prepare the agent
async def setup():
    try:
        print("Initializing Sidekick agent...")
        # Create new Sidekick instance
        sidekick = Sidekick()
        # Initialize all agent components (LLMs, tools, graph)
        await sidekick.setup()
        print("Sidekick agent initialized successfully!")
        return sidekick
    except Exception as e:
        print(f"Error initializing Sidekick agent: {e}")
        import traceback
        traceback.print_exc()
        return None

# Generate clarifying questions for user input
# First phase of two-phase processing workflow
async def generate_clarifying_questions(sidekick, message, success_criteria, chatbot):
    try:
        # Validate inputs
        if not message or not message.strip():
            return ["Please provide a message first", "", ""], gr.update(visible=True), gr.update(visible=False)

        if not sidekick:
            return ["Agent not initialized", "", ""], gr.update(visible=True), gr.update(visible=False)

        # Generate 3 clarifying questions using the agent
        questions = await sidekick.generate_clarifying_questions(message.strip(), success_criteria or "")
        # Return questions to display in UI
        return questions, gr.update(visible=True), gr.update(visible=False)
    except Exception as e:
        print(f"Error in generate_clarifying_questions: {e}")
        return [f"Error generating questions: {e!s}", "", ""], gr.update(visible=True), gr.update(visible=False)

# Main message processing function with clarifying answers
# Second phase of processing workflow that includes clarifying context
async def process_with_clarifying(sidekick, message, success_criteria, chatbot, q1_answer, q2_answer, q3_answer, clarifying_questions):
    import time
    start_time = time.time()
    print(f"\n🔍 [CLARIFYING] Starting process_with_clarifying at {time.strftime('%H:%M:%S')}")

    try:
        # Log input parameters
        print(f"📝 [CLARIFYING] Original message length: {len(message) if message else 0}")
        print(f"📝 [CLARIFYING] Success criteria: {success_criteria[:100] if success_criteria else 'None'}...")
        print(f"📝 [CLARIFYING] Questions available: {len(clarifying_questions) if clarifying_questions else 0}")
        print(f"📝 [CLARIFYING] Chatbot history type: {type(chatbot)}, length: {len(chatbot) if hasattr(chatbot, '__len__') else 'N/A'}")

        # Combine original message with clarifying answers
        clarifying_context = ""
        if clarifying_questions and len(clarifying_questions) >= 3:
            answers = [q1_answer, q2_answer, q3_answer]
            answered_questions = []
            for i, (question, answer) in enumerate(zip(clarifying_questions, answers, strict=False)):
                if answer and answer.strip():
                    answered_questions.append(f"Q{i+1}: {question}\nA{i+1}: {answer.strip()}")
                    print(f"✅ [CLARIFYING] Answer {i+1}: {answer.strip()[:50]}...")

            if answered_questions:
                clarifying_context = "\n\nClarifying Questions and Answers:\n" + "\n\n".join(answered_questions)
                print(f"📋 [CLARIFYING] Clarifying context length: {len(clarifying_context)}")

        # Enhance the original message with clarifying context
        enhanced_message = message + clarifying_context
        print(f"📏 [CLARIFYING] Enhanced message total length: {len(enhanced_message)}")
        print(f"📄 [CLARIFYING] Enhanced message preview: {enhanced_message[:200]}...")

        # Log before calling run_superstep
        pre_superstep_time = time.time()
        print(f"🚀 [CLARIFYING] Calling run_superstep at {time.strftime('%H:%M:%S')} (prep took {pre_superstep_time - start_time:.2f}s)")

        # Run the complete agent workflow with enhanced context
        # Add Gradio-specific timeout protection (120 seconds)
        print("⏱️ [CLARIFYING] Starting run_superstep with 120s timeout protection...")
        try:
            results = await asyncio.wait_for(
                sidekick.run_superstep(enhanced_message, success_criteria, chatbot),
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

        # FIXED: Proper return format matching Gradio event handler expectations
        # [chatbot, sidekick, clarifying_section, main_controls]
        return results, sidekick, gr.update(visible=False), gr.update(visible=True)

    except Exception as e:
        error_time = time.time()
        print(f"❌ [CLARIFYING] Error at {time.strftime('%H:%M:%S')} (after {error_time - start_time:.2f}s): {e}")
        import traceback
        traceback.print_exc()

        # CIRCUIT BREAKER: Fall back to direct processing if clarifying workflow fails
        print("🔄 [CLARIFYING] Attempting fallback to direct processing...")
        try:
            fallback_start = time.time()
            # Try direct processing with original message as fallback
            fallback_results = await sidekick.run_superstep(message, success_criteria, chatbot)
            fallback_end = time.time()
            print(f"✅ [CLARIFYING] Fallback successful in {fallback_end - fallback_start:.2f}s")

            # Add notification about fallback to the beginning of new messages
            if len(fallback_results) > len(chatbot):
                new_messages = fallback_results[len(chatbot):]
                notification = {"role": "assistant", "content": "⚠️ Clarifying questions workflow encountered issues, processed your request directly instead."}
                enhanced_results = chatbot + [notification] + new_messages
            else:
                enhanced_results = fallback_results

            return enhanced_results, sidekick, gr.update(visible=False), gr.update(visible=True)

        except Exception as fallback_error:
            print(f"❌ [CLARIFYING] Fallback also failed: {fallback_error}")
            # Final error state - ensure proper format
            error_message = {"role": "assistant", "content": "❌ Error: Both clarifying and direct processing failed. Please try again or reset the conversation."}
            error_history = chatbot + [error_message] if isinstance(chatbot, list) else [error_message]
            return error_history, sidekick, gr.update(visible=False), gr.update(visible=True)

# Original process_message function for direct processing (skip clarifying questions)
async def process_message_direct(sidekick, message, success_criteria, chatbot):
    import time
    start_time = time.time()
    print(f"\n🔄 [DIRECT] Starting process_message_direct at {time.strftime('%H:%M:%S')}")

    try:
        # Log input parameters
        print(f"📝 [DIRECT] Message length: {len(message) if message else 0}")
        print(f"📝 [DIRECT] Success criteria: {success_criteria[:100] if success_criteria else 'None'}...")
        print(f"📄 [DIRECT] Message preview: {message[:200] if message else 'None'}...")

        # Run the complete agent workflow (worker-evaluator pattern)
        print(f"🚀 [DIRECT] Calling run_superstep at {time.strftime('%H:%M:%S')}")
        results = await sidekick.run_superstep(message, success_criteria, chatbot)

        # Log completion
        end_time = time.time()
        print(f"✅ [DIRECT] Completed at {time.strftime('%H:%M:%S')} (took {end_time - start_time:.2f}s)")

        # Return updated chat history and agent state
        return results, sidekick

    except Exception as e:
        error_time = time.time()
        print(f"❌ [DIRECT] Error at {time.strftime('%H:%M:%S')} (after {error_time - start_time:.2f}s): {e}")
        import traceback
        traceback.print_exc()

        # Return error state
        error_history = chatbot + [{"role": "assistant", "content": f"Error in direct processing: {e!s}"}]
        return error_history, sidekick

# Reset function to clear conversation and create fresh agent instance
# Useful for starting new conversations or clearing memory
async def reset():
    # Create and setup new Sidekick instance
    new_sidekick = Sidekick()
    await new_sidekick.setup()
    # Return empty values to clear UI components and new agent
    return "", "", None, new_sidekick, [], "", "", "", gr.update(visible=False), gr.update(visible=True)

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
        # Clean up browser and Playwright resources if agent exists
        if sidekick:
            sidekick.cleanup()  # Note: should be 'cleanup' not 'free_resources'
    except Exception as e:
        print(f"Exception during cleanup: {e}")


# Gradio interface definition using Blocks for custom layout
# Creates a chat-based UI for interacting with the Sidekick agent
with gr.Blocks(title="Sidekick", theme=gr.themes.Default(primary_hue="emerald")) as ui:
    # Main title for the application
    gr.Markdown("## Sidekick Personal Co-Worker")
    # Gradio state to hold the agent instance with automatic cleanup
    sidekick = gr.State(delete_callback=free_resources)
    # State to hold clarifying questions
    clarifying_questions = gr.State([])

    # Chat display area showing conversation history
    with gr.Row():
        chatbot = gr.Chatbot(label="Sidekick", height=300, type="messages")

    # Input area for user messages and success criteria
    with gr.Group():
        with gr.Row():
            # Main message input field
            message = gr.Textbox(show_label=False, placeholder="Your request to the Sidekick")
        with gr.Row():
            # Success criteria input for task evaluation
            success_criteria = gr.Textbox(show_label=False, placeholder="What are your success critiera?")

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
            # Reset conversation and agent state
            reset_button = gr.Button("Reset", variant="stop")
            # Generate clarifying questions first
            clarify_button = gr.Button("Ask Clarifying Questions First", variant="secondary")
            # Submit message and start agent workflow directly
            go_button = gr.Button("Go Directly!", variant="primary")

    # Event handlers for UI interactions
    # Initialize agent when interface loads
    ui.load(setup, [], [sidekick])

    # Generate and display clarifying questions
    clarify_button.click(
        generate_and_display_questions,
        [sidekick, message, success_criteria, chatbot],
        [clarifying_questions, clarifying_section, main_controls, q1_display, q2_display, q3_display, q1_answer, q2_answer, q3_answer],
        concurrency_limit=2  # Allow limited concurrent question generation
    )

    # Continue with processing using clarifying answers
    continue_button.click(
        process_with_clarifying,
        [sidekick, message, success_criteria, chatbot, q1_answer, q2_answer, q3_answer, clarifying_questions],
        [chatbot, sidekick, clarifying_section, main_controls],
        concurrency_limit=1  # Limit to 1 concurrent clarifying operation to prevent timeouts
    )

    # Skip clarifying questions and process directly
    skip_clarifying_button.click(
        process_message_direct,
        [sidekick, message, success_criteria, chatbot],
        [chatbot, sidekick]
    ).then(
        lambda: (gr.update(visible=False), gr.update(visible=True)),
        [],
        [clarifying_section, main_controls]
    )

    # Direct processing without clarifying questions
    go_button.click(process_message_direct, [sidekick, message, success_criteria, chatbot], [chatbot, sidekick])

    # Process message when user presses Enter in message field (direct processing)
    message.submit(process_message_direct, [sidekick, message, success_criteria, chatbot], [chatbot, sidekick])

    # Process message when user presses Enter in success criteria field (direct processing)
    success_criteria.submit(process_message_direct, [sidekick, message, success_criteria, chatbot], [chatbot, sidekick])

    # Reset all components when user clicks Reset button
    reset_button.click(
        reset,
        [],
        [message, success_criteria, chatbot, sidekick, clarifying_questions, q1_answer, q2_answer, q3_answer, clarifying_section, main_controls]
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
