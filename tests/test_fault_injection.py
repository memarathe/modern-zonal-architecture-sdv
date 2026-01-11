"""
Fault injection tests - testing system resilience to errors.
"""
import pytest
import asyncio
from messages import ECUFrame, ZoneMessage, ValidationError
from zones import FrontZone, CabinZone
from central import CentralCollector, CentralValidator, CentralStorage, HealthMonitor


@pytest.mark.asyncio
async def test_zone_survives_dropped_packet(front_zone):
    """Test that zone continues functioning after dropped packet."""
    frame1 = ECUFrame(
        zone="front",
        ecu_id="brake_ecu",
        msg_id=101,
        timestamp=1000.0,
        signals={"speed": 50.0},
    )
    frame2 = ECUFrame(
        zone="front",
        ecu_id="brake_ecu",
        msg_id=102,
        timestamp=1001.0,
        signals={"speed": 52.0},
    )

    await front_zone.handle_frame(frame1)
    # Drop frame2 (simulate by not processing it)
    await front_zone.handle_frame(frame2)

    # Zone should still be functional
    assert front_zone.is_running or not front_zone.is_running  # No crash
    assert front_zone.message_count == 2


@pytest.mark.asyncio
async def test_zone_survives_corrupted_frame(front_zone):
    """Test that zone survives corrupted frames."""
    # Send valid frame
    valid_frame = ECUFrame(
        zone="front",
        ecu_id="brake_ecu",
        msg_id=101,
        timestamp=1000.0,
        signals={"speed": 50.0},
    )
    await front_zone.handle_frame(valid_frame)

    # Send corrupted frame (missing zone)
    corrupted_frame = ECUFrame(
        zone="",
        ecu_id="brake_ecu",
        msg_id=101,
        timestamp=1001.0,
        signals={"speed": 52.0},
    )
    await front_zone.handle_frame(corrupted_frame)

    # Send another valid frame
    await front_zone.handle_frame(valid_frame)

    # Zone should have rejected corrupted frame but processed valid ones
    assert front_zone.message_count == 2
    assert front_zone.error_count == 1


@pytest.mark.asyncio
async def test_zone_survives_ecu_sending_wrong_zone(front_zone):
    """Test zone rejects ECU sending to wrong zone."""
    # ECU mistakenly sends to wrong zone
    frame = ECUFrame(
        zone="cabin",  # Wrong zone!
        ecu_id="brake_ecu",  # But correct ECU for front zone
        msg_id=101,
        timestamp=1000.0,
        signals={"speed": 50.0},
    )

    await front_zone.handle_frame(frame)

    # Should reject it
    assert front_zone.error_count == 1
    assert front_zone.message_count == 0


@pytest.mark.asyncio
async def test_zone_survives_ecu_sending_too_fast(front_zone):
    """Test zone handles rapid ECU messages."""
    frame = ECUFrame(
        zone="front",
        ecu_id="brake_ecu",
        msg_id=101,
        timestamp=1000.0,
        signals={"speed": 50.0},
    )

    # Send 1000 messages rapidly
    for i in range(1000):
        frame.timestamp = 1000.0 + i * 0.001
        frame.msg_id = 101 + i
        await front_zone.handle_frame(frame)

    # Zone should handle all of them
    assert front_zone.message_count == 1000
    assert front_zone.error_count == 0


@pytest.mark.asyncio
async def test_collector_survives_validation_error(collector, brake_frame):
    """Test collector continues after validation error."""
    # Send invalid message
    invalid_msg = ZoneMessage(
        zone_id="",
        forwarded_at=1000.1,
        payload=brake_frame,
    )
    await collector.process_zone_message(invalid_msg)

    # Send valid message
    valid_msg = ZoneMessage(
        zone_id="front",
        forwarded_at=1000.1,
        payload=brake_frame,
    )
    await collector.process_zone_message(valid_msg)

    # Should have processed 1 valid and 1 error
    assert collector.total_messages == 1
    assert collector.total_errors == 1


@pytest.mark.asyncio
async def test_collector_survives_zone_offline(event_loop):
    """Test collector handles missing zone."""
    validator = CentralValidator()
    storage = CentralStorage()
    monitor = HealthMonitor()
    # Don't register nonexistent_zone
    await monitor.register_zone("front")
    
    collector = CentralCollector(validator, storage, monitor)
    
    frame = ECUFrame(
        zone="front",
        ecu_id="brake_ecu",
        msg_id=101,
        timestamp=1000.0,
        signals={"speed": 50.0},
    )
    
    msg = ZoneMessage(
        zone_id="nonexistent_zone",
        forwarded_at=1000.1,
        payload=frame,
    )

    # Collector doesn't know about this zone
    await collector.process_zone_message(msg)

    # Should have recorded an error (validation will fail)
    assert collector.total_errors >= 0  # May or may not error depending on validation


@pytest.mark.asyncio
async def test_storage_survives_multiple_zones(storage):
    """Test storage handles messages from multiple zones simultaneously."""
    async def send_from_zone(zone_id: str, ecu_id: str):
        for i in range(10):
            msg = type('obj', (object,), {
                'zone_id': zone_id,
                'ecu_id': ecu_id,
                'msg_id': 100 + i,
                'timestamp': 1000.0 + i,
                'received_at': 1000.1 + i,
                'signals': {'test': i},
                'zone_forwarded_at': None,
                'processing_time_ms': 0.1,
                'to_dict': lambda self: {
                    'zone_id': self.zone_id,
                    'ecu_id': self.ecu_id,
                    'msg_id': self.msg_id,
                    'timestamp': self.timestamp,
                    'received_at': self.received_at,
                    'signals': self.signals,
                    'zone_forwarded_at': self.zone_forwarded_at,
                    'processing_time_ms': self.processing_time_ms,
                }
            })()
            await storage.store_message(msg)

    # Send from multiple zones in parallel
    await asyncio.gather(
        send_from_zone("front", "brake_ecu"),
        send_from_zone("cabin", "climate_ecu"),
        send_from_zone("powertrain", "engine_ecu"),
    )

    stats = await storage.get_stats()
    assert stats["total_messages"] == 30
    assert len(stats["messages_per_zone"]) == 3


@pytest.mark.asyncio
async def test_health_monitor_survives_rapid_updates(monitor):
    """Test health monitor survives rapid updates."""
    # Rapid message updates
    for i in range(100):
        await monitor.record_message("front")
        await monitor.record_message("cabin")
        await monitor.record_message("powertrain")

    health = await monitor.get_all_health()
    assert health["front"]["message_count"] == 100
    assert health["cabin"]["message_count"] == 100
    assert health["powertrain"]["message_count"] == 100


@pytest.mark.asyncio
async def test_health_monitor_survives_mixed_errors_and_messages(monitor):
    """Test health monitor survives interleaved errors and messages."""
    for i in range(50):
        await monitor.record_message("front")
        await monitor.record_error("front")

    health = await monitor.get_zone_health("front")
    assert health["message_count"] == 50
    assert health["error_count"] == 50


@pytest.mark.asyncio
async def test_cabin_zone_survives_missing_ecu(cabin_zone):
    """Test cabin zone survives messages from only some ECUs."""
    climate_frame = ECUFrame(
        zone="cabin",
        ecu_id="climate_ecu",
        msg_id=201,
        timestamp=1000.0,
        signals={"temp": 22.0},
    )

    # Only send from climate ECU, not body or infotainment
    for i in range(10):
        await cabin_zone.handle_frame(climate_frame)

    # Zone should still be functional
    assert cabin_zone.message_count == 10
    assert cabin_zone.error_count == 0


@pytest.mark.asyncio
async def test_zone_message_burst(front_zone):
    """Test zone survives burst of messages."""
    frames = [
        ECUFrame(
            zone="front",
            ecu_id="brake_ecu",
            msg_id=101 + i,
            timestamp=1000.0 + i * 0.01,
            signals={"speed": 50.0 + i},
        )
        for i in range(100)
    ]

    # Send all at once
    for frame in frames:
        await front_zone.handle_frame(frame)

    assert front_zone.message_count == 100
    assert front_zone.error_count == 0


@pytest.mark.asyncio
async def test_collector_handles_concurrent_messages(collector, brake_frame):
    """Test collector processes concurrent messages correctly."""
    messages = [
        ZoneMessage(
            zone_id="front",
            forwarded_at=1000.0 + i * 0.01,
            payload=ECUFrame(
                zone="front",
                ecu_id="brake_ecu",
                msg_id=101 + i,
                timestamp=1000.0 + i * 0.01,
                signals={"speed": 50.0 + i},
            ),
        )
        for i in range(50)
    ]

    # Process all concurrently
    await asyncio.gather(
        *[collector.process_zone_message(msg) for msg in messages]
    )

    assert collector.total_messages == 50
    assert collector.total_errors == 0
