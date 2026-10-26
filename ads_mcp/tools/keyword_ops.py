"""Keyword and negative-keyword mutation tools."""

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


keywords_mcp = FastMCP("keywords")


def _match_type(c, match_type: str):
    return enum_value(
        c.enums.KeywordMatchTypeEnum,
        match_type,
        ["BROAD", "PHRASE", "EXACT"],
    )


def _set_keyword_status(
    customer_id: str | int,
    ad_group_id: str | int,
    criterion_id: str | int,
    status: str,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    customer_id = clean_id(customer_id)
    ad_group_id = clean_id(ad_group_id)
    criterion_id = clean_id(criterion_id)
    c = client(login_customer_id)
    service = c.get_service("AdGroupCriterionService")
    op = c.get_type("AdGroupCriterionOperation")
    criterion = op.update
    criterion.resource_name = service.ad_group_criterion_path(
        customer_id, ad_group_id, criterion_id
    )
    criterion.status = enum_value(
        c.enums.AdGroupCriterionStatusEnum,
        status,
        ["ENABLED", "PAUSED"],
    )
    apply_mask(c, op, criterion)
    response = mutate(
        service, "mutate_ad_group_criteria", customer_id, [op]
    )
    return {
        "resource_name": first_resource_name(response),
        "status": status.upper(),
    }


@keywords_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def create_keyword(
    customer_id: str | int,
    ad_group_id: str | int,
    keyword_text: str,
    match_type: str,
    status: str = "PAUSED",
    cpc_bid: float | None = None,
    final_url: str | None = None,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Create a positive keyword. Defaults to PAUSED for safety."""
    customer_id = clean_id(customer_id)
    ad_group_id = clean_id(ad_group_id)
    c = client(login_customer_id)
    service = c.get_service("AdGroupCriterionService")
    ad_group_service = c.get_service("AdGroupService")
    op = c.get_type("AdGroupCriterionOperation")
    criterion = op.create
    criterion.ad_group = ad_group_service.ad_group_path(
        customer_id, ad_group_id
    )
    criterion.status = enum_value(
        c.enums.AdGroupCriterionStatusEnum,
        status,
        ["ENABLED", "PAUSED"],
    )
    criterion.keyword.text = keyword_text
    criterion.keyword.match_type = _match_type(c, match_type)
    criterion.negative = False
    if cpc_bid is not None:
        criterion.cpc_bid_micros = money_to_micros(cpc_bid)
    if final_url:
        criterion.final_urls.append(final_url)
    response = mutate(
        service, "mutate_ad_group_criteria", customer_id, [op]
    )
    return {
        "resource_name": first_resource_name(response),
        "keyword_text": keyword_text,
        "match_type": match_type.upper(),
        "status": status.upper(),
        "cpc_bid": cpc_bid,
    }


@keywords_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def pause_keyword(
    customer_id: str | int,
    ad_group_id: str | int,
    criterion_id: str | int,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Pause a positive keyword."""
    return _set_keyword_status(
        customer_id, ad_group_id, criterion_id, "PAUSED",
        login_customer_id
    )


@keywords_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def enable_keyword(
    customer_id: str | int,
    ad_group_id: str | int,
    criterion_id: str | int,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Enable a positive keyword."""
    return _set_keyword_status(
        customer_id, ad_group_id, criterion_id, "ENABLED",
        login_customer_id
    )


@keywords_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True)
)
def remove_keyword(
    customer_id: str | int,
    ad_group_id: str | int,
    criterion_id: str | int,
    confirm_remove: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Remove a keyword. Requires confirm_remove=True."""
    if not confirm_remove:
        raise ToolError("Removing a keyword requires confirm_remove=True.")
    customer_id = clean_id(customer_id)
    ad_group_id = clean_id(ad_group_id)
    criterion_id = clean_id(criterion_id)
    c = client(login_customer_id)
    service = c.get_service("AdGroupCriterionService")
    op = c.get_type("AdGroupCriterionOperation")
    op.remove = service.ad_group_criterion_path(
        customer_id, ad_group_id, criterion_id
    )
    response = mutate(
        service, "mutate_ad_group_criteria", customer_id, [op]
    )
    return {"resource_name": first_resource_name(response), "removed": True}


@keywords_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def update_keyword_cpc_bid(
    customer_id: str | int,
    ad_group_id: str | int,
    criterion_id: str | int,
    cpc_bid: float,
    confirm_large_increase: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Update a keyword CPC bid in account currency.

    Increases above 20% require confirm_large_increase=True. The campaign must
    use a bidding strategy that supports keyword-level manual bids.
    """
    customer_id = clean_id(customer_id)
    ad_group_id = clean_id(ad_group_id)
    criterion_id = clean_id(criterion_id)
    c = client(login_customer_id)

    ga_service = c.get_service("GoogleAdsService")
    query = (
        "SELECT ad_group_criterion.cpc_bid_micros "
        "FROM keyword_view "
        f"WHERE ad_group.id = {ad_group_id} "
        f"AND ad_group_criterion.criterion_id = {criterion_id} LIMIT 1"
    )
    try:
        rows = list(ga_service.search(customer_id=customer_id, query=query))
    except GoogleAdsException as ex:
        raise_ads_error(ex)
    if not rows:
        raise ToolError("Keyword criterion not found.")

    current_micros = int(rows[0].ad_group_criterion.cpc_bid_micros)
    new_micros = money_to_micros(cpc_bid)
    if (
        current_micros > 0
        and new_micros > current_micros * 1.20
        and not confirm_large_increase
    ):
        current = current_micros / 1_000_000
        pct = ((new_micros / current_micros) - 1) * 100
        raise ToolError(
            f"Keyword bid increase is {pct:.1f}% ({current:.2f} -> "
            f"{cpc_bid:.2f}). Re-run with confirm_large_increase=True."
        )

    service = c.get_service("AdGroupCriterionService")
    op = c.get_type("AdGroupCriterionOperation")
    criterion = op.update
    criterion.resource_name = service.ad_group_criterion_path(
        customer_id, ad_group_id, criterion_id
    )
    criterion.cpc_bid_micros = new_micros
    apply_mask(c, op, criterion)
    response = mutate(
        service, "mutate_ad_group_criteria", customer_id, [op]
    )
    return {
        "resource_name": first_resource_name(response),
        "previous_cpc_bid": current_micros / 1_000_000,
        "cpc_bid": float(cpc_bid),
    }


@keywords_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def add_campaign_negative_keyword(
    customer_id: str | int,
    campaign_id: str | int,
    keyword_text: str,
    match_type: str = "BROAD",
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Add a negative keyword directly to a campaign."""
    customer_id = clean_id(customer_id)
    campaign_id = clean_id(campaign_id)
    c = client(login_customer_id)
    service = c.get_service("CampaignCriterionService")
    campaign_service = c.get_service("CampaignService")
    op = c.get_type("CampaignCriterionOperation")
    criterion = op.create
    criterion.campaign = campaign_service.campaign_path(
        customer_id, campaign_id
    )
    criterion.negative = True
    criterion.keyword.text = keyword_text
    criterion.keyword.match_type = _match_type(c, match_type)
    response = mutate(
        service, "mutate_campaign_criteria", customer_id, [op]
    )
    return {
        "resource_name": first_resource_name(response),
        "keyword_text": keyword_text,
        "match_type": match_type.upper(),
    }


@keywords_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def add_ad_group_negative_keyword(
    customer_id: str | int,
    ad_group_id: str | int,
    keyword_text: str,
    match_type: str = "BROAD",
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Add a negative keyword directly to an ad group."""
    customer_id = clean_id(customer_id)
    ad_group_id = clean_id(ad_group_id)
    c = client(login_customer_id)
    service = c.get_service("AdGroupCriterionService")
    ad_group_service = c.get_service("AdGroupService")
    op = c.get_type("AdGroupCriterionOperation")
    criterion = op.create
    criterion.ad_group = ad_group_service.ad_group_path(
        customer_id, ad_group_id
    )
    criterion.negative = True
    criterion.keyword.text = keyword_text
    criterion.keyword.match_type = _match_type(c, match_type)
    response = mutate(
        service, "mutate_ad_group_criteria", customer_id, [op]
    )
    return {
        "resource_name": first_resource_name(response),
        "keyword_text": keyword_text,
        "match_type": match_type.upper(),
    }


@keywords_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def add_negative_keyword_to_shared_set(
    customer_id: str | int,
    shared_set_id: str | int,
    keyword_text: str,
    match_type: str = "BROAD",
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Add a keyword to an existing shared negative keyword list."""
    customer_id = clean_id(customer_id)
    shared_set_id = clean_id(shared_set_id)
    c = client(login_customer_id)
    service = c.get_service("SharedCriterionService")
    shared_set_service = c.get_service("SharedSetService")
    op = c.get_type("SharedCriterionOperation")
    criterion = op.create
    criterion.shared_set = shared_set_service.shared_set_path(
        customer_id, shared_set_id
    )
    criterion.keyword.text = keyword_text
    criterion.keyword.match_type = _match_type(c, match_type)
    response = mutate(
        service, "mutate_shared_criteria", customer_id, [op]
    )
    return {
        "resource_name": first_resource_name(response),
        "keyword_text": keyword_text,
        "match_type": match_type.upper(),
    }


@keywords_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True)
)
def remove_campaign_negative_keyword(
    customer_id: str | int,
    campaign_id: str | int,
    criterion_id: str | int,
    confirm_remove: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Remove a campaign-level negative keyword criterion."""
    if not confirm_remove:
        raise ToolError(
            "Removing a campaign negative requires confirm_remove=True."
        )
    customer_id = clean_id(customer_id)
    campaign_id = clean_id(campaign_id)
    criterion_id = clean_id(criterion_id)
    c = client(login_customer_id)
    service = c.get_service("CampaignCriterionService")
    op = c.get_type("CampaignCriterionOperation")
    op.remove = service.campaign_criterion_path(
        customer_id, campaign_id, criterion_id
    )
    response = mutate(
        service, "mutate_campaign_criteria", customer_id, [op]
    )
    return {"resource_name": first_resource_name(response), "removed": True}


@keywords_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def attach_shared_negative_list_to_campaign(
    customer_id: str | int,
    campaign_id: str | int,
    shared_set_id: str | int,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Attach an existing shared negative keyword list to a campaign."""
    customer_id = clean_id(customer_id)
    campaign_id = clean_id(campaign_id)
    shared_set_id = clean_id(shared_set_id)
    c = client(login_customer_id)
    service = c.get_service("CampaignSharedSetService")
    campaign_service = c.get_service("CampaignService")
    shared_set_service = c.get_service("SharedSetService")
    op = c.get_type("CampaignSharedSetOperation")
    item = op.create
    item.campaign = campaign_service.campaign_path(
        customer_id, campaign_id
    )
    item.shared_set = shared_set_service.shared_set_path(
        customer_id, shared_set_id
    )
    response = mutate(
        service, "mutate_campaign_shared_sets", customer_id, [op]
    )
    return {"resource_name": first_resource_name(response)}


@keywords_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True)
)
def remove_shared_negative_keyword(
    customer_id: str | int,
    shared_set_id: str | int,
    criterion_id: str | int,
    confirm_remove: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Remove one keyword from a shared negative keyword list."""
    if not confirm_remove:
        raise ToolError(
            "Removing a shared negative keyword requires confirm_remove=True."
        )
    customer_id = clean_id(customer_id)
    shared_set_id = clean_id(shared_set_id)
    criterion_id = clean_id(criterion_id)
    c = client(login_customer_id)
    service = c.get_service("SharedCriterionService")
    op = c.get_type("SharedCriterionOperation")
    op.remove = service.shared_criterion_path(
        customer_id, shared_set_id, criterion_id
    )
    response = mutate(
        service, "mutate_shared_criteria", customer_id, [op]
    )
    return {"resource_name": first_resource_name(response), "removed": True}
