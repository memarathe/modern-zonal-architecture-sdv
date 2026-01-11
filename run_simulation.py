"""
Main simulation runner - orchestrates ECUs, zones, and central compute.
"""
import asyncio
import threading
from typing import List, Dict
from ecus import (
    BrakeECU,
    EngineECU,
    ClimateECU,
    InfotainmentECU,
    BodyECU,
)
from zones import FrontZone, RearZone, CabinZone, PowertrainZone
from central import CentralCollector, CentralValidator, CentralStorage, HealthMonitor
from central.api import create_api
from messages import ECUFrame, ZoneMessage


class ZonalSimulator:
    """Main simulator coordinating ECUs, zones, and central compute."""

    def __init__(self):
        # Create ECUs
        self.ecus = [
            BrakeECU(),
            EngineECU(),
            ClimateECU(),
            InfotainmentECU(),
            BodyECU(),
        ]

        # Create zones
        self.zones = [
            FrontZone(),
            CabinZone(),
            PowertrainZone(),
        ]

        # Create central compute components
        self.validator = CentralValidator()
        self.storage = CentralStorage()
        self.monitor = HealthMonitor()
        self.collector = CentralCollector(
            self.validator, self.storage, self.monitor
        )

        # Tasks for async operations
        self.tasks: List[asyncio.Task] = []
        self.event_loop: asyncio.AbstractEventLoop = None
        self.loop_thread: threading.Thread = None

    async def initialize(self) -> None:
        """Initialize zones in monitor."""
        for zone in self.zones:
            await self.monitor.register_zone(zone.zone_id)

    def _setup_connections(self) -> None:
        """Set up ECU -> Zone and Zone -> Collector connections."""
        # Connect ECUs to zones
        for ecu in self.ecus:
            # Find matching zone for this ECU
            for zone in self.zones:
                if zone.zone_id == ecu.zone:
                    # Create callback that queues frame to zone
                    def make_callback(z):
                        async def callback(frame: ECUFrame):
                            await z.receive_frame(frame)
                        return callback

                    ecu.set_send_callback(
                        lambda f, z=zone: asyncio.run_coroutine_threadsafe(
                            z.receive_frame(f), self.event_loop
                        )
                    )
                    break

        # Connect zones to central collector
        for zone in self.zones:

            def make_forward_callback(z):
                def callback(msg: ZoneMessage):
                    asyncio.run_coroutine_threadsafe(
                        self.collector.receive_message(msg),
                        self.event_loop,
                    )

                return callback

            zone.set_forward_callback(make_forward_callback(zone))

    def _run_event_loop(self) -> None:
        """Run the asyncio event loop in a separate thread."""
        self.event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.event_loop)

        # Initialize zones
        self.event_loop.run_until_complete(self.initialize())

        # Create and run all tasks
        async def run_all():
            tasks = []

            # Start zones
            for zone in self.zones:
                tasks.append(asyncio.create_task(zone.run()))

            # Start central collector
            tasks.append(asyncio.create_task(self.collector.run()))

            # Keep running
            try:
                await asyncio.gather(*tasks)
            except asyncio.CancelledError:
                pass

        try:
            self.event_loop.run_until_complete(run_all())
        finally:
            self.event_loop.close()

    def start(self) -> None:
        """Start the simulator."""
        print("[Simulator] Starting...")

        # Setup connections
        self._setup_connections()

        # Start event loop in thread
        self.loop_thread = threading.Thread(
            target=self._run_event_loop, daemon=True
        )
        self.loop_thread.start()

        # Start ECUs in threads
        for ecu in self.ecus:
            thread = threading.Thread(
                target=lambda e=ecu: asyncio.run(e.run()), daemon=True
            )
            thread.start()

        print("[Simulator] Started. ECUs and zones running.")

    def stop(self) -> None:
        """Stop the simulator."""
        print("[Simulator] Stopping...")

        # Stop ECUs
        for ecu in self.ecus:
            ecu.stop()

        # Stop zones
        for zone in self.zones:
            zone.stop()

        # Stop collector
        self.collector.stop()

        print("[Simulator] Stopped.")

    def get_status(self) -> Dict:
        """Get simulator status (synchronous wrapper)."""
        if self.event_loop and self.event_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self.collector.get_status(), self.event_loop
            )
            return future.result(timeout=5)
        return {"status": "not running"}

    def start_api(self, host: str = "0.0.0.0", port: int = 5000) -> None:
        """Start the Flask API server."""
        app = create_api(self.collector)
        print(f"[API] Starting on {host}:{port}")
        app.run(host=host, port=port, debug=False, threaded=True)


def main():
    """Main entry point."""
    simulator = ZonalSimulator()
    simulator.start()

    # Keep running
    try:
        import time

        while True:
            time.sleep(5)
            print("\n[Info] System status:")
            print("  ECUs running:", sum(1 for e in simulator.ecus if e.is_running))
            print("  Zones running:", sum(1 for z in simulator.zones if z.is_running))
            print("  Collector running:", simulator.collector.is_running)

    except KeyboardInterrupt:
        print("\n[Info] Shutting down...")
        simulator.stop()


if __name__ == "__main__":
    main()
