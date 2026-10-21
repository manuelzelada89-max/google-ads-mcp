"""Responsive Search Ad write tools."""

from __future__ import annotations

from typing import Any, Dict, List

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from ads_mcp.tools._mutation_helpers import (
    apply_mask,
    clean_id,
    client,
    enum_value,
    first_resource_name,
    mutate,
)


ads_mcp = FastMCP("ads")


def _validate_rsa(headlines: List[str], descriptions: List[str]) -> None:
    if not 3 <= len(headlines) <= 15:
        raise ToolError("RSA requires 3 to 15 headlines.")
    if not 2 <= len(descriptions) <= 4:
        raise ToolError("RSA requires 2 to 4 descriptions.")
    too_long_headlines = [h for h in headlines if len(h) > 30]
    too_long_descriptions = [d for d in descriptions if len(d) > 90]
    if too_long_headlines:
        raise ToolError(
            "RSA headlines must be 30 characters or fewer: "
            + " | ".join(too_long_headlines)
        )
    if too_long_descriptions:
        raise ToolError(
            "RSA descriptions must be 90 characters or fewer: "
            + " | ".join(too_long_descriptions)
        )


def _set_ad_status(
    customer_id: str | int,
    ad_group_id: str | int,
    ad_id: str | int,
    status: str,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    customer_id = clean_id(customer_id)
    ad_group_id = clean_id(ad_group_id)
    ad_id = clean_id(ad_id)
    c = client(login_customer_id)
    service = c.get_service("AdGroupAdService")
    op = c.get_type("AdGroupAdOperation")
    ad_group_ad = op.update
    ad_group_ad.resource_name = service.ad_group_ad_path(
        customer_id, ad_group_id, ad_id
    )
    ad_group_ad.status = enum_value(
        c.enums.AdGroupAdStatusEnum, status, ["ENABLED", "PAUSED"]
    )
    apply_mask(c, op, ad_group_ad)
    response = mutate(service, "mutate_ad_group_ads", customer_id, [op])
    return {
        "resource_name": first_resource_name(response),
        "status": status.upper(),
    }


@ads_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def create_responsive_search_ad(
    customer_id: str | int,
    ad_group_id: str | int,
    final_url: str,
    headlines: List[str],
    descriptions: List[str],
    path1: str | None = None,
    path2: str | None = None,
    status: str = "PAUSED",
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Create a Responsive Search Ad. Defaults to PAUSED for safety."""
    _validate_rsa(headlines, descriptions)
    if path1 and len(path1) > 15:
        raise ToolError("path1 must be 15 characters or fewer.")
    if path2 and len(path2) > 15:
        raise ToolError("path2 must be 15 characters or fewer.")

    customer_id = clean_id(customer_id)
    ad_group_id = clean_id(ad_group_id)
    c = client(login_customer_id)
    service = c.get_service("AdGroupAdService")
    ad_group_service = c.get_service("AdGroupService")
    op = c.get_type("AdGroupAdOperation")
    ad_group_ad = op.create
    ad_group_ad.ad_group = ad_group_service.ad_group_path(
        customer_id, ad_group_id
    )
    ad_group_ad.status = enum_value(
        c.enums.AdGroupAdStatusEnum, status, ["ENABLED", "PAUSED"]
    )
    ad_group_ad.ad.final_urls.append(final_url)

    for text in headlines:
        asset = c.get_type("AdTextAsset")
        asset.text = text
        ad_group_ad.ad.responsive_search_ad.headlines.append(asset)

    for text in descriptions:
        asset = c.get_type("AdTextAsset")
        asset.text = text
        ad_group_ad.ad.responsive_search_ad.descriptions.append(asset)

    if path1:
        ad_group_ad.ad.responsive_search_ad.path1 = path1
    if path2:
        ad_group_ad.ad.responsive_search_ad.path2 = path2

    response = mutate(service, "mutate_ad_group_ads", customer_id, [op])
    return {
        "resource_name": first_resource_name(response),
        "status": status.upper(),
        "headline_count": len(headlines),
        "description_count": len(descriptions),
        "final_url": final_url,
    }


@ads_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def pause_ad(
    customer_id: str | int,
    ad_group_id: str | int,
    ad_id: str | int,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Pause an ad."""
    return _set_ad_status(
        customer_id, ad_group_id, ad_id, "PAUSED", login_customer_id
    )


@ads_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def enable_ad(
    customer_id: str | int,
    ad_group_id: str | int,
    ad_id: str | int,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Enable an ad."""
    return _set_ad_status(
        customer_id, ad_group_id, ad_id, "ENABLED", login_customer_id
    )


@ads_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True))
def remove_ad(
    customer_id: str | int,
    ad_group_id: str | int,
    ad_id: str | int,
    confirm_remove: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Remove an ad. Requires confirm_remove=True."""
    if not confirm_remove:
        raise ToolError("Removing an ad requires confirm_remove=True.")
    customer_id = clean_id(customer_id)
    ad_group_id = clean_id(ad_group_id)
    ad_id = clean_id(ad_id)
    c = client(login_customer_id)
    service = c.get_service("AdGroupAdService")
    op = c.get_type("AdGroupAdOperation")
    op.remove = service.ad_group_ad_path(
        customer_id, ad_group_id, ad_id
    )
    response = mutate(service, "mutate_ad_group_ads", customer_id, [op])
    return {"resource_name": first_resource_name(response), "removed": True}
