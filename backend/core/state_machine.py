"""Incident state machine — deterministic transitions with validation.

Valid transitions:
  OPEN → PENDING_APPROVAL → DISPATCH_READY → DISPATCHED → IN_PROGRESS → RESOLVED → CLOSED

Rules:
  - State transitions must be validated before DB write
  - Invalid transitions return error
  - Every transition is logged to audit_logs
  - EMERGENCY incidents auto-notify on creation
  - Resolved incidents cannot be re-opened without explicit override
"""
import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class IncidentStatus(str, Enum):
    """Valid incident states."""
    OPEN = "OPEN"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    DISPATCH_READY = "DISPATCH_READY"
    DISPATCHED = "DISPATCHED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


# Define valid state transitions as a directed graph
VALID_TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]] = {
    IncidentStatus.OPEN: {
        IncidentStatus.PENDING_APPROVAL,
        IncidentStatus.CLOSED,  # Can close directly if cancelled
    },
    IncidentStatus.PENDING_APPROVAL: {
        IncidentStatus.DISPATCH_READY,
        IncidentStatus.OPEN,  # Back to open if needs revision
    },
    IncidentStatus.DISPATCH_READY: {
        IncidentStatus.DISPATCHED,
        IncidentStatus.PENDING_APPROVAL,  # Back if needs more info
    },
    IncidentStatus.DISPATCHED: {
        IncidentStatus.IN_PROGRESS,
        IncidentStatus.DISPATCH_READY,  # Revert if failed
    },
    IncidentStatus.IN_PROGRESS: {
        IncidentStatus.RESOLVED,
        IncidentStatus.DISPATCHED,  # Revert if issue resurfaces
    },
    IncidentStatus.RESOLVED: {
        IncidentStatus.CLOSED,
        # Re-opening requires explicit override endpoint
    },
    IncidentStatus.CLOSED: set(),  # Terminal state
}


class StateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""
    pass


def validate_transition(
    current_status: str,
    new_status: str,
    allow_override: bool = False,
) -> tuple[bool, Optional[str]]:
    """
    Validate a state transition.

    Args:
        current_status: Current incident status
        new_status: Desired incident status
        allow_override: If True, allow transitions from RESOLVED

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        current = IncidentStatus(current_status)
        target = IncidentStatus(new_status)
    except ValueError as e:
        return False, f"Invalid status value: {e}"

    # Same state — no-op but not an error
    if current == target:
        return True, None

    # RESOLVED → OPEN only with explicit override
    if current == IncidentStatus.RESOLVED and target != IncidentStatus.CLOSED:
        if not allow_override:
            return False, "Resolved incidents cannot be re-opened without explicit override. Use /reopen endpoint."
        logger.warning(f"State transition {current} → {target} with override flag")

    # Check if transition is valid
    if target not in VALID_TRANSITIONS.get(current, set()):
        valid_next = VALID_TRANSITIONS.get(current, set())
        valid_str = ", ".join(s.value for s in valid_next) if valid_next else "none"
        return False, f"Cannot transition from {current.value} to {target.value}. Valid next states: {valid_str}"

    return True, None


def get_valid_transitions(current_status: str) -> list[str]:
    """Get list of valid next states for current status."""
    try:
        current = IncidentStatus(current_status)
        valid = VALID_TRANSITIONS.get(current, set())
        return sorted([s.value for s in valid])
    except ValueError:
        return []
</
>
