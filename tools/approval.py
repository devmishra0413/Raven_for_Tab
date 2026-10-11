"""
Approval gate: Risk-based approval logic for tool execution.
"""


class ApprovalGate:
    """
    Manages approval requirements for tools based on risk level.
    
    - low: no approval needed
    - medium: approval needed once per session per tool
    - high: always requires approval (every execution)
    """
    
    def __init__(self):
        # Track medium-risk tools approved this session
        self._approved_medium: set[str] = set()
    
    def requires_approval(self, tool_name: str, risk: str) -> bool:
        """
        Check if tool execution requires user approval.
        
        Args:
            tool_name: Name of the tool
            risk: Risk level ("low", "medium", "high")
            
        Returns:
            True if approval is required, False otherwise
        """
        if risk == "low":
            return False
        elif risk == "medium":
            return tool_name not in self._approved_medium
        elif risk == "high":
            return True
        else:
            # Unknown risk level - be conservative
            return True
    
    def record_approval(self, tool_name: str) -> None:
        """
        Record that a medium-risk tool has been approved this session.
        
        Args:
            tool_name: Name of the approved tool
        """
        self._approved_medium.add(tool_name)
    
    def clear_session(self) -> None:
        """
        Clear session-scoped approvals.
        
        Called when starting a new conversation (/new).
        """
        self._approved_medium.clear()
