"""
API routes for tools management.
"""

import logging
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from tools import all_tools, ToolRouter, ApprovalGate
from tools.registry import get_tool


log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tools")

# Shared tool router instance
_tool_router = ToolRouter(ApprovalGate())


def get_tool_router() -> ToolRouter:
    """Get the global tool router instance."""
    return _tool_router


@router.get("")
async def list_tools():
    """
    List all available tools with schemas and risk levels.
    
    Returns:
        List of tool metadata including name, description, risk, parameters
    """
    tools = all_tools()
    return JSONResponse(
        status_code=200,
        content={
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "risk": tool.risk,
                    "needs_termux_api": tool.needs_termux_api,
                    "parameters": tool.parameters
                }
                for tool in tools
            ]
        }
    )


@router.post("/approve")
async def approve_tool(req: dict):
    """
    Handle tool approval request from UI.
    
    Args:
        req: {tool_name: str, args_preview: dict}
    
    Returns:
        {approved: bool, message: str}
    
    Note: This is a placeholder. In production, this would:
    - Store the approval request
    - Notify the UI to show approval dialog
    - Return when user responds
    
    For now, it auto-approves low-risk tools and denies others
    (since we don't have a real-time approval UI yet).
    """
    if not isinstance(req, dict):
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid request body", "code": "INVALID_INPUT"}
        )
    
    tool_name = req.get("tool_name")
    args_preview = req.get("args_preview", {})
    
    if not tool_name:
        return JSONResponse(
            status_code=400,
            content={"error": "Missing tool_name", "code": "INVALID_INPUT"}
        )
    
    tool_schema = get_tool(tool_name)
    if not tool_schema:
        return JSONResponse(
            status_code=404,
            content={"error": "Unknown tool", "code": "NOT_FOUND"}
        )
    
    # For now: auto-approve low-risk, deny others
    # TODO: Implement real approval flow with UI notifications
    if tool_schema.risk == "low":
        return JSONResponse(
            status_code=200,
            content={
                "approved": True,
                "message": f"Auto-approved low-risk tool: {tool_name}"
            }
        )
    else:
        return JSONResponse(
            status_code=200,
            content={
                "approved": False,
                "message": f"Approval required for {tool_schema.risk}-risk tool: {tool_name}"
            }
        )


@router.get("/history")
async def tool_history():
    """
    Get recent tool execution history from audit log.
    
    Returns:
        Last 20 tool runs with metadata (no raw arguments)
    """
    router_instance = get_tool_router()
    history = router_instance.get_audit_history(limit=20)
    
    return JSONResponse(
        status_code=200,
        content={"history": history}
    )
