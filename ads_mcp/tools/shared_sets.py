"""Shared negative keyword list tools."""

from __future__ import annotations

from typing import Any, Dict

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from ads_mcp.tools._mutation_helpers import (
    clean_id,
    client,
    first_resource_name,
    mutate,
)


shared_sets_mcp = FastMCP("shared_sets")


@shared_sets_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def create_negative_keyword_list(
    customer_id: str | int,
    name: str,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Create an empty shared negative keyword list."""
    customer_id = clean_id(customer_id)
    c = client(login_customer_id)
    service = c.get_service("SharedSetService")
    op = c.get_type("SharedSetOperation")
    shared_set = op.create
    shared_set.name = name
    shared_set.type_ = c.enums.SharedSetTypeEnum.NEGATIVE_KEYWORDS
    response = mutate(service, "mutate_shared_sets", customer_id, [op])
    return {
        "resource_name": first_resource_name(response),
        "name": name,
    }


@shared_sets_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def attach_shared_set_to_campaign(
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


@shared_sets_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True)
)
def detach_shared_set_from_campaign(
    customer_id: str | int,
    campaign_id: str | int,
    shared_set_id: str | int,
    confirm_remove: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Detach a shared negative keyword list from a campaign."""
    if not confirm_remove:
        raise ToolError("Detaching a shared set requires confirm_remove=True.")
    customer_id = clean_id(customer_id)
    campaign_id = clean_id(campaign_id)
    shared_set_id = clean_id(shared_set_id)
    c = client(login_customer_id)
    service = c.get_service("CampaignSharedSetService")
    op = c.get_type("CampaignSharedSetOperation")
    op.remove = service.campaign_shared_set_path(
        customer_id, campaign_id, shared_set_id
    )
    response = mutate(
        service, "mutate_campaign_shared_sets", customer_id, [op]
    )
    return {"resource_name": first_resource_name(response), "removed": True}


@shared_sets_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True)
)
def remove_shared_negative_keyword_list(
    customer_id: str | int,
    shared_set_id: str | int,
    confirm_remove: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Remove a shared negative keyword list. It must not be in use."""
    if not confirm_remove:
        raise ToolError(
            "Removing a shared negative list requires confirm_remove=True."
        )
    customer_id = clean_id(customer_id)
    shared_set_id = clean_id(shared_set_id)
    c = client(login_customer_id)
    service = c.get_service("SharedSetService")
    op = c.get_type("SharedSetOperation")
    op.remove = service.shared_set_path(customer_id, shared_set_id)
    response = mutate(service, "mutate_shared_sets", customer_id, [op])
    return {"resource_name": first_resource_name(response), "removed": True}
