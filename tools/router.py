"""
Tool router: Orchestrates tool execution with approval and error handling.
"""

import logging
import shutil
from dataclasses import dataclass
from typing import Any, Callable, Optional, Awaitable

from tools.registry import get_tool
from tools.approval import ApprovalGate
from privacy.vault import Vault


log = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Result of tool execution."""
    tool_name: str
    success: bool
    output: str
    error: Optional[str] = None


# Check Termux:API availability once at module load
_TERMUX_API_AVAILABLE: Optional[bool] = None


def termux_api_available() -> bool:
    """
    Check if Termux:API is available on this system.
    
    Cached after first call. Returns False on non-Android (dev machines).
    """
    global _TERMUX_API_AVAILABLE
    if _TERMUX_API_AVAILABLE is None:
        _TERMUX_API_AVAILABLE = shutil.which("termux-notification") is not None
    return _TERMUX_API_AVAILABLE


class ToolRouter:
    """
    Routes tool calls to their implementations with approval and safety checks.
    """
    
    def __init__(self, approval_gate: Optional[ApprovalGate] = None):
        self.approval_gate = approval_gate or ApprovalGate()
        self._audit_log: list[dict] = []
    
    async def run(
        self,
        tool_name: str,
        args: dict,
        vault: Vault,
        approval_callback: Optional[Callable[[str, dict], Awaitable[bool]]] = None
    ) -> ToolResult:
        """
        Execute a tool with approval and error handling.
        
        Args:
            tool_name: Name of the tool to execute
            args: Tool arguments (already unmasked by caller)
            vault: Vault instance (not used in execution, kept for future needs)
            approval_callback: Async function to request user approval
            
        Returns:
            ToolResult with success status and output/error
            
        Flow:
            1. Look up tool in registry
            2. Check Termux:API availability if needed
            3. Check approval gate
            4. Execute tool function
            5. Log to audit
        """
        # 1. Look up tool
        tool_schema = get_tool(tool_name)
        if tool_schema is None:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                output="",
                error=f"Unknown tool: {tool_name}"
            )
        
        # 2. Check Termux:API availability
        if tool_schema.needs_termux_api and not termux_api_available():
            return ToolResult(
                tool_name=tool_name,
                success=False,
                output="",
                error="Termux:API not available. Install termux-api package."
            )
        
        # 3. Check approval gate
        needs_approval = self.approval_gate.requires_approval(
            tool_name, tool_schema.risk
        )
        
        approved = True
        if needs_approval:
            if approval_callback:
                try:
                    approved = await approval_callback(tool_name, args)
                except Exception as e:
                    log.error(f"Approval callback failed: {e}")
                    approved = False
            else:
                # No callback provided - deny by default for safety
                approved = False
        
        if not approved:
            self._log_audit(tool_name, tool_schema.risk, approved=False, success=False)
            return ToolResult(
                tool_name=tool_name,
                success=False,
                output="Tool execution cancelled by user.",
                error=None
            )
        
        # Record approval for medium-risk tools
        if needs_approval and tool_schema.risk == "medium":
            self.approval_gate.record_approval(tool_name)
        
        # 4. Execute tool
        try:
            result = await self._execute_tool(tool_name, args)
            self._log_audit(tool_name, tool_schema.risk, approved=True, success=result.success)
            return result
        except Exception as e:
            log.error(f"Tool execution failed: {tool_name} - {type(e).__name__}")
            self._log_audit(tool_name, tool_schema.risk, approved=True, success=False)
            return ToolResult(
                tool_name=tool_name,
                success=False,
                output="",
                error="Tool execution failed. Please try again."
            )
    
    async def _execute_tool(self, tool_name: str, args: dict) -> ToolResult:
        """
        Execute the actual tool implementation.
        
        Imports tool module dynamically and calls its execute function.
        """
        # Map tool names to modules
        tool_modules = {
            "set_reminder": "tools.builtin.reminder",
            "add_note": "tools.builtin.notes",
            "read_note": "tools.builtin.notes",
            "search_files": "tools.builtin.files",
            "play_song": "tools.builtin.media",
            "pause_media": "tools.builtin.media",
            "next_track": "tools.builtin.media",
            "set_volume": "tools.builtin.media",
            "open_app": "tools.builtin.apps",
        }
        
        module_name = tool_modules.get(tool_name)
        if not module_name:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                output="",
                error=f"Tool implementation not found: {tool_name}"
            )
        
        try:
            # Dynamic import
            import importlib
            module = importlib.import_module(module_name)
            
            # Call the tool's execute function
            if hasattr(module, tool_name):
                func = getattr(module, tool_name)
                return await func(**args)
            else:
                return ToolResult(
                    tool_name=tool_name,
                    success=False,
                    output="",
                    error=f"Function {tool_name} not found in {module_name}"
                )
        except Exception as e:
            log.error(f"Tool import/execution error: {tool_name} - {e}")
            raise
    
    def _log_audit(self, tool_name: str, risk: str, approved: bool, success: bool) -> None:
        """
        Log tool execution to audit trail.
        
        Never logs raw arguments to protect privacy.
        """
        from datetime import datetime, timezone
        
        entry = {
            "kind": "tool_run",
            "tool_name": tool_name,
            "risk": risk,
            "approved": approved,
            "success": success,
            "ts": datetime.now(timezone.utc).isoformat()
        }
        self._audit_log.append(entry)
        
        # Keep only last 100 entries
        if len(self._audit_log) > 100:
            self._audit_log = self._audit_log[-100:]
    
    def get_audit_history(self, limit: int = 20) -> list[dict]:
        """Get recent tool execution history."""
        return self._audit_log[-limit:]
