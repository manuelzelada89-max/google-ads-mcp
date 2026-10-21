from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from google.ads.googleads.errors import GoogleAdsException
import ads_mcp.utils as utils
from ads_mcp.tools._mutation_utils import clean_id, google_ads_error

targeting_mcp = FastMCP("targeting")

@targeting_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def add_campaign_location(customer_id: str | int, campaign_id: str | int, location_id: str | int, negative: bool = False, bid_modifier: float | None = None):
    """Add a geo target or geo exclusion to a campaign using a Google geo target constant ID."""
    customer_id, campaign_id, location_id = map(clean_id, (customer_id, campaign_id, location_id))
    client = utils.get_googleads_client()
    service = client.get_service("CampaignCriterionService")
    campaign_service = client.get_service("CampaignService")
    geo_service = client.get_service("GeoTargetConstantService")
    op = client.get_type("CampaignCriterionOperation")
    criterion = op.create
    criterion.campaign = campaign_service.campaign_path(customer_id, campaign_id)
    criterion.location.geo_target_constant = geo_service.geo_target_constant_path(location_id)
    criterion.negative = bool(negative)
    if bid_modifier is not None:
        if negative:
            raise ValueError("bid_modifier cannot be used on a negative location.")
        if bid_modifier <= 0:
            raise ValueError("bid_modifier must be greater than zero.")
        criterion.bid_modifier = float(bid_modifier)
    try:
        response = service.mutate_campaign_criteria(customer_id=customer_id, operations=[op])
        return {"resource_name": response.results[0].resource_name, "negative": bool(negative)}
    except GoogleAdsException as ex:
        raise google_ads_error(ex)

@targeting_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def remove_campaign_criterion(customer_id: str | int, campaign_id: str | int, criterion_id: str | int):
    """Remove any removable campaign criterion, such as a location, device, or schedule criterion."""
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

@targeting_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def set_campaign_criterion_bid_modifier(customer_id: str | int, campaign_id: str | int, criterion_id: str | int, bid_modifier: float):
    """Set the bid modifier for an existing campaign criterion when Google Ads supports bid modifiers for that criterion type."""
    if bid_modifier <= 0:
        raise ValueError("bid_modifier must be greater than zero.")
    customer_id, campaign_id, criterion_id = map(clean_id, (customer_id, campaign_id, criterion_id))
    client = utils.get_googleads_client()
    service = client.get_service("CampaignCriterionService")
    op = client.get_type("CampaignCriterionOperation")
    op.update.resource_name = service.campaign_criterion_path(customer_id, campaign_id, criterion_id)
    op.update.bid_modifier = float(bid_modifier)
    op.update_mask.paths.append("bid_modifier")
    try:
        response = service.mutate_campaign_criteria(customer_id=customer_id, operations=[op])
        return {"resource_name": response.results[0].resource_name, "bid_modifier": bid_modifier}
    except GoogleAdsException as ex:
        raise google_ads_error(ex)

@targeting_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def add_device_bid_modifier(customer_id: str | int, campaign_id: str | int, device: str, bid_modifier: float):
    """Add a device criterion and bid modifier. device: MOBILE, DESKTOP, TABLET, CONNECTED_TV, OTHER."""
    device = device.upper().strip()
    allowed = {"MOBILE", "DESKTOP", "TABLET", "CONNECTED_TV", "OTHER"}
    if device not in allowed:
        raise ValueError(f"device must be one of {sorted(allowed)}")
    if bid_modifier <= 0:
        raise ValueError("bid_modifier must be greater than zero.")
    customer_id, campaign_id = clean_id(customer_id), clean_id(campaign_id)
    client = utils.get_googleads_client()
    service = client.get_service("CampaignCriterionService")
    campaign_service = client.get_service("CampaignService")
    op = client.get_type("CampaignCriterionOperation")
    criterion = op.create
    criterion.campaign = campaign_service.campaign_path(customer_id, campaign_id)
    criterion.device.type_ = getattr(client.enums.DeviceEnum, device)
    criterion.bid_modifier = float(bid_modifier)
    try:
        response = service.mutate_campaign_criteria(customer_id=customer_id, operations=[op])
        return {"resource_name": response.results[0].resource_name, "device": device, "bid_modifier": bid_modifier}
    except GoogleAdsException as ex:
        raise google_ads_error(ex)

@targeting_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def add_ad_schedule(customer_id: str | int, campaign_id: str | int, day_of_week: str, start_hour: int, end_hour: int, start_minute: str = "ZERO", end_minute: str = "ZERO", bid_modifier: float | None = None):
    """Add an ad schedule criterion to a campaign.

    day_of_week uses MONDAY..SUNDAY. Minutes: ZERO, FIFTEEN, THIRTY, FORTY_FIVE.
    """
    day_of_week = day_of_week.upper().strip()
    start_minute, end_minute = start_minute.upper().strip(), end_minute.upper().strip()
    if day_of_week not in {"MONDAY","TUESDAY","WEDNESDAY","THURSDAY","FRIDAY","SATURDAY","SUNDAY"}:
        raise ValueError("Invalid day_of_week.")
    if not (0 <= start_hour <= 23 and 0 <= end_hour <= 24):
        raise ValueError("start_hour must be 0..23 and end_hour 0..24.")
    minute_values = {"ZERO","FIFTEEN","THIRTY","FORTY_FIVE"}
    if start_minute not in minute_values or end_minute not in minute_values:
        raise ValueError("Minutes must be ZERO, FIFTEEN, THIRTY, or FORTY_FIVE.")
    if bid_modifier is not None and bid_modifier <= 0:
        raise ValueError("bid_modifier must be greater than zero.")

    customer_id, campaign_id = clean_id(customer_id), clean_id(campaign_id)
    client = utils.get_googleads_client()
    service = client.get_service("CampaignCriterionService")
    campaign_service = client.get_service("CampaignService")
    op = client.get_type("CampaignCriterionOperation")
    criterion = op.create
    criterion.campaign = campaign_service.campaign_path(customer_id, campaign_id)
    schedule = criterion.ad_schedule
    schedule.day_of_week = getattr(client.enums.DayOfWeekEnum, day_of_week)
    schedule.start_hour = start_hour
    schedule.end_hour = end_hour
    schedule.start_minute = getattr(client.enums.MinuteOfHourEnum, start_minute)
    schedule.end_minute = getattr(client.enums.MinuteOfHourEnum, end_minute)
    if bid_modifier is not None:
        criterion.bid_modifier = float(bid_modifier)
    try:
        response = service.mutate_campaign_criteria(customer_id=customer_id, operations=[op])
        return {"resource_name": response.results[0].resource_name}
    except GoogleAdsException as ex:
        raise google_ads_error(ex)

@targeting_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def add_ad_group_user_list(customer_id: str | int, ad_group_id: str | int, user_list_id: str | int, bid_modifier: float | None = None, status: str = "ENABLED"):
    """Add an existing Google Ads user list/audience criterion to an ad group."""
    status = status.upper().strip()
    if status not in {"ENABLED","PAUSED"}:
        raise ValueError("status must be ENABLED or PAUSED.")
    if bid_modifier is not None and bid_modifier <= 0:
        raise ValueError("bid_modifier must be greater than zero.")
    customer_id, ad_group_id, user_list_id = map(clean_id, (customer_id, ad_group_id, user_list_id))
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupCriterionService")
    ad_group_service = client.get_service("AdGroupService")
    user_list_service = client.get_service("UserListService")
    op = client.get_type("AdGroupCriterionOperation")
    criterion = op.create
    criterion.ad_group = ad_group_service.ad_group_path(customer_id, ad_group_id)
    criterion.status = getattr(client.enums.AdGroupCriterionStatusEnum, status)
    criterion.user_list.user_list = user_list_service.user_list_path(customer_id, user_list_id)
    if bid_modifier is not None:
        criterion.bid_modifier = float(bid_modifier)
    try:
        response = service.mutate_ad_group_criteria(customer_id=customer_id, operations=[op])
        return {"resource_name": response.results[0].resource_name}
    except GoogleAdsException as ex:
        raise google_ads_error(ex)
