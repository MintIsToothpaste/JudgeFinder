from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from judgefinder.domain.entities import Notice

COMMITTEE_SEARCH_SUFFIX = "#judgefinder-committee-search"


@dataclass(frozen=True, slots=True)
class OriginCandidate:
    discovery_url: str
    origin_url: str
    discovered_date: date
    discovery_error: str = ""

    @property
    def from_committee_search(self) -> bool:
        return self.discovery_url.endswith(COMMITTEE_SEARCH_SUFFIX)


@dataclass(frozen=True, slots=True)
class OriginRoute:
    source_slug: str
    municipality: str
    canonical_url: str
    official_id: str
    identity_key: str


@dataclass(frozen=True, slots=True)
class OriginDetails:
    notice: Notice
    body_text: str
    attachment_text: str = ""


class OriginDiscovery(Protocol):
    label: str

    def discover(self, start: date, end: date) -> Iterable[OriginCandidate]: ...


class OriginReader(Protocol):
    def resolve(self, url: str) -> OriginRoute: ...

    def read(self, route: OriginRoute, *, committee_search: bool = False) -> OriginDetails: ...

    def identity(self, municipality: str, url: str) -> str | None: ...


@dataclass(frozen=True, slots=True)
class OriginRecord:
    id: int
    candidate: OriginCandidate
    status: str
    reason: str
    source_slug: str
    canonical_url: str
    official_id: str
    body_text: str
    attempts: int
    official_title: str
    published_date: date | None
    notice_id: int | None


class OriginStore(Protocol):
    def enqueue(self, candidate: OriginCandidate) -> int: ...

    def pending(self, start: date, end: date) -> list[OriginRecord]: ...

    def attempt(self, record_id: int) -> None: ...

    def finish(self, record_id: int, status: str, reason: str, *,
               route: OriginRoute | None = None, details: OriginDetails | None = None) -> None: ...

    def existing_notices(self, municipality: str) -> list[Notice]: ...

    def save_verified(self, record_id: int, route: OriginRoute, details: OriginDetails,
                      equivalent_urls: list[str]) -> bool: ...
