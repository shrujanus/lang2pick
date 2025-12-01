import asyncio
import logging
from collections import defaultdict
from common.messages import CombinedResult, Detection, DetectionMessage, PoseMessage

logging.basicConfig(level=logging.INFO)


class ResultAggregator:
    def __init__(self):
        self.sessions = defaultdict(
            lambda: {"detections": {}, "poses": {}, "results": asyncio.Queue()}
        )

    async def start_session(self, session_id):
        """Async generator yielding CombinedResult as they become available."""
        logging.info("Session started: %s", session_id)
        while True:
            try:
                result = await asyncio.wait_for(
                    self.sessions[session_id]["results"].get(), timeout=1.0
                )
                yield result
            except asyncio.TimeoutError:
                yield None

    async def add_detection(self, detection: DetectionMessage):
        self.sessions[detection.session_id]["detections"][
            detection.frame_id
        ] = detection
        await self._try_join(detection.session_id, detection.frame_id)

    async def add_pose(self, pose: PoseMessage):
        self.sessions[pose.session_id]["poses"][pose.frame_id] = pose
        await self._try_join(pose.session_id, pose.frame_id)

    async def _try_join(self, session_id, frame_id):
        detections = self.sessions[session_id]["detections"]
        poses = self.sessions[session_id]["poses"]
        if frame_id in detections and frame_id in poses:
            combined = CombinedResult(
                session_id=session_id,
                frame_id=frame_id,
                detections=detections[frame_id],
                pose=poses[frame_id],
            )
            await self.sessions[session_id]["results"].put(combined)
            del detections[frame_id]
            del poses[frame_id]


async def main():
    aggregator = ResultAggregator()
    session_id = "default"
    # Demo: seed with a detection and pose to showcase join
    detection = DetectionMessage(
        session_id=session_id,
        frame_id="frame-1",
        detections=[Detection(bbox=(0, 0, 10, 10), score=0.9, label="object")],
        embeddings=None,
        shm_handle=None,
    )
    pose = PoseMessage(
        session_id=session_id,
        frame_id="frame-1",
        quaternion=(1, 0, 0, 0),
        translation=(0, 0, 1),
        confidence=0.9,
    )
    await aggregator.add_detection(detection)
    await aggregator.add_pose(pose)
    async for result in aggregator.start_session(session_id):
        if result:
            logging.info(
                "CombinedResult sent for session %s frame %s",
                result.session_id,
                result.frame_id,
            )
            break
        else:
            logging.info("Heartbeat for session %s", session_id)


if __name__ == "__main__":
    asyncio.run(main())
