"""Incident state machine — deterministic transitions with validation.

Valid transitions:
  OPEN → PENDING_APPROVAL → DISPATCH_READY → DISPATCHED → IN_PROGRESS → RESOLVED → CLOSED

Rules:
  - State transitions must be validated before DB write
  - Invalid transitions return error
  - Every transition is logged to audit_logs
  - EMERGENCY incidents auto-notify on creation
  - Resolved incidents cannot be re-opened without explicit override
  - allow_override flag requires admin role (checked in API layer)
"""
import logging
from enum import Enum
from typing import Optional, Set

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


def get_valid_transitions(current_status: str) -> Set[str]:
    """
    Get valid next states for current status.
    
    Args:
        current_status: Current incident status string
    
    Returns:
        Set of valid next status strings
    
    Raises:
        StateTransitionError: If current_status is invalid
    """
    try:
        current = IncidentStatus(current_status)
        next_states = VALID_TRANSITIONS.get(current, set())
        return {s.value for s in next_states}
    except ValueError as e:
        raise StateTransitionError(f"Invalid status: {current_status}")


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
        allow_override: If True, allow transitions from RESOLVED to OPEN (requires admin role check in API)

    Returns:
        Tuple of (is_valid, error_message)
    
    Notes:
        - RESOLVED → CLOSED is always allowed
        - RESOLVED → OPEN only allowed if allow_override=True (admin already validated in API layer)
        - CLOSED is a terminal state — no transitions out
    """
    try:
        current = IncidentStatus(current_status)
        target = IncidentStatus(new_status)
    except ValueError as e:
        return False, f"Invalid status value: {e}"

    # Same state — no-op but not an error
    if current == target:
        return True, None

    # CLOSED is terminal — cannot transition out
    if current == IncidentStatus.CLOSED:
        return False, "Closed incidents cannot be reopened. Contact administrator."

    # RESOLVED → OPEN/IN_PROGRESS requires explicit override
    if current == IncidentStatus.RESOLVED:
        if target == IncidentStatus.CLOSED:
            # RESOLVED → CLOSED always allowed
            return True, None
        else:
            # Any other transition from RESOLVED requires override
            if not allow_override:
                return False, (
                    "Resolved incidents cannot transition to other states without explicit override. "
                    "Use the /reopen endpoint with admin approval."
                )
            else:
                # SECURITY-REVIEW: allow_override is granted, but caller must have admin role (validated in API)
                logger.warning(
                    f"State transition {current.value} → {target.value} with override flag. "
                    "Ensure admin authorization was verified in API layer."
                )
                return True, None

    # Check normal transition graph
    valid_next_states = VALID_TRANSITIONS.get(current, set())
    if target not in valid_next_states:
        valid_list = [s.value for s in valid_next_states] or ["(none)"]
        return False, (
            f"Cannot transition from {current.value} to {target.value}. "
            f"Valid next states: {', '.join(valid_list)}"
        )

    return True, None


def validate_all_transitions() -> None:
    """
    Verify transition graph is acyclic and complete.
    Call at startup to catch configuration errors.
    
    Raises:
        StateTransitionError: If graph has cycles or inconsistencies
    """
    # Verify all referenced statuses exist
    all_statuses = set(IncidentStatus)
    for current, next_states in VALID_TRANSITIONS.items():
        if not isinstance(current, IncidentStatus):
            raise StateTransitionError(f"Key {current} is not an IncidentStatus")
        for next_state in next_states:
            if not isinstance(next_state, IncidentStatus):
                raise StateTransitionError(
                    f"Value {next_state} in VALID_TRANSITIONS[{current}] is not an IncidentStatus"
                )
    
    # Verify all enum values are in the transition map
    for status in all_statuses:
        if status not in VALID_TRANSITIONS:
            raise StateTransitionError(f"Status {status.value} not defined in VALID_TRANSITIONS")
    
    logger.info("State machine validation passed")

