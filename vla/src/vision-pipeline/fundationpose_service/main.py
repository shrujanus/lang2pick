"""FoundationPose-style pose estimation using ONNX Runtime (with stub fallback)."""

import asyncio
import logging
import numpy as np
import onnxruntime as ort

from common.messages import Detection, DetectionMessage, PoseMessage

logging.basicConfig(level=logging.INFO)


class HotSwappableFoundationPose:
    def __init__(
        self, model_path: str | None = None, provider: str = "CUDAExecutionProvider"
    ):
        self.model_path = model_path
        self.session: ort.InferenceSession | None = None
        self.provider = provider
        if model_path:
            self._load(model_path)

    def _load(self, path: str):
        providers = (
            [self.provider, "CPUExecutionProvider"]
            if self.provider
            else ["CPUExecutionProvider"]
        )
        self.session = ort.InferenceSession(path, providers=providers)
        self.model_path = path
        logging.info(
            "Loaded FoundationPose ONNX model from %s with providers %s",
            path,
            providers,
        )

    async def reload_models(self, model_path: str):
        self._load(model_path)

    async def infer(
        self, detection: DetectionMessage, intrinsics: np.ndarray
    ) -> PoseMessage:
        if not detection.detections:
            raise ValueError("No detections to estimate pose for")

        if self.session is None:
            det = detection.detections[0]
            bbox = det.bbox
            center = ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)
            translation = (center[0], center[1], 1.0)
            quaternion = (1.0, 0.0, 0.0, 0.0)
            return PoseMessage(
                session_id=detection.session_id,
                frame_id=detection.frame_id,
                quaternion=quaternion,
                translation=translation,
                confidence=det.score,
            )

        # Minimal placeholder; adapt to your ONNX FoundationPose outputs.
        # Inputs/outputs names depend on your exported model.
        input_name = self.session.get_inputs()[0].name
        # Example dummy input: bbox center and intrinsics flattened
        det = detection.detections[0]
        bbox = det.bbox
        center = np.array(
            [[(bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0]], dtype=np.float32
        )
        outputs = self.session.run(None, {input_name: center})
        # Expect outputs: quaternion (4,), translation (3,), confidence (1,)
        quat = outputs[0].ravel().tolist() if len(outputs) > 0 else [1, 0, 0, 0]
        trans = (
            outputs[1].ravel().tolist()
            if len(outputs) > 1
            else [center[0, 0], center[0, 1], 1.0]
        )
        conf = float(outputs[2].ravel()[0]) if len(outputs) > 2 else float(det.score)
        return PoseMessage(
            session_id=detection.session_id,
            frame_id=detection.frame_id,
            quaternion=tuple(map(float, quat[:4])),
            translation=tuple(map(float, trans[:3])),
            confidence=conf,
        )


class IntrinsicsManager:
    def __init__(self):
        self.intrinsics = {"default": np.eye(3, dtype=np.float32)}

    async def update_intrinsics(self, session_id, K):
        self.intrinsics[session_id] = K
        logging.info("Intrinsics updated for session %s", session_id)


async def process_detections(
    fp_engine: HotSwappableFoundationPose,
    intrinsics_manager: IntrinsicsManager,
    detection_queue: asyncio.Queue,
    pose_queue: asyncio.Queue,
):
    while True:
        detection_msg: DetectionMessage = await detection_queue.get()
        K = intrinsics_manager.intrinsics.get(
            detection_msg.session_id, np.eye(3, dtype=np.float32)
        )
        pose_msg = await fp_engine.infer(detection_msg, K)
        await pose_queue.put(pose_msg)
        logging.info(
            "Pose produced for frame %s session %s",
            detection_msg.frame_id,
            detection_msg.session_id,
        )


async def main():
    fp_engine = (
        HotSwappableFoundationPose()
    )  # Pass model_path to enable real inference.
    intrinsics_manager = IntrinsicsManager()
    detection_queue: asyncio.Queue = asyncio.Queue()
    pose_queue: asyncio.Queue = asyncio.Queue()

    # Demo: seed with a fake detection
    detection_queue.put_nowait(
        DetectionMessage(
            session_id="default",
            frame_id="frame-1",
            detections=[Detection(bbox=(0, 0, 10, 10), score=0.9, label="object")],
            embeddings=None,
            shm_handle=None,
        )
    )

    consumer = asyncio.create_task(
        process_detections(fp_engine, intrinsics_manager, detection_queue, pose_queue)
    )
    pose = await pose_queue.get()
    logging.info("Pose output: %s", pose)
    consumer.cancel()


if __name__ == "__main__":
    asyncio.run(main())
