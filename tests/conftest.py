"""
Pytest configuration and shared fixtures.
"""
import pytest
import asyncio
from messages import ECUFrame, ZoneMessage, CentralMessage
from central import (
    CentralCollector,
    CentralValidator,
    CentralStorage,
    HealthMonitor,
)
from zones import FrontZone, CabinZone, PowertrainZone
from ecus import BrakeECU, ClimateECU, EngineECU


@pytest.fixture(autouse=True)
def cleanup_asyncio():
    yield
    try:
        asyncio.get_event_loop().stop()
    except RuntimeError:
        pass

@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture
def validator():
    """Create a validator instance."""
    return CentralValidator()


@pytest.fixture
def storage():
    """Create a storage instance."""
    return CentralStorage(max_messages_per_zone=100)


@pytest.fixture
def monitor(event_loop):
    """Create a health monitor instance."""
    monitor = HealthMonitor(timeout_seconds=5.0)
    event_loop.run_until_complete(monitor.register_zone("front"))
    event_loop.run_until_complete(monitor.register_zone("cabin"))
    event_loop.run_until_complete(monitor.register_zone("powertrain"))
    return monitor


@pytest.fixture
def collector(validator, storage, monitor):
    """Create a collector instance."""
    return CentralCollector(validator, storage, monitor)


@pytest.fixture
def brake_ecu():
    """Create a brake ECU instance."""
    return BrakeECU()


@pytest.fixture
def climate_ecu():
    """Create a climate ECU instance."""
    return ClimateECU()


@pytest.fixture
def engine_ecu():
    """Create an engine ECU instance."""
    return EngineECU()


@pytest.fixture
def front_zone():
    """Create a front zone instance."""
    return FrontZone()


@pytest.fixture
def cabin_zone():
    """Create a cabin zone instance."""
    return CabinZone()


@pytest.fixture
def powertrain_zone():
    """Create a powertrain zone instance."""
    return PowertrainZone()


@pytest.fixture
def brake_frame():
    """Create a sample brake ECU frame."""
    return ECUFrame(
        zone="front",
        ecu_id="brake_ecu",
        msg_id=101,
        timestamp=1000.0,
        signals={
            "wheel_speed_fl": 50.0,
            "wheel_speed_fr": 50.0,
            "brake_pressure": 50.0,
        },
    )


@pytest.fixture
def climate_frame():
    """Create a sample climate ECU frame."""
    return ECUFrame(
        zone="cabin",
        ecu_id="climate_ecu",
        msg_id=201,
        timestamp=1000.0,
        signals={
            "cabin_temperature": 22.0,
            "humidity": 50.0,
        },
    )


@pytest.fixture
def engine_frame():
    """Create a sample engine ECU frame."""
    return ECUFrame(
        zone="powertrain",
        ecu_id="engine_ecu",
        msg_id=102,
        timestamp=1000.0,
        signals={
            "rpm": 3000.0,
            "engine_temp": 90.0,
        },
    )


@pytest.fixture
def zone_message(brake_frame):
    """Create a sample zone message."""
    return ZoneMessage(
        zone_id="front",
        forwarded_at=1000.1,
        payload=brake_frame,
    )
