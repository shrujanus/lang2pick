"""YOLO-World service using ONNX Runtime (with a stub fallback)."""

import asyncio
import logging
from typing import List, Optional
import numpy as np
import onnxruntime as ort

from common.messages import Detection, DetectionMessage, FrameMessage

logging.basicConfig(level=logging.INFO)


class HotSwappableYOLOWorld:
    """Loads an ONNX model into ORT; falls back to a stub if no model path."""

    def __init__(
        self, model_path: Optional[str] = None, provider: str = "CUDAExecutionProvider"
    ):
        self.model_path = model_path
        self.session: Optional[ort.InferenceSession] = None
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
            "Loaded YOLO-World ONNX model from %s with providers %s", path, providers
        )

    async def reload_engine(self, path: str):
        self._load(path)

    async def infer(self, frame: np.ndarray, prompts: List[str]) -> DetectionMessage:
        if self.session is None:
            # Stub inference: return a single bbox covering center region.
            h, w, _ = frame.shape
            bbox = (w * 0.25, h * 0.25, w * 0.75, h * 0.75)
            score = 0.9
            label = prompts[0] if prompts else "object"
            detection = Detection(bbox=bbox, score=score, label=label)
            return DetectionMessage(
                session_id="default",
                frame_id="",
                detections=[detection],
                embeddings=None,
                shm_handle=None,
            )

        # Minimal example; adapt input/output names to your exported model.
        input_name = self.session.get_inputs()[0].name
        # Expect NCHW float32; convert HWC uint8
        img = frame.astype(np.float32) / 255.0
        chw = np.transpose(img, (2, 0, 1))[None, ...]
        outputs = self.session.run(None, {input_name: chw})
        # Expect outputs: bboxes (N,4), scores (N), labels (N)
        bboxes, scores, labels = outputs[:3]
        detections = []
        for bbox, score, label_idx in zip(bboxes, scores, labels):
            label = (
                str(label_idx)
                if isinstance(label_idx, (int, np.integer))
                else str(label_idx)
            )
            detections.append(
                Detection(bbox=tuple(map(float, bbox)), score=float(score), label=label)
            )
        return DetectionMessage(
            session_id="default",
            frame_id="",
            detections=detections,
            embeddings=None,
            shm_handle=None,
        )


class PromptManager:
    def __init__(self):
        self.prompts = {"default": ["object"]}

    async def update_prompts(self, session_id, prompts):
        self.prompts[session_id] = prompts
        logging.info("Prompts updated for session %s: %s", session_id, prompts)


async def process_frames(
    engine: HotSwappableYOLOWorld,
    prompt_manager: PromptManager,
    frame_queue: asyncio.Queue,
    detection_queue: asyncio.Queue,
):
    while True:
        frame_msg: FrameMessage = await frame_queue.get()
        session_id = frame_msg.session_id
        prompts = prompt_manager.prompts.get(session_id, ["object"])
        detection_msg = await engine.infer(frame_msg.image, prompts)
        detection_msg.session_id = session_id
        detection_msg.frame_id = frame_msg.frame_id
        await detection_queue.put(detection_msg)
        logging.info(
            "Detections produced for frame %s session %s",
            frame_msg.frame_id,
            session_id,
        )


async def main():
    engine = HotSwappableYOLOWorld()
    prompt_manager = PromptManager()
    frame_queue: asyncio.Queue = asyncio.Queue()
    detection_queue: asyncio.Queue = asyncio.Queue()

    dummy = np.zeros((480, 640, 3), dtype=np.uint8)
    await frame_queue.put(FrameMessage.new(dummy))

    consumer = asyncio.create_task(
        process_frames(engine, prompt_manager, frame_queue, detection_queue)
    )
    detection = await detection_queue.get()
    logging.info("Detection output: %s", detection)
    consumer.cancel()


if __name__ == "__main__":
    asyncio.run(main())
