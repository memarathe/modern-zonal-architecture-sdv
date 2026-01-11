"""
Base ECU class and ECU implementations.
"""
import asyncio
import time
import random
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable
from messages import ECUFrame


class BaseECU(ABC):
    """Abstract base class for all ECUs."""

    def __init__(
        self,
        ecu_id: str,
        zone: str,
        msg_id: int,
        send_interval: float = 0.1,
    ):
        self.ecu_id = ecu_id
        self.zone = zone
        self.msg_id = msg_id
        self.send_interval = send_interval
        self.is_running = False
        self.message_count = 0
        self.error_count = 0
        self._send_callback: Optional[Callable[[ECUFrame], None]] = None

    def set_send_callback(self, callback: Callable[[ECUFrame], None]) -> None:
        """Register callback to send messages to zone."""
        self._send_callback = callback

    @abstractmethod
    def get_signals(self) -> Dict[str, Any]:
        """Generate current signal values. Subclasses implement this."""
        pass

    def create_frame(self) -> ECUFrame:
        """Create an ECU frame with current signals."""
        return ECUFrame(
            zone=self.zone,
            ecu_id=self.ecu_id,
            msg_id=self.msg_id,
            timestamp=time.time(),
            signals=self.get_signals(),
        )

    async def run(self) -> None:
        """Continuously generate and send frames."""
        self.is_running = True
        try:
            while self.is_running:
                try:
                    frame = self.create_frame()
                    if self._send_callback:
                        self._send_callback(frame)
                    self.message_count += 1
                except Exception as e:
                    self.error_count += 1
                    print(f"[{self.ecu_id}] Error: {e}")

                await asyncio.sleep(self.send_interval)
        except asyncio.CancelledError:
            self.is_running = False

    def stop(self) -> None:
        """Stop the ECU."""
        self.is_running = False


class BrakeECU(BaseECU):
    """Brake ECU - generates wheel speed and brake pressure signals."""

    def __init__(self, zone: str = "front"):
        super().__init__(
            ecu_id="brake_ecu",
            zone=zone,
            msg_id=101,
            send_interval=0.05,
        )
        self.base_speed = 0.0

    def get_signals(self) -> Dict[str, Any]:
        # Simulate varying wheel speeds
        self.base_speed = max(0, self.base_speed + random.uniform(-1, 1))
        self.base_speed = min(120, self.base_speed)  # Max 120 km/h

        return {
            "wheel_speed_fl": self.base_speed + random.uniform(-0.5, 0.5),
            "wheel_speed_fr": self.base_speed + random.uniform(-0.5, 0.5),
            "wheel_speed_rl": self.base_speed + random.uniform(-0.5, 0.5),
            "wheel_speed_rr": self.base_speed + random.uniform(-0.5, 0.5),
            "brake_pressure": random.uniform(0, 100) if self.base_speed > 10 else 0,
            "brake_temp": random.uniform(40, 120),
        }


class EngineECU(BaseECU):
    """Engine ECU - generates RPM, temperature, fuel signals."""

    def __init__(self):
        super().__init__(
            ecu_id="engine_ecu",
            zone="powertrain",
            msg_id=102,
            send_interval=0.05,
        )
        self.rpm = 0.0

    def get_signals(self) -> Dict[str, Any]:
        # Simulate engine RPM variations
        self.rpm = max(0, self.rpm + random.uniform(-100, 100))
        self.rpm = min(7000, self.rpm)  # Max 7000 RPM

        return {
            "rpm": self.rpm,
            "engine_temp": 80 + (self.rpm / 100),  # Higher RPM = higher temp
            "fuel_pressure": 3.0 + (self.rpm / 2000),
            "fuel_consumption": (self.rpm / 1000) * 0.5,  # L/min estimate
            "throttle_position": (self.rpm / 7000) * 100,  # 0-100%
        }


class ClimateECU(BaseECU):
    """Climate control ECU - generates temperature, humidity signals."""

    def __init__(self):
        super().__init__(
            ecu_id="climate_ecu",
            zone="cabin",
            msg_id=201,
            send_interval=0.1,
        )
        self.cabin_temp = 20.0
        self.setpoint = 22.0

    def get_signals(self) -> Dict[str, Any]:
        # Simulate temperature regulation
        diff = self.setpoint - self.cabin_temp
        self.cabin_temp += diff * 0.05 + random.uniform(-0.1, 0.1)

        return {
            "cabin_temperature": round(self.cabin_temp, 2),
            "setpoint_temperature": self.setpoint,
            "humidity": random.uniform(30, 70),
            "ac_status": "on" if self.cabin_temp > self.setpoint else "off",
            "fan_speed": int((abs(diff) / 5) * 100) if abs(diff) > 0.5 else 0,
        }


class InfotainmentECU(BaseECU):
    """Infotainment ECU - generates audio, display, connectivity signals."""

    def __init__(self):
        super().__init__(
            ecu_id="infotainment_ecu",
            zone="cabin",
            msg_id=202,
            send_interval=0.2,
        )
        self.volume = 50

    def get_signals(self) -> Dict[str, Any]:
        # Random volume adjustments
        self.volume = max(0, min(100, self.volume + random.randint(-5, 5)))

        return {
            "volume": self.volume,
            "source": random.choice(["radio", "usb", "bluetooth", "aux"]),
            "display_brightness": random.randint(30, 100),
            "gps_signal_strength": random.randint(0, 100),
            "connected_devices": random.randint(0, 3),
        }


class BodyECU(BaseECU):
    """Body ECU - generates lighting, door, window signals."""

    def __init__(self):
        super().__init__(
            ecu_id="body_ecu",
            zone="cabin",
            msg_id=203,
            send_interval=0.1,
        )

    def get_signals(self) -> Dict[str, Any]:
        return {
            "door_fl": random.choice(["open", "closed"]),
            "door_fr": random.choice(["open", "closed"]),
            "door_rl": random.choice(["open", "closed"]),
            "door_rr": random.choice(["open", "closed"]),
            "trunk": random.choice(["open", "closed"]),
            "headlights": random.choice(["off", "low", "high"]),
            "window_fl_position": random.randint(0, 100),
            "window_fr_position": random.randint(0, 100),
        }
