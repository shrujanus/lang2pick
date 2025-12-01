"""Local end-to-end pipeline runner tying together the stub services.

This keeps everything in-process with asyncio queues so you can validate the
control/data flow without GPU drivers or FlatBuffers. Swap each component
for the production implementation once ready.
"""

import asyncio
import logging

from shared_memory_ring.ring import SharedMemoryRing
from webrtc_ingress.main import synthetic_frame_producer
from yolo_world_service.main import HotSwappableYOLOWorld, PromptManager, process_frames
from fundationpose_service.main import (
    HotSwappableFoundationPose,
    IntrinsicsManager,
    process_detections,
)
from result_aggregator.main import ResultAggregator

logging.basicConfig(level=logging.INFO)


async def detection_router(
    det_in: asyncio.Queue, det_out_fp: asyncio.Queue, aggregator: ResultAggregator
):
    """Fan out detections to pose estimator and aggregator."""
    while True:
        det_msg = await det_in.get()
        await det_out_fp.put(det_msg)
        await aggregator.add_detection(det_msg)


async def pose_router(pose_in: asyncio.Queue, aggregator: ResultAggregator):
    """Send poses to aggregator."""
    while True:
        pose_msg = await pose_in.get()
        await aggregator.add_pose(pose_msg)


async def consume_results(
    aggregator: ResultAggregator, session_id: str, limit: int = 3
):
    seen = 0
    async for result in aggregator.start_session(session_id):
        if result:
            logging.info(
                "CombinedResult: frame=%s pose=%s", result.frame_id, result.pose
            )
            seen += 1
            if seen >= limit:
                break


async def main():
    session_id = "default"
    ring = SharedMemoryRing(size=8, frame_shape=(480, 640, 3))

    frame_queue: asyncio.Queue = asyncio.Queue()
    detection_queue_in: asyncio.Queue = asyncio.Queue()
    detection_queue_fp: asyncio.Queue = asyncio.Queue()
    pose_queue: asyncio.Queue = asyncio.Queue()

    yolo_engine = HotSwappableYOLOWorld()
    prompt_manager = PromptManager()
    fp_engine = HotSwappableFoundationPose()
    intrinsics_manager = IntrinsicsManager()
    aggregator = ResultAggregator()

    tasks = [
        asyncio.create_task(synthetic_frame_producer(frame_queue, ring, fps=5)),
        asyncio.create_task(
            process_frames(yolo_engine, prompt_manager, frame_queue, detection_queue_in)
        ),
        asyncio.create_task(
            detection_router(detection_queue_in, detection_queue_fp, aggregator)
        ),
        asyncio.create_task(
            process_detections(
                fp_engine, intrinsics_manager, detection_queue_fp, pose_queue
            )
        ),
        asyncio.create_task(pose_router(pose_queue, aggregator)),
        asyncio.create_task(consume_results(aggregator, session_id)),
    ]

    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in tasks:
        t.cancel()


if __name__ == "__main__":
    asyncio.run(main())
