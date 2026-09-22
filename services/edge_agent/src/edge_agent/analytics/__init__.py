"""ANPR analytics: vehicle detection, tracking, plate reading, temporal voting."""

from edge_agent.analytics.pipeline import AnprPipeline, PlateReaderPort, VehicleDetectorPort
from edge_agent.analytics.plate_reader import FastAlprPlateReader, PlateCandidate
from edge_agent.analytics.tracker import SimpleTracker, TrackedVehicle, TrackerConfig
from edge_agent.analytics.vehicle_detector import VehicleDetection, VehicleDetector
from edge_agent.analytics.voting import PlateVoter, VotedPlate

__all__ = [
    "AnprPipeline",
    "FastAlprPlateReader",
    "PlateCandidate",
    "PlateReaderPort",
    "PlateVoter",
    "SimpleTracker",
    "TrackedVehicle",
    "TrackerConfig",
    "VehicleDetection",
    "VehicleDetector",
    "VehicleDetectorPort",
    "VotedPlate",
]
