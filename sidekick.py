# Core type system for function annotations and graph state management
import asyncio
import uuid
from datetime import datetime
from typing import Annotated, Any

from dotenv import load_dotenv

# LangChain message types for structured conversation handling
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

# OpenAI LLM integration via LangChain
from langchain_openai import ChatOpenAI

# SQLite-based memory persistence for long-term conversation storage
# LangGraph core components for building stateful agent workflows
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages  # Reducer for message accumulation

# Pre-built LangGraph component for handling tool execution
from langgraph.prebuilt import ToolNode

# Pydantic for structured output validation and parsing
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from config import ensure_directories

# Local memory and auth management
from memory_manager import memory_manager

# Local tool definitions for browser automation and other capabilities
from sidekick_tools import other_tools, playwright_tools

# Load environment variables for API keys and configuration
load_dotenv(override=True)

# LangGraph State definition using TypedDict for shared data across graph nodes
# This state is passed between all nodes and maintains the conversation context
class State(TypedDict):
    # Message history with automatic accumulation via add_messages reducer
    messages: Annotated[list[Any], add_messages]
    # User-defined criteria for successful task completion
    success_criteria: str
    # Evaluator feedback on worker performance for iterative improvement
    feedback_on_work: str | None
    # Boolean flag indicating if the task has been completed successfully
    success_criteria_met: bool
    # Flag indicating if more user input is required to proceed
    user_input_needed: bool
    # Counter to track worker-evaluator iterations
    iteration_count: int
    # High-level execution plan created by the planner
    execution_plan: str | None
    # Counter to track planner iterations for replanning scenarios
    planner_iterations: int


# Pydantic model for structured evaluator output using LangChain's structured output feature
# Ensures consistent evaluation format and enables LLM to return structured data
class EvaluatorOutput(BaseModel):
    # Detailed feedback on the worker's performance and completion status
    feedback: str = Field(description="Feedback on the assistant's response")
    # Boolean assessment of whether the task meets user-defined success criteria
    success_criteria_met: bool = Field(description="Whether the success criteria have been met")
    # Indicator for whether the workflow should pause for user interaction
    user_input_needed: bool = Field(description="True if more input is needed from the user, or clarifications, or the assistant is stuck")


# Pydantic model for structured planner output using LangChain's structured output feature
# Ensures the planner creates consistent, actionable execution plans for the worker
class PlannerOutput(BaseModel):
    # High-level strategy and approach for completing the task
    strategy: str = Field(description="Overall strategy and approach for the task")
    # Ordered list of specific steps the worker should execute
    execution_steps: list[str] = Field(description="Ordered list of specific steps to complete the task")
    # Tools and resources the worker should prioritize using
    recommended_tools: list[str] = Field(description="Tools and resources the worker should use")
    # Key considerations, constraints, or requirements to keep in mind
    considerations: str = Field(description="Important considerations, constraints, or requirements")


# Main Sidekick agent class implementing a worker-evaluator pattern with LangGraph
# Combines task execution (worker) with quality assessment (evaluator) in a stateful workflow
class Sidekick:
    def __init__(self, username: str = None, conversation_id: str = None):
        # User context for authentication and memory isolation
        self.username = username
        self.conversation_id = conversation_id
        self.thread_id = None  # Will be set based on user context

        # Worker LLM bound with tools for task execution
        self.worker_llm_with_tools = None
        # Evaluator LLM configured for structured output assessment
        self.evaluator_llm_with_output = None
        # Planner LLM configured for structured plan generation
        self.planner_llm_with_output = None
        # Collection of available tools (browser, files, search, etc.)
        self.tools = None
        # Legacy field kept for compatibility
        self.llm_with_tools = None
        # Compiled LangGraph workflow with nodes and edges
        self.graph = None
        # Unique identifier for this agent instance (fallback for non-authenticated use)
        self.sidekick_id = str(uuid.uuid4())
        # SQLite-based memory persistence for long-term conversation storage
        self.memory = None  # Will be initialized in setup()
        # Playwright browser instance for web automation
        self.browser = None
        # Playwright context manager for browser lifecycle
        self.playwright = None
        # Flag to indicate if the browser and playwright are shared
        self.using_shared_browser = False

    # Async initialization of all agent components and dependencies
    async def setup(self, shared_browser=None, shared_playwright=None):
        # Ensure required directories exist
        ensure_directories()

        # Initialize SQLite-based memory persistence
        self.memory = await memory_manager.get_checkpointer()

        # Set up thread ID for user isolation
        if self.username and self.conversation_id:
            self.thread_id = memory_manager._format_thread_id(self.username, self.conversation_id)
        else:
            # Fallback to sidekick_id for non-authenticated use
            self.thread_id = self.sidekick_id

        # Initialize Playwright browser tools - use shared browser if provided
        if shared_browser and shared_playwright:
            print("🔄 [SETUP] Using shared browser instance")
            self.tools, self.browser, self.playwright = await playwright_tools(shared_browser, shared_playwright)
            self.using_shared_browser = True
        else:
            print("🆕 [SETUP] Creating new browser instance")
            self.tools, self.browser, self.playwright = await playwright_tools()
            self.using_shared_browser = False

        # Add additional tools: file management, search, notifications, Python REPL
        self.tools += await other_tools()

        # Create worker LLM instance with GPT-4o-mini for task execution
        worker_llm = ChatOpenAI(model="gpt-4o-mini")
        # Bind tools to worker LLM enabling function calling capabilities
        self.worker_llm_with_tools = worker_llm.bind_tools(self.tools)
        # Create separate evaluator LLM instance for quality assessment
        evaluator_llm = ChatOpenAI(model="gpt-4o-mini")
        # Configure evaluator for structured output using Pydantic model
        self.evaluator_llm_with_output = evaluator_llm.with_structured_output(EvaluatorOutput)
        # Create separate planner LLM instance for strategic planning
        planner_llm = ChatOpenAI(model="gpt-4o-mini")
        # Configure planner for structured output using Pydantic model
        self.planner_llm_with_output = planner_llm.with_structured_output(PlannerOutput)
        # Build the LangGraph workflow with nodes, edges, and routing logic
        await self.build_graph()

    # Generate clarifying questions for user input
    # Uses LLM to create 3 relevant questions that could improve task understanding
    async def generate_clarifying_questions(self, message: str, success_criteria: str) -> list[str]:
        """Generate 3 clarifying questions based on user input to improve task understanding"""

        # System prompt for clarifying questions generation
        system_prompt = """You are a helpful assistant that generates clarifying questions to better understand user requests.
        
Your task is to analyze the user's request and success criteria, then generate exactly 3 relevant clarifying questions that would help you provide a better, more tailored response.

Guidelines for good clarifying questions:
- Ask about specific preferences, constraints, or requirements
- Focus on ambiguous aspects of the request
- Ask about scope, format, or level of detail desired
- Consider technical vs non-technical audience needs
- Ask about timeline, resources, or limitations
- Avoid yes/no questions when possible
- Make questions specific and actionable

Respond with exactly 3 questions, one per line, without numbering or bullet points."""

        # User prompt with the actual request
        user_prompt = f"""User Request: {message}

Success Criteria: {success_criteria}

Please generate 3 clarifying questions that would help you provide the best possible response to this request."""

        # Create messages for the LLM
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]

        try:
            # Use worker LLM (without tools) for question generation
            llm = ChatOpenAI(model="gpt-4o-mini")
            response = await llm.ainvoke(messages)

            # Parse the response into individual questions
            questions_text = response.content.strip()
            questions = [q.strip() for q in questions_text.split('\n') if q.strip()]

            # Ensure we have exactly 3 questions
            if len(questions) < 3:
                # Pad with generic questions if needed
                while len(questions) < 3:
                    questions.append("Are there any specific preferences or requirements I should consider?")
            elif len(questions) > 3:
                # Take only the first 3 questions
                questions = questions[:3]

            return questions

        except Exception as e:
            # Fallback questions if generation fails
            print(f"Error generating clarifying questions: {e}")
            return [
                "What specific format or style would you prefer for the response?",
                "Are there any constraints or limitations I should be aware of?",
                "What level of detail would be most helpful for your needs?"
            ]

    # Planner node: Strategic planning component of the LangGraph workflow
    # Analyzes user request and creates detailed execution plan for the worker
    def planner(self, state: State) -> dict[str, Any]:
        """Generate strategic execution plan based on user request and available tools"""
        current_planner_iteration = state.get("planner_iterations", 0)
        current_iteration = state.get("iteration_count", 0)

        # Extract the user's original request from messages
        original_request = ""
        for message in state["messages"]:
            if isinstance(message, HumanMessage):
                original_request = message.content
                break

        # Create available tools list for planning context
        tool_names = [tool.name for tool in self.tools] if self.tools else []
        tools_description = ", ".join(tool_names)

        # Dynamic system prompt for strategic planning
        system_message = f"""You are a strategic planner that creates detailed execution plans for an AI agent.
        
Your task is to analyze the user's request and create a comprehensive, actionable plan that a worker agent can follow.

Available tools for the worker: {tools_description}

The current date and time is {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

This is planner iteration {current_planner_iteration + 1}, overall iteration {current_iteration}.

Create a strategic plan that:
1. Breaks down the task into logical, sequential steps
2. Recommends appropriate tools for each phase
3. Considers potential challenges and mitigation strategies
4. Ensures the plan aligns with the success criteria

Be specific and actionable in your planning. The worker will execute your plan step-by-step."""

        # Include feedback from evaluator for replanning scenarios
        user_message = f"""User Request: {original_request}

Success Criteria: {state['success_criteria']}"""

        if state.get("feedback_on_work"):
            user_message += f"""

Previous Attempt Feedback: {state['feedback_on_work']}

Please create a revised plan that addresses the feedback and improves upon the previous approach."""

        if state.get("execution_plan"):
            user_message += f"""

Previous Plan: {state['execution_plan']}

Consider what worked and what didn't work in the previous plan when creating the new one."""

        # Create messages for planner LLM
        planner_messages = [
            SystemMessage(content=system_message),
            HumanMessage(content=user_message)
        ]

        try:
            # Invoke planner LLM with structured output
            plan_result = self.planner_llm_with_output.invoke(planner_messages)

            # Format the plan into a comprehensive execution plan string
            execution_plan = f"""
STRATEGY: {plan_result.strategy}

EXECUTION STEPS:
{chr(10).join([f"{i+1}. {step}" for i, step in enumerate(plan_result.execution_steps)])}

RECOMMENDED TOOLS: {', '.join(plan_result.recommended_tools)}

CONSIDERATIONS: {plan_result.considerations}
            """.strip()

            # Create plan summary message
            plan_message = f"Planning Phase: Created execution plan with {len(plan_result.execution_steps)} steps using strategy: {plan_result.strategy[:100]}..."

            return {
                "messages": [AIMessage(content=plan_message)],
                "execution_plan": execution_plan,
                "planner_iterations": current_planner_iteration + 1
            }

        except Exception as e:
            # Fallback plan if planning fails
            fallback_plan = f"""
STRATEGY: Direct approach to complete the user's request

EXECUTION STEPS:
1. Analyze the request and success criteria carefully
2. Use available tools to research and gather information as needed
3. Execute the task step by step
4. Verify the output meets the success criteria

RECOMMENDED TOOLS: {tools_description}

CONSIDERATIONS: Ensure thoroughness and accuracy in task completion
            """.strip()

            print(f"Error in planner: {e}")
            return {
                "messages": [AIMessage(content=f"Planning Phase: Using fallback plan due to error: {str(e)[:100]}...")],
                "execution_plan": fallback_plan,
                "planner_iterations": current_planner_iteration + 1
            }

    # Worker node: Core task execution component of the LangGraph workflow
    # Receives state, processes tasks with tools, and returns updated state
    def worker(self, state: State) -> dict[str, Any]:
        current_iteration = state.get("iteration_count", 0)

        # Dynamic system prompt incorporating current context and success criteria
        system_message = f"""You are a helpful assistant that can use tools to complete tasks.
    You keep working on a task until either you have a question or clarification for the user, or the success criteria is met.
    You have many tools to help you, including tools to browse the internet, navigating and retrieving web pages.
    You have a tool to run python code, but note that you would need to include a print() statement if you wanted to receive output.
    The current date and time is {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

    This is the success criteria:
    {state['success_criteria']}
    
    IMPORTANT: This is iteration {current_iteration}. Work efficiently and be decisive. If you have enough information to reasonably complete the task, do so rather than endlessly searching for perfect information.
    
    You should reply either with a question for the user about this assignment, or with your final response.
    If you have a question for the user, you need to reply by clearly stating your question. An example might be:

    Question: please clarify whether you want a summary or a detailed answer

    If you've finished, reply with the final answer, and don't ask a question; simply reply with the answer.
    """

        # Include execution plan from planner if available
        if state.get("execution_plan"):
            system_message += f"""
    
    EXECUTION PLAN:
    You have been provided with a strategic execution plan created by a planner. Follow this plan as a guide for completing the task:
    
    {state['execution_plan']}
    
    Use this plan to structure your approach, but adapt as needed based on the actual results you encounter."""

        # Include evaluator feedback for iterative improvement if available
        if state.get("feedback_on_work"):
            system_message += f"""
    Previously you thought you completed the assignment, but your reply was rejected because the success criteria was not met.
    Here is the feedback on why this was rejected:
    {state['feedback_on_work']}
    With this feedback, please continue the assignment, ensuring that you meet the success criteria or have a question for the user.
    
    NOTE: If you're repeating the same actions after {current_iteration} iterations, try a different approach or ask for clarification."""

        # Get messages from state and validate/clean them
        messages = state["messages"]

        # CRITICAL: Validate and clean messages to prevent OpenAI API errors
        messages = self.validate_and_clean_messages(messages)

        # System message management: update existing or prepend new system message
        found_system_message = False
        # Search for existing system message to update with current context
        for message in messages:
            if isinstance(message, SystemMessage):
                message.content = system_message
                found_system_message = True

        # Prepend system message if none exists in conversation history
        if not found_system_message:
            messages = [SystemMessage(content=system_message)] + messages

        # Invoke worker LLM with tools, enabling function calling for task execution
        response = self.worker_llm_with_tools.invoke(messages)

        # Return state update containing the LLM response (may include tool calls)
        return {
            "messages": [response],
        }


    # Conditional edge function: Routes workflow based on worker output
    # LangGraph uses this to determine the next node in the execution path
    def worker_router(self, state: State) -> str:
        # Examine the most recent message from the worker
        last_message = state["messages"][-1]

        # If worker made tool calls, route to tools node for execution
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        # If no tool calls, route to evaluator for quality assessment
        return "evaluator"

    # Utility function: Formats message history for evaluator context
    # Converts LangChain message objects into readable conversation text
    def format_conversation(self, messages: list[Any]) -> str:
        conversation = "Conversation history:\n\n"
        # Iterate through message history and format by sender type
        for message in messages:
            if isinstance(message, HumanMessage):
                conversation += f"User: {message.content}\n"
            elif isinstance(message, AIMessage):
                # Handle tool usage by showing placeholder when content is empty
                text = message.content or "[Tools use]"
                conversation += f"Assistant: {text}\n"
        return conversation

    # Evaluator node: Quality assessment component using structured output
    # Analyzes worker performance against success criteria and determines next actions
    def evaluator(self, state: State) -> State:
        # Extract the worker's most recent response for evaluation
        last_response = state["messages"][-1].content
        current_iteration = state.get("iteration_count", 0) + 1

        # System prompt defining the evaluator's role and responsibilities
        system_message = f"""You are an evaluator that determines if a task has been completed successfully by an Assistant.
    Assess the Assistant's last response based on the given criteria. Respond with your feedback, and with your decision on whether the success criteria has been met,
    and whether more input is needed from the user.
    
    IMPORTANT: This is iteration {current_iteration}. If the iteration count is getting high (>15), be more lenient and consider accepting the work if it's reasonably complete, even if not perfect."""

        # Comprehensive evaluation prompt with full conversation context
        user_message = f"""You are evaluating a conversation between the User and Assistant. You decide what action to take based on the last response from the Assistant.

    The entire conversation with the assistant, with the user's original request and all replies, is:
    {self.format_conversation(state['messages'])}

    The success criteria for this assignment is:
    {state['success_criteria']}

    And the final response from the Assistant that you are evaluating is:
    {last_response}

    This is iteration {current_iteration}. If this is a high iteration count (>15), be more forgiving and accept work that is reasonably complete.

    Respond with your feedback, and decide if the success criteria is met by this response.
    Also, decide if more user input is required, either because the assistant has a question, needs clarification, or seems to be stuck and unable to answer without help.

    The Assistant has access to a tool to write files. If the Assistant says they have written a file, then you can assume they have done so.
    Overall you should give the Assistant the benefit of the doubt if they say they've done something. But you should reject if you feel that more work should go into this.

    """
        # Include previous feedback context to prevent repetitive mistakes
        if state["feedback_on_work"]:
            user_message += f"Also, note that in a prior attempt from the Assistant, you provided this feedback: {state['feedback_on_work']}\n"
            user_message += f"If you're seeing the Assistant repeating the same mistakes after {current_iteration} iterations, then consider responding that user input is required."

        # Construct message sequence for evaluator LLM
        evaluator_messages = [SystemMessage(content=system_message), HumanMessage(content=user_message)]

        # Invoke evaluator with structured output, returns EvaluatorOutput Pydantic model
        eval_result = self.evaluator_llm_with_output.invoke(evaluator_messages)

        # Force completion after too many iterations to prevent infinite loops
        if current_iteration >= 20:
            eval_result.success_criteria_met = True
            eval_result.feedback += f" [Auto-accepted after {current_iteration} iterations to prevent infinite loop]"

        # Update state with evaluation results and workflow control flags
        new_state = {
            "messages": [{"role": "assistant", "content": f"Evaluator Feedback on this answer: {eval_result.feedback}"}],
            "feedback_on_work": eval_result.feedback,
            "success_criteria_met": eval_result.success_criteria_met,
            "user_input_needed": eval_result.user_input_needed,
            "iteration_count": current_iteration
        }
        return new_state

    # Conditional edge function: Controls workflow continuation based on evaluation
    # Determines whether to end the workflow, continue with worker, or replan
    def route_based_on_evaluation(self, state: State) -> str:
        # End workflow if task is complete or requires user intervention
        if state["success_criteria_met"] or state["user_input_needed"]:
            return "END"

        current_iteration = state.get("iteration_count", 0)
        planner_iterations = state.get("planner_iterations", 0)
        feedback = state.get("feedback_on_work", "")

        print(f"🔀 [ROUTING] Iteration {current_iteration}, Planner iterations: {planner_iterations}")

        # AGGRESSIVE TIMEOUT PREVENTION: Force end after reasonable iterations
        if current_iteration >= 15:  # Reduced from 20 for faster timeout prevention
            print(f"⏰ [ROUTING] Force ending due to high iteration count: {current_iteration}")
            return "END"

        # CONSERVATIVE REPLANNING: Only replan in very specific circumstances
        should_replan = False

        # Only replan if we have clear indicators and low planner iterations
        if planner_iterations < 2:  # Reduced from 3 to limit replanning
            # Replan only at specific iteration thresholds (less frequent)
            if current_iteration == 7:  # Single replan opportunity instead of every 5
                should_replan = True
                print(f"🔄 [ROUTING] Replanning at iteration threshold: {current_iteration}")

            # Replan if feedback explicitly suggests fundamental issues
            replan_keywords = ["different approach", "strategy", "plan", "reconsider", "rethink"]
            if feedback and any(keyword in feedback.lower() for keyword in replan_keywords):
                should_replan = True
                print("🔄 [ROUTING] Replanning due to feedback keywords")

        # Route based on decision
        if should_replan:
            print("➡️ [ROUTING] Routing to planner")
            return "planner"
        print("➡️ [ROUTING] Routing to worker")
        return "worker"


    # LangGraph workflow construction: Defines the agent's execution flow
    # Creates a stateful graph with planner-worker-evaluator pattern and tool integration
    async def build_graph(self):
        # Initialize StateGraph with our custom State schema
        graph_builder = StateGraph(State)

        # Add nodes: Core components of the agent workflow
        # Planner node: Strategic planning and task breakdown
        graph_builder.add_node("planner", self.planner)
        # Worker node: Task execution with LLM and tools following the plan
        graph_builder.add_node("worker", self.worker)
        # Tools node: Pre-built LangGraph component for handling tool execution
        graph_builder.add_node("tools", ToolNode(tools=self.tools))
        # Evaluator node: Quality assessment and workflow control
        graph_builder.add_node("evaluator", self.evaluator)

        # Add edges: Define the workflow execution paths
        # Entry point: Start workflow with planner node for strategic planning
        graph_builder.add_edge(START, "planner")
        # Direct edge: Planner always proceeds to worker with the execution plan
        graph_builder.add_edge("planner", "worker")
        # Conditional edge from worker: Route to tools or evaluator based on output
        graph_builder.add_conditional_edges("worker", self.worker_router, {"tools": "tools", "evaluator": "evaluator"})
        # Direct edge: Tools always return to worker for processing results
        graph_builder.add_edge("tools", "worker")
        # Conditional edge from evaluator: Continue, replan, or end based on assessment
        graph_builder.add_conditional_edges("evaluator", self.route_based_on_evaluation, {"worker": "worker", "planner": "planner", "END": END})

        # Compile graph with memory persistence for conversation continuity
        self.graph = graph_builder.compile(checkpointer=self.memory)

    # Main execution method: Runs the complete agent workflow for a single interaction
    # Manages state initialization, graph execution, and result formatting
    async def run_superstep(self, message, success_criteria, history, original_message=None):
        import time
        start_time = time.time()
        print(f"\n🎯 [SUPERSTEP] Starting run_superstep at {time.strftime('%H:%M:%S')}")
        print(f"👤 [SUPERSTEP] User: {self.username}, Conversation: {self.conversation_id}, Thread: {self.thread_id}")

        try:
            # Determine which message to use for storage vs LLM processing
            # Use original_message for storage/auto-titling, enhanced message for LLM
            message_for_storage = original_message if original_message is not None else message
            message_for_llm = message
            
            print(f"📝 [SUPERSTEP] Message for storage: {message_for_storage[:100] if message_for_storage else 'None'}...")
            print(f"🤖 [SUPERSTEP] Message for LLM: {message_for_llm[:100] if message_for_llm else 'None'}...")
            
            # Configuration for LangGraph execution with user-specific thread-based memory
            config = {"configurable": {"thread_id": self.thread_id}}

            # Initialize state for this execution cycle
            # Use enhanced message for LLM processing but store original for conversation history
            state = {
                "messages": message_for_llm,
                "success_criteria": success_criteria or "The answer should be clear and accurate",
                "feedback_on_work": None,
                "success_criteria_met": False,
                "user_input_needed": False,
                "iteration_count": 0,
                "execution_plan": None,
                "planner_iterations": 0
            }

            # Update conversation metadata if user context is available
            if self.username and self.conversation_id:
                # Auto-title conversation based on first message if it has default title
                # Use original message for titling, not enhanced message with clarifying context
                try:
                    memory_manager.auto_title_conversation(
                        self.conversation_id,
                        self.username,
                        message_for_storage
                    )
                except Exception as e:
                    print(f"Warning: Could not auto-title conversation: {e}")

                # Update message count
                memory_manager.update_conversation(
                    self.conversation_id,
                    self.username,
                    increment_messages=True
                )

            print(f"📊 [SUPERSTEP] State initialized with message length: {len(message) if message else 0}")
            print(f"📊 [SUPERSTEP] Success criteria: {success_criteria[:100] if success_criteria else 'Default'}...")

            # Allow deep recursion for complex multi-step tasks - increased to handle planner-worker cycles
            config["recursion_limit"] = 200  # Increased for complex clarifying workflows
            print(f"⚙️ [SUPERSTEP] Config set with recursion_limit: {config['recursion_limit']}")

            # Execute the compiled graph workflow asynchronously
            graph_start_time = time.time()
            print(f"🚀 [SUPERSTEP] Starting graph execution at {time.strftime('%H:%M:%S')}")
            result = await self.graph.ainvoke(state, config=config)

            graph_end_time = time.time()
            print(f"✅ [SUPERSTEP] Graph execution completed at {time.strftime('%H:%M:%S')} (took {graph_end_time - graph_start_time:.2f}s)")

            # Log result details
            print(f"📈 [SUPERSTEP] Result keys: {list(result.keys()) if result else 'None'}")
            print(f"📈 [SUPERSTEP] Final iteration count: {result.get('iteration_count', 'Unknown')}")
            print(f"📈 [SUPERSTEP] Planner iterations: {result.get('planner_iterations', 'Unknown')}")
            print(f"📈 [SUPERSTEP] Success criteria met: {result.get('success_criteria_met', 'Unknown')}")
            print(f"📈 [SUPERSTEP] Messages count: {len(result.get('messages', [])) if result else 0}")

            # Format results for Gradio chat interface with deduplication
            format_start_time = time.time()
            # Use original message for display, not enhanced message with clarifying context
            user_message = {"role": "user", "content": message_for_storage}
            
            # Filter out internal system messages - only show main assistant response to user
            # Find the last non-evaluator assistant message
            assistant_response = None
            for msg in reversed(result["messages"]):
                if (hasattr(msg, 'content') and msg.content and 
                    not msg.content.startswith("Evaluator Feedback") and
                    not msg.content.startswith("Planning Phase")):
                    assistant_response = msg.content
                    break
            
            # Fallback to last message if no suitable response found
            if not assistant_response and result["messages"]:
                assistant_response = result["messages"][-1].content
            
            assistant_message = {"role": "assistant", "content": assistant_response or "I apologize, but I couldn't generate a proper response."}
            
            # Smart deduplication: only add messages if they're not already in history
            formatted_result = self._merge_conversation_with_deduplication(
                history, user_message, assistant_message
            )
            format_end_time = time.time()

            print(f"🎨 [SUPERSTEP] Result formatting took {format_end_time - format_start_time:.2f}s")

            total_time = time.time() - start_time
            print(f"🏁 [SUPERSTEP] Total run_superstep time: {total_time:.2f}s")

            return formatted_result

        except Exception as e:
            error_time = time.time()
            print(f"❌ [SUPERSTEP] Error at {time.strftime('%H:%M:%S')} (after {error_time - start_time:.2f}s): {e}")
            import traceback
            traceback.print_exc()
            raise e

    # Set user context for authenticated sessions
    def set_user_context(self, username: str, conversation_id: str):
        """Set user context for authentication and memory isolation"""
        self.username = username
        self.conversation_id = conversation_id
        self.thread_id = memory_manager._format_thread_id(username, conversation_id)
        print(f"👤 [CONTEXT] Set user context - Username: {username}, Conversation: {conversation_id}, Thread: {self.thread_id}")

    # Get conversation history for UI display
    async def get_conversation_history(self, limit: int = 50) -> list[dict[str, str]]:
        """Get formatted conversation history for UI display"""
        if not self.memory or not self.thread_id:
            return []

        try:
            # Get checkpoints from memory
            config = {"configurable": {"thread_id": self.thread_id}}
            history = []

            # Get the latest checkpoint
            checkpoints = []
            async for checkpoint in self.memory.alist(config, limit=limit):
                checkpoints.append(checkpoint)

            # Extract messages from the LATEST checkpoint only (to avoid duplication)
            # Each checkpoint contains the complete conversation state, so we only need the most recent one
            raw_messages = []
            if checkpoints:
                latest_checkpoint = checkpoints[0]  # checkpoints are already in reverse order
                if "messages" in latest_checkpoint.checkpoint["channel_values"]:
                    raw_messages = latest_checkpoint.checkpoint["channel_values"]["messages"]
                    print(f"📚 [HISTORY] Extracted {len(raw_messages)} messages from latest checkpoint")

            # CRITICAL: Validate and clean messages before processing
            cleaned_messages = self.validate_and_clean_messages(raw_messages)

            # Advanced message filtering for UI display
            seen_contents = set()  # Track seen content for deduplication
            conversation_pairs = []  # Track user-assistant pairs
            
            print(f"📚 [HISTORY] Processing {len(cleaned_messages)} cleaned messages for UI display")
            
            for i, msg in enumerate(cleaned_messages):
                if not hasattr(msg, 'content') or not msg.content:
                    continue
                    
                if isinstance(msg, HumanMessage):
                    # Process user messages
                    content = self._clean_user_message(msg.content)
                    if content and content not in seen_contents:
                        seen_contents.add(content)
                        conversation_pairs.append({"role": "user", "content": content})
                        print(f"  📝 [HISTORY] Added user message: {content[:50]}...")
                        
                elif isinstance(msg, AIMessage):
                    # Process assistant messages - filter out internal system messages
                    if self._is_user_facing_message(msg.content):
                        content = msg.content.strip()
                        if content and content not in seen_contents:
                            seen_contents.add(content)
                            conversation_pairs.append({"role": "assistant", "content": content})
                            print(f"  🤖 [HISTORY] Added assistant message: {content[:50]}...")
                    else:
                        print(f"  🚫 [HISTORY] Filtered internal message: {msg.content[:50]}...")
            
            print(f"📚 [HISTORY] Final conversation pairs: {len(conversation_pairs)}")
            return conversation_pairs[-limit:] if conversation_pairs else []

        except Exception as e:
            print(f"Error getting conversation history: {e}")
            return []
    
    def _clean_user_message(self, content: str) -> str:
        """Clean user message content by removing clarifying questions context"""
        if not content:
            return ""
            
        # Remove clarifying questions section if present
        if "\n\nClarifying Questions and Answers:" in content:
            content = content.split("\n\nClarifying Questions and Answers:")[0]
        
        return content.strip()
    
    def _is_user_facing_message(self, content: str) -> bool:
        """Determine if an AI message should be shown to the user"""
        if not content:
            return False
            
        # Filter out internal system messages
        internal_prefixes = [
            "Evaluator Feedback",
            "Planning Phase",
            "Planner:",
            "Worker:",
            "Evaluator:",
            "[PLANNING]",
            "[EVALUATION]",
            "[INTERNAL]"
        ]
        
        for prefix in internal_prefixes:
            if content.startswith(prefix):
                return False
                
        # Filter out tool execution messages
        if content.startswith("[Tools use]") or content.startswith("Tool execution"):
            return False
            
        return True
    
    def _merge_conversation_with_deduplication(self, history: list, user_message: dict, assistant_message: dict) -> list:
        """Merge new messages with existing history, avoiding duplicates"""
        print(f"🔀 [MERGE] Starting deduplication with history length: {len(history)}")
        print(f"🔀 [MERGE] New user message: {user_message['content'][:50]}...")
        print(f"🔀 [MERGE] New assistant message: {assistant_message['content'][:50]}...")
        
        # Create a copy of history to work with
        result = list(history) if history else []
        
        # Check if the user message already exists (by content)
        user_content = user_message['content'].strip()
        user_exists = any(
            msg.get('role') == 'user' and msg.get('content', '').strip() == user_content 
            for msg in result
        )
        
        # Check if the assistant message already exists (by content)
        assistant_content = assistant_message['content'].strip()
        assistant_exists = any(
            msg.get('role') == 'assistant' and msg.get('content', '').strip() == assistant_content 
            for msg in result
        )
        
        print(f"🔀 [MERGE] User message exists: {user_exists}, Assistant message exists: {assistant_exists}")
        
        # Only add messages that don't already exist
        if not user_exists:
            result.append(user_message)
            print(f"✅ [MERGE] Added new user message")
        else:
            print(f"🚫 [MERGE] Skipped duplicate user message")
            
        if not assistant_exists:
            result.append(assistant_message)
            print(f"✅ [MERGE] Added new assistant message")
        else:
            print(f"🚫 [MERGE] Skipped duplicate assistant message")
        
        print(f"🔀 [MERGE] Final result length: {len(result)}")
        return result

    # Validate and clean conversation history to prevent OpenAI API errors
    # Ensures tool calls are properly matched with tool responses
    def validate_and_clean_messages(self, messages: list[Any]) -> list[Any]:
        """Validate and clean message history to ensure tool calls have corresponding responses"""
        if not messages:
            return messages

        cleaned_messages = []
        pending_tool_calls = []

        for message in messages:
            if isinstance(message, AIMessage):
                # Check if this message has tool calls
                if hasattr(message, 'tool_calls') and message.tool_calls:
                    # Track pending tool calls
                    pending_tool_calls.extend([tool_call.get('id') for tool_call in message.tool_calls if tool_call.get('id')])
                    cleaned_messages.append(message)
                else:
                    # Regular AI message without tool calls
                    cleaned_messages.append(message)
            elif hasattr(message, 'tool_call_id'):
                # This is a tool response message
                if message.tool_call_id in pending_tool_calls:
                    # Valid tool response - remove from pending
                    pending_tool_calls.remove(message.tool_call_id)
                    cleaned_messages.append(message)
                # If not in pending, this is an orphaned tool response - skip it
            else:
                # Regular message (HumanMessage, SystemMessage, etc.)
                cleaned_messages.append(message)

        # If we have pending tool calls at the end, remove the messages that created them
        if pending_tool_calls:
            print(f"⚠️ [VALIDATION] Found {len(pending_tool_calls)} unmatched tool calls, cleaning up...")
            final_messages = []
            for message in cleaned_messages:
                if isinstance(message, AIMessage) and hasattr(message, 'tool_calls') and message.tool_calls:
                    # Check if any of this message's tool calls are still pending
                    message_tool_call_ids = [tool_call.get('id') for tool_call in message.tool_calls if tool_call.get('id')]
                    if any(tool_id in pending_tool_calls for tool_id in message_tool_call_ids):
                        # This message has unmatched tool calls, skip it
                        print(f"⚠️ [VALIDATION] Removing message with unmatched tool calls: {message_tool_call_ids}")
                        continue
                final_messages.append(message)
            cleaned_messages = final_messages

        print(f"✅ [VALIDATION] Cleaned {len(messages)} messages -> {len(cleaned_messages)} messages")
        return cleaned_messages

    # Resource cleanup: Properly closes browser and Playwright instances
    # Handles both event loop and non-event loop contexts gracefully
    def cleanup(self):
        # Only close browser if we're not using a shared instance
        if self.browser and not self.using_shared_browser:
            print("🧹 [CLEANUP] Closing individual browser instance")
            try:
                # Try to use existing event loop for cleanup
                loop = asyncio.get_running_loop()
                loop.create_task(self.browser.close())
                if self.playwright:
                    loop.create_task(self.playwright.stop())
            except RuntimeError:
                # Fallback: Create new event loop if none exists
                asyncio.run(self.browser.close())
                if self.playwright:
                    asyncio.run(self.playwright.stop())
        elif self.using_shared_browser:
            print("🔄 [CLEANUP] Using shared browser - not closing")

        # Close memory checkpointer if needed
        if self.memory and hasattr(self.memory, 'close'):
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.memory.close())
            except (RuntimeError, AttributeError):
                pass
