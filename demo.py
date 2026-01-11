#!/usr/bin/env python
"""
Quick demo script to show the zonal architecture simulator in action.
"""
import asyncio
import time
from messages import ECUFrame, ZoneMessage
from central import CentralCollector, CentralValidator, CentralStorage, HealthMonitor
from zones import FrontZone, CabinZone, PowertrainZone


async def demo():
    """Run a simple demo."""
    print("=" * 70)
    print("ZONAL ARCHITECTURE SIMULATOR - Demo")
    print("=" * 70)
    
    # Create zones
    print("\n[1] Creating zone controllers...")
    front_zone = FrontZone()
    cabin_zone = CabinZone()
    powertrain_zone = PowertrainZone()
    print("    ✓ Front, Cabin, and Powertrain zones created")
    
    # Create central compute
    print("\n[2] Creating central compute...")
    validator = CentralValidator()
    storage = CentralStorage()
    monitor = HealthMonitor()
    await monitor.register_zone("front")
    await monitor.register_zone("cabin")
    await monitor.register_zone("powertrain")
    collector = CentralCollector(validator, storage, monitor)
    print("    ✓ Validator, Storage, Health Monitor, Collector initialized")
    
    # Simulate some messages
    print("\n[3] Simulating ECU messages...")
    
    # Front zone - brake ECU
    brake_frame = ECUFrame(
        zone="front",
        ecu_id="brake_ecu",
        msg_id=101,
        timestamp=time.time(),
        signals={"wheel_speed_fl": 52.3, "wheel_speed_fr": 51.8, "brake_pressure": 75.0}
    )
    brake_msg = ZoneMessage(zone_id="front", forwarded_at=time.time(), payload=brake_frame)
    
    # Cabin zone - climate ECU
    climate_frame = ECUFrame(
        zone="cabin",
        ecu_id="climate_ecu",
        msg_id=201,
        timestamp=time.time(),
        signals={"cabin_temperature": 22.1, "humidity": 55.2}
    )
    climate_msg = ZoneMessage(zone_id="cabin", forwarded_at=time.time(), payload=climate_frame)
    
    # Powertrain zone - engine ECU
    engine_frame = ECUFrame(
        zone="powertrain",
        ecu_id="engine_ecu",
        msg_id=102,
        timestamp=time.time(),
        signals={"rpm": 3200.0, "engine_temp": 92.5}
    )
    engine_msg = ZoneMessage(zone_id="powertrain", forwarded_at=time.time(), payload=engine_frame)
    
    print("    ✓ Brake ECU (front zone)")
    print("    ✓ Climate ECU (cabin zone)")
    print("    ✓ Engine ECU (powertrain zone)")
    
    # Process messages through collector
    print("\n[4] Processing messages through zones and central compute...")
    await collector.process_zone_message(brake_msg)
    await collector.process_zone_message(climate_msg)
    await collector.process_zone_message(engine_msg)
    print("    ✓ All 3 messages processed successfully")
    
    # Query results
    print("\n[5] Querying stored data...")
    
    status = await collector.get_status()
    print(f"    • Total messages processed: {status['total_messages']}")
    print(f"    • Total errors: {status['total_errors']}")
    
    all_signals = await storage.get_latest_signals()
    print(f"    • Active zones: {len(all_signals)}")
    for zone_id, signals in all_signals.items():
        print(f"      - {zone_id.upper()}: {len(signals)} ECUs")
        for ecu_id, ecu_signals in signals.items():
            print(f"        - {ecu_id}: {len(ecu_signals)} signals")
    
    # Zone health
    print("\n[6] Zone health status:")
    all_health = await monitor.get_all_health()
    for zone_id, health in all_health.items():
        status_str = "✓ ALIVE" if health["is_alive"] else "✗ OFFLINE"
        print(f"    {zone_id.upper():12} {status_str:10} | Messages: {health['message_count']:3} | Errors: {health['error_count']}")
    
    # Example API-like access
    print("\n[7] Sample API responses (as if from REST endpoint):")
    
    brake_signals = await storage.get_latest_signals("front")
    if brake_signals.get("brake_ecu"):
        ws = brake_signals["brake_ecu"]["wheel_speed_fl"]
        print(f"    • GET /zones/front/signals → wheel_speed_fl: {ws}")
    
    all_messages = await storage.get_messages(limit=10)
    print(f"    • GET /zones/*/messages?limit=10 → {len(all_messages)} total messages")
    
    print(f"    • GET /stats → total_messages: {status['total_messages']}, total_errors: {status['total_errors']}")
    
    print("\n" + "=" * 70)
    print("Demo complete! The system is ready for:")
    print("  • Running the full simulator: python run_simulation.py")
    print("  • Running the API server: simulator.start_api()")
    print("  • Running tests: pytest tests/ -v")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(demo())
