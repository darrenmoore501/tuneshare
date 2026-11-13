from dataclasses import dataclass
from datetime import datetime
import math


@dataclass(frozen=True)
class TideData:
    phase: float
    demo: bool = True


class DemoTides:
    def get(self, now: datetime) -> TideData:
        return TideData(2 * math.pi * now.timestamp() / (12.42 * 3600))
