"""Lightweight message definitions for the vision pipeline.

These dataclasses keep the services decoupled from FlatBuffers so the
pipeline can run locally and under test without generated code. When you
are ready to switch to FlatBuffers, mirror these fields and swap the
serialization layer.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple
import json
import time
import uuid
import numpy as np


def _now_ns() -> int:
    return time.time_ns()


@dataclass
class FrameMessage:
    session_id: str
    frame_id: str
    timestamp_ns: int
    image: np.ndarray  # HWC uint8
    intrinsics: Optional[List[float]] = None
    shm_handle: Optional[str] = None
    offset: int = 0

    @staticmethod
    def new(
        image: np.ndarray,
        session_id: str = "default",
        intrinsics: Optional[List[float]] = None,
    ) -> "FrameMessage":
        return FrameMessage(
            session_id=session_id,
            frame_id=str(uuid.uuid4()),
            timestamp_ns=_now_ns(),
            image=image,
            intrinsics=intrinsics,
        )


@dataclass
class Detection:
    bbox: Tuple[float, float, float, float]  # x1, y1, x2, y2
    score: float
    label: str


@dataclass
class DetectionMessage:
    session_id: str
    frame_id: str
    detections: List[Detection] = field(default_factory=list)
    embeddings: Optional[np.ndarray] = None
    shm_handle: Optional[str] = None


@dataclass
class PoseMessage:
    session_id: str
    frame_id: str
    quaternion: Tuple[float, float, float, float]
    translation: Tuple[float, float, float]
    confidence: float


@dataclass
class CombinedResult:
    session_id: str
    frame_id: str
    detections: DetectionMessage
    pose: PoseMessage


def to_bytes(obj) -> bytes:
    """Simple JSON serialization for transport/testing."""

    def _encode(val):
        if isinstance(val, np.ndarray):
            return val.tolist()
        if hasattr(val, "__dict__"):
            return asdict(val)
        return val

    return json.dumps(obj, default=_encode).encode()
