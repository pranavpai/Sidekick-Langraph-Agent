# Gradio web interface framework for building interactive ML demos
import gradio as gr
# Import the main Sidekick agent class
from sidekick import Sidekick


# Async initialization function for Sidekick agent
# Called when Gradio interface loads to prepare the agent
async def setup():
    # Create new Sidekick instance
    sidekick = Sidekick()
    # Initialize all agent components (LLMs, tools, graph)
    await sidekick.setup()
    return sidekick

# Main message processing function for chat interactions
# Executes the agent workflow and returns updated conversation history
async def process_message(sidekick, message, success_criteria, history):
    # Run the complete agent workflow (worker-evaluator pattern)
    results = await sidekick.run_superstep(message, success_criteria, history)
    # Return updated chat history and agent state
    return results, sidekick
    
# Reset function to clear conversation and create fresh agent instance
# Useful for starting new conversations or clearing memory
async def reset():
    # Create and setup new Sidekick instance
    new_sidekick = Sidekick()
    await new_sidekick.setup()
    # Return empty values to clear UI components and new agent
    return "", "", None, new_sidekick

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
    # Control buttons for interaction
    with gr.Row():
        # Reset conversation and agent state
        reset_button = gr.Button("Reset", variant="stop")
        # Submit message and start agent workflow
        go_button = gr.Button("Go!", variant="primary")
        
    # Event handlers for UI interactions
    # Initialize agent when interface loads
    ui.load(setup, [], [sidekick])
    # Process message when user presses Enter in message field
    message.submit(process_message, [sidekick, message, success_criteria, chatbot], [chatbot, sidekick])
    # Process message when user presses Enter in success criteria field
    success_criteria.submit(process_message, [sidekick, message, success_criteria, chatbot], [chatbot, sidekick])
    # Process message when user clicks Go button
    go_button.click(process_message, [sidekick, message, success_criteria, chatbot], [chatbot, sidekick])
    # Reset all components when user clicks Reset button
    reset_button.click(reset, [], [message, success_criteria, chatbot, sidekick])

# Launch the Gradio interface in the default web browser
# Creates a local web server for the chat interface
ui.launch(inbrowser=True)