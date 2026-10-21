"""Campaign, budget and bidding write tools."""

from __future__ import annotations

from typing import Any, Dict
from uuid import uuid4

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


campaigns_mcp = FastMCP("campaigns")


def _set_campaign_status(
    customer_id: str | int,
    campaign_id: str | int,
    status: str,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    customer_id = clean_id(customer_id)
    campaign_id = clean_id(campaign_id)
    c = client(login_customer_id)
    service = c.get_service("CampaignService")
    op = c.get_type("CampaignOperation")
    campaign = op.update
    campaign.resource_name = service.campaign_path(customer_id, campaign_id)
    campaign.status = enum_value(
        c.enums.CampaignStatusEnum, status, ["ENABLED", "PAUSED"]
    )
    apply_mask(c, op, campaign)
    response = mutate(service, "mutate_campaigns", customer_id, [op])
    return {
        "resource_name": first_resource_name(response),
        "campaign_id": campaign_id,
        "status": status.upper(),
    }


@campaigns_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def pause_campaign(
    customer_id: str | int,
    campaign_id: str | int,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Pause a campaign."""
    return _set_campaign_status(
        customer_id, campaign_id, "PAUSED", login_customer_id
    )


@campaigns_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def enable_campaign(
    customer_id: str | int,
    campaign_id: str | int,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Enable a campaign."""
    return _set_campaign_status(
        customer_id, campaign_id, "ENABLED", login_customer_id
    )


@campaigns_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def update_campaign_budget(
    customer_id: str | int,
    campaign_id: str | int,
    daily_budget: float,
    confirm_large_increase: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Set the campaign daily budget in account currency.

    Budget increases greater than 20% require confirm_large_increase=True.
    """
    customer_id = clean_id(customer_id)
    campaign_id = clean_id(campaign_id)
    c = client(login_customer_id)
    ga_service = c.get_service("GoogleAdsService")
    query = (
        "SELECT campaign.campaign_budget, campaign_budget.amount_micros "
        "FROM campaign "
        f"WHERE campaign.id = {campaign_id} LIMIT 1"
    )
    try:
        rows = list(ga_service.search(customer_id=customer_id, query=query))
    except GoogleAdsException as ex:
        raise_ads_error(ex)
    if not rows:
        raise ToolError("Campaign not found.")

    current_micros = int(rows[0].campaign_budget.amount_micros)
    new_micros = money_to_micros(daily_budget)
    if (
        current_micros > 0
        and new_micros > current_micros * 1.20
        and not confirm_large_increase
    ):
        current = current_micros / 1_000_000
        pct = ((new_micros / current_micros) - 1) * 100
        raise ToolError(
            f"Budget increase is {pct:.1f}% ({current:.2f} -> "
            f"{daily_budget:.2f}). Re-run with "
            "confirm_large_increase=True to approve."
        )

    budget_service = c.get_service("CampaignBudgetService")
    op = c.get_type("CampaignBudgetOperation")
    budget = op.update
    budget.resource_name = rows[0].campaign.campaign_budget
    budget.amount_micros = new_micros
    apply_mask(c, op, budget)
    response = mutate(
        budget_service, "mutate_campaign_budgets", customer_id, [op]
    )
    return {
        "resource_name": first_resource_name(response),
        "previous_daily_budget": current_micros / 1_000_000,
        "daily_budget": float(daily_budget),
    }


@campaigns_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def update_bidding_strategy(
    customer_id: str | int,
    campaign_id: str | int,
    strategy: str,
    target_cpa: float | None = None,
    target_roas: float | None = None,
    confirm_change: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Change campaign bidding.

    Supported strategy values: MAXIMIZE_CLICKS, MAXIMIZE_CONVERSIONS,
    MAXIMIZE_CONVERSION_VALUE, MANUAL_CPC. A bidding change requires
    confirm_change=True. target_cpa is in account currency. target_roas is a
    ratio, e.g. 4.0 means 400%.
    """
    if not confirm_change:
        raise ToolError(
            "Bidding strategy changes require confirm_change=True."
        )

    customer_id = clean_id(customer_id)
    campaign_id = clean_id(campaign_id)
    strategy = str(strategy).upper().strip()
    allowed = [
        "MAXIMIZE_CLICKS",
        "MAXIMIZE_CONVERSIONS",
        "MAXIMIZE_CONVERSION_VALUE",
        "MANUAL_CPC",
    ]
    if strategy not in allowed:
        raise ToolError(f"Allowed strategies: {', '.join(allowed)}")

    c = client(login_customer_id)
    service = c.get_service("CampaignService")
    op = c.get_type("CampaignOperation")
    campaign = op.update
    campaign.resource_name = service.campaign_path(customer_id, campaign_id)

    if strategy == "MAXIMIZE_CLICKS":
        campaign.target_spend.target_spend_micros = 0
    elif strategy == "MAXIMIZE_CONVERSIONS":
        campaign.maximize_conversions.target_cpa_micros = (
            money_to_micros(target_cpa) if target_cpa is not None else None
        )
    elif strategy == "MAXIMIZE_CONVERSION_VALUE":
        campaign.maximize_conversion_value.target_roas = (
            float(target_roas) if target_roas is not None else None
        )
    elif strategy == "MANUAL_CPC":
        campaign.manual_cpc = c.get_type("ManualCpc")

    apply_mask(c, op, campaign)
    response = mutate(service, "mutate_campaigns", customer_id, [op])
    return {
        "resource_name": first_resource_name(response),
        "strategy": strategy,
        "target_cpa": target_cpa,
        "target_roas": target_roas,
    }


@campaigns_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def create_search_campaign(
    customer_id: str | int,
    name: str,
    daily_budget: float,
    bidding_strategy: str = "MAXIMIZE_CLICKS",
    status: str = "PAUSED",
    target_cpa: float | None = None,
    target_roas: float | None = None,
    include_search_partners: bool = False,
    include_display_network: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Create a Search campaign and its budget.

    Campaigns default to PAUSED for safety.
    """
    customer_id = clean_id(customer_id)
    c = client(login_customer_id)
    strategy = str(bidding_strategy).upper().strip()
    allowed = [
        "MAXIMIZE_CLICKS",
        "MAXIMIZE_CONVERSIONS",
        "MAXIMIZE_CONVERSION_VALUE",
        "MANUAL_CPC",
    ]
    if strategy not in allowed:
        raise ToolError(f"Allowed strategies: {', '.join(allowed)}")

    budget_service = c.get_service("CampaignBudgetService")
    budget_op = c.get_type("CampaignBudgetOperation")
    budget = budget_op.create
    budget.name = f"{name} - Budget - {uuid4().hex[:8]}"
    budget.amount_micros = money_to_micros(daily_budget)
    budget.delivery_method = c.enums.BudgetDeliveryMethodEnum.STANDARD
    budget.explicitly_shared = False
    budget_response = mutate(
        budget_service, "mutate_campaign_budgets", customer_id, [budget_op]
    )
    budget_resource = first_resource_name(budget_response)

    service = c.get_service("CampaignService")
    op = c.get_type("CampaignOperation")
    campaign = op.create
    campaign.name = name
    campaign.status = enum_value(
        c.enums.CampaignStatusEnum, status, ["PAUSED", "ENABLED"]
    )
    campaign.advertising_channel_type = (
        c.enums.AdvertisingChannelTypeEnum.SEARCH
    )
    campaign.campaign_budget = budget_resource
    campaign.network_settings.target_google_search = True
    campaign.network_settings.target_search_network = bool(
        include_search_partners
    )
    campaign.network_settings.target_partner_search_network = False
    campaign.network_settings.target_content_network = bool(
        include_display_network
    )
    campaign.contains_eu_political_advertising = (
        c.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    )

    if strategy == "MAXIMIZE_CLICKS":
        campaign.target_spend.target_spend_micros = 0
    elif strategy == "MAXIMIZE_CONVERSIONS":
        campaign.maximize_conversions.target_cpa_micros = (
            money_to_micros(target_cpa) if target_cpa is not None else None
        )
    elif strategy == "MAXIMIZE_CONVERSION_VALUE":
        campaign.maximize_conversion_value.target_roas = (
            float(target_roas) if target_roas is not None else None
        )
    elif strategy == "MANUAL_CPC":
        campaign.manual_cpc = c.get_type("ManualCpc")

    response = mutate(service, "mutate_campaigns", customer_id, [op])
    return {
        "campaign_resource_name": first_resource_name(response),
        "budget_resource_name": budget_resource,
        "status": status.upper(),
        "bidding_strategy": strategy,
        "daily_budget": float(daily_budget),
    }
