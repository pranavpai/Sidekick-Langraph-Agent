# Playwright automation for web browsing capabilities
# Async support and file path handling
import asyncio
import os
from datetime import datetime

# Markdown to HTML conversion for PDF generation
import markdown

# HTTP requests for push notifications
import requests

# Environment variable management
from dotenv import load_dotenv

# LangChain tool wrapper for custom functions
from langchain.agents import Tool

# LangChain integration for Playwright browser tools
# File system operations toolkit for sandbox directory
from langchain_community.agent_toolkits import (
    FileManagementToolkit,
    PlayWrightBrowserToolkit,
)

# Wikipedia search and retrieval tool
from langchain_community.tools.wikipedia.tool import WikipediaQueryRun

# Google search API wrapper via Serper
from langchain_community.utilities import GoogleSerperAPIWrapper

# Wikipedia API utilities for content retrieval
from langchain_community.utilities.wikipedia import WikipediaAPIWrapper

# Python code execution environment
from langchain_experimental.tools import PythonREPLTool
from playwright.async_api import async_playwright

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
async def playwright_tools(shared_browser=None, shared_playwright=None):
    if shared_browser and shared_playwright:
        # Use shared browser instance
        print("🔄 Using shared browser instance for tools")
        browser = shared_browser
        playwright = shared_playwright
    else:
        # Create new browser instance (legacy behavior)
        print("🆕 Creating new browser instance for tools")
        playwright = await async_playwright().start()
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


# Markdown to PDF conversion using Playwright
# Converts markdown content to PDF and saves to sandbox directory
async def markdown_to_pdf(markdown_content: str, filename: str | None = None) -> str:
    """Convert markdown content to PDF using Playwright browser engine"""
    try:
        # Generate filename if not provided
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"markdown_document_{timestamp}.pdf"

        # Ensure filename ends with .pdf
        if not filename.endswith('.pdf'):
            filename += '.pdf'

        # Convert markdown to HTML
        html_content = markdown.markdown(markdown_content, extensions=['tables', 'fenced_code'])

        # Create full HTML document with basic styling
        full_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 40px; }}
                h1, h2, h3 {{ color: #333; }}
                code {{ background-color: #f4f4f4; padding: 2px 4px; border-radius: 3px; }}
                pre {{ background-color: #f4f4f4; padding: 10px; border-radius: 5px; overflow-x: auto; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """

        # Initialize Playwright for PDF generation
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page()

        # Set HTML content and generate PDF
        await page.set_content(full_html, wait_until="networkidle")

        # Ensure sandbox directory exists
        os.makedirs("sandbox", exist_ok=True)

        # Save PDF to sandbox directory (use absolute path for file creation)
        pdf_path = os.path.join("sandbox", filename)
        await page.pdf(path=pdf_path, format="A4", print_background=True)

        # Cleanup
        await browser.close()
        await playwright.stop()

        return f"Successfully created PDF: {filename}"

    except Exception as e:
        return f"Error creating PDF: {e!s}"


# Synchronous wrapper for markdown_to_pdf to use with LangChain Tool
def markdown_to_pdf_sync(input_string: str) -> str:
    """Synchronous wrapper for markdown_to_pdf function

    Input format: 
    - 'FILENAME:filename\nmarkdown_content' (explicit filename + content)
    - 'filename.md' or 'filename.txt' (auto-detects and reads file from sandbox)
    - 'markdown_content' (treats input as content)
    """
    try:
        # Parse input - check if filename is provided at the start
        lines = input_string.strip().split('\n', 1)

        if lines[0].startswith('FILENAME:'):
            # Extract filename and remaining content
            filename = lines[0].replace('FILENAME:', '').strip()
            markdown_content = lines[1] if len(lines) > 1 else ""
        elif ((input_string.strip().endswith('.md') or input_string.strip().endswith('.txt')) and
              '\n' not in input_string.strip() and
              os.path.exists(os.path.join('sandbox', input_string.strip()))):
            # Auto-detect filename and read content from sandbox
            filename_to_read = input_string.strip()
            try:
                with open(os.path.join('sandbox', filename_to_read), encoding='utf-8') as f:
                    markdown_content = f.read()
                # Generate PDF filename from source filename
                if filename_to_read.endswith('.md'):
                    filename = filename_to_read.replace('.md', '.pdf')
                elif filename_to_read.endswith('.txt'):
                    filename = filename_to_read.replace('.txt', '.pdf')
                else:
                    filename = filename_to_read + '.pdf'
            except Exception as read_error:
                return f"Error reading file {filename_to_read}: {read_error!s}"
        else:
            # No filename provided, use entire input as markdown content
            filename = None
            markdown_content = input_string.strip()

        # Run async function in event loop
        try:
            loop = asyncio.get_running_loop()
            # If we're in an async context, create a task
            loop.create_task(markdown_to_pdf(markdown_content, filename))
            return "PDF generation started. Check sandbox directory for output."
        except RuntimeError:
            # If no event loop is running, create one
            return asyncio.run(markdown_to_pdf(markdown_content, filename))
    except Exception as e:
        return f"Error processing markdown to PDF: {e!s}"


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

    # Markdown to PDF conversion tool
    pdf_tool = Tool(
        name="markdown_to_pdf",
        func=markdown_to_pdf_sync,
        description="Convert markdown to PDF. Input formats: 1) 'filename.md' or 'filename.txt' (reads file from sandbox), 2) 'FILENAME:name\\nmarkdown_content' (explicit), 3) 'markdown_content' (direct content). PDFs saved to sandbox with relative paths."
    )

    # Combine all tools into a single list for the agent
    return [*file_tools, push_tool, tool_search, python_repl, wiki_tool, pdf_tool]

