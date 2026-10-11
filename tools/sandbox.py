"""
Sandbox: Restrict all file operations to ~/raven_workspace/
"""

from pathlib import Path


class SandboxViolation(Exception):
    """Raised when a path attempts to escape the workspace."""
    pass


# Workspace directory - all file operations must stay inside this
WORKSPACE = Path.home() / "raven_workspace"


def safe_path(user_path: str) -> Path:
    """
    Resolve user_path and verify it is inside WORKSPACE.
    
    Creates WORKSPACE if it doesn't exist.
    
    Args:
        user_path: Relative or absolute path string from user/tool
        
    Returns:
        Resolved Path object inside WORKSPACE
        
    Raises:
        SandboxViolation: If path escapes WORKSPACE via:
            - ../ traversal
            - absolute paths outside WORKSPACE
            - symlinks pointing outside
            - empty/invalid paths
    """
    if not user_path or not user_path.strip():
        raise SandboxViolation("Empty path not allowed")
    
    # Ensure workspace exists
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    
    # Resolve the path relative to workspace
    try:
        if Path(user_path).is_absolute():
            # Absolute paths must be inside workspace
            resolved = Path(user_path).resolve()
        else:
            # Relative paths are resolved from workspace
            resolved = (WORKSPACE / user_path).resolve()
    except (RuntimeError, OSError) as e:
        raise SandboxViolation(f"Invalid path: {e}")
    
    # Check if resolved path is inside workspace
    try:
        resolved.relative_to(WORKSPACE)
    except ValueError:
        raise SandboxViolation(f"Path escapes workspace: {user_path}")
    
    return resolved
