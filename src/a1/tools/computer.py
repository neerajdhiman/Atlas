"""Computer use tools — browser automation (Playwright) and desktop (pyautogui).

These register as tools in the global ToolRegistry and can be assigned
to agents via their tool manifest. Gated behind settings.computer_use_enabled.

Browser tools:
  browser_navigate, browser_click, browser_type, browser_screenshot,
  browser_extract_text, browser_run_js

Desktop tools:
  desktop_screenshot, desktop_click, desktop_type, desktop_hotkey
"""

import asyncio
import base64

from a1.common.logging import get_logger
from a1.tools import ToolDefinition, register_tool
from config.settings import settings

log = get_logger("tools.computer")

# Lazy-initialized browser context
_browser = None
_page = None


async def _get_page():
    """Lazily initialize Playwright browser and return the active page."""
    global _browser, _page
    if _page is not None:
        return _page
    try:
        from playwright.async_api import async_playwright

        pw = await async_playwright().start()
        _browser = await pw.chromium.launch(headless=True)
        _page = await _browser.new_page()
        log.info("Playwright browser initialized (headless Chromium)")
        return _page
    except ImportError:
        raise RuntimeError(
            "playwright not installed — run: pip install playwright && playwright install chromium"
        )
    except Exception as e:
        raise RuntimeError(f"Failed to start Playwright: {e}")


# ---------------------------------------------------------------------------
# Browser tools
# ---------------------------------------------------------------------------


async def browser_navigate(args: dict) -> str:
    url = args.get("url", "")
    if not url:
        return "Error: url is required"
    page = await _get_page()
    resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    status = resp.status if resp else "unknown"
    title = await page.title()
    return f"Navigated to {url} (status={status}, title={title})"


async def browser_click(args: dict) -> str:
    selector = args.get("selector", "")
    if not selector:
        return "Error: selector is required"
    page = await _get_page()
    await page.click(selector, timeout=10000)
    return f"Clicked: {selector}"


async def browser_type(args: dict) -> str:
    selector = args.get("selector", "")
    text = args.get("text", "")
    if not selector or not text:
        return "Error: selector and text are required"
    page = await _get_page()
    await page.fill(selector, text)
    return f"Typed into {selector}: {text[:50]}..."


async def browser_screenshot(args: dict) -> str:
    page = await _get_page()
    buf = await page.screenshot(type="png")
    b64 = base64.b64encode(buf).decode("ascii")
    log.info(f"Screenshot captured: {len(buf)} bytes")
    return f"data:image/png;base64,{b64[:100]}... ({len(buf)} bytes)"


async def browser_extract_text(args: dict) -> str:
    selector = args.get("selector", "body")
    page = await _get_page()
    text = await page.inner_text(selector, timeout=10000)
    return text[:4000]


async def browser_run_js(args: dict) -> str:
    code = args.get("code", "")
    if not code:
        return "Error: code is required"
    page = await _get_page()
    result = await page.evaluate(code)
    return str(result)[:4000]


# ---------------------------------------------------------------------------
# Desktop tools
# ---------------------------------------------------------------------------


async def desktop_screenshot(args: dict) -> str:
    import pyautogui

    img = await asyncio.to_thread(pyautogui.screenshot)
    import io

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64[:100]}... ({buf.tell()} bytes)"


async def desktop_click(args: dict) -> str:
    import pyautogui

    x = args.get("x", 0)
    y = args.get("y", 0)
    await asyncio.to_thread(pyautogui.click, x, y)
    return f"Clicked at ({x}, {y})"


async def desktop_type(args: dict) -> str:
    import pyautogui

    text = args.get("text", "")
    if not text:
        return "Error: text is required"
    await asyncio.to_thread(pyautogui.typewrite, text, interval=0.02)
    return f"Typed: {text[:50]}..."


async def desktop_hotkey(args: dict) -> str:
    import pyautogui

    keys = args.get("keys", [])
    if not keys:
        return "Error: keys list is required"
    await asyncio.to_thread(pyautogui.hotkey, *keys)
    return f"Pressed: {'+'.join(keys)}"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_computer_tools():
    """Register all computer use tools in the global registry.

    Only registers if settings.computer_use_enabled is True.
    """
    if not settings.computer_use_enabled:
        log.info("Computer use tools disabled (A1_COMPUTER_USE_ENABLED=false)")
        return

    # Browser tools
    register_tool(
        ToolDefinition(
            "browser_navigate",
            "Navigate the browser to a URL",
            browser_navigate,
            {"url": "string (required)"},
        )
    )
    register_tool(
        ToolDefinition(
            "browser_click",
            "Click an element by CSS selector",
            browser_click,
            {"selector": "string (required)"},
        )
    )
    register_tool(
        ToolDefinition(
            "browser_type",
            "Type text into an input by CSS selector",
            browser_type,
            {"selector": "string (required)", "text": "string (required)"},
        )
    )
    register_tool(
        ToolDefinition(
            "browser_screenshot",
            "Take a screenshot of the browser page",
            browser_screenshot,
            {},
        )
    )
    register_tool(
        ToolDefinition(
            "browser_extract_text",
            "Extract text content from a page element",
            browser_extract_text,
            {"selector": "string (default: body)"},
        )
    )
    register_tool(
        ToolDefinition(
            "browser_run_js",
            "Execute JavaScript in the browser page",
            browser_run_js,
            {"code": "string (required)"},
        )
    )

    # Desktop tools
    register_tool(
        ToolDefinition(
            "desktop_screenshot",
            "Take a desktop screenshot",
            desktop_screenshot,
            {},
        )
    )
    register_tool(
        ToolDefinition(
            "desktop_click",
            "Click at screen coordinates",
            desktop_click,
            {"x": "int (required)", "y": "int (required)"},
        )
    )
    register_tool(
        ToolDefinition(
            "desktop_type",
            "Type text using the keyboard",
            desktop_type,
            {"text": "string (required)"},
        )
    )
    register_tool(
        ToolDefinition(
            "desktop_hotkey",
            "Press a keyboard shortcut",
            desktop_hotkey,
            {"keys": "list of strings (e.g. ['ctrl', 'c'])"},
        )
    )

    log.info("Registered 10 computer use tools (6 browser + 4 desktop)")
