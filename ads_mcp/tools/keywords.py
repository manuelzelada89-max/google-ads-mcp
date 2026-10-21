from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from google.ads.googleads.errors import GoogleAdsException
import ads_mcp.utils as utils
from ads_mcp.tools._mutation_utils import clean_id, money_to_micros, google_ads_error

keywords_mcp = FastMCP("keywords")

def _match_type(client, match_type):
    value = match_type.upper().strip()
    if value not in {"BROAD", "PHRASE", "EXACT"}:
        raise ValueError("match_type must be BROAD, PHRASE, or EXACT.")
    return getattr(client.enums.KeywordMatchTypeEnum, value)

@keywords_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def add_keyword(customer_id: str | int, ad_group_id: str | int, keyword_text: str, match_type: str = "PHRASE", cpc_bid: float | None = None, status: str = "ENABLED"):
    """Add a positive keyword to an ad group."""
    status = status.upper().strip()
    if status not in {"ENABLED", "PAUSED"}:
        raise ValueError("status must be ENABLED or PAUSED.")
    customer_id, ad_group_id = clean_id(customer_id), clean_id(ad_group_id)
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupCriterionService")
    ad_group_service = client.get_service("AdGroupService")
    op = client.get_type("AdGroupCriterionOperation")
    criterion = op.create
    criterion.ad_group = ad_group_service.ad_group_path(customer_id, ad_group_id)
    criterion.status = getattr(client.enums.AdGroupCriterionStatusEnum, status)
    criterion.keyword.text = keyword_text
    criterion.keyword.match_type = _match_type(client, match_type)
    if cpc_bid is not None:
        if cpc_bid <= 0:
            raise ValueError("cpc_bid must be greater than zero.")
        criterion.cpc_bid_micros = money_to_micros(cpc_bid)
    try:
        response = service.mutate_ad_group_criteria(customer_id=customer_id, operations=[op])
        return {"resource_name": response.results[0].resource_name, "status": status}
    except GoogleAdsException as ex:
        raise google_ads_error(ex)

def _set_keyword_status(customer_id, ad_group_id, criterion_id, status):
    customer_id, ad_group_id, criterion_id = map(clean_id, (customer_id, ad_group_id, criterion_id))
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupCriterionService")
    op = client.get_type("AdGroupCriterionOperation")
    op.update.resource_name = service.ad_group_criterion_path(customer_id, ad_group_id, criterion_id)
    op.update.status = getattr(client.enums.AdGroupCriterionStatusEnum, status)
    op.update_mask.paths.append("status")
    try:
        response = service.mutate_ad_group_criteria(customer_id=customer_id, operations=[op])
        return {"resource_name": response.results[0].resource_name, "status": status}
    except GoogleAdsException as ex:
        raise google_ads_error(ex)

@keywords_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def pause_keyword(customer_id: str | int, ad_group_id: str | int, criterion_id: str | int):
    """Pause a keyword criterion."""
    return _set_keyword_status(customer_id, ad_group_id, criterion_id, "PAUSED")

@keywords_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def enable_keyword(customer_id: str | int, ad_group_id: str | int, criterion_id: str | int):
    """Enable a keyword criterion."""
    return _set_keyword_status(customer_id, ad_group_id, criterion_id, "ENABLED")

@keywords_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def remove_keyword(customer_id: str | int, ad_group_id: str | int, criterion_id: str | int):
    """Remove a keyword criterion."""
    customer_id, ad_group_id, criterion_id = map(clean_id, (customer_id, ad_group_id, criterion_id))
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupCriterionService")
    op = client.get_type("AdGroupCriterionOperation")
    op.remove = service.ad_group_criterion_path(customer_id, ad_group_id, criterion_id)
    try:
        response = service.mutate_ad_group_criteria(customer_id=customer_id, operations=[op])
        return {"resource_name": response.results[0].resource_name, "removed": True}
    except GoogleAdsException as ex:
        raise google_ads_error(ex)

@keywords_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def set_keyword_cpc_bid(customer_id: str | int, ad_group_id: str | int, criterion_id: str | int, cpc_bid: float):
    """Set a keyword-level CPC bid."""
    if cpc_bid <= 0:
        raise ValueError("cpc_bid must be greater than zero.")
    customer_id, ad_group_id, criterion_id = map(clean_id, (customer_id, ad_group_id, criterion_id))
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupCriterionService")
    op = client.get_type("AdGroupCriterionOperation")
    op.update.resource_name = service.ad_group_criterion_path(customer_id, ad_group_id, criterion_id)
    op.update.cpc_bid_micros = money_to_micros(cpc_bid)
    op.update_mask.paths.append("cpc_bid_micros")
    try:
        response = service.mutate_ad_group_criteria(customer_id=customer_id, operations=[op])
        return {"resource_name": response.results[0].resource_name, "cpc_bid": cpc_bid}
    except GoogleAdsException as ex:
        raise google_ads_error(ex)

@keywords_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def add_ad_group_negative_keyword(customer_id: str | int, ad_group_id: str | int, keyword_text: str, match_type: str = "PHRASE"):
    """Add a negative keyword directly to an ad group."""
    customer_id, ad_group_id = clean_id(customer_id), clean_id(ad_group_id)
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupCriterionService")
    ad_group_service = client.get_service("AdGroupService")
    op = client.get_type("AdGroupCriterionOperation")
    criterion = op.create
    criterion.ad_group = ad_group_service.ad_group_path(customer_id, ad_group_id)
    criterion.negative = True
    criterion.keyword.text = keyword_text
    criterion.keyword.match_type = _match_type(client, match_type)
    try:
        response = service.mutate_ad_group_criteria(customer_id=customer_id, operations=[op])
        return {"resource_name": response.results[0].resource_name}
    except GoogleAdsException as ex:
        raise google_ads_error(ex)

@keywords_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def add_campaign_negative_keyword(customer_id: str | int, campaign_id: str | int, keyword_text: str, match_type: str = "PHRASE"):
    """Add a negative keyword directly to a campaign."""
    customer_id, campaign_id = clean_id(customer_id), clean_id(campaign_id)
    client = utils.get_googleads_client()
    service = client.get_service("CampaignCriterionService")
    campaign_service = client.get_service("CampaignService")
    op = client.get_type("CampaignCriterionOperation")
    criterion = op.create
    criterion.campaign = campaign_service.campaign_path(customer_id, campaign_id)
    criterion.negative = True
    criterion.keyword.text = keyword_text
    criterion.keyword.match_type = _match_type(client, match_type)
    try:
        response = service.mutate_campaign_criteria(customer_id=customer_id, operations=[op])
        return {"resource_name": response.results[0].resource_name}
    except GoogleAdsException as ex:
        raise google_ads_error(ex)

@keywords_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def remove_campaign_negative_keyword(customer_id: str | int, campaign_id: str | int, criterion_id: str | int):
    """Remove a campaign criterion by criterion ID, typically a campaign negative keyword."""
    customer_id, campaign_id, criterion_id = map(clean_id, (customer_id, campaign_id, criterion_id))
    client = utils.get_googleads_client()
    service = client.get_service("CampaignCriterionService")
    op = client.get_type("CampaignCriterionOperation")
    op.remove = service.campaign_criterion_path(customer_id, campaign_id, criterion_id)
    try:
        response = service.mutate_campaign_criteria(customer_id=customer_id, operations=[op])
        return {"resource_name": response.results[0].resource_name, "removed": True}
    except GoogleAdsException as ex:
        raise google_ads_error(ex)

@keywords_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def add_negative_keyword_to_shared_set(customer_id: str | int, shared_set_id: str | int, keyword_text: str, match_type: str = "PHRASE"):
    """Add a negative keyword to an existing shared negative-keyword list."""
    customer_id, shared_set_id = clean_id(customer_id), clean_id(shared_set_id)
    client = utils.get_googleads_client()
    service = client.get_service("SharedCriterionService")
    shared_set_service = client.get_service("SharedSetService")
    op = client.get_type("SharedCriterionOperation")
    criterion = op.create
    criterion.shared_set = shared_set_service.shared_set_path(customer_id, shared_set_id)
    criterion.keyword.text = keyword_text
    criterion.keyword.match_type = _match_type(client, match_type)
    try:
        response = service.mutate_shared_criteria(customer_id=customer_id, operations=[op])
        return {"resource_name": response.results[0].resource_name}
    except GoogleAdsException as ex:
        raise google_ads_error(ex)

@keywords_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def remove_shared_negative_keyword(customer_id: str | int, shared_set_id: str | int, criterion_id: str | int):
    """Remove a negative keyword criterion from a shared negative-keyword list."""
    customer_id, shared_set_id, criterion_id = map(clean_id, (customer_id, shared_set_id, criterion_id))
    client = utils.get_googleads_client()
    service = client.get_service("SharedCriterionService")
    op = client.get_type("SharedCriterionOperation")
    op.remove = service.shared_criterion_path(customer_id, shared_set_id, criterion_id)
    try:
        response = service.mutate_shared_criteria(customer_id=customer_id, operations=[op])
        return {"resource_name": response.results[0].resource_name, "removed": True}
    except GoogleAdsException as ex:
        raise google_ads_error(ex)
