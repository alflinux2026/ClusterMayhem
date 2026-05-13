from dataclasses import dataclass
import time


@dataclass
class Lease:
    owner_id: str
    ttl_seconds: float
    granted_at: float

    def expires_at(self) -> float:
        return self.granted_at + self.ttl_seconds

    def is_valid(self, now: float | None = None) -> bool:
        now = now or time.time()
        return now < self.expires_at()

    def renew(self):
        self.granted_at = time.time()