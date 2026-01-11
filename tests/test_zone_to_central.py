"""
Tests for Zone -> Central Compute communication.
"""
import pytest
import asyncio
from messages import (
    ZoneMessage,
    ECUFrame,
    ValidationError,
    CentralMessage,
)
from central import CentralValidator, CentralStorage, HealthMonitor, CentralCollector


@pytest.mark.asyncio
async def test_validator_accepts_valid_zone_message(
    zone_message, event_loop
):
    """Test that validator accepts valid zone message."""
    validator = CentralValidator()
    # Should not raise
    validator.validate_zone_message(zone_message)


@pytest.mark.asyncio
async def test_validator_rejects_missing_zone_id(brake_frame):
    """Test that validator rejects message without zone_id."""
    validator = CentralValidator()
    msg = ZoneMessage(
        zone_id="",
        forwarded_at=1000.1,
        payload=brake_frame,
    )
    with pytest.raises(ValidationError):
        validator.validate_zone_message(msg)


@pytest.mark.asyncio
async def test_validator_rejects_invalid_timestamp(
    brake_frame
):
    """Test that validator rejects invalid timestamp."""
    validator = CentralValidator()
    msg = ZoneMessage(
        zone_id="front",
        forwarded_at=-1.0,
        payload=brake_frame,
    )
    with pytest.raises(ValidationError):
        validator.validate_zone_message(msg)


@pytest.mark.asyncio
async def test_validator_rejects_missing_payload():
    """Test that validator rejects message without payload."""
    validator = CentralValidator()
    msg = ZoneMessage(
        zone_id="front",
        forwarded_at=1000.1,
        payload=None,
    )
    with pytest.raises(ValidationError):
        validator.validate_zone_message(msg)


@pytest.mark.asyncio
async def test_storage_stores_message(storage, brake_frame):
    """Test that storage stores messages."""
    msg = CentralMessage(
        zone_id="front",
        ecu_id="brake_ecu",
        msg_id=101,
        timestamp=1000.0,
        received_at=1000.1,
        signals=brake_frame.signals,
    )

    await storage.store_message(msg)

    assert "front" in storage.messages
    assert len(storage.messages["front"]) == 1


@pytest.mark.asyncio
async def test_storage_retrieves_messages(storage, brake_frame):
    """Test that storage retrieves stored messages."""
    for i in range(5):
        msg = CentralMessage(
            zone_id="front",
            ecu_id="brake_ecu",
            msg_id=101,
            timestamp=1000.0 + i,
            received_at=1000.1 + i,
            signals=brake_frame.signals,
        )
        await storage.store_message(msg)

    messages = await storage.get_messages("front")
    assert len(messages) == 5


@pytest.mark.asyncio
async def test_storage_filters_by_ecu(storage):
    """Test that storage can filter messages by ECU."""
    for i in range(3):
        msg = CentralMessage(
            zone_id="cabin",
            ecu_id="climate_ecu",
            msg_id=201,
            timestamp=1000.0 + i,
            received_at=1000.1 + i,
            signals={"temp": 22.0},
        )
        await storage.store_message(msg)

    for i in range(2):
        msg = CentralMessage(
            zone_id="cabin",
            ecu_id="body_ecu",
            msg_id=203,
            timestamp=1000.0 + i,
            received_at=1000.1 + i,
            signals={"door": "closed"},
        )
        await storage.store_message(msg)

    climate_msgs = await storage.get_messages("cabin", ecu_id="climate_ecu")
    assert len(climate_msgs) == 3

    body_msgs = await storage.get_messages("cabin", ecu_id="body_ecu")
    assert len(body_msgs) == 2


@pytest.mark.asyncio
async def test_storage_limits_messages(storage, brake_frame):
    """Test that storage limits total messages per zone."""
    small_storage = CentralStorage(max_messages_per_zone=10)

    # Store 20 messages
    for i in range(20):
        msg = CentralMessage(
            zone_id="front",
            ecu_id="brake_ecu",
            msg_id=101,
            timestamp=1000.0 + i,
            received_at=1000.1 + i,
            signals=brake_frame.signals,
        )
        await small_storage.store_message(msg)

    # Should only have 10 (latest)
    messages = await small_storage.get_messages("front")
    assert len(messages) == 10


@pytest.mark.asyncio
async def test_storage_tracks_latest_signals(storage, brake_frame):
    """Test that storage tracks latest signals from each ECU."""
    frame1 = CentralMessage(
        zone_id="front",
        ecu_id="brake_ecu",
        msg_id=101,
        timestamp=1000.0,
        received_at=1000.1,
        signals={"wheel_speed": 50.0},
    )
    frame2 = CentralMessage(
        zone_id="front",
        ecu_id="brake_ecu",
        msg_id=101,
        timestamp=1001.0,
        received_at=1001.1,
        signals={"wheel_speed": 55.0},
    )

    await storage.store_message(frame1)
    await storage.store_message(frame2)

    signals = await storage.get_latest_signals("front")
    assert signals["brake_ecu"]["wheel_speed"] == 55.0


@pytest.mark.asyncio
async def test_monitor_records_message(monitor):
    """Test that health monitor records message reception."""
    await monitor.record_message("front")

    health = await monitor.get_zone_health("front")
    assert health["message_count"] == 1
    assert health["last_message_at"] is not None


@pytest.mark.asyncio
async def test_monitor_records_error(monitor):
    """Test that health monitor records errors."""
    await monitor.record_error("cabin")

    health = await monitor.get_zone_health("cabin")
    assert health["error_count"] == 1


@pytest.mark.asyncio
async def test_monitor_detects_timeout(monitor):
    """Test that health monitor detects timeouts."""
    # Record a message
    await monitor.record_message("powertrain")
    health1 = await monitor.get_zone_health("powertrain")
    assert health1["is_alive"] is True

    # Manually adjust timeout to trigger it
    zone_health = monitor.zone_health["powertrain"]
    zone_health.timeout_seconds = 0.1
    zone_health.last_message_at = 0.0

    # Check timeout
    timed_out = await monitor.check_timeouts()
    assert "powertrain" in timed_out

    health2 = await monitor.get_zone_health("powertrain")
    assert health2["is_alive"] is False


@pytest.mark.asyncio
async def test_collector_processes_valid_message(
    collector, zone_message
):
    """Test that collector processes valid zone message."""
    await collector.process_zone_message(zone_message)

    assert collector.total_messages == 1
    assert collector.total_errors == 0


@pytest.mark.asyncio
async def test_collector_rejects_invalid_message(collector):
    """Test that collector rejects invalid zone message."""
    invalid_msg = ZoneMessage(
        zone_id="",
        forwarded_at=1000.1,
        payload=None,
    )

    await collector.process_zone_message(invalid_msg)

    assert collector.total_errors == 1


@pytest.mark.asyncio
async def test_collector_queue_processing(collector, zone_message):
    """Test that collector processes queued messages."""
    await collector.receive_message(zone_message)
    await collector.receive_message(zone_message)

    task = asyncio.create_task(collector.run())
    await asyncio.sleep(0.2)
    collector.stop()

    assert collector.total_messages == 2


@pytest.mark.asyncio
async def test_collector_updates_health(collector, zone_message):
    """Test that collector updates health monitor."""
    await collector.process_zone_message(zone_message)

    health = await collector.monitor.get_zone_health("front")
    assert health["message_count"] == 1


@pytest.mark.asyncio
async def test_collector_stores_messages(collector, zone_message):
    """Test that collector stores messages in storage."""
    await collector.process_zone_message(zone_message)

    messages = await collector.storage.get_messages("front")
    assert len(messages) == 1
    assert messages[0].ecu_id == "brake_ecu"
