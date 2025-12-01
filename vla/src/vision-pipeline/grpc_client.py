"""Simple CLI client for exercising the Detector gRPC service."""

import argparse
import logging
from typing import Optional
import grpc
from proto import detector_pb2, detector_pb2_grpc

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def set_prompt(
    stub: detector_pb2_grpc.DetectorStub, session_id: str, prompt: str
) -> None:
    """Send a SetPrompt RPC to prime the backend."""
    logging.info("Setting prompt for session '%s'", session_id)
    stub.SetPrompt(detector_pb2.PromptRequest(session_id=session_id, prompt=prompt))


def stream_detections(
    stub: detector_pb2_grpc.DetectorStub,
    session_id: str,
    max_messages: Optional[int],
) -> None:
    """Subscribe to detections and log them until interrupted."""
    request = detector_pb2.DetectionStreamRequest(session_id=session_id)
    logging.info("Subscribing to detections (session=%s)", session_id)
    count = 0
    try:
        for box in stub.SubscribeDetections(request):
            count += 1
            logging.info(
                "Detection #%d frame=%s label=%s score=%.3f bbox=%s",
                count,
                box.frame_id,
                box.label,
                box.score,
                list(box.bbox),
            )
            if max_messages and count >= max_messages:
                break
    except KeyboardInterrupt:
        logging.info("Interrupted by user, closing stream.")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Detector gRPC test client")
    parser.add_argument(
        "--target", default="localhost:50051", help="gRPC server host:port"
    )
    parser.add_argument(
        "--session-id", default="default", help="Session identifier used by the server"
    )
    parser.add_argument(
        "--prompt",
        default="Describe what you see.",
        help="Prompt to send before streaming",
    )
    parser.add_argument(
        "--max-messages",
        type=int,
        help="If set, stop after receiving this many detections",
    )
    args = parser.parse_args(argv)

    channel = grpc.insecure_channel(args.target)
    stub = detector_pb2_grpc.DetectorStub(channel)

    set_prompt(stub, args.session_id, args.prompt)
    stream_detections(stub, args.session_id, args.max_messages)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
