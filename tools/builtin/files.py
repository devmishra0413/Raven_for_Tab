"""
Built-in tool: File search
"""

from pathlib import Path

from tools.sandbox import WORKSPACE
from tools.router import ToolResult


async def search_files(query: str, max_results: int = 10) -> ToolResult:
    """
    Search for files in workspace by name pattern.
    
    Args:
        query: Search query for filename (case-insensitive)
        max_results: Maximum number of results (1-50)
    
    Returns files as relative paths from workspace root.
    """
    if not query or not query.strip():
        return ToolResult(
            tool_name="search_files",
            success=False,
            output="",
            error="Search query cannot be empty"
        )
    
    query = query.strip().lower()
    max_results = max(1, min(max_results, 50))
    
    try:
        # Ensure workspace exists
        WORKSPACE.mkdir(parents=True, exist_ok=True)
        
        matches = []
        
        # Walk through workspace directory
        for path in WORKSPACE.rglob("*"):
            if path.is_file():
                # Check if query matches filename (case-insensitive)
                if query in path.name.lower():
                    # Return relative path from workspace
                    try:
                        rel_path = path.relative_to(WORKSPACE)
                        matches.append(str(rel_path))
                        
                        if len(matches) >= max_results:
                            break
                    except ValueError:
                        # Skip files that somehow escaped workspace
                        continue
        
        if not matches:
            return ToolResult(
                tool_name="search_files",
                success=True,
                output=f"No files found matching: {query}",
                error=None
            )
        
        result_text = f"Found {len(matches)} file(s) matching '{query}':\n"
        result_text += "\n".join(f"- {m}" for m in matches)
        
        return ToolResult(
            tool_name="search_files",
            success=True,
            output=result_text,
            error=None
        )
    except Exception:
        return ToolResult(
            tool_name="search_files",
            success=False,
            output="",
            error="File search failed"
        )
