from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from google.ads.googleads.errors import GoogleAdsException
import ads_mcp.utils as utils
from ads_mcp.tools._mutation_utils import clean_id, money_to_micros, google_ads_error

campaigns_mcp = FastMCP("campaigns")

def _set_campaign_status(customer_id, campaign_id, status):
    customer_id, campaign_id = clean_id(customer_id), clean_id(campaign_id)
    client = utils.get_googleads_client()
    service = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    op.update.resource_name = service.campaign_path(customer_id, campaign_id)
    op.update.status = getattr(client.enums.CampaignStatusEnum, status)
    op.update_mask.paths.append("status")
    try:
        response = service.mutate_campaigns(customer_id=customer_id, operations=[op])
        return {"resource_name": response.results[0].resource_name, "status": status}
    except GoogleAdsException as ex:
        raise google_ads_error(ex)

@campaigns_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def pause_campaign(customer_id: str | int, campaign_id: str | int):
    """Pause a Google Ads campaign."""
    return _set_campaign_status(customer_id, campaign_id, "PAUSED")

@campaigns_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def enable_campaign(customer_id: str | int, campaign_id: str | int):
    """Enable a Google Ads campaign."""
    return _set_campaign_status(customer_id, campaign_id, "ENABLED")

@campaigns_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def set_campaign_daily_budget(customer_id: str | int, campaign_id: str | int, daily_budget: float):
    """Set a campaign's daily budget in the account currency."""
    if daily_budget <= 0:
        raise ValueError("daily_budget must be greater than zero.")
    customer_id, campaign_id = clean_id(customer_id), clean_id(campaign_id)
    client = utils.get_googleads_client()
    google_ads_service = client.get_service("GoogleAdsService")
    query = f"""
      SELECT campaign.campaign_budget
      FROM campaign
      WHERE campaign.id = {campaign_id}
      LIMIT 1
    """
    try:
        rows = list(google_ads_service.search(customer_id=customer_id, query=query))
        if not rows:
            raise ValueError(f"Campaign {campaign_id} was not found.")
        budget_resource = rows[0].campaign.campaign_budget
        budget_service = client.get_service("CampaignBudgetService")
        op = client.get_type("CampaignBudgetOperation")
        op.update.resource_name = budget_resource
        op.update.amount_micros = money_to_micros(daily_budget)
        op.update_mask.paths.append("amount_micros")
        response = budget_service.mutate_campaign_budgets(customer_id=customer_id, operations=[op])
        return {
            "campaign_id": campaign_id,
            "budget_resource_name": response.results[0].resource_name,
            "daily_budget": daily_budget,
        }
    except GoogleAdsException as ex:
        raise google_ads_error(ex)

@campaigns_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def set_campaign_bidding_strategy(
    customer_id: str | int,
    campaign_id: str | int,
    strategy: str,
    target_cpa: float | None = None,
    target_roas: float | None = None,
    max_cpc: float | None = None,
    enhanced_cpc: bool = False,
):
    """Change a campaign's standard bidding strategy.

    Supported strategy values:
    MANUAL_CPC, MAXIMIZE_CLICKS, MAXIMIZE_CONVERSIONS,
    MAXIMIZE_CONVERSION_VALUE, TARGET_CPA, TARGET_ROAS.

    target_cpa and max_cpc use the account currency. target_roas is a ratio
    (for example 4.0 means 400% ROAS).
    """
    strategy = strategy.upper().strip()
    supported = {
        "MANUAL_CPC", "MAXIMIZE_CLICKS", "MAXIMIZE_CONVERSIONS",
        "MAXIMIZE_CONVERSION_VALUE", "TARGET_CPA", "TARGET_ROAS",
    }
    if strategy not in supported:
        raise ValueError(f"Unsupported strategy {strategy}. Supported: {sorted(supported)}")
    if strategy == "TARGET_CPA" and (target_cpa is None or target_cpa <= 0):
        raise ValueError("TARGET_CPA requires target_cpa > 0.")
    if strategy == "TARGET_ROAS" and (target_roas is None or target_roas <= 0):
        raise ValueError("TARGET_ROAS requires target_roas > 0.")

    customer_id, campaign_id = clean_id(customer_id), clean_id(campaign_id)
    client = utils.get_googleads_client()
    service = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    campaign = op.update
    campaign.resource_name = service.campaign_path(customer_id, campaign_id)

    if strategy == "MANUAL_CPC":
        campaign.manual_cpc = client.get_type("ManualCpc")
        campaign.manual_cpc.enhanced_cpc_enabled = enhanced_cpc
        op.update_mask.paths.append("manual_cpc")
    elif strategy == "MAXIMIZE_CLICKS":
        campaign.target_spend = client.get_type("TargetSpend")
        if max_cpc is not None:
            if max_cpc <= 0:
                raise ValueError("max_cpc must be greater than zero.")
            campaign.target_spend.cpc_bid_ceiling_micros = money_to_micros(max_cpc)
        op.update_mask.paths.append("target_spend")
    elif strategy == "MAXIMIZE_CONVERSIONS":
        campaign.maximize_conversions = client.get_type("MaximizeConversions")
        if target_cpa is not None:
            if target_cpa <= 0:
                raise ValueError("target_cpa must be greater than zero.")
            campaign.maximize_conversions.target_cpa_micros = money_to_micros(target_cpa)
        op.update_mask.paths.append("maximize_conversions")
    elif strategy == "MAXIMIZE_CONVERSION_VALUE":
        campaign.maximize_conversion_value = client.get_type("MaximizeConversionValue")
        if target_roas is not None:
            if target_roas <= 0:
                raise ValueError("target_roas must be greater than zero.")
            campaign.maximize_conversion_value.target_roas = float(target_roas)
        op.update_mask.paths.append("maximize_conversion_value")
    elif strategy == "TARGET_CPA":
        campaign.target_cpa = client.get_type("TargetCpa")
        campaign.target_cpa.target_cpa_micros = money_to_micros(target_cpa)
        op.update_mask.paths.append("target_cpa")
    elif strategy == "TARGET_ROAS":
        campaign.target_roas = client.get_type("TargetRoas")
        campaign.target_roas.target_roas = float(target_roas)
        op.update_mask.paths.append("target_roas")

    try:
        response = service.mutate_campaigns(customer_id=customer_id, operations=[op])
        return {"resource_name": response.results[0].resource_name, "strategy": strategy}
    except GoogleAdsException as ex:
        raise google_ads_error(ex)
