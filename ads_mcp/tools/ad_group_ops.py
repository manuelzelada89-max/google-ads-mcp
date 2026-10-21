"""Ad group write tools."""

from __future__ import annotations

from typing import Any, Dict

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException
from mcp.types import ToolAnnotations

from ads_mcp.tools._mutation_helpers import (
    apply_mask,
    clean_id,
    client,
    enum_value,
    first_resource_name,
    money_to_micros,
    mutate,
    raise_ads_error,
)


ad_groups_mcp = FastMCP("ad_groups")


def _set_status(
    customer_id: str | int,
    ad_group_id: str | int,
    status: str,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    customer_id = clean_id(customer_id)
    ad_group_id = clean_id(ad_group_id)
    c = client(login_customer_id)
    service = c.get_service("AdGroupService")
    op = c.get_type("AdGroupOperation")
    ad_group = op.update
    ad_group.resource_name = service.ad_group_path(customer_id, ad_group_id)
    ad_group.status = enum_value(
        c.enums.AdGroupStatusEnum, status, ["ENABLED", "PAUSED"]
    )
    apply_mask(c, op, ad_group)
    response = mutate(service, "mutate_ad_groups", customer_id, [op])
    return {
        "resource_name": first_resource_name(response),
        "ad_group_id": ad_group_id,
        "status": status.upper(),
    }


@ad_groups_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def create_ad_group(
    customer_id: str | int,
    campaign_id: str | int,
    name: str,
    status: str = "PAUSED",
    cpc_bid: float | None = None,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Create a Search ad group. Defaults to PAUSED for safety."""
    customer_id = clean_id(customer_id)
    campaign_id = clean_id(campaign_id)
    c = client(login_customer_id)
    service = c.get_service("AdGroupService")
    campaign_service = c.get_service("CampaignService")
    op = c.get_type("AdGroupOperation")
    ad_group = op.create
    ad_group.name = name
    ad_group.campaign = campaign_service.campaign_path(
        customer_id, campaign_id
    )
    ad_group.status = enum_value(
        c.enums.AdGroupStatusEnum, status, ["ENABLED", "PAUSED"]
    )
    ad_group.type_ = c.enums.AdGroupTypeEnum.SEARCH_STANDARD
    if cpc_bid is not None:
        ad_group.cpc_bid_micros = money_to_micros(cpc_bid)
    response = mutate(service, "mutate_ad_groups", customer_id, [op])
    return {
        "resource_name": first_resource_name(response),
        "name": name,
        "status": status.upper(),
        "cpc_bid": cpc_bid,
    }


@ad_groups_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def pause_ad_group(
    customer_id: str | int,
    ad_group_id: str | int,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Pause an ad group."""
    return _set_status(customer_id, ad_group_id, "PAUSED", login_customer_id)


@ad_groups_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def enable_ad_group(
    customer_id: str | int,
    ad_group_id: str | int,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Enable an ad group."""
    return _set_status(customer_id, ad_group_id, "ENABLED", login_customer_id)


@ad_groups_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def update_ad_group_cpc_bid(
    customer_id: str | int,
    ad_group_id: str | int,
    cpc_bid: float,
    confirm_large_increase: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Update ad group default CPC bid in account currency.

    Increases above 20% require confirm_large_increase=True.
    This applies only where the campaign bidding strategy supports manual bids.
    """
    customer_id = clean_id(customer_id)
    ad_group_id = clean_id(ad_group_id)
    c = client(login_customer_id)
    ga_service = c.get_service("GoogleAdsService")
    query = (
        "SELECT ad_group.cpc_bid_micros FROM ad_group "
        f"WHERE ad_group.id = {ad_group_id} LIMIT 1"
    )
    try:
        rows = list(ga_service.search(customer_id=customer_id, query=query))
    except GoogleAdsException as ex:
        raise_ads_error(ex)
    if not rows:
        raise ToolError("Ad group not found.")

    current_micros = int(rows[0].ad_group.cpc_bid_micros)
    new_micros = money_to_micros(cpc_bid)
    if (
        current_micros > 0
        and new_micros > current_micros * 1.20
        and not confirm_large_increase
    ):
        current = current_micros / 1_000_000
        pct = ((new_micros / current_micros) - 1) * 100
        raise ToolError(
            f"CPC bid increase is {pct:.1f}% ({current:.2f} -> "
            f"{cpc_bid:.2f}). Re-run with confirm_large_increase=True."
        )

    service = c.get_service("AdGroupService")
    op = c.get_type("AdGroupOperation")
    ad_group = op.update
    ad_group.resource_name = service.ad_group_path(customer_id, ad_group_id)
    ad_group.cpc_bid_micros = new_micros
    apply_mask(c, op, ad_group)
    response = mutate(service, "mutate_ad_groups", customer_id, [op])
    return {
        "resource_name": first_resource_name(response),
        "previous_cpc_bid": current_micros / 1_000_000,
        "cpc_bid": float(cpc_bid),
    }
