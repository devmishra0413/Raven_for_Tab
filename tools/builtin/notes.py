"""
Built-in tools: Notes management
"""

from datetime import datetime, timezone
from pathlib import Path

from tools.sandbox import safe_path, SandboxViolation
from tools.router import ToolResult


async def add_note(title: str, content: str) -> ToolResult:
    """
    Create or update a note file.
    
    Args:
        title: Note title (becomes filename)
        content: Note content
    """
    # Validate inputs
    if not title or not title.strip():
        return ToolResult(
            tool_name="add_note",
            success=False,
            output="",
            error="Note title cannot be empty"
        )
    
    if not content or not content.strip():
        return ToolResult(
            tool_name="add_note",
            success=False,
            output="",
            error="Note content cannot be empty"
        )
    
    title = title.strip()[:100]
    content = content.strip()[:5000]
    
    # Sanitize title for filename
    safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
    if not safe_title:
        safe_title = "untitled"
    
    try:
        note_path = safe_path(f"notes/{safe_title}.txt")
        note_path.parent.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now(timezone.utc).isoformat()
        
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n")
            f.write(f"Created: {timestamp}\n\n")
            f.write(content)
        
        return ToolResult(
            tool_name="add_note",
            success=True,
            output=f"Note saved: {title}",
            error=None
        )
    except SandboxViolation as e:
        return ToolResult(
            tool_name="add_note",
            success=False,
            output="",
            error="Invalid note path"
        )
    except Exception:
        return ToolResult(
            tool_name="add_note",
            success=False,
            output="",
            error="Failed to save note"
        )


async def read_note(title: str) -> ToolResult:
    """
    Read content of a note by title.
    
    Args:
        title: Note title to read
    """
    if not title or not title.strip():
        return ToolResult(
            tool_name="read_note",
            success=False,
            output="",
            error="Note title cannot be empty"
        )
    
    title = title.strip()[:100]
    safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
    if not safe_title:
        safe_title = "untitled"
    
    try:
        note_path = safe_path(f"notes/{safe_title}.txt")
        
        if not note_path.exists():
            return ToolResult(
                tool_name="read_note",
                success=False,
                output="",
                error=f"Note not found: {title}"
            )
        
        with open(note_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        return ToolResult(
            tool_name="read_note",
            success=True,
            output=content,
            error=None
        )
    except SandboxViolation:
        return ToolResult(
            tool_name="read_note",
            success=False,
            output="",
            error="Invalid note path"
        )
    except Exception:
        return ToolResult(
            tool_name="read_note",
            success=False,
            output="",
            error="Failed to read note"
        )
