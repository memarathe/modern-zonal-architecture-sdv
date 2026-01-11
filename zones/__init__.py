"""
Zone controller implementations.
"""
import asyncio
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable, List
from messages import ECUFrame, ZoneMessage, ValidationError


class BaseZone(ABC):
    """Abstract base class for zone controllers."""

    def __init__(self, zone_id: str, timeout_seconds: float = 2.0):
        self.zone_id = zone_id
        self.timeout_seconds = timeout_seconds
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self.received_frames: Dict[str, ECUFrame] = {}
        self.is_running = False
        self.message_count = 0
        self.error_count = 0
        self._forward_callback: Optional[Callable[[ZoneMessage], None]] = None

    def set_forward_callback(
        self, callback: Callable[[ZoneMessage], None]
    ) -> None:
        """Register callback to forward messages to central compute."""
        self._forward_callback = callback

    @abstractmethod
    def validate_frame(self, frame: ECUFrame) -> None:
        """Validate incoming ECU frame. Raise ValidationError if invalid."""
        pass

    def get_ecu_ids(self) -> List[str]:
        """Return list of expected ECU IDs for this zone."""
        return list(self.received_frames.keys())

    async def handle_frame(self, frame: ECUFrame) -> None:
        """Process incoming ECU frame."""
        try:
            # Validate frame
            self.validate_frame(frame)

            # Store latest frame from this ECU
            self.received_frames[frame.ecu_id] = frame

            # Create zone message
            zone_msg = ZoneMessage(
                zone_id=self.zone_id,
                forwarded_at=time.time(),
                payload=frame,
            )

            # Forward to central compute
            if self._forward_callback:
                self._forward_callback(zone_msg)

            self.message_count += 1

        except ValidationError as e:
            self.error_count += 1
            print(f"[{self.zone_id}] Validation error: {e}")

    async def run(self) -> None:
        """Process messages from queue."""
        self.is_running = True
        try:
            while self.is_running:
                try:
                    # Get message with timeout
                    frame = await asyncio.wait_for(
                        self.message_queue.get(), timeout=1.0
                    )
                    await self.handle_frame(frame)
                except asyncio.TimeoutError:
                    # No messages - that's okay
                    pass
        except asyncio.CancelledError:
            self.is_running = False

    async def receive_frame(self, frame: ECUFrame) -> None:
        """Queue incoming frame for processing."""
        await self.message_queue.put(frame)

    def stop(self) -> None:
        """Stop the zone."""
        self.is_running = False

    async def cleanup(self) -> None:
        """Clean up asyncio resources properly."""
        self.is_running = False
        # Allow pending tasks to complete
        await asyncio.sleep(0)
        # Clear the queue
        while not self.message_queue.empty():
            try:
                self.message_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def get_health(self) -> Dict[str, Any]:
        """Get zone health status."""
        return {
            "zone_id": self.zone_id,
            "is_running": self.is_running,
            "message_count": self.message_count,
            "error_count": self.error_count,
            "queue_size": self.message_queue.qsize(),
            "connected_ecus": len(self.received_frames),
            "received_ecu_ids": list(self.received_frames.keys()),
        }


class FrontZone(BaseZone):
    """Front zone - handles brake, steering, headlight ECUs."""

    def __init__(self):
        super().__init__("front")
        self.received_frames = {
            "brake_ecu": None,
            "steering_ecu": None,
        }

    def validate_frame(self, frame: ECUFrame) -> None:
        """Validate front zone frames."""
        if frame.zone != "front":
            raise ValidationError(
                f"Frame zone '{frame.zone}' doesn't match zone 'front'"
            )

        if frame.ecu_id not in ["brake_ecu", "steering_ecu"]:
            raise ValidationError(f"Unknown ECU ID: {frame.ecu_id}")

        if not frame.signals:
            raise ValidationError("Frame has no signals")

        if frame.timestamp <= 0:
            raise ValidationError("Invalid timestamp")


class RearZone(BaseZone):
    """Rear zone - handles tail lights, trunk, rear sensors."""

    def __init__(self):
        super().__init__("rear")
        self.received_frames = {
            "rear_lights_ecu": None,
            "trunk_ecu": None,
        }

    def validate_frame(self, frame: ECUFrame) -> None:
        """Validate rear zone frames."""
        if frame.zone != "rear":
            raise ValidationError(
                f"Frame zone '{frame.zone}' doesn't match zone 'rear'"
            )

        if frame.ecu_id not in ["rear_lights_ecu", "trunk_ecu"]:
            raise ValidationError(f"Unknown ECU ID: {frame.ecu_id}")

        if not frame.signals:
            raise ValidationError("Frame has no signals")


class CabinZone(BaseZone):
    """Cabin zone - handles climate, infotainment, body control ECUs."""

    def __init__(self):
        super().__init__("cabin")
        self.received_frames = {
            "climate_ecu": None,
            "infotainment_ecu": None,
            "body_ecu": None,
        }

    def validate_frame(self, frame: ECUFrame) -> None:
        """Validate cabin zone frames."""
        if frame.zone != "cabin":
            raise ValidationError(
                f"Frame zone '{frame.zone}' doesn't match zone 'cabin'"
            )

        if frame.ecu_id not in [
            "climate_ecu",
            "infotainment_ecu",
            "body_ecu",
        ]:
            raise ValidationError(f"Unknown ECU ID: {frame.ecu_id}")

        if not frame.signals:
            raise ValidationError("Frame has no signals")


class PowertrainZone(BaseZone):
    """Powertrain zone - handles engine, transmission, battery ECUs."""

    def __init__(self):
        super().__init__("powertrain")
        self.received_frames = {
            "engine_ecu": None,
            "transmission_ecu": None,
        }

    def validate_frame(self, frame: ECUFrame) -> None:
        """Validate powertrain zone frames."""
        if frame.zone != "powertrain":
            raise ValidationError(
                f"Frame zone '{frame.zone}' doesn't match zone 'powertrain'"
            )

        if frame.ecu_id not in ["engine_ecu", "transmission_ecu"]:
            raise ValidationError(f"Unknown ECU ID: {frame.ecu_id}")

        if not frame.signals:
            raise ValidationError("Frame has no signals")
