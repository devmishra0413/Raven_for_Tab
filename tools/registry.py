"""
Tool registry: Fixed set of tools with schemas and metadata.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ToolSchema:
    """Metadata for a registered tool."""
    name: str
    description: str
    risk: str  # "low", "medium", "high"
    needs_termux_api: bool
    parameters: dict  # JSON Schema style


# Fixed tool list - no dynamic registration
TOOLS = {
    # LOW RISK — run immediately
    "set_reminder": ToolSchema(
        name="set_reminder",
        description="Set a reminder notification with text and delay in minutes",
        risk="low",
        needs_termux_api=True,
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Reminder message"},
                "minutes": {"type": "integer", "minimum": 1, "maximum": 1440, "description": "Delay in minutes (1-1440)"}
            },
            "required": ["text", "minutes"]
        }
    ),
    "add_note": ToolSchema(
        name="add_note",
        description="Create or update a note file with title and content",
        risk="low",
        needs_termux_api=False,
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "maxLength": 100, "description": "Note title (filename)"},
                "content": {"type": "string", "maxLength": 5000, "description": "Note content"}
            },
            "required": ["title", "content"]
        }
    ),
    "read_note": ToolSchema(
        name="read_note",
        description="Read content of a note by title",
        risk="low",
        needs_termux_api=False,
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Note title to read"}
            },
            "required": ["title"]
        }
    ),
    "search_files": ToolSchema(
        name="search_files",
        description="Search for files in workspace by name pattern",
        risk="low",
        needs_termux_api=False,
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query for filename"},
                "max_results": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50}
            },
            "required": ["query"]
        }
    ),
    "play_song": ToolSchema(
        name="play_song",
        description="Play a song from workspace or open YouTube search",
        risk="low",
        needs_termux_api=True,
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Song name or search query"}
            },
            "required": ["query"]
        }
    ),
    "pause_media": ToolSchema(
        name="pause_media",
        description="Pause currently playing media",
        risk="low",
        needs_termux_api=True,
        parameters={"type": "object", "properties": {}}
    ),
    "next_track": ToolSchema(
        name="next_track",
        description="Skip to next track in media player",
        risk="low",
        needs_termux_api=True,
        parameters={"type": "object", "properties": {}}
    ),
    "set_volume": ToolSchema(
        name="set_volume",
        description="Set volume level for music stream",
        risk="low",
        needs_termux_api=True,
        parameters={
            "type": "object",
            "properties": {
                "level": {"type": "integer", "minimum": 0, "maximum": 100, "description": "Volume level (0-100)"},
                "stream": {"type": "string", "default": "music", "enum": ["music", "notification", "ring"]}
            },
            "required": ["level"]
        }
    ),
    "open_app": ToolSchema(
        name="open_app",
        description="Open a whitelisted Android app",
        risk="low",
        needs_termux_api=True,
        parameters={
            "type": "object",
            "properties": {
                "app_name": {"type": "string", "enum": ["camera", "gallery", "browser", "settings", "calculator", "clock", "maps"]}
            },
            "required": ["app_name"]
        }
    ),
}


def get_tool(name: str) -> Optional[ToolSchema]:
    """Get tool schema by name."""
    return TOOLS.get(name)


def all_tools() -> list[ToolSchema]:
    """Get all registered tool schemas."""
    return list(TOOLS.values())


def tool_schemas_for_prompt() -> str:
    """
    Generate compact tool list for system prompt.
    
    Returns formatted string with tool names, descriptions, and parameters.
    """
    lines = []
    for tool in all_tools():
        params = []
        props = tool.parameters.get("properties", {})
        required = tool.parameters.get("required", [])
        
        for param_name, param_spec in props.items():
            req_marker = "*" if param_name in required else ""
            param_type = param_spec.get("type", "string")
            desc = param_spec.get("description", "")
            params.append(f"{param_name}{req_marker}: {param_type} - {desc}")
        
        param_str = ", ".join(params) if params else "no parameters"
        lines.append(f"- {tool.name}: {tool.description} ({param_str})")
    
    return "\n".join(lines)
