from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from google.ads.googleads.errors import GoogleAdsException
import ads_mcp.utils as utils
from ads_mcp.tools._mutation_utils import clean_id, money_to_micros, google_ads_error

ad_groups_mcp = FastMCP("ad_groups")

@ad_groups_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def create_ad_group(
    customer_id: str | int,
    campaign_id: str | int,
    name: str,
    cpc_bid: float | None = None,
    status: str = "PAUSED",
):
    """Create a Search ad group. Defaults to PAUSED for safety."""
    status = status.upper().strip()
    if status not in {"PAUSED", "ENABLED"}:
        raise ValueError("status must be PAUSED or ENABLED.")
    customer_id, campaign_id = clean_id(customer_id), clean_id(campaign_id)
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupService")
    campaign_service = client.get_service("CampaignService")
    op = client.get_type("AdGroupOperation")
    ad_group = op.create
    ad_group.name = name
    ad_group.campaign = campaign_service.campaign_path(customer_id, campaign_id)
    ad_group.status = getattr(client.enums.AdGroupStatusEnum, status)
    ad_group.type_ = client.enums.AdGroupTypeEnum.SEARCH_STANDARD
    if cpc_bid is not None:
        if cpc_bid <= 0:
            raise ValueError("cpc_bid must be greater than zero.")
        ad_group.cpc_bid_micros = money_to_micros(cpc_bid)
    try:
        response = service.mutate_ad_groups(customer_id=customer_id, operations=[op])
        return {"resource_name": response.results[0].resource_name, "status": status}
    except GoogleAdsException as ex:
        raise google_ads_error(ex)

def _set_ad_group_status(customer_id, ad_group_id, status):
    customer_id, ad_group_id = clean_id(customer_id), clean_id(ad_group_id)
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupService")
    op = client.get_type("AdGroupOperation")
    op.update.resource_name = service.ad_group_path(customer_id, ad_group_id)
    op.update.status = getattr(client.enums.AdGroupStatusEnum, status)
    op.update_mask.paths.append("status")
    try:
        response = service.mutate_ad_groups(customer_id=customer_id, operations=[op])
        return {"resource_name": response.results[0].resource_name, "status": status}
    except GoogleAdsException as ex:
        raise google_ads_error(ex)

@ad_groups_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def pause_ad_group(customer_id: str | int, ad_group_id: str | int):
    """Pause an ad group."""
    return _set_ad_group_status(customer_id, ad_group_id, "PAUSED")

@ad_groups_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def enable_ad_group(customer_id: str | int, ad_group_id: str | int):
    """Enable an ad group."""
    return _set_ad_group_status(customer_id, ad_group_id, "ENABLED")

@ad_groups_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def set_ad_group_cpc_bid(customer_id: str | int, ad_group_id: str | int, cpc_bid: float):
    """Set the default CPC bid for an ad group."""
    if cpc_bid <= 0:
        raise ValueError("cpc_bid must be greater than zero.")
    customer_id, ad_group_id = clean_id(customer_id), clean_id(ad_group_id)
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupService")
    op = client.get_type("AdGroupOperation")
    op.update.resource_name = service.ad_group_path(customer_id, ad_group_id)
    op.update.cpc_bid_micros = money_to_micros(cpc_bid)
    op.update_mask.paths.append("cpc_bid_micros")
    try:
        response = service.mutate_ad_groups(customer_id=customer_id, operations=[op])
        return {"resource_name": response.results[0].resource_name, "cpc_bid": cpc_bid}
    except GoogleAdsException as ex:
        raise google_ads_error(ex)
