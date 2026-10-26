"""Shared helpers for Google Ads mutation tools."""

from __future__ import annotations

from typing import Any, List

from fastmcp.exceptions import ToolError
from google.api_core import protobuf_helpers
from google.ads.googleads.errors import GoogleAdsException

import ads_mcp.utils as utils


def clean_id(value: str | int) -> str:
    return utils.clean_customer_id(value)


def client(login_customer_id: str | int | None = None):
    return utils.get_googleads_client(login_customer_id=login_customer_id)


def apply_mask(googleads_client, operation, resource) -> None:
    googleads_client.copy_from(
        operation.update_mask,
        protobuf_helpers.field_mask(None, resource._pb),
    )


def first_resource_name(response) -> str:
    if not response.results:
        raise ToolError("Google Ads returned no mutation result.")
    return response.results[0].resource_name


def money_to_micros(amount: float) -> int:
    amount = float(amount)
    if amount < 0:
        raise ToolError("Money amount cannot be negative.")
    return int(round(amount * 1_000_000))


def enum_value(enum_type, name: str, allowed: List[str] | None = None):
    key = str(name).strip().upper()
    if allowed and key not in allowed:
        raise ToolError(
            f"Invalid value '{name}'. Allowed: {', '.join(allowed)}"
        )
    try:
        return getattr(enum_type, key)
    except AttributeError as exc:
        raise ToolError(f"Unsupported enum value '{name}'.") from exc


def raise_ads_error(ex: GoogleAdsException) -> None:
    messages = []
    for error in ex.failure.errors:
        message = error.message
        if error.location:
            fields = [
                item.field_name
                for item in error.location.field_path_elements
                if item.field_name
            ]
            if fields:
                message += f" (field: {'.'.join(fields)})"
        messages.append(message)
    raise ToolError(
        f"Google Ads API request failed. Request ID: {ex.request_id}\n"
        + "\n".join(messages)
    )


def mutate(service, method_name: str, customer_id: str, operations: list):
    try:
        return getattr(service, method_name)(
            customer_id=customer_id, operations=operations
        )
    except GoogleAdsException as ex:
        raise_ads_error(ex)
