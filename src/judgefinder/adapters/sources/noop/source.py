from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from judgefinder.domain.entities import Notice

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class NoopSource:
    slug: str
    municipality: str
    reason: str

    def fetch(self, target_date: date) -> list[Notice]:
        LOGGER.warning(
            "Skipping source '%s' (%s) for %s: %s",
            self.slug,
            self.municipality,
            target_date.isoformat(),
            self.reason,
        )
        return []
