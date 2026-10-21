from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException
import ads_mcp.utils as utils

def clean_id(value):
    return utils.clean_customer_id(value)

def money_to_micros(value):
    return int(round(float(value) * 1_000_000))

def google_ads_error(ex: GoogleAdsException) -> ToolError:
    lines = []
    for error in ex.failure.errors:
        location = ""
        if error.location:
            fields = [e.field_name for e in error.location.field_path_elements]
            if fields:
                location = f" ({'.'.join(fields)})"
        lines.append(f"{error.message}{location}")
    return ToolError(f"Request ID: {ex.request_id}\n" + "\n".join(lines))

def resource_id(resource_name: str) -> str:
    return str(resource_name).split("/")[-1]
