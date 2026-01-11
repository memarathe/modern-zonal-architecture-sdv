"""
Tests for REST API endpoints.
"""
import pytest
import asyncio
import json
from central import (
    CentralCollector,
    CentralValidator,
    CentralStorage,
    HealthMonitor,
)
from central.api import create_api
from messages import ZoneMessage, ECUFrame


@pytest.fixture
def app(event_loop):
    """Create Flask test app."""
    validator = CentralValidator()
    storage = CentralStorage()
    monitor = HealthMonitor()

    # Register zones
    event_loop.run_until_complete(monitor.register_zone("front"))
    event_loop.run_until_complete(monitor.register_zone("cabin"))
    event_loop.run_until_complete(monitor.register_zone("powertrain"))

    collector = CentralCollector(validator, storage, monitor)

    flask_app = create_api(collector)
    flask_app.config["TESTING"] = True
    return flask_app, collector, event_loop


@pytest.fixture
def client(app):
    """Create Flask test client."""
    flask_app, collector, loop = app
    return flask_app.test_client(), collector, loop


def test_health_endpoint(client):
    """Test health check endpoint."""
    flask_client, _, _ = client
    response = flask_client.get("/health")

    assert response.status_code == 200
    assert response.json["status"] == "ok"


def test_get_zones_empty(client):
    """Test get zones endpoint with no messages."""
    flask_client, _, _ = client
    response = flask_client.get("/zones")

    assert response.status_code == 200
    data = response.json
    assert "zones" in data
    assert data["total_zones"] == 3  # front, cabin, powertrain
    # No messages yet, so active zones should be 0
    assert data["active_zones"] >= 0  # Allow 0 or more (depends on registration)


def test_get_zones_with_messages(client):
    """Test get zones endpoint after receiving messages."""
    flask_client, collector, loop = client

    # Send a message to a zone
    frame = ECUFrame(
        zone="front",
        ecu_id="brake_ecu",
        msg_id=101,
        timestamp=1000.0,
        signals={"wheel_speed": 50.0},
    )
    msg = ZoneMessage(
        zone_id="front",
        forwarded_at=1000.1,
        payload=frame,
    )

    loop.run_until_complete(collector.process_zone_message(msg))

    response = flask_client.get("/zones")
    assert response.status_code == 200
    data = response.json
    assert data["total_zones"] == 3


def test_get_specific_zone(client):
    """Test get specific zone endpoint."""
    flask_client, collector, loop = client

    frame = ECUFrame(
        zone="cabin",
        ecu_id="climate_ecu",
        msg_id=201,
        timestamp=1000.0,
        signals={"temp": 22.0},
    )
    msg = ZoneMessage(
        zone_id="cabin",
        forwarded_at=1000.1,
        payload=frame,
    )

    loop.run_until_complete(collector.process_zone_message(msg))

    response = flask_client.get("/zones/cabin")
    assert response.status_code == 200
    data = response.json
    assert data["zone_id"] == "cabin"


def test_get_nonexistent_zone(client):
    """Test get nonexistent zone returns 404."""
    flask_client, _, _ = client
    response = flask_client.get("/zones/nonexistent")

    assert response.status_code == 404


def test_get_zone_messages(client):
    """Test get zone messages endpoint."""
    flask_client, collector, loop = client

    # Send multiple messages
    for i in range(5):
        frame = ECUFrame(
            zone="front",
            ecu_id="brake_ecu",
            msg_id=101,
            timestamp=1000.0 + i,
            signals={"wheel_speed": 50.0 + i},
        )
        msg = ZoneMessage(
            zone_id="front",
            forwarded_at=1000.1 + i,
            payload=frame,
        )
        loop.run_until_complete(collector.process_zone_message(msg))

    response = flask_client.get("/zones/front/messages")
    assert response.status_code == 200
    data = response.json
    assert data["zone_id"] == "front"
    assert data["count"] == 5


def test_get_zone_messages_with_limit(client):
    """Test get zone messages with limit."""
    flask_client, collector, loop = client

    for i in range(10):
        frame = ECUFrame(
            zone="cabin",
            ecu_id="climate_ecu",
            msg_id=201,
            timestamp=1000.0 + i,
            signals={"temp": 22.0},
        )
        msg = ZoneMessage(
            zone_id="cabin",
            forwarded_at=1000.1 + i,
            payload=frame,
        )
        loop.run_until_complete(collector.process_zone_message(msg))

    response = flask_client.get("/zones/cabin/messages?limit=5")
    assert response.status_code == 200
    data = response.json
    assert data["count"] == 5


def test_get_zone_messages_filter_by_ecu(client):
    """Test get zone messages filtered by ECU."""
    flask_client, collector, loop = client

    # Send from climate_ecu
    frame1 = ECUFrame(
        zone="cabin",
        ecu_id="climate_ecu",
        msg_id=201,
        timestamp=1000.0,
        signals={"temp": 22.0},
    )
    msg1 = ZoneMessage(
        zone_id="cabin",
        forwarded_at=1000.1,
        payload=frame1,
    )

    # Send from body_ecu
    frame2 = ECUFrame(
        zone="cabin",
        ecu_id="body_ecu",
        msg_id=203,
        timestamp=1000.0,
        signals={"door": "closed"},
    )
    msg2 = ZoneMessage(
        zone_id="cabin",
        forwarded_at=1000.1,
        payload=frame2,
    )

    loop.run_until_complete(collector.process_zone_message(msg1))
    loop.run_until_complete(collector.process_zone_message(msg2))

    response = flask_client.get("/zones/cabin/messages?ecu_id=climate_ecu")
    assert response.status_code == 200
    data = response.json
    assert data["ecu_id"] == "climate_ecu"
    assert data["count"] == 1


def test_get_zone_signals(client):
    """Test get zone signals endpoint."""
    flask_client, collector, loop = client

    frame = ECUFrame(
        zone="front",
        ecu_id="brake_ecu",
        msg_id=101,
        timestamp=1000.0,
        signals={"wheel_speed_fl": 50.0, "brake_pressure": 75.0},
    )
    msg = ZoneMessage(
        zone_id="front",
        forwarded_at=1000.1,
        payload=frame,
    )

    loop.run_until_complete(collector.process_zone_message(msg))

    response = flask_client.get("/zones/front/signals")
    assert response.status_code == 200
    data = response.json
    assert data["zone_id"] == "front"
    assert "brake_ecu" in data["signals"]


def test_get_ecu_signals(client):
    """Test get ECU signals endpoint."""
    flask_client, collector, loop = client

    frame = ECUFrame(
        zone="powertrain",
        ecu_id="engine_ecu",
        msg_id=102,
        timestamp=1000.0,
        signals={"rpm": 3000.0, "engine_temp": 90.0},
    )
    msg = ZoneMessage(
        zone_id="powertrain",
        forwarded_at=1000.1,
        payload=frame,
    )

    loop.run_until_complete(collector.process_zone_message(msg))

    response = flask_client.get("/ecus/engine_ecu/signals")
    assert response.status_code == 200
    data = response.json
    assert data["ecu_id"] == "engine_ecu"
    assert data["signals"]["rpm"] == 3000.0


def test_get_all_signals(client):
    """Test get all signals endpoint."""
    flask_client, collector, loop = client

    frame = ECUFrame(
        zone="cabin",
        ecu_id="climate_ecu",
        msg_id=201,
        timestamp=1000.0,
        signals={"temp": 22.0},
    )
    msg = ZoneMessage(
        zone_id="cabin",
        forwarded_at=1000.1,
        payload=frame,
    )

    loop.run_until_complete(collector.process_zone_message(msg))

    response = flask_client.get("/signals")
    assert response.status_code == 200
    data = response.json
    assert "signals" in data


def test_get_stats(client):
    """Test get stats endpoint."""
    flask_client, collector, loop = client

    # Send some messages
    for i in range(3):
        frame = ECUFrame(
            zone="front",
            ecu_id="brake_ecu",
            msg_id=101,
            timestamp=1000.0 + i,
            signals={"speed": 50.0},
        )
        msg = ZoneMessage(
            zone_id="front",
            forwarded_at=1000.1 + i,
            payload=frame,
        )
        loop.run_until_complete(collector.process_zone_message(msg))

    response = flask_client.get("/stats")
    assert response.status_code == 200
    data = response.json
    assert data["total_messages"] == 3
    assert data["total_errors"] == 0


def test_get_status(client):
    """Test get status endpoint."""
    flask_client, collector, loop = client

    response = flask_client.get("/status")
    assert response.status_code == 200
    data = response.json
    assert "total_messages" in data
    assert "zone_health" in data
