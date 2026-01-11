"""
Tests for ECU -> Zone communication.
"""
import pytest
import asyncio
from messages import ECUFrame, ValidationError
from zones import FrontZone, CabinZone


@pytest.mark.asyncio
async def test_zone_accepts_valid_frame(front_zone, brake_frame):
    """Test that zone accepts valid ECU frame."""
    await front_zone.handle_frame(brake_frame)
    assert front_zone.message_count == 1
    assert front_zone.error_count == 0
    assert "brake_ecu" in front_zone.received_frames


@pytest.mark.asyncio
async def test_zone_rejects_wrong_zone_id(front_zone, climate_frame):
    """Test that zone rejects frame from wrong zone."""
    # Climate frame has zone="cabin", not "front"
    await front_zone.handle_frame(climate_frame)
    assert front_zone.error_count == 1
    assert front_zone.message_count == 0


@pytest.mark.asyncio
async def test_zone_rejects_unknown_ecu(front_zone):
    """Test that zone rejects unknown ECU."""
    frame = ECUFrame(
        zone="front",
        ecu_id="unknown_ecu",
        msg_id=999,
        timestamp=1000.0,
        signals={"test": 1.0},
    )
    await front_zone.handle_frame(frame)
    assert front_zone.error_count == 1


@pytest.mark.asyncio
async def test_zone_rejects_empty_signals(front_zone):
    """Test that zone rejects frame with no signals."""
    frame = ECUFrame(
        zone="front",
        ecu_id="brake_ecu",
        msg_id=101,
        timestamp=1000.0,
        signals={},
    )
    await front_zone.handle_frame(frame)
    assert front_zone.error_count == 1


@pytest.mark.asyncio
async def test_zone_rejects_invalid_timestamp(front_zone):
    """Test that zone rejects frame with invalid timestamp."""
    frame = ECUFrame(
        zone="front",
        ecu_id="brake_ecu",
        msg_id=101,
        timestamp=-1.0,
        signals={"wheel_speed": 50.0},
    )
    await front_zone.handle_frame(frame)
    assert front_zone.error_count == 1


@pytest.mark.asyncio
async def test_zone_adds_forwarding_metadata(front_zone, brake_frame):
    """Test that zone wraps frame with correct metadata."""
    forwarded_messages = []

    def capture_forward(msg):
        forwarded_messages.append(msg)

    front_zone.set_forward_callback(capture_forward)
    await front_zone.handle_frame(brake_frame)

    assert len(forwarded_messages) == 1
    msg = forwarded_messages[0]
    assert msg.zone_id == "front"
    assert msg.forwarded_at > 0
    assert msg.payload.ecu_id == "brake_ecu"


@pytest.mark.asyncio
async def test_zone_stores_latest_frame(front_zone):
    """Test that zone stores latest frame from each ECU."""
    frame1 = ECUFrame(
        zone="front",
        ecu_id="brake_ecu",
        msg_id=101,
        timestamp=1000.0,
        signals={"wheel_speed": 50.0},
    )
    frame2 = ECUFrame(
        zone="front",
        ecu_id="brake_ecu",
        msg_id=101,
        timestamp=1001.0,
        signals={"wheel_speed": 55.0},
    )

    await front_zone.handle_frame(frame1)
    await front_zone.handle_frame(frame2)

    # Should have only the latest frame
    assert front_zone.received_frames["brake_ecu"].signals["wheel_speed"] == 55.0


@pytest.mark.asyncio
async def test_zone_queue_processing(front_zone, brake_frame):
    """Test that zone processes frames from queue."""
    forwarded = []

    def capture(msg):
        forwarded.append(msg)

    front_zone.set_forward_callback(capture)

    # Queue multiple frames
    await front_zone.receive_frame(brake_frame)
    await front_zone.receive_frame(brake_frame)

    # Start processing
    task = asyncio.create_task(front_zone.run())
    await asyncio.sleep(0.1)
    front_zone.stop()

    # Should have processed 2 frames
    assert len(forwarded) == 2
    assert front_zone.message_count == 2


@pytest.mark.asyncio
async def test_cabin_zone_accepts_multiple_ecus(cabin_zone):
    """Test that cabin zone can receive from multiple ECUs."""
    climate_frame = ECUFrame(
        zone="cabin",
        ecu_id="climate_ecu",
        msg_id=201,
        timestamp=1000.0,
        signals={"temperature": 22.0},
    )
    body_frame = ECUFrame(
        zone="cabin",
        ecu_id="body_ecu",
        msg_id=203,
        timestamp=1000.0,
        signals={"door_fl": "closed"},
    )

    await cabin_zone.handle_frame(climate_frame)
    await cabin_zone.handle_frame(body_frame)

    assert cabin_zone.message_count == 2
    assert cabin_zone.error_count == 0
    assert "climate_ecu" in cabin_zone.received_frames
    assert "body_ecu" in cabin_zone.received_frames


@pytest.mark.asyncio
async def test_zone_health_status(front_zone, brake_frame):
    """Test zone health status reporting."""
    await front_zone.handle_frame(brake_frame)

    health = front_zone.get_health()
    assert health["zone_id"] == "front"
    assert health["message_count"] == 1
    assert health["error_count"] == 0
    assert "brake_ecu" in health["received_ecu_ids"]


@pytest.mark.asyncio
async def test_zone_rate_limiting(front_zone):
    """Test that zone can handle rapid frame delivery."""
    frame = ECUFrame(
        zone="front",
        ecu_id="brake_ecu",
        msg_id=101,
        timestamp=1000.0,
        signals={"speed": 50.0},
    )

    # Send 100 frames rapidly
    for i in range(100):
        frame.timestamp = 1000.0 + i * 0.01
        await front_zone.handle_frame(frame)

    assert front_zone.message_count == 100
    assert front_zone.error_count == 0
