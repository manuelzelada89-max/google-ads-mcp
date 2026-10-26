"""Google Keyword Planner read-only tools."""

from __future__ import annotations

from typing import Any, Dict, List

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException
from mcp.types import ToolAnnotations

from ads_mcp.tools._mutation_helpers import (
    clean_id,
    client,
    enum_value,
    money_to_micros,
    raise_ads_error,
)


keyword_planner_mcp = FastMCP("keyword_planner")


def _resource_paths(c, geo_target_constant_ids, language_constant_id):
    google_ads_service = c.get_service("GoogleAdsService")
    geo_paths = [
        google_ads_service.geo_target_constant_path(clean_id(value))
        for value in (geo_target_constant_ids or [])
    ]
    language_path = None
    if language_constant_id is not None:
        language_path = google_ads_service.language_constant_path(
            clean_id(language_constant_id)
        )
    return geo_paths, language_path


def _network(c, network: str):
    return enum_value(
        c.enums.KeywordPlanNetworkEnum,
        network,
        ["GOOGLE_SEARCH", "GOOGLE_SEARCH_AND_PARTNERS"],
    )


def _match_type(c, match_type: str):
    return enum_value(
        c.enums.KeywordMatchTypeEnum,
        match_type,
        ["BROAD", "PHRASE", "EXACT"],
    )


def _enum_name(value: Any) -> str:
    name = getattr(value, "name", None)
    return str(name if name is not None else value)


def _monthly_volumes(metrics: Any) -> List[Dict[str, Any]]:
    result = []
    for item in metrics.monthly_search_volumes:
        result.append(
            {
                "year": int(item.year),
                "month": _enum_name(item.month),
                "monthly_searches": int(item.monthly_searches),
            }
        )
    return result


def _historical_metrics(metrics: Any) -> Dict[str, Any]:
    low_micros = int(metrics.low_top_of_page_bid_micros)
    high_micros = int(metrics.high_top_of_page_bid_micros)
    average_cpc_micros = int(getattr(metrics, "average_cpc_micros", 0))
    return {
        "avg_monthly_searches": int(metrics.avg_monthly_searches),
        "competition": _enum_name(metrics.competition),
        "competition_index": int(metrics.competition_index),
        "low_top_of_page_bid_micros": low_micros,
        "low_top_of_page_bid": low_micros / 1_000_000,
        "high_top_of_page_bid_micros": high_micros,
        "high_top_of_page_bid": high_micros / 1_000_000,
        "average_cpc_micros": average_cpc_micros,
        "average_cpc": average_cpc_micros / 1_000_000,
        "monthly_search_volumes": _monthly_volumes(metrics),
    }


@keyword_planner_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def generate_keyword_ideas(
    customer_id: str | int,
    seed_keywords: List[str] | None = None,
    seed_url: str | None = None,
    geo_target_constant_ids: List[str | int] | None = None,
    language_constant_id: str | int | None = None,
    network: str = "GOOGLE_SEARCH",
    include_adult_keywords: bool = False,
    max_results: int = 500,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Generate Keyword Planner ideas from keywords, a URL, or both.

    seed_keywords accepts 1-20 keywords. geo_target_constant_ids are Google Ads
    geo target constant IDs (for example 2840 for the United States).
    language_constant_id is a Google Ads language constant ID (for example 1000
    for English). Results include Keyword Planner historical metrics.
    """
    customer_id = clean_id(customer_id)
    keywords = [str(k).strip() for k in (seed_keywords or []) if str(k).strip()]
    url = str(seed_url).strip() if seed_url else ""

    if not keywords and not url:
        raise ToolError("Provide seed_keywords, seed_url, or both.")
    if len(keywords) > 20:
        raise ToolError("Keyword Planner accepts at most 20 seed keywords.")
    if max_results < 1 or max_results > 10_000:
        raise ToolError("max_results must be between 1 and 10000.")

    c = client(login_customer_id)
    service = c.get_service("KeywordPlanIdeaService")
    request = c.get_type("GenerateKeywordIdeasRequest")
    request.customer_id = customer_id
    request.keyword_plan_network = _network(c, network)
    request.include_adult_keywords = bool(include_adult_keywords)

    geo_paths, language_path = _resource_paths(
        c, geo_target_constant_ids, language_constant_id
    )
    request.geo_target_constants.extend(geo_paths)
    if language_path:
        request.language = language_path

    if keywords and url:
        request.keyword_and_url_seed.url = url
        request.keyword_and_url_seed.keywords.extend(keywords)
    elif keywords:
        request.keyword_seed.keywords.extend(keywords)
    else:
        request.url_seed.url = url

    try:
        response = service.generate_keyword_ideas(request=request)
        ideas = []
        for idea in response:
            ideas.append(
                {
                    "text": idea.text,
                    "close_variants": list(idea.close_variants),
                    "metrics": _historical_metrics(idea.keyword_idea_metrics),
                }
            )
            if len(ideas) >= max_results:
                break
    except GoogleAdsException as ex:
        raise_ads_error(ex)

    return {
        "customer_id": customer_id,
        "seed_keywords": keywords,
        "seed_url": url or None,
        "network": str(network).upper(),
        "geo_target_constant_ids": [
            clean_id(value) for value in (geo_target_constant_ids or [])
        ],
        "language_constant_id": (
            clean_id(language_constant_id)
            if language_constant_id is not None
            else None
        ),
        "result_count": len(ideas),
        "ideas": ideas,
    }


@keyword_planner_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_historical_metrics(
    customer_id: str | int,
    keywords: List[str],
    geo_target_constant_ids: List[str | int] | None = None,
    language_constant_id: str | int | None = None,
    network: str = "GOOGLE_SEARCH",
    include_average_cpc: bool = True,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Get Keyword Planner historical metrics for an existing keyword list.

    Returns average monthly searches, monthly search-volume history, competition,
    competition index, and low/high top-of-page bid estimates. Google may merge
    close variants, so the response can contain fewer rows than the input list.
    """
    customer_id = clean_id(customer_id)
    cleaned_keywords = [str(k).strip() for k in keywords if str(k).strip()]
    if not cleaned_keywords:
        raise ToolError("Provide at least one keyword.")
    if len(cleaned_keywords) > 10_000:
        raise ToolError("At most 10000 keywords are allowed per request.")

    c = client(login_customer_id)
    service = c.get_service("KeywordPlanIdeaService")
    request = c.get_type("GenerateKeywordHistoricalMetricsRequest")
    request.customer_id = customer_id
    request.keywords.extend(cleaned_keywords)
    request.keyword_plan_network = _network(c, network)

    geo_paths, language_path = _resource_paths(
        c, geo_target_constant_ids, language_constant_id
    )
    request.geo_target_constants.extend(geo_paths)
    if language_path:
        request.language = language_path
    request.historical_metrics_options.include_average_cpc = bool(
        include_average_cpc
    )

    try:
        response = service.generate_keyword_historical_metrics(request=request)
    except GoogleAdsException as ex:
        raise_ads_error(ex)

    rows = []
    for item in response.results:
        rows.append(
            {
                "text": item.text,
                "close_variants": list(item.close_variants),
                "metrics": _historical_metrics(item.keyword_metrics),
            }
        )

    return {
        "customer_id": customer_id,
        "input_keyword_count": len(cleaned_keywords),
        "result_count": len(rows),
        "network": str(network).upper(),
        "results": rows,
    }


@keyword_planner_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def generate_forecast(
    customer_id: str | int,
    keywords: List[str],
    geo_target_constant_ids: List[str | int] | None = None,
    language_constant_ids: List[str | int] | None = None,
    match_type: str = "BROAD",
    bidding_strategy: str = "MANUAL_CPC",
    daily_budget: float = 50.0,
    max_cpc_bid: float = 2.0,
    forecast_start_date: str | None = None,
    forecast_end_date: str | None = None,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Generate Keyword Planner forecast metrics for proposed keywords.

    Supported bidding strategies are MANUAL_CPC, MAXIMIZE_CLICKS, and
    MAXIMIZE_CONVERSIONS. Dates are YYYY-MM-DD and must either both be supplied
    or both omitted. When omitted, Google uses its default forecast period.

    In Google Ads API v24+, forecast output depends on bidding strategy:
    MANUAL_CPC/MAXIMIZE_CLICKS return clicks and average CPC; MAXIMIZE_CONVERSIONS
    returns conversions and average CPA. Cost is returned for all strategies.
    """
    customer_id = clean_id(customer_id)
    cleaned_keywords = [str(k).strip() for k in keywords if str(k).strip()]
    if not cleaned_keywords:
        raise ToolError("Provide at least one keyword.")
    if len(cleaned_keywords) > 10_000:
        raise ToolError("At most 10000 keywords are allowed per request.")
    if (forecast_start_date is None) != (forecast_end_date is None):
        raise ToolError(
            "forecast_start_date and forecast_end_date must be supplied together."
        )

    c = client(login_customer_id)
    strategy = str(bidding_strategy).strip().upper()
    allowed_strategies = [
        "MANUAL_CPC",
        "MAXIMIZE_CLICKS",
        "MAXIMIZE_CONVERSIONS",
    ]
    if strategy not in allowed_strategies:
        raise ToolError(
            "bidding_strategy must be MANUAL_CPC, MAXIMIZE_CLICKS, "
            "or MAXIMIZE_CONVERSIONS."
        )

    service = c.get_service("KeywordPlanIdeaService")
    google_ads_service = c.get_service("GoogleAdsService")
    request = c.get_type("GenerateKeywordForecastMetricsRequest")
    request.customer_id = customer_id

    campaign = c.get_type("CampaignToForecast")
    daily_budget_micros = money_to_micros(daily_budget)
    max_cpc_micros = money_to_micros(max_cpc_bid)

    if strategy == "MANUAL_CPC":
        campaign.bidding_strategy.manual_cpc_bidding_strategy.daily_budget_micros = (
            daily_budget_micros
        )
        campaign.bidding_strategy.manual_cpc_bidding_strategy.max_cpc_bid_micros = (
            max_cpc_micros
        )
    elif strategy == "MAXIMIZE_CLICKS":
        campaign.bidding_strategy.maximize_clicks_bidding_strategy.daily_target_spend_micros = (
            daily_budget_micros
        )
        campaign.bidding_strategy.maximize_clicks_bidding_strategy.max_cpc_bid_ceiling_micros = (
            max_cpc_micros
        )
    else:
        campaign.bidding_strategy.maximize_conversions_bidding_strategy.daily_target_spend_micros = (
            daily_budget_micros
        )

    for geo_id in geo_target_constant_ids or []:
        campaign.geo_target_constants.append(
            google_ads_service.geo_target_constant_path(clean_id(geo_id))
        )
    for language_id in language_constant_ids or []:
        campaign.language_constants.append(
            google_ads_service.language_constant_path(clean_id(language_id))
        )

    forecast_ad_group = c.get_type("ForecastAdGroup")
    keyword_match_type = _match_type(c, match_type)
    for keyword_text in cleaned_keywords:
        keyword_info = c.get_type("KeywordInfo")
        keyword_info.text = keyword_text
        keyword_info.match_type = keyword_match_type
        forecast_ad_group.keywords.append(keyword_info)
    campaign.ad_groups.append(forecast_ad_group)
    request.campaign = campaign

    if forecast_start_date and forecast_end_date:
        request.forecast_period.start_date = forecast_start_date
        request.forecast_period.end_date = forecast_end_date

    try:
        response = service.generate_keyword_forecast_metrics(request=request)
    except GoogleAdsException as ex:
        raise_ads_error(ex)

    metrics = response.campaign_forecast_metrics
    cost_micros = int(getattr(metrics, "cost_micros", 0))
    average_cpc_micros = int(getattr(metrics, "average_cpc_micros", 0))
    average_cpa_micros = int(getattr(metrics, "average_cpa_micros", 0))

    return {
        "customer_id": customer_id,
        "keyword_count": len(cleaned_keywords),
        "match_type": str(match_type).upper(),
        "bidding_strategy": strategy,
        "daily_budget": float(daily_budget),
        "max_cpc_bid": (
            float(max_cpc_bid)
            if strategy in ["MANUAL_CPC", "MAXIMIZE_CLICKS"]
            else None
        ),
        "forecast_start_date": forecast_start_date,
        "forecast_end_date": forecast_end_date,
        "metrics": {
            "clicks": float(getattr(metrics, "clicks", 0.0)),
            "cost_micros": cost_micros,
            "cost": cost_micros / 1_000_000,
            "average_cpc_micros": average_cpc_micros,
            "average_cpc": average_cpc_micros / 1_000_000,
            "conversions": float(getattr(metrics, "conversions", 0.0)),
            "average_cpa_micros": average_cpa_micros,
            "average_cpa": average_cpa_micros / 1_000_000,
        },
    }
