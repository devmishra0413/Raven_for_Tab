"""
Built-in tool: Reminders
"""

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from tools.sandbox import safe_path, WORKSPACE
from tools.router import ToolResult, termux_api_available


async def set_reminder(text: str, minutes: int) -> ToolResult:
    """
    Set a reminder notification.
    
    Args:
        text: Reminder message
        minutes: Delay in minutes (1-1440)
    
    Uses termux-notification if available, otherwise writes to file.
    """
    # Validate inputs
    if not text or not text.strip():
        return ToolResult(
            tool_name="set_reminder",
            success=False,
            output="",
            error="Reminder text cannot be empty"
        )
    
    if not (1 <= minutes <= 1440):
        return ToolResult(
            tool_name="set_reminder",
            success=False,
            output="",
            error="Minutes must be between 1 and 1440"
        )
    
    text = text.strip()[:200]  # Limit length
    
    if termux_api_available():
        # Use Termux:API notification
        try:
            seconds = minutes * 60
            subprocess.run(
                [
                    "termux-notification",
                    "--title", "RAVEN Reminder",
                    "--content", text,
                    "--after", str(seconds)
                ],
                check=True,
                capture_output=True,
                timeout=5
            )
            return ToolResult(
                tool_name="set_reminder",
                success=True,
                output=f"Reminder set for {minutes} minute{'s' if minutes != 1 else ''}: {text}",
                error=None
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                tool_name="set_reminder",
                success=False,
                output="",
                error="Reminder command timed out"
            )
        except subprocess.CalledProcessError as e:
            return ToolResult(
                tool_name="set_reminder",
                success=False,
                output="",
                error="Failed to set reminder notification"
            )
        except Exception:
            return ToolResult(
                tool_name="set_reminder",
                success=False,
                output="",
                error="Reminder command failed"
            )
    else:
        # Fallback: write to file
        try:
            reminders_path = safe_path("reminders.txt")
            timestamp = datetime.now(timezone.utc).isoformat()
            reminder_time = datetime.now(timezone.utc).timestamp() + (minutes * 60)
            
            with open(reminders_path, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} | +{minutes}m | {text} | due:{int(reminder_time)}\n")
            
            return ToolResult(
                tool_name="set_reminder",
                success=True,
                output=f"Reminder saved to file (Termux:API not available): {text} in {minutes} minutes",
                error=None
            )
        except Exception:
            return ToolResult(
                tool_name="set_reminder",
                success=False,
                output="",
                error="Failed to save reminder to file"
            )
