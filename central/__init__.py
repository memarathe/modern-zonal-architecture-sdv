"""
Central compute components: collector, validator, storage, health monitor.
"""
import asyncio
import time
from typing import Dict, List, Any, Optional
from messages import (
    ZoneMessage,
    CentralMessage,
    ValidationError,
    ZoneHealth,
)


class CentralValidator:
    """Validates messages received from zones."""

    def __init__(self):
        self.validation_errors: List[str] = []

    def validate_zone_message(self, msg: ZoneMessage) -> None:
        """Validate zone-wrapped message."""
        if not msg.zone_id:
            raise ValidationError("Missing zone_id")

        if msg.forwarded_at <= 0:
            raise ValidationError("Invalid forwarded_at timestamp")

        if msg.payload is None:
            raise ValidationError("Missing payload")

        # Validate payload
        payload = msg.payload
        if not payload.ecu_id:
            raise ValidationError("Missing ECU ID in payload")

        if payload.timestamp <= 0:
            raise ValidationError("Invalid timestamp in payload")

        if not payload.signals:
            raise ValidationError("No signals in payload")


class CentralStorage:
    """In-memory storage for messages."""

    def __init__(self, max_messages_per_zone: int = 1000):
        self.max_messages_per_zone = max_messages_per_zone
        self.messages: Dict[str, List[CentralMessage]] = {}
        self.latest_signals: Dict[str, Dict[str, Any]] = {}
        self.lock = asyncio.Lock()

    async def store_message(self, msg: CentralMessage) -> None:
        """Store a message from central compute."""
        async with self.lock:
            if msg.zone_id not in self.messages:
                self.messages[msg.zone_id] = []
                self.latest_signals[msg.zone_id] = {}

            # Store message
            messages = self.messages[msg.zone_id]
            messages.append(msg)

            # Trim old messages
            if len(messages) > self.max_messages_per_zone:
                messages.pop(0)

            # Update latest signals
            self.latest_signals[msg.zone_id][msg.ecu_id] = msg.signals

    async def get_messages(
        self,
        zone_id: Optional[str] = None,
        ecu_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[CentralMessage]:
        """Retrieve messages with optional filtering."""
        async with self.lock:
            results = []

            if zone_id:
                zone_messages = self.messages.get(zone_id, [])
                if ecu_id:
                    results = [m for m in zone_messages if m.ecu_id == ecu_id]
                else:
                    results = zone_messages
            else:
                for zone_messages in self.messages.values():
                    results.extend(zone_messages)

            # Return latest messages
            return results[-limit:]

    async def get_latest_signals(
        self, zone_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get latest signals for a zone or all zones."""
        async with self.lock:
            if zone_id:
                return self.latest_signals.get(zone_id, {})
            return self.latest_signals

    async def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        async with self.lock:
            total_messages = sum(
                len(msgs) for msgs in self.messages.values()
            )
            return {
                "total_messages": total_messages,
                "zones": len(self.messages),
                "messages_per_zone": {
                    zone_id: len(messages)
                    for zone_id, messages in self.messages.items()
                },
            }


class HealthMonitor:
    """Monitors health of zones and detects timeouts."""

    def __init__(self, timeout_seconds: float = 5.0):
        self.timeout_seconds = timeout_seconds
        self.zone_health: Dict[str, ZoneHealth] = {}
        self.lock = asyncio.Lock()

    async def register_zone(self, zone_id: str) -> None:
        """Register a zone for monitoring."""
        async with self.lock:
            if zone_id not in self.zone_health:
                self.zone_health[zone_id] = ZoneHealth(
                    zone_id=zone_id,
                    timeout_seconds=self.timeout_seconds,
                )

    async def record_message(self, zone_id: str) -> None:
        """Record message reception from a zone."""
        async with self.lock:
            if zone_id in self.zone_health:
                self.zone_health[zone_id].update_message()

    async def record_error(self, zone_id: str) -> None:
        """Record error from a zone."""
        async with self.lock:
            if zone_id in self.zone_health:
                self.zone_health[zone_id].record_error()

    async def get_zone_health(self, zone_id: str) -> Optional[Dict[str, Any]]:
        """Get health status for a zone."""
        async with self.lock:
            if zone_id in self.zone_health:
                return self.zone_health[zone_id].to_dict()
            return None

    async def get_all_health(self) -> Dict[str, Dict[str, Any]]:
        """Get health status for all zones."""
        async with self.lock:
            return {
                zone_id: health.to_dict()
                for zone_id, health in self.zone_health.items()
            }

    async def check_timeouts(self) -> List[str]:
        """Check for timed-out zones. Returns list of timed-out zone IDs."""
        async with self.lock:
            timed_out = []
            for zone_id, health in self.zone_health.items():
                if health.check_timeout():
                    health.is_alive = False
                    timed_out.append(zone_id)
                else:
                    health.is_alive = True
            return timed_out


class CentralCollector:
    """Central compute collector - receives and processes zone messages."""

    def __init__(
        self,
        validator: CentralValidator,
        storage: CentralStorage,
        monitor: HealthMonitor,
    ):
        self.validator = validator
        self.storage = storage
        self.monitor = monitor
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self.is_running = False
        self.total_messages = 0
        self.total_errors = 0

    async def process_zone_message(self, msg: ZoneMessage) -> None:
        """Process incoming zone message."""
        try:
            # Validate
            self.validator.validate_zone_message(msg)

            # Record in health monitor
            await self.monitor.record_message(msg.zone_id)

            # Convert to central message
            processing_time = time.time() - msg.forwarded_at
            central_msg = CentralMessage(
                zone_id=msg.zone_id,
                ecu_id=msg.payload.ecu_id,
                msg_id=msg.payload.msg_id,
                timestamp=msg.payload.timestamp,
                received_at=time.time(),
                signals=msg.payload.signals,
                zone_forwarded_at=msg.forwarded_at,
                processing_time_ms=processing_time * 1000,
            )

            # Store
            await self.storage.store_message(central_msg)
            self.total_messages += 1

        except ValidationError as e:
            await self.monitor.record_error(msg.zone_id)
            self.total_errors += 1
            print(f"[Central] Validation error: {e}")

    async def receive_message(self, msg: ZoneMessage) -> None:
        """Queue incoming zone message."""
        await self.message_queue.put(msg)

    async def run(self) -> None:
        """Process messages from queue."""
        self.is_running = True
        try:
            while self.is_running:
                try:
                    msg = await asyncio.wait_for(
                        self.message_queue.get(), timeout=1.0
                    )
                    await self.process_zone_message(msg)
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            self.is_running = False

    def stop(self) -> None:
        """Stop the collector."""
        self.is_running = False

    async def get_status(self) -> Dict[str, Any]:
        """Get collector status."""
        stats = await self.storage.get_stats()
        health = await self.monitor.get_all_health()
        return {
            "is_running": self.is_running,
            "total_messages": self.total_messages,
            "total_errors": self.total_errors,
            "queue_size": self.message_queue.qsize(),
            "storage_stats": stats,
            "zone_health": health,
        }
