"""
Shared message types and data structures for the zonal architecture simulator.
"""
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional
from datetime import datetime
import time


@dataclass
class ECUFrame:
    """Raw frame sent from an ECU to a zone."""
    zone: str
    ecu_id: str
    msg_id: int
    timestamp: float
    signals: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ECUFrame":
        return cls(**data)


@dataclass
class ZoneMessage:
    """Message wrapped by a zone controller before sending to central compute."""
    zone_id: str
    forwarded_at: float
    payload: ECUFrame
    errors: list = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "forwarded_at": self.forwarded_at,
            "payload": self.payload.to_dict(),
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ZoneMessage":
        payload = ECUFrame.from_dict(data["payload"])
        return cls(
            zone_id=data["zone_id"],
            forwarded_at=data["forwarded_at"],
            payload=payload,
            errors=data.get("errors", []),
        )


@dataclass
class CentralMessage:
    """Message stored in central compute with metadata."""
    zone_id: str
    ecu_id: str
    msg_id: int
    timestamp: float
    received_at: float
    signals: Dict[str, Any]
    zone_forwarded_at: Optional[float] = None
    processing_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ZoneHealth:
    """Health status of a zone."""
    zone_id: str
    last_message_at: Optional[float] = None
    message_count: int = 0
    error_count: int = 0
    is_alive: bool = True
    timeout_seconds: float = 5.0

    def update_message(self) -> None:
        self.last_message_at = time.time()
        self.message_count += 1

    def record_error(self) -> None:
        self.error_count += 1

    def check_timeout(self) -> bool:
        """Returns True if zone has timed out."""
        if self.last_message_at is None:
            return False
        elapsed = time.time() - self.last_message_at
        return elapsed > self.timeout_seconds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "last_message_at": self.last_message_at,
            "message_count": self.message_count,
            "error_count": self.error_count,
            "is_alive": self.is_alive and not self.check_timeout(),
            "uptime_seconds": (
                time.time() - self.last_message_at
                if self.last_message_at
                else 0
            ),
        }


class ValidationError(Exception):
    """Raised when a message fails validation."""
    pass
