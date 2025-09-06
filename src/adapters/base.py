from __future__ import annotations

from typing import Iterable, Dict

from src.core.models import Discovered


class Adapter:
    def __init__(self, site_id: str, cfg: Dict, ctx: Dict):
        self.site_id = site_id
        self.cfg = cfg
        self.ctx = ctx  # contains http client, robots, scheduler, db, counters

    def discover(self) -> Iterable[Discovered]:
        raise NotImplementedError

