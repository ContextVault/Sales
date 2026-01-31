"""
Policy Store - Temporal Policy Version Management

Manages business policies with version history, enabling queries like:
"What policy was active when this decision was made?"

This is critical for decision tracing - we need to know which rules
were in effect at the exact moment a decision was made.
"""
from datetime import datetime
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# POLICY DEFINITIONS
# =============================================================================

# Policy version history - ordered chronologically
POLICY_VERSIONS: List[Dict[str, Any]] = [
    {
        "version": "3.1",
        "effective_from": datetime(2025, 6, 1, 0, 0, 0),
        "effective_until": datetime(2025, 12, 31, 23, 59, 59),
        "rules": {
            "discount_limits": {
                "standard_limit": 10,      # Rep can approve up to 10%
                "manager_limit": 15,        # Manager can approve up to 15%
                "vp_limit": 20,             # VP can approve up to 20%
                "cfo_limit": 30             # CFO can approve up to 30%
            },
            "approval_thresholds": {
                "arr_threshold_for_manager": 100000,    # >$100K ARR needs manager
                "arr_threshold_for_vp": 500000,         # >$500K ARR needs VP
                "discount_auto_approve_limit": 5        # Auto-approve up to 5%
            },
            "exception_rules": {
                "max_exception_discount": 25,           # Max even with exception
                "requires_documentation": True,
                "requires_finance_approval_above": 20
            }
        },
        "description": "Q3-Q4 2025 discount policy",
        "changelog": "Initial policy version for tracking"
    },
    {
        "version": "3.2",
        "effective_from": datetime(2026, 1, 1, 0, 0, 0),
        "effective_until": None,  # Current policy (no end date)
        "rules": {
            "discount_limits": {
                "standard_limit": 10,       # Rep can approve up to 10%
                "manager_limit": 15,        # Manager can approve up to 15%
                "vp_limit": 25,             # VP limit INCREASED from 20% to 25%
                "cfo_limit": 35             # CFO limit increased
            },
            "approval_thresholds": {
                "arr_threshold_for_manager": 100000,
                "arr_threshold_for_vp": 500000,
                "discount_auto_approve_limit": 5
            },
            "exception_rules": {
                "max_exception_discount": 30,           # Increased max
                "requires_documentation": True,
                "requires_finance_approval_above": 25   # Raised threshold
            },
            "enterprise_special": {
                "enabled": True,
                "max_discount": 30,
                "requires_cfo_approval": True,
                "min_arr": 500000,
                "description": "Enterprise customers with $500K+ ARR can get up to 30% with CFO approval"
            }
        },
        "description": "Q1 2026 discount policy - VP limits increased",
        "changelog": "Increased VP discount limit from 20% to 25%. Added enterprise special program."
    }
]


# =============================================================================
# POLICY STORE CLASS
# =============================================================================

class PolicyStore:
    """
    Temporal policy store supporting version queries by timestamp.
    
    Key capabilities:
    - Get policy active at a specific timestamp
    - List all policy versions
    - Check if a discount exceeds policy limits
    - Determine required approval level
    """
    
    def __init__(self):
        """Initialize with pre-defined policy versions."""
        self._policies = POLICY_VERSIONS
        logger.info(f"PolicyStore initialized with {len(self._policies)} versions")
    
    def get_policy_at_time(self, timestamp: datetime) -> Optional[Dict[str, Any]]:
        """
        Get the policy version that was active at a specific timestamp.
        
        This is the core temporal query - given a decision timestamp,
        return the exact policy rules that were in effect.
        
        Args:
            timestamp: The datetime to query
            
        Returns:
            Policy dict with version, effective dates, and rules.
            Returns None if no policy was active at that time.
        """
        for policy in self._policies:
            effective_from = policy["effective_from"]
            effective_until = policy["effective_until"]
            
            # Check if timestamp falls within this policy's effective period
            if timestamp >= effective_from:
                if effective_until is None or timestamp <= effective_until:
                    return policy.copy()
        
        # No policy found for this timestamp
        logger.warning(f"No policy found for timestamp {timestamp}")
        return None
    
    def get_current_policy(self) -> Dict[str, Any]:
        """
        Get the currently active policy (no end date).
        
        Returns:
            Current policy dict
        """
        for policy in self._policies:
            if policy["effective_until"] is None:
                return policy.copy()
        
        # Fallback to latest policy if none is marked as current
        return self._policies[-1].copy()
    
    def get_all_policies(self) -> List[Dict[str, Any]]:
        """
        Get all policy versions (for display/audit purposes).
        
        Returns:
            List of all policy versions in chronological order
        """
        result = []
        current_policy = self.get_current_policy()
        
        for policy in self._policies:
            policy_copy = policy.copy()
            policy_copy["is_current"] = (policy["version"] == current_policy["version"])
            result.append(policy_copy)
        
        return result
    
    def get_discount_limit(
        self, 
        timestamp: datetime, 
        approver_role: str = "standard"
    ) -> Optional[int]:
        """
        Get the maximum discount limit for a given role at a specific time.
        
        Args:
            timestamp: When the decision was made
            approver_role: Role of approver (standard, manager, vp, cfo)
            
        Returns:
            Maximum discount percentage allowed, or None if policy not found
        """
        policy = self.get_policy_at_time(timestamp)
        if not policy:
            return None
        
        limits = policy["rules"].get("discount_limits", {})
        limit_key = f"{approver_role}_limit"
        
        return limits.get(limit_key, limits.get("standard_limit", 10))
    
    def check_discount_exceeds_limit(
        self,
        discount_percent: float,
        timestamp: datetime,
        approver_role: str = "standard"
    ) -> Dict[str, Any]:
        """
        Check if a discount exceeds the policy limit for a given role.
        
        Args:
            discount_percent: The discount being requested/approved
            timestamp: When the decision was made
            approver_role: Role of approver
            
        Returns:
            Dict with:
                - exceeds: bool - whether limit is exceeded
                - limit: int - the applicable limit
                - deviation: float - how much over limit (if any)
                - policy_version: str - which policy was checked
        """
        policy = self.get_policy_at_time(timestamp)
        if not policy:
            return {
                "exceeds": True,
                "limit": 0,
                "deviation": discount_percent,
                "policy_version": "unknown",
                "error": "No policy found for timestamp"
            }
        
        limit = self.get_discount_limit(timestamp, approver_role)
        exceeds = discount_percent > limit
        
        return {
            "exceeds": exceeds,
            "limit": limit,
            "deviation": max(0, discount_percent - limit),
            "policy_version": policy["version"],
            "approver_role": approver_role
        }
    
    def get_required_approval_level(
        self,
        discount_percent: float,
        timestamp: datetime
    ) -> Dict[str, Any]:
        """
        Determine what approval level is required for a given discount.
        
        Args:
            discount_percent: The discount percentage
            timestamp: When the decision is being made
            
        Returns:
            Dict with required_role and explanation
        """
        policy = self.get_policy_at_time(timestamp)
        if not policy:
            return {
                "required_role": "unknown",
                "explanation": "No policy found for timestamp"
            }
        
        limits = policy["rules"].get("discount_limits", {})
        
        if discount_percent <= limits.get("standard_limit", 10):
            return {
                "required_role": "standard",
                "explanation": f"Discount {discount_percent}% within standard limit of {limits.get('standard_limit', 10)}%"
            }
        elif discount_percent <= limits.get("manager_limit", 15):
            return {
                "required_role": "manager",
                "explanation": f"Discount {discount_percent}% requires manager approval (limit: {limits.get('manager_limit', 15)}%)"
            }
        elif discount_percent <= limits.get("vp_limit", 20):
            return {
                "required_role": "vp",
                "explanation": f"Discount {discount_percent}% requires VP approval (limit: {limits.get('vp_limit', 20)}%)"
            }
        elif discount_percent <= limits.get("cfo_limit", 30):
            return {
                "required_role": "cfo",
                "explanation": f"Discount {discount_percent}% requires CFO approval (limit: {limits.get('cfo_limit', 30)}%)"
            }
        else:
            return {
                "required_role": "exception",
                "explanation": f"Discount {discount_percent}% exceeds all standard limits, requires executive exception"
            }


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

policy_store = PolicyStore()


# =============================================================================
# MODULE-LEVEL HELPER FUNCTIONS
# =============================================================================

def get_policy_at_time(timestamp: datetime) -> Optional[Dict[str, Any]]:
    """Convenience function for getting policy at a specific time."""
    return policy_store.get_policy_at_time(timestamp)


def get_current_policy() -> Dict[str, Any]:
    """Convenience function for getting current policy."""
    return policy_store.get_current_policy()


def get_all_policies() -> List[Dict[str, Any]]:
    """Convenience function for getting all policies."""
    return policy_store.get_all_policies()
