"""
Built-in tool: App launcher
"""

import subprocess

from tools.router import ToolResult, termux_api_available


# Hardcoded safe list of apps - never accept package names directly from user
SAFE_APPS = {
    "camera": "com.android.camera2",
    "gallery": "com.google.android.apps.photos",
    "browser": "com.android.browser",
    "settings": "com.android.settings",
    "calculator": "com.android.calculator2",
    "clock": "com.android.deskclock",
    "maps": "com.google.android.apps.maps",
}


async def open_app(app_name: str) -> ToolResult:
    """
    Open a whitelisted Android app.
    
    Args:
        app_name: App name from whitelist (camera, gallery, browser, etc.)
    """
    if not app_name or not app_name.strip():
        return ToolResult(
            tool_name="open_app",
            success=False,
            output="",
            error="App name cannot be empty"
        )
    
    app_name = app_name.strip().lower()
    
    if app_name not in SAFE_APPS:
        available = ", ".join(SAFE_APPS.keys())
        return ToolResult(
            tool_name="open_app",
            success=False,
            output="",
            error=f"App not in safe list. Available: {available}"
        )
    
    if not termux_api_available():
        return ToolResult(
            tool_name="open_app",
            success=False,
            output="",
            error="Termux:API not available"
        )
    
    package_name = SAFE_APPS[app_name]
    
    try:
        # Try termux-open first
        subprocess.run(
            ["termux-open", "--chooser", "--content-type", "application/*"],
            check=False,
            capture_output=True,
            timeout=5
        )
        
        # Use am start for specific package
        subprocess.run(
            ["am", "start", "-n", package_name],
            check=True,
            capture_output=True,
            timeout=5
        )
        
        return ToolResult(
            tool_name="open_app",
            success=True,
            output=f"Opened {app_name}",
            error=None
        )
    except subprocess.TimeoutExpired:
        return ToolResult(
            tool_name="open_app",
            success=False,
            output="",
            error="App launch command timed out"
        )
    except subprocess.CalledProcessError:
        return ToolResult(
            tool_name="open_app",
            success=False,
            output="",
            error=f"Failed to open {app_name}"
        )
    except Exception:
        return ToolResult(
            tool_name="open_app",
            success=False,
            output="",
            error="App launch failed"
        )
