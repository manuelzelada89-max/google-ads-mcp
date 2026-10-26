"""Location, schedule, audience and bid-modifier tools."""

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
    mutate,
    raise_ads_error,
)


targeting_mcp = FastMCP("targeting")


def _minute_enum(c, minute: int):
    mapping = {
        0: "ZERO",
        15: "FIFTEEN",
        30: "THIRTY",
        45: "FORTY_FIVE",
    }
    if int(minute) not in mapping:
        raise ToolError("Minutes must be one of 0, 15, 30, 45.")
    return getattr(c.enums.MinuteOfHourEnum, mapping[int(minute)])


@targeting_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def add_location_target(
    customer_id: str | int,
    campaign_id: str | int,
    geo_target_constant_id: str | int,
    exclude: bool = False,
    bid_modifier: float | None = None,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Add or exclude a geographic target from a campaign.

    geo_target_constant_id is the Google Ads geo target constant ID.
    bid_modifier is optional and only works for compatible bidding strategies.
    """
    customer_id = clean_id(customer_id)
    campaign_id = clean_id(campaign_id)
    geo_target_constant_id = clean_id(geo_target_constant_id)
    c = client(login_customer_id)
    service = c.get_service("CampaignCriterionService")
    campaign_service = c.get_service("CampaignService")
    geo_service = c.get_service("GeoTargetConstantService")
    op = c.get_type("CampaignCriterionOperation")
    criterion = op.create
    criterion.campaign = campaign_service.campaign_path(
        customer_id, campaign_id
    )
    criterion.location.geo_target_constant = (
        geo_service.geo_target_constant_path(geo_target_constant_id)
    )
    criterion.negative = bool(exclude)
    if bid_modifier is not None:
        if exclude:
            raise ToolError("Excluded locations cannot have a bid modifier.")
        if float(bid_modifier) <= 0:
            raise ToolError("bid_modifier must be greater than 0.")
        criterion.bid_modifier = float(bid_modifier)
    response = mutate(
        service, "mutate_campaign_criteria", customer_id, [op]
    )
    return {
        "resource_name": first_resource_name(response),
        "geo_target_constant_id": geo_target_constant_id,
        "excluded": bool(exclude),
        "bid_modifier": bid_modifier,
    }


@targeting_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def add_ad_schedule(
    customer_id: str | int,
    campaign_id: str | int,
    day_of_week: str,
    start_hour: int,
    start_minute: int,
    end_hour: int,
    end_minute: int,
    bid_modifier: float | None = None,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Add a campaign ad schedule block.

    Hours use 0-24. Minutes must be 0, 15, 30 or 45. A bid modifier is
    optional and is only effective on compatible bidding strategies.
    """
    if not 0 <= int(start_hour) <= 23:
        raise ToolError("start_hour must be between 0 and 23.")
    if not 0 <= int(end_hour) <= 24:
        raise ToolError("end_hour must be between 0 and 24.")
    if (int(end_hour), int(end_minute)) <= (
        int(start_hour),
        int(start_minute),
    ):
        raise ToolError("Schedule end must be after schedule start.")

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
    schedule = criterion.ad_schedule
    schedule.day_of_week = enum_value(
        c.enums.DayOfWeekEnum,
        day_of_week,
        [
            "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY",
            "FRIDAY", "SATURDAY", "SUNDAY"
        ],
    )
    schedule.start_hour = int(start_hour)
    schedule.start_minute = _minute_enum(c, start_minute)
    schedule.end_hour = int(end_hour)
    schedule.end_minute = _minute_enum(c, end_minute)
    if bid_modifier is not None:
        if float(bid_modifier) <= 0:
            raise ToolError("bid_modifier must be greater than 0.")
        criterion.bid_modifier = float(bid_modifier)
    response = mutate(
        service, "mutate_campaign_criteria", customer_id, [op]
    )
    return {
        "resource_name": first_resource_name(response),
        "day_of_week": day_of_week.upper(),
        "start": f"{int(start_hour):02d}:{int(start_minute):02d}",
        "end": f"{int(end_hour):02d}:{int(end_minute):02d}",
        "bid_modifier": bid_modifier,
    }


@targeting_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def add_device_bid_modifier(
    customer_id: str | int,
    campaign_id: str | int,
    device: str,
    bid_modifier: float,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Add a campaign device criterion with a bid modifier.

    Supported device values: MOBILE, DESKTOP, TABLET. The campaign bidding
    strategy must support bid modifiers.
    """
    if float(bid_modifier) <= 0:
        raise ToolError("bid_modifier must be greater than 0.")
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
    criterion.device.type_ = enum_value(
        c.enums.DeviceEnum,
        device,
        ["MOBILE", "DESKTOP", "TABLET"],
    )
    criterion.bid_modifier = float(bid_modifier)
    response = mutate(
        service, "mutate_campaign_criteria", customer_id, [op]
    )
    return {
        "resource_name": first_resource_name(response),
        "device": device.upper(),
        "bid_modifier": float(bid_modifier),
    }


@targeting_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def update_campaign_criterion_bid_modifier(
    customer_id: str | int,
    campaign_id: str | int,
    criterion_id: str | int,
    bid_modifier: float,
    confirm_large_increase: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Update a campaign criterion bid modifier.

    Values above 1.20 require confirm_large_increase=True as a safety guardrail.
    Useful for compatible location, schedule, device or audience criteria.
    """
    if float(bid_modifier) <= 0:
        raise ToolError("bid_modifier must be greater than 0.")
    if float(bid_modifier) > 1.20 and not confirm_large_increase:
        raise ToolError(
            "Bid modifier above +20% requires confirm_large_increase=True."
        )
    customer_id = clean_id(customer_id)
    campaign_id = clean_id(campaign_id)
    criterion_id = clean_id(criterion_id)
    c = client(login_customer_id)
    service = c.get_service("CampaignCriterionService")
    op = c.get_type("CampaignCriterionOperation")
    criterion = op.update
    criterion.resource_name = service.campaign_criterion_path(
        customer_id, campaign_id, criterion_id
    )
    criterion.bid_modifier = float(bid_modifier)
    apply_mask(c, op, criterion)
    response = mutate(
        service, "mutate_campaign_criteria", customer_id, [op]
    )
    return {
        "resource_name": first_resource_name(response),
        "bid_modifier": float(bid_modifier),
    }


@targeting_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True)
)
def remove_campaign_criterion(
    customer_id: str | int,
    campaign_id: str | int,
    criterion_id: str | int,
    confirm_remove: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Remove a campaign criterion such as a location or ad schedule."""
    if not confirm_remove:
        raise ToolError("Removing a criterion requires confirm_remove=True.")
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


@targeting_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def add_user_list_audience_to_ad_group(
    customer_id: str | int,
    ad_group_id: str | int,
    user_list_id: str | int,
    bid_modifier: float | None = None,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Attach an existing Google Ads user-list audience to an ad group."""
    customer_id = clean_id(customer_id)
    ad_group_id = clean_id(ad_group_id)
    user_list_id = clean_id(user_list_id)
    c = client(login_customer_id)
    service = c.get_service("AdGroupCriterionService")
    ad_group_service = c.get_service("AdGroupService")
    user_list_service = c.get_service("UserListService")
    op = c.get_type("AdGroupCriterionOperation")
    criterion = op.create
    criterion.ad_group = ad_group_service.ad_group_path(
        customer_id, ad_group_id
    )
    criterion.user_list.user_list = user_list_service.user_list_path(
        customer_id, user_list_id
    )
    if bid_modifier is not None:
        if float(bid_modifier) <= 0:
            raise ToolError("bid_modifier must be greater than 0.")
        criterion.bid_modifier = float(bid_modifier)
    response = mutate(
        service, "mutate_ad_group_criteria", customer_id, [op]
    )
    return {
        "resource_name": first_resource_name(response),
        "user_list_id": user_list_id,
        "bid_modifier": bid_modifier,
    }


@targeting_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def update_ad_group_audience_bid_modifier(
    customer_id: str | int,
    ad_group_id: str | int,
    criterion_id: str | int,
    bid_modifier: float,
    confirm_large_increase: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Update an ad-group audience criterion bid modifier."""
    if float(bid_modifier) <= 0:
        raise ToolError("bid_modifier must be greater than 0.")
    if float(bid_modifier) > 1.20 and not confirm_large_increase:
        raise ToolError(
            "Bid modifier above +20% requires confirm_large_increase=True."
        )
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
    criterion.bid_modifier = float(bid_modifier)
    apply_mask(c, op, criterion)
    response = mutate(
        service, "mutate_ad_group_criteria", customer_id, [op]
    )
    return {
        "resource_name": first_resource_name(response),
        "bid_modifier": float(bid_modifier),
    }


@targeting_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def set_ad_group_audience_mode(
    customer_id: str | int,
    ad_group_id: str | int,
    mode: str,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Set audience mode for an ad group to OBSERVATION or TARGETING.

    Existing non-audience targeting restrictions are preserved.
    """
    mode = str(mode).strip().upper()
    if mode not in ["OBSERVATION", "TARGETING"]:
        raise ToolError("mode must be OBSERVATION or TARGETING.")

    customer_id = clean_id(customer_id)
    ad_group_id = clean_id(ad_group_id)
    c = client(login_customer_id)
    ga_service = c.get_service("GoogleAdsService")
    query = (
        "SELECT ad_group.targeting_setting.target_restrictions "
        "FROM ad_group "
        f"WHERE ad_group.id = {ad_group_id} LIMIT 1"
    )
    try:
        rows = list(ga_service.search(customer_id=customer_id, query=query))
    except GoogleAdsException as ex:
        raise_ads_error(ex)
    if not rows:
        raise ToolError("Ad group not found.")

    setting = c.get_type("TargetingSetting")
    audience_found = False
    for restriction in rows[0].ad_group.targeting_setting.target_restrictions:
        new_item = setting.target_restrictions.add()
        new_item.targeting_dimension = restriction.targeting_dimension
        if (
            restriction.targeting_dimension
            == c.enums.TargetingDimensionEnum.AUDIENCE
        ):
            new_item.bid_only = mode == "OBSERVATION"
            audience_found = True
        else:
            new_item.bid_only = restriction.bid_only

    if not audience_found:
        new_item = setting.target_restrictions.add()
        new_item.targeting_dimension = c.enums.TargetingDimensionEnum.AUDIENCE
        new_item.bid_only = mode == "OBSERVATION"

    service = c.get_service("AdGroupService")
    op = c.get_type("AdGroupOperation")
    ad_group = op.update
    ad_group.resource_name = service.ad_group_path(
        customer_id, ad_group_id
    )
    ad_group.targeting_setting.target_restrictions.extend(
        setting.target_restrictions
    )
    apply_mask(c, op, ad_group)
    response = mutate(service, "mutate_ad_groups", customer_id, [op])
    return {
        "resource_name": first_resource_name(response),
        "audience_mode": mode,
    }


@targeting_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def set_campaign_geo_targeting_mode(
    customer_id: str | int,
    campaign_id: str | int,
    positive_mode: str = "PRESENCE",
    negative_mode: str = "PRESENCE",
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Set campaign location presence/interest behavior.

    positive_mode: PRESENCE, PRESENCE_OR_INTEREST, or SEARCH_INTEREST.
    negative_mode: PRESENCE or PRESENCE_OR_INTEREST.
    """
    customer_id = clean_id(customer_id)
    campaign_id = clean_id(campaign_id)
    c = client(login_customer_id)
    service = c.get_service("CampaignService")
    op = c.get_type("CampaignOperation")
    campaign = op.update
    campaign.resource_name = service.campaign_path(
        customer_id, campaign_id
    )
    campaign.geo_target_type_setting.positive_geo_target_type = enum_value(
        c.enums.PositiveGeoTargetTypeEnum,
        positive_mode,
        ["PRESENCE", "PRESENCE_OR_INTEREST", "SEARCH_INTEREST"],
    )
    campaign.geo_target_type_setting.negative_geo_target_type = enum_value(
        c.enums.NegativeGeoTargetTypeEnum,
        negative_mode,
        ["PRESENCE", "PRESENCE_OR_INTEREST"],
    )
    apply_mask(c, op, campaign)
    response = mutate(service, "mutate_campaigns", customer_id, [op])
    return {
        "resource_name": first_resource_name(response),
        "positive_mode": positive_mode.upper(),
        "negative_mode": negative_mode.upper(),
    }


@targeting_mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def add_demographic_criterion(
    customer_id: str | int,
    ad_group_id: str | int,
    dimension: str,
    value: str,
    exclude: bool = False,
    bid_modifier: float | None = None,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Add age, gender, or household-income targeting to an ad group.

    dimension must be AGE_RANGE, GENDER, or INCOME_RANGE.

    AGE_RANGE values: AGE_RANGE_18_24, AGE_RANGE_25_34,
    AGE_RANGE_35_44, AGE_RANGE_45_54, AGE_RANGE_55_64,
    AGE_RANGE_65_UP, AGE_RANGE_UNDETERMINED.

    GENDER values: MALE, FEMALE, UNDETERMINED.

    INCOME_RANGE values: INCOME_RANGE_0_50, INCOME_RANGE_50_60,
    INCOME_RANGE_60_70, INCOME_RANGE_70_80, INCOME_RANGE_80_90,
    INCOME_RANGE_90_UP, INCOME_RANGE_UNDETERMINED.
    """
    customer_id = clean_id(customer_id)
    ad_group_id = clean_id(ad_group_id)
    dimension = str(dimension).strip().upper()
    value = str(value).strip().upper()
    c = client(login_customer_id)
    service = c.get_service("AdGroupCriterionService")
    ad_group_service = c.get_service("AdGroupService")
    op = c.get_type("AdGroupCriterionOperation")
    criterion = op.create
    criterion.ad_group = ad_group_service.ad_group_path(
        customer_id, ad_group_id
    )
    criterion.negative = bool(exclude)

    if dimension == "AGE_RANGE":
        allowed = [
            "AGE_RANGE_18_24",
            "AGE_RANGE_25_34",
            "AGE_RANGE_35_44",
            "AGE_RANGE_45_54",
            "AGE_RANGE_55_64",
            "AGE_RANGE_65_UP",
            "AGE_RANGE_UNDETERMINED",
        ]
        criterion.age_range.type_ = enum_value(
            c.enums.AgeRangeTypeEnum, value, allowed
        )
    elif dimension == "GENDER":
        criterion.gender.type_ = enum_value(
            c.enums.GenderTypeEnum,
            value,
            ["MALE", "FEMALE", "UNDETERMINED"],
        )
    elif dimension == "INCOME_RANGE":
        allowed = [
            "INCOME_RANGE_0_50",
            "INCOME_RANGE_50_60",
            "INCOME_RANGE_60_70",
            "INCOME_RANGE_70_80",
            "INCOME_RANGE_80_90",
            "INCOME_RANGE_90_UP",
            "INCOME_RANGE_UNDETERMINED",
        ]
        criterion.income_range.type_ = enum_value(
            c.enums.IncomeRangeTypeEnum, value, allowed
        )
    else:
        raise ToolError(
            "dimension must be AGE_RANGE, GENDER, or INCOME_RANGE."
        )

    if bid_modifier is not None:
        if float(bid_modifier) <= 0:
            raise ToolError("bid_modifier must be greater than 0.")
        criterion.bid_modifier = float(bid_modifier)

    response = mutate(
        service, "mutate_ad_group_criteria", customer_id, [op]
    )
    return {
        "resource_name": first_resource_name(response),
        "dimension": dimension,
        "value": value,
        "excluded": bool(exclude),
        "bid_modifier": bid_modifier,
    }


@targeting_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True)
)
def remove_ad_group_criterion(
    customer_id: str | int,
    ad_group_id: str | int,
    criterion_id: str | int,
    confirm_remove: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Remove a non-keyword ad-group criterion such as an audience or demographic."""
    if not confirm_remove:
        raise ToolError("Removing a criterion requires confirm_remove=True.")
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
