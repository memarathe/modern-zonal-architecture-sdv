"""
Zonal Architecture Simulator - Modern vehicle architecture simulation in Python.

This package provides:
- ECU simulations for generating sensor data
- Zone controllers for aggregating messages
- Central compute for validation and storage
- REST API for data access
- Comprehensive test suite
"""

__version__ = "1.0.0"
__author__ = "Backend Engineer"

from messages import ECUFrame, ZoneMessage, CentralMessage, ZoneHealth, ValidationError

__all__ = [
    "ECUFrame",
    "ZoneMessage", 
    "CentralMessage",
    "ZoneHealth",
    "ValidationError",
]
