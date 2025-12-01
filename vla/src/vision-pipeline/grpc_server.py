"""gRPC + WebRTC ingress server for promptable detection."""

import asyncio
import logging
from collections import defaultdict
from typing import Dict, List
import grpc
from common.messages import FrameMessage
from yolo_world_service.main import HotSwappableYOLOWorld, PromptManager
from webrtc_ingress.main import main as webrtc_main
from proto import detector_pb2, detector_pb2_grpc

logging.basicConfig(level=logging.INFO)


class DetectionBroker:
    """Fan-out detections to subscribers per session."""

    def __init__(self):
        self.subscribers: Dict[str, List[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, session_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.subscribers[session_id].append(q)
        return q

    async def publish(self, session_id: str, det_msg):
        queues = self.subscribers.get(session_id, [])
        for q in queues:
            await q.put(det_msg)


class DetectorService(detector_pb2_grpc.DetectorServicer):
    def __init__(self, prompt_manager: PromptManager, broker: DetectionBroker):
        self.prompt_manager = prompt_manager
        self.broker = broker

    async def SetPrompt(self, request, context):
        await self.prompt_manager.update_prompts(request.session_id, [request.prompt])
        return detector_pb2.Empty()

    async def SubscribeDetections(self, request, context):
        q = self.broker.subscribe(request.session_id or "default")
        try:
            while True:
                det_msg = await q.get()
                yield det_msg
        except asyncio.CancelledError:
            return


async def detection_loop(
    frame_queue: asyncio.Queue,
    yolo: HotSwappableYOLOWorld,
    prompt_manager: PromptManager,
    broker: DetectionBroker,
):
    while True:
        frame_msg: FrameMessage = await frame_queue.get()
        prompts = prompt_manager.prompts.get(frame_msg.session_id, ["object"])
        det = await yolo.infer(frame_msg.image, prompts)
        det.session_id = frame_msg.session_id
        det.frame_id = frame_msg.frame_id

        # Publish each detection as a gRPC DetectionBox message
        for d in det.detections:
            det_box = detector_pb2.DetectionBox(
                session_id=det.session_id,
                frame_id=det.frame_id,
                bbox=list(map(float, d.bbox)),
                score=float(d.score),
                label=d.label,
            )
            await broker.publish(det.session_id, det_box)


async def serve(
    grpc_port: int = 50051,
    webrtc_host: str = "0.0.0.0",
    webrtc_port: int = 8080,
    yolo_model: str | None = None,
):
    yolo = HotSwappableYOLOWorld(model_path=yolo_model)
    prompt_manager = PromptManager()
    broker = DetectionBroker()

    frame_queue, _runner = await webrtc_main(host=webrtc_host, port=webrtc_port)

    server = grpc.aio.server()
    detector_pb2_grpc.add_DetectorServicer_to_server(
        DetectorService(prompt_manager, broker), server
    )
    server.add_insecure_port(f"[::]:{grpc_port}")

    await server.start()
    logging.info("gRPC server listening on :%s", grpc_port)

    detect_task = asyncio.create_task(
        detection_loop(frame_queue, yolo, prompt_manager, broker)
    )
    await server.wait_for_termination()
    detect_task.cancel()


if __name__ == "__main__":
    asyncio.run(serve())
