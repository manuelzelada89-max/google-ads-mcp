from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from google.ads.googleads.errors import GoogleAdsException
import ads_mcp.utils as utils
from ads_mcp.tools._mutation_utils import clean_id, google_ads_error

shared_sets_mcp = FastMCP("shared_sets")

@shared_sets_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def create_negative_keyword_list(customer_id: str | int, name: str):
    """Create a shared negative keyword list."""
    customer_id = clean_id(customer_id)
    client = utils.get_googleads_client()
    service = client.get_service("SharedSetService")
    op = client.get_type("SharedSetOperation")
    shared_set = op.create
    shared_set.name = name
    shared_set.type_ = client.enums.SharedSetTypeEnum.NEGATIVE_KEYWORDS
    try:
        response = service.mutate_shared_sets(customer_id=customer_id, operations=[op])
        return {"resource_name": response.results[0].resource_name}
    except GoogleAdsException as ex:
        raise google_ads_error(ex)

@shared_sets_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def attach_shared_set_to_campaign(customer_id: str | int, campaign_id: str | int, shared_set_id: str | int):
    """Attach an existing shared set, such as a negative keyword list, to a campaign."""
    customer_id, campaign_id, shared_set_id = map(clean_id, (customer_id, campaign_id, shared_set_id))
    client = utils.get_googleads_client()
    service = client.get_service("CampaignSharedSetService")
    campaign_service = client.get_service("CampaignService")
    shared_set_service = client.get_service("SharedSetService")
    op = client.get_type("CampaignSharedSetOperation")
    item = op.create
    item.campaign = campaign_service.campaign_path(customer_id, campaign_id)
    item.shared_set = shared_set_service.shared_set_path(customer_id, shared_set_id)
    try:
        response = service.mutate_campaign_shared_sets(customer_id=customer_id, operations=[op])
        return {"resource_name": response.results[0].resource_name}
    except GoogleAdsException as ex:
        raise google_ads_error(ex)
