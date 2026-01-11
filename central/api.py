"""
REST API for the zonal architecture simulator.
Built with Flask.
"""
from flask import Flask, jsonify, request
import asyncio
from typing import Optional
from central import CentralCollector


def create_api(collector: CentralCollector) -> Flask:
    """Create and configure Flask API."""
    app = Flask(__name__)

    # Store collector in app context
    app.collector = collector

    @app.route("/health", methods=["GET"])
    def health():
        """Health check endpoint."""
        return jsonify({"status": "ok"}), 200

    @app.route("/zones", methods=["GET"])
    def get_zones():
        """List all zones with health status."""
        try:
            # Get status from collector
            loop = asyncio.new_event_loop()
            status = loop.run_until_complete(collector.get_status())
            loop.close()

            zones = status.get("zone_health", {})
            return jsonify(
                {
                    "zones": zones,
                    "total_zones": len(zones),
                    "active_zones": sum(
                        1 for z in zones.values() if z.get("is_alive")
                    ),
                }
            ), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/zones/<zone_id>", methods=["GET"])
    def get_zone(zone_id: str):
        """Get health status for a specific zone."""
        try:
            loop = asyncio.new_event_loop()
            health = loop.run_until_complete(
                collector.monitor.get_zone_health(zone_id)
            )
            loop.close()

            if not health:
                return jsonify({"error": "Zone not found"}), 404

            return jsonify(health), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/zones/<zone_id>/messages", methods=["GET"])
    def get_zone_messages(zone_id: str):
        """Get messages from a specific zone."""
        try:
            limit = request.args.get("limit", 100, type=int)
            ecu_id = request.args.get("ecu_id", None, type=str)

            loop = asyncio.new_event_loop()
            messages = loop.run_until_complete(
                collector.storage.get_messages(
                    zone_id=zone_id, ecu_id=ecu_id, limit=limit
                )
            )
            loop.close()

            return jsonify(
                {
                    "zone_id": zone_id,
                    "ecu_id": ecu_id,
                    "count": len(messages),
                    "messages": [m.to_dict() for m in messages],
                }
            ), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/zones/<zone_id>/signals", methods=["GET"])
    def get_zone_signals(zone_id: str):
        """Get latest signals from a zone."""
        try:
            loop = asyncio.new_event_loop()
            signals = loop.run_until_complete(
                collector.storage.get_latest_signals(zone_id=zone_id)
            )
            loop.close()

            if not signals:
                return jsonify({"error": "Zone not found"}), 404

            return jsonify(
                {
                    "zone_id": zone_id,
                    "signals": signals,
                }
            ), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/ecus/<ecu_id>/signals", methods=["GET"])
    def get_ecu_signals(ecu_id: str):
        """Get latest signals from a specific ECU."""
        try:
            loop = asyncio.new_event_loop()
            all_signals = loop.run_until_complete(
                collector.storage.get_latest_signals()
            )
            loop.close()

            # Find ECU signals
            ecu_signals = {}
            for zone_signals in all_signals.values():
                if ecu_id in zone_signals:
                    ecu_signals = zone_signals[ecu_id]
                    break

            if not ecu_signals:
                return jsonify({"error": "ECU not found"}), 404

            return jsonify(
                {
                    "ecu_id": ecu_id,
                    "signals": ecu_signals,
                }
            ), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/signals", methods=["GET"])
    def get_all_signals():
        """Get latest signals from all zones."""
        try:
            loop = asyncio.new_event_loop()
            signals = loop.run_until_complete(
                collector.storage.get_latest_signals()
            )
            loop.close()

            return jsonify({"signals": signals}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/stats", methods=["GET"])
    def get_stats():
        """Get system statistics."""
        try:
            loop = asyncio.new_event_loop()
            status = loop.run_until_complete(collector.get_status())
            loop.close()

            return jsonify(
                {
                    "total_messages": status["total_messages"],
                    "total_errors": status["total_errors"],
                    "queue_size": status["queue_size"],
                    "storage": status["storage_stats"],
                }
            ), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/status", methods=["GET"])
    def get_status():
        """Get overall system status."""
        try:
            loop = asyncio.new_event_loop()
            status = loop.run_until_complete(collector.get_status())
            loop.close()

            return jsonify(status), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return app
