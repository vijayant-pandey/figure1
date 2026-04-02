"""
Read-Only Mode Utility

Centralized utilities for managing read-only development mode that prevents all write operations.
"""

import logging
from typing import Optional, Any
from figure1.configuration import app_settings

logger = logging.getLogger('figure1.read_only_mode')


def is_read_only_mode() -> bool:
    """Check if read-only development mode is enabled."""
    return app_settings.read_only_dev_mode


def log_blocked_operation(operation: str, target: Optional[str] = None, details: Optional[dict] = None) -> None:
    """
    Log a blocked operation in read-only mode.
    
    Args:
        operation: The operation being blocked (e.g., 'database_commit', 's3_upload')
        target: The target of the operation (e.g., table name, file path)
        details: Additional details about the operation
    """
    message = f"READ-ONLY MODE: Blocked {operation}"
    if target:
        message += f" on {target}"
    
    if details:
        detail_str = ", ".join([f"{k}={v}" for k, v in details.items()])
        message += f" ({detail_str})"
    
    logger.warning(message)


def block_if_read_only(operation: str, target: Optional[str] = None, details: Optional[dict] = None) -> bool:
    """
    Check if read-only mode is enabled and log/block the operation if so.
    
    Args:
        operation: The operation being checked
        target: The target of the operation
        details: Additional details about the operation
    
    Returns:
        True if the operation should be blocked, False if it can proceed
    """
    if is_read_only_mode():
        log_blocked_operation(operation, target, details)
        return True
    return False


def get_read_only_status() -> dict:
    """
    Get the current status of read-only mode including configuration details.
    
    Returns:
        Dictionary with read-only mode status information
    """
    return {
        'enabled': is_read_only_mode(),
        'test_mode': app_settings.test_mode,
        'components_blocked': [
            'database_operations',
            'external_api_calls',
            'firestore_operations', 
            's3_operations',
            'elasticsearch_operations'
        ]
    }


class ReadOnlyModeException(Exception):
    """Exception raised when a write operation is attempted in read-only mode."""
    
    def __init__(self, operation: str, target: Optional[str] = None):
        self.operation = operation
        self.target = target
        message = f"Write operation '{operation}' blocked by read-only mode"
        if target:
            message += f" (target: {target})"
        super().__init__(message)