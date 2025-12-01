"""RunPod serverless handler for promptable detection + pose (stubbed).

This keeps a minimal dependency set and reuses the in-repo stub engines.
Swap HotSwappableYOLOWorld/HotSwappableFoundationPose with real TensorRT
implementations and keep the handler contract stable.
"""

import base64
from io import BytesIO
import logging
from typing import Any, Dict

import numpy as np
from PIL import Image
import runpod

from common.messages import FrameMessage, DetectionMessage
from yolo_world_service.main import HotSwappableYOLOWorld, PromptManager
from fundationpose_service.main import HotSwappableFoundationPose, IntrinsicsManager

logging.basicConfig(level=logging.INFO)

# Initialize models/managers at import time to avoid cold-start penalties.
YOLO_ENGINE = HotSwappableYOLOWorld()
PROMPT_MANAGER = PromptManager()
POSE_ENGINE = HotSwappableFoundationPose()
INTRINSICS_MANAGER = IntrinsicsManager()


def _decode_image_b64(image_b64: str) -> np.ndarray:
    data = base64.b64decode(image_b64)
    with BytesIO(data) as bio:
        img = Image.open(bio).convert("RGB")
        return np.array(img)


async def handler(event: Dict[str, Any]) -> Dict[str, Any]:
    """Run promptable detection + pose on a single frame.

    Expected event payload:
    {
      "session_id": "default",
      "prompt": "red bottle",
      "image_b64": "<base64-encoded JPEG/PNG>"
    }
    """
    session_id = event.get("session_id", "default")
    prompt = event.get("prompt", "object")
    image_b64 = event.get("image_b64")
    if not image_b64:
        raise ValueError("image_b64 is required")

    # Update prompts for this session.
    await PROMPT_MANAGER.update_prompts(session_id, [prompt])

    # Decode image and build frame message.
    image_np = _decode_image_b64(image_b64)
    frame_msg = FrameMessage.new(image_np, session_id=session_id)

    # Run YOLO-World (stub) -> DetectionMessage.
    detection_msg: DetectionMessage = await YOLO_ENGINE.infer(frame_msg.image, [prompt])
    detection_msg.session_id = session_id
    detection_msg.frame_id = frame_msg.frame_id

    # Run pose (stub) -> PoseMessage.
    K = INTRINSICS_MANAGER.intrinsics.get(session_id, np.eye(3, dtype=np.float32))
    pose_msg = await POSE_ENGINE.infer(detection_msg, K)

    return {
        "session_id": session_id,
        "frame_id": frame_msg.frame_id,
        "prompt": prompt,
        "detections": [
            {
                "bbox": det.bbox,
                "score": det.score,
                "label": det.label,
            }
            for det in detection_msg.detections
        ],
        "pose": {
            "quaternion": pose_msg.quaternion,
            "translation": pose_msg.translation,
            "confidence": pose_msg.confidence,
        },
    }


runpod.serverless.start({"handler": handler})
