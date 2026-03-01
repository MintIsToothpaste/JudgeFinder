from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EngineType(str, Enum):
    SAEOL_GOSI = "saeol_gosi"
    EMINWON_OFR = "eminwon_ofr"
    CITYNET_SAPGOSI = "citynet_sapgosi"
    INTEGRATED_SEARCH_GOSI = "integrated_search_gosi"
    GENERIC_EGOV_BBS = "generic_egov_bbs"
    JSON_LIST_API = "json_list_api"
    UNKNOWN_ENGINE = "unknown_engine"


class AccessProfile(str, Enum):
    OPEN = "open"
    SESSION_REQUIRED = "session_required"
    REFERER_REQUIRED = "referer_required"
    JS_RENDERED = "js_rendered"
    BLOCKED_WAF = "blocked_waf"
    THROTTLED = "throttled"
    UNKNOWN_ACCESS = "unknown_access"


class FallbackStrategy(str, Enum):
    NONE = "none"
    API_BACKTRACK = "api_backtrack"
    MANUAL_REVIEW = "manual_review"


@dataclass(slots=True)
class RequestStrategy:
    session: bool = False
    referer: bool = False
    retries: int = 3
    timeout_seconds: float = 10.0
    throttle_seconds: float = 0.0

    @classmethod
    def from_access_profile(cls, access_profile: AccessProfile) -> RequestStrategy:
        if access_profile is AccessProfile.SESSION_REQUIRED:
            return cls(session=True, referer=True, retries=3)
        if access_profile is AccessProfile.REFERER_REQUIRED:
            return cls(session=False, referer=True, retries=3)
        if access_profile is AccessProfile.THROTTLED:
            return cls(session=False, referer=False, retries=5, throttle_seconds=0.3)
        return cls()
