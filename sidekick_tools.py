# Playwright automation for web browsing capabilities
from playwright.async_api import async_playwright
# LangChain integration for Playwright browser tools
from langchain_community.agent_toolkits import PlayWrightBrowserToolkit
# Environment variable management
from dotenv import load_dotenv
import os
# HTTP requests for push notifications
import requests
# LangChain tool wrapper for custom functions
from langchain.agents import Tool
# File system operations toolkit for sandbox directory
from langchain_community.agent_toolkits import FileManagementToolkit
# Wikipedia search and retrieval tool
from langchain_community.tools.wikipedia.tool import WikipediaQueryRun
# Python code execution environment
from langchain_experimental.tools import PythonREPLTool
# Google search API wrapper via Serper
from langchain_community.utilities import GoogleSerperAPIWrapper
# Wikipedia API utilities for content retrieval
from langchain_community.utilities.wikipedia import WikipediaAPIWrapper

# Load environment variables for API keys and tokens
load_dotenv(override=True)
# Pushover notification service configuration
pushover_token = os.getenv("PUSHOVER_TOKEN")
pushover_user = os.getenv("PUSHOVER_USER")
pushover_url = "https://api.pushover.net/1/messages.json"
# Initialize Google search wrapper with API key from environment
serper = GoogleSerperAPIWrapper()

# Async function to initialize Playwright browser automation tools
# Returns tools, browser instance, and playwright context for lifecycle management
async def playwright_tools():
    # Start Playwright async context manager
    playwright = await async_playwright().start()
    # Launch Chromium browser in non-headless mode for debugging visibility
    browser = await playwright.chromium.launch(headless=False)
    # Create LangChain toolkit from browser instance
    toolkit = PlayWrightBrowserToolkit.from_browser(async_browser=browser)
    # Return tools list and browser objects for cleanup management
    return toolkit.get_tools(), browser, playwright


# Push notification function using Pushover service
# Enables the agent to send alerts and updates to the user's device
def push(text: str):
    """Send a push notification to the user"""
    # Send POST request to Pushover API with authentication and message
    requests.post(pushover_url, data = {"token": pushover_token, "user": pushover_user, "message": text})
    return "success"


# File management tools configuration
# Restricts file operations to sandbox directory for security
def get_file_tools():
    # Create file toolkit with sandbox root to contain file access
    toolkit = FileManagementToolkit(root_dir="sandbox")
    # Return list of file operation tools (read, write, list, etc.)
    return toolkit.get_tools()


# Async function to initialize and configure additional agent tools
# Combines various capabilities: notifications, files, search, knowledge, and code execution
async def other_tools():
    # Wrap push notification function as LangChain tool
    push_tool = Tool(name="send_push_notification", func=push, description="Use this tool when you want to send a push notification")
    # Get file management tools restricted to sandbox directory
    file_tools = get_file_tools()

    # Web search tool using Google Serper API for current information
    tool_search =Tool(
        name="search",
        func=serper.run,
        description="Use this tool when you want to get the results of an online web search"
    )

    # Wikipedia knowledge base access for encyclopedic information
    wikipedia = WikipediaAPIWrapper()
    wiki_tool = WikipediaQueryRun(api_wrapper=wikipedia)

    # Python REPL for code execution and data analysis
    python_repl = PythonREPLTool()
    
    # Combine all tools into a single list for the agent
    return file_tools + [push_tool, tool_search, python_repl,  wiki_tool]