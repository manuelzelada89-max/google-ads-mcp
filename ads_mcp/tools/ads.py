from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from google.ads.googleads.errors import GoogleAdsException
import ads_mcp.utils as utils
from ads_mcp.tools._mutation_utils import clean_id, google_ads_error

ads_mcp = FastMCP("ads")

@ads_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def create_responsive_search_ad(customer_id: str | int, ad_group_id: str | int, final_url: str, headlines: list[str], descriptions: list[str], status: str = "PAUSED"):
    """Create a responsive search ad. Defaults to PAUSED for safety."""
    if len(headlines) < 3:
        raise ValueError("At least 3 headlines are required.")
    if len(descriptions) < 2:
        raise ValueError("At least 2 descriptions are required.")
    if len(headlines) > 15:
        raise ValueError("Google Ads supports at most 15 headlines.")
    if len(descriptions) > 4:
        raise ValueError("Google Ads supports at most 4 descriptions.")
    if any(len(x) > 30 for x in headlines):
        raise ValueError("Each headline must be 30 characters or fewer.")
    if any(len(x) > 90 for x in descriptions):
        raise ValueError("Each description must be 90 characters or fewer.")
    status = status.upper().strip()
    if status not in {"PAUSED", "ENABLED"}:
        raise ValueError("status must be PAUSED or ENABLED.")
    customer_id, ad_group_id = clean_id(customer_id), clean_id(ad_group_id)
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupAdService")
    ad_group_service = client.get_service("AdGroupService")
    op = client.get_type("AdGroupAdOperation")
    ad_group_ad = op.create
    ad_group_ad.ad_group = ad_group_service.ad_group_path(customer_id, ad_group_id)
    ad_group_ad.status = getattr(client.enums.AdGroupAdStatusEnum, status)
    ad_group_ad.ad.final_urls.append(final_url)
    for text in headlines:
        asset = client.get_type("AdTextAsset")
        asset.text = text
        ad_group_ad.ad.responsive_search_ad.headlines.append(asset)
    for text in descriptions:
        asset = client.get_type("AdTextAsset")
        asset.text = text
        ad_group_ad.ad.responsive_search_ad.descriptions.append(asset)
    try:
        response = service.mutate_ad_group_ads(customer_id=customer_id, operations=[op])
        return {"resource_name": response.results[0].resource_name, "status": status}
    except GoogleAdsException as ex:
        raise google_ads_error(ex)

def _set_ad_status(customer_id, ad_group_id, ad_id, status):
    customer_id, ad_group_id, ad_id = map(clean_id, (customer_id, ad_group_id, ad_id))
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupAdService")
    op = client.get_type("AdGroupAdOperation")
    op.update.resource_name = service.ad_group_ad_path(customer_id, ad_group_id, ad_id)
    op.update.status = getattr(client.enums.AdGroupAdStatusEnum, status)
    op.update_mask.paths.append("status")
    try:
        response = service.mutate_ad_group_ads(customer_id=customer_id, operations=[op])
        return {"resource_name": response.results[0].resource_name, "status": status}
    except GoogleAdsException as ex:
        raise google_ads_error(ex)

@ads_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def pause_ad(customer_id: str | int, ad_group_id: str | int, ad_id: str | int):
    """Pause an ad."""
    return _set_ad_status(customer_id, ad_group_id, ad_id, "PAUSED")

@ads_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def enable_ad(customer_id: str | int, ad_group_id: str | int, ad_id: str | int):
    """Enable an ad."""
    return _set_ad_status(customer_id, ad_group_id, ad_id, "ENABLED")

@ads_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def remove_ad(customer_id: str | int, ad_group_id: str | int, ad_id: str | int):
    """Remove an ad."""
    customer_id, ad_group_id, ad_id = map(clean_id, (customer_id, ad_group_id, ad_id))
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupAdService")
    op = client.get_type("AdGroupAdOperation")
    op.remove = service.ad_group_ad_path(customer_id, ad_group_id, ad_id)
    try:
        response = service.mutate_ad_group_ads(customer_id=customer_id, operations=[op])
        return {"resource_name": response.results[0].resource_name, "removed": True}
    except GoogleAdsException as ex:
        raise google_ads_error(ex)
