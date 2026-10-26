from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse


@dataclass(slots=True)
class HtmlProfile:
    container_selector: str
    row_selector: str
    date_selector: str = ""
    link_selector: str = "a[href]"
    link_attribute: str = "href"
    title_selector: str = ""
    detail_date_selector: str = ""
    detail_title_selector: str = ""
    id_pattern: str = ""
    detail_url_template: str = ""
    search_param: str = ""
    page_param: str = "pageIndex"
    request_method: str = "GET"
    request_encoding: str = "utf-8"
    page_number_selector: str = ""
    offset_param: str = ""
    page_size: int = 10
    title_exclude_selector: str = ""
    id_format: str = "numeric"
    detail_body_selector: str = ""
    total_count_selector: str = ""
    total_count_pattern: str = ""
    detail_origin: str = ""

    def __post_init__(self) -> None:
        if self.id_format not in {"numeric", "hex32"}:
            raise ValueError("html_profile.id_format must be numeric or hex32")
        if self.id_format != "numeric" and not self.id_pattern:
            raise ValueError("html_profile.id_format requires an identifier pattern")
        if not self.date_selector and not self.detail_date_selector:
            raise ValueError("html_profile requires a registration-date selector")
        if self.request_method not in {"GET", "POST"}:
            raise ValueError("html_profile.request_method must be GET or POST")
        if self.request_encoding not in {"utf-8", "euc-kr", "cp949"}:
            raise ValueError("html_profile.request_encoding must be utf-8, euc-kr or cp949")
        data_identifier = bool(re.fullmatch(
            r"data-[a-z][a-z0-9]*(?:-[a-z0-9]+)*", self.link_attribute,
        ))
        if self.link_attribute not in {"href", "onclick", "data-action"} and not data_identifier:
            raise ValueError(
                "html_profile.link_attribute must be href, onclick or a data-* attribute",
            )
        if (self.link_attribute == "onclick" or (
            data_identifier and self.link_attribute != "data-action"
        )) and not self.id_pattern:
            raise ValueError("html_profile identifier attributes require an identifier pattern")
        if type(self.page_size) is not int or not 1 <= self.page_size <= 1000:
            raise ValueError("html_profile.page_size must be an integer between 1 and 1000")
        if self.offset_param and not self.page_param:
            raise ValueError("html_profile offset pagination requires a page parameter")
        if self.offset_param and self.offset_param == self.page_param:
            raise ValueError("html_profile offset and page parameters must differ")
        if bool(self.total_count_selector) != bool(self.total_count_pattern):
            raise ValueError("html_profile total-count selector and pattern must be paired")
        if self.total_count_selector:
            if not self.page_number_selector or not self.page_param:
                raise ValueError("html_profile total count requires page-number validation")
            if re.compile(self.total_count_pattern).groups != 1:
                raise ValueError("html_profile.total_count_pattern requires one capture group")
        if bool(self.id_pattern) != bool(self.detail_url_template):
            raise ValueError("html_profile requires both id_pattern and detail_url_template")
        if self.id_pattern:
            if re.compile(self.id_pattern).groups != 1:
                raise ValueError("html_profile.id_pattern must have exactly one capture group")
            if self.detail_url_template.count("{id}") != 1:
                raise ValueError("html_profile.detail_url_template must contain {id} once")
            if any(char in self.detail_url_template.replace("{id}", "") for char in "{}"):
                raise ValueError("html_profile.detail_url_template supports only {id}")
        if self.detail_origin:
            origin = urlparse(self.detail_origin)
            template = urlparse(self.detail_url_template)
            if (
                origin.scheme != "https" or not origin.hostname
                or origin.netloc != origin.hostname or origin.path
                or origin.params or origin.query or origin.fragment
                or not self.id_pattern
                or template.scheme != origin.scheme or template.netloc != origin.netloc
                or template.username or template.password
            ):
                raise ValueError(
                    "html_profile.detail_origin requires an HTTPS origin and matching ID template",
                )


@dataclass(slots=True)
class JsonProfile:
    rows_path: str
    title_key: str
    date_key: str
    id_key: str
    detail_url_template: str
    status_path: str = ""
    success_value: str = ""
    total_path: str = ""
    page_path: str = ""
    search_param: str = ""
    page_param: str = "pageIndex"
    offset_param: str = ""
    offset_base: int = 1
    page_size: int = 10
    request_method: str = "GET"
    request_encoding: str = "utf-8"

    def __post_init__(self) -> None:
        for path in (self.rows_path, self.status_path, self.total_path, self.page_path):
            if path and any(not part.strip() for part in path.split(".")):
                raise ValueError("json_profile paths require nonempty object keys")
        if not all((self.rows_path, self.title_key, self.date_key, self.id_key)):
            raise ValueError("json_profile requires explicit row fields")
        if bool(self.status_path) != bool(self.success_value):
            raise ValueError("json_profile status path and success value must be paired")
        if not self.status_path and not self.total_path:
            raise ValueError("json_profile requires a success status or validated total")
        if type(self.offset_base) is not int or self.offset_base not in {0, 1}:
            raise ValueError("json_profile.offset_base must be 0 or 1")
        if self.offset_param and self.offset_param == self.page_param:
            raise ValueError("json_profile offset and page parameters must differ")
        if self.detail_url_template.count("{id}") != 1 or any(
            char in self.detail_url_template.replace("{id}", "") for char in "{}"
        ):
            raise ValueError("json_profile detail URL requires exactly one {id}")
        if type(self.page_size) is not int or not 1 <= self.page_size <= 1000:
            raise ValueError("json_profile.page_size must be an integer between 1 and 1000")
        if self.offset_param and not self.page_param:
            raise ValueError("json_profile offset pagination requires a page parameter")
        if self.request_method not in {"GET", "POST"}:
            raise ValueError("json_profile.request_method must be GET or POST")
        if self.request_encoding not in {"utf-8", "euc-kr", "cp949"}:
            raise ValueError("json_profile.request_encoding must be utf-8, euc-kr or cp949")


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
    verify_tls: bool = True

    @classmethod
    def from_access_profile(cls, access_profile: AccessProfile) -> RequestStrategy:
        if access_profile is AccessProfile.SESSION_REQUIRED:
            return cls(session=True, referer=True, retries=3)
        if access_profile is AccessProfile.REFERER_REQUIRED:
            return cls(session=False, referer=True, retries=3)
        if access_profile is AccessProfile.THROTTLED:
            return cls(session=False, referer=False, retries=5, throttle_seconds=0.3)
        return cls()
