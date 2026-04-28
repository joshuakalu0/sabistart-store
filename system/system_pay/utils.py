"""
System-level payment utilities for multi-tenant e-commerce platform
===================================================================

These utilities operate on system-wide payment models and are meant for 
platform-level operations rather than tenant-specific actions.
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone

from .models import PaymentGatewayDefinition, PlatformGatewayCredential, GatewayWebhookConfig

logger = logging.getLogger("system_pay")


@dataclass
class SystemGatewayResult:
    success: bool = False
    gateway_definition_id: Optional[str] = None
    gateway_provider: str = ""
    is_enabled: bool = False
    message: str = ""
    errors: list = field(default_factory=list)


def get_enabled_gateways():
    """
    Return all enabled payment gateway definitions.
    
    Returns:
        QuerySet of PaymentGatewayDefinition objects that are enabled.
    """
    return PaymentGatewayDefinition.objects.filter(is_enabled=True)


def get_platform_credential(gateway_id, environment="live"):
    """
    Retrieve an active platform credential for a specific gateway.
    
    Args:
        gateway_id: UUID of the gateway definition
        environment: "test" or "live" environment
        
    Returns:
        PlatformGatewayCredential object or None
    """
    return PlatformGatewayCredential.objects.filter(
        gateway_id=gateway_id,
        environment=environment,
        is_active=True
    ).order_by("-priority").first()


def get_all_platform_credentials(gateway_provider=None, environment=None):
    """
    Get all active platform credentials, optionally filtered.
    
    Args:
        gateway_provider: Optional provider name to filter
        environment: Optional environment to filter ("test" or "live")
        
    Returns:
        QuerySet of PlatformGatewayCredential objects
    """
    qs = PlatformGatewayCredential.objects.filter(is_active=True)
    
    if gateway_provider:
        qs = qs.filter(gateway__provider=gateway_provider)
    
    if environment:
        qs = qs.filter(environment=environment)
    
    return qs


def get_gateway_webhook_config(provider_name):
    """
    Get the webhook configuration for a specific gateway.
    
    Args:
        provider_name: Name of the gateway provider
        
    Returns:
        GatewayWebhookConfig object or None
    """
    try:
        gateway_def = PaymentGatewayDefinition.objects.get(provider=provider_name, is_enabled=True)
        return GatewayWebhookConfig.objects.filter(gateway=gateway_def, is_active=True).first()
    except PaymentGatewayDefinition.DoesNotExist:
        return None


def validate_platform_credential_health(credential_id):
    """
    Perform a health check on a platform credential.
    
    Args:
        credential_id: UUID of the PlatformGatewayCredential
        
    Returns:
        dict with health status and details
    """
    try:
        credential = PlatformGatewayCredential.objects.get(id=credential_id)
        # In a real implementation, this would perform actual API calls to verify credentials
        # For now, we'll simulate a basic health check
        is_healthy = credential.is_active and credential.secret_key.strip() != ""
        
        credential.is_healthy = is_healthy
        credential.last_health_check_at = timezone.now()
        credential.health_note = "Health check performed" if is_healthy else "Credential appears invalid"
        credential.save(update_fields=["is_healthy", "last_health_check_at", "health_note"])
        
        return {
            "credential_id": str(credential.id),
            "is_healthy": is_healthy,
            "last_checked": credential.last_health_check_at,
            "note": credential.health_note,
        }
    except PlatformGatewayCredential.DoesNotExist:
        return {
            "credential_id": credential_id,
            "is_healthy": False,
            "error": "Credential not found",
        }


def get_system_payment_stats():
    """
    Get system-wide payment statistics.
    
    Returns:
        dict with system payment stats
    """
    enabled_gateways = PaymentGatewayDefinition.objects.filter(is_enabled=True).count()
    active_credentials = PlatformGatewayCredential.objects.filter(is_active=True).count()
    configured_webhooks = GatewayWebhookConfig.objects.filter(is_active=True).count()
    
    return {
        "enabled_gateways": enabled_gateways,
        "active_credentials": active_credentials,
        "configured_webhooks": configured_webhooks,
    }


def register_new_gateway_definition(provider, name, **kwargs):
    """
    Register a new payment gateway definition at the system level.
    
    Args:
        provider: Provider identifier (must match GatewayProvider choices)
        name: Display name for the gateway
        **kwargs: Additional fields to set on the model
        
    Returns:
        SystemGatewayResult
    """
    try:
        # Check if this provider already exists
        existing = PaymentGatewayDefinition.objects.filter(provider=provider).first()
        if existing:
            return SystemGatewayResult(
                success=False,
                message=f"Gateway with provider '{provider}' already exists",
                errors=["Provider already registered"]
            )
        
        gateway = PaymentGatewayDefinition.objects.create(
            provider=provider,
            name=name,
            **kwargs
        )
        
        return SystemGatewayResult(
            success=True,
            gateway_definition_id=str(gateway.id),
            gateway_provider=provider,
            is_enabled=gateway.is_enabled,
            message=f"Successfully registered {name} ({provider})"
        )
    except Exception as e:
        logger.error(f"Error registering gateway {provider}: {str(e)}")
        return SystemGatewayResult(
            success=False,
            errors=[str(e)],
            message=f"Failed to register gateway: {str(e)}"
        )