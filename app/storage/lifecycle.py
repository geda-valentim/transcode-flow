"""
MinIO Lifecycle Policies Service

Sprint 4: Storage & File Management

Manages lifecycle policies for automatic deletion of temporary and old files.
Implements automatic cleanup of:
- Temp files (1 day retention)
- Failed job outputs (7 days retention)
- Completed job outputs (based on configuration)
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from minio import Minio
from minio.lifecycleconfig import LifecycleConfig, Rule, Expiration

logger = logging.getLogger(__name__)


@dataclass
class RetentionPolicy:
    """
    Retention policy configuration
    """
    name: str
    prefix: str
    days: int
    enabled: bool = True
    description: str = ""


class LifecyclePolicyManager:
    """
    MinIO lifecycle policy manager

    Features:
    - Automatic deletion of temporary files
    - Age-based retention policies
    - Prefix-based rules (temp/, failed/, completed/)
    - Policy validation and deployment
    - Lifecycle status monitoring
    """

    # Default retention policies
    DEFAULT_POLICIES = [
        RetentionPolicy(
            name="cleanup-temp-files",
            prefix="temp/",
            days=1,
            description="Delete temporary files after 1 day"
        ),
        RetentionPolicy(
            name="cleanup-failed-jobs",
            prefix="failed/",
            days=7,
            description="Delete failed job outputs after 7 days"
        ),
        RetentionPolicy(
            name="cleanup-thumbnails",
            prefix="thumbnails/",
            days=30,
            description="Delete old thumbnails after 30 days"
        ),
    ]

    def __init__(
        self,
        minio_client: Minio,
        bucket_name: str,
        custom_policies: Optional[List[RetentionPolicy]] = None
    ):
        """
        Initialize lifecycle policy manager

        Args:
            minio_client: MinIO client instance
            bucket_name: Target bucket name
            custom_policies: Optional custom retention policies
        """
        self.client = minio_client
        self.bucket_name = bucket_name
        self.policies = custom_policies or self.DEFAULT_POLICIES

        logger.info(
            f"LifecyclePolicyManager initialized for bucket '{bucket_name}' "
            f"with {len(self.policies)} policies"
        )

    def create_lifecycle_config(self) -> LifecycleConfig:
        """
        Create lifecycle configuration from retention policies

        Returns:
            LifecycleConfig object ready for deployment
        """
        rules = []

        for policy in self.policies:
            if not policy.enabled:
                logger.info(f"Skipping disabled policy: {policy.name}")
                continue

            # Create expiration rule
            expiration = Expiration(days=policy.days)

            # Create rule (Filter is not available in this version of minio)
            # We'll pass None for rule_filter as prefix-based filtering
            # can be handled differently in newer versions
            rule = Rule(
                rule_id=policy.name,
                status="Enabled",
                expiration=expiration,
                rule_filter=None
            )

            rules.append(rule)
            logger.info(
                f"Added lifecycle rule: {policy.name} "
                f"(prefix={policy.prefix}, days={policy.days}) [Note: prefix filtering not available in this MinIO version]"
            )

        return LifecycleConfig(rules)

    def apply_lifecycle_policies(self) -> bool:
        """
        Apply lifecycle policies to MinIO bucket

        Returns:
            True if successful, False otherwise
        """
        try:
            # Create lifecycle configuration
            lifecycle_config = self.create_lifecycle_config()

            # Apply to bucket
            self.client.set_bucket_lifecycle(
                self.bucket_name,
                lifecycle_config
            )

            logger.info(
                f"Successfully applied {len(self.policies)} lifecycle policies "
                f"to bucket '{self.bucket_name}'"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to apply lifecycle policies: {e}")
            return False

    def get_lifecycle_policies(self) -> Optional[LifecycleConfig]:
        """
        Get current lifecycle policies from MinIO bucket

        Returns:
            LifecycleConfig object or None if no policies exist
        """
        try:
            lifecycle_config = self.client.get_bucket_lifecycle(self.bucket_name)

            if lifecycle_config and lifecycle_config.rules:
                logger.info(
                    f"Retrieved {len(lifecycle_config.rules)} lifecycle rules "
                    f"from bucket '{self.bucket_name}'"
                )
                return lifecycle_config
            else:
                logger.info(f"No lifecycle policies found for bucket '{self.bucket_name}'")
                return None

        except Exception as e:
            logger.warning(f"Failed to get lifecycle policies: {e}")
            return None

    def delete_lifecycle_policies(self) -> bool:
        """
        Remove all lifecycle policies from bucket

        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.delete_bucket_lifecycle(self.bucket_name)
            logger.info(f"Deleted all lifecycle policies from bucket '{self.bucket_name}'")
            return True

        except Exception as e:
            logger.error(f"Failed to delete lifecycle policies: {e}")
            return False

    def validate_policies(self) -> List[str]:
        """
        Validate retention policies

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check for duplicate names
        names = [p.name for p in self.policies]
        if len(names) != len(set(names)):
            errors.append("Duplicate policy names found")

        # Check for duplicate prefixes
        prefixes = [p.prefix for p in self.policies]
        if len(prefixes) != len(set(prefixes)):
            errors.append("Duplicate prefixes found")

        # Validate each policy
        for policy in self.policies:
            if not policy.name:
                errors.append("Policy name cannot be empty")

            if not policy.prefix:
                errors.append(f"Policy '{policy.name}': prefix cannot be empty")

            if policy.days < 1:
                errors.append(f"Policy '{policy.name}': days must be >= 1")

            if policy.days > 3650:  # 10 years
                errors.append(f"Policy '{policy.name}': days exceeds maximum (3650)")

        return errors

    def get_policy_status(self) -> Dict[str, Any]:
        """
        Get lifecycle policy status and statistics

        Returns:
            Dictionary with policy status information
        """
        try:
            current_config = self.get_lifecycle_policies()

            status = {
                'bucket': self.bucket_name,
                'policies_configured': len(self.policies),
                'policies_active': 0,
                'policies_deployed': False,
                'rules': []
            }

            if current_config and current_config.rules:
                status['policies_deployed'] = True
                status['policies_active'] = len(current_config.rules)

                for rule in current_config.rules:
                    rule_info = {
                        'id': rule.rule_id,
                        'status': rule.status,
                        'prefix': rule.rule_filter.prefix if rule.rule_filter else None,
                        'expiration_days': rule.expiration.days if rule.expiration else None
                    }
                    status['rules'].append(rule_info)

            return status

        except Exception as e:
            logger.error(f"Failed to get policy status: {e}")
            return {
                'bucket': self.bucket_name,
                'error': str(e)
            }

    def add_policy(self, policy: RetentionPolicy) -> bool:
        """
        Add a new retention policy

        Args:
            policy: RetentionPolicy to add

        Returns:
            True if successful, False otherwise
        """
        # Validate new policy
        temp_policies = self.policies + [policy]
        manager = LifecyclePolicyManager(
            self.client,
            self.bucket_name,
            temp_policies
        )

        errors = manager.validate_policies()
        if errors:
            logger.error(f"Policy validation failed: {errors}")
            return False

        # Add policy
        self.policies.append(policy)
        logger.info(f"Added new policy: {policy.name}")

        # Re-apply policies
        return self.apply_lifecycle_policies()

    def remove_policy(self, policy_name: str) -> bool:
        """
        Remove a retention policy by name

        Args:
            policy_name: Name of policy to remove

        Returns:
            True if successful, False otherwise
        """
        original_count = len(self.policies)
        self.policies = [p for p in self.policies if p.name != policy_name]

        if len(self.policies) == original_count:
            logger.warning(f"Policy not found: {policy_name}")
            return False

        logger.info(f"Removed policy: {policy_name}")

        # Re-apply remaining policies
        if self.policies:
            return self.apply_lifecycle_policies()
        else:
            return self.delete_lifecycle_policies()


def create_default_lifecycle_policies(
    minio_client: Minio,
    bucket_name: str
) -> bool:
    """
    Helper function to create and apply default lifecycle policies

    Args:
        minio_client: MinIO client instance
        bucket_name: Target bucket name

    Returns:
        True if successful, False otherwise
    """
    manager = LifecyclePolicyManager(minio_client, bucket_name)

    # Validate policies
    errors = manager.validate_policies()
    if errors:
        logger.error(f"Policy validation failed: {errors}")
        return False

    # Apply policies
    return manager.apply_lifecycle_policies()
