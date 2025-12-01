"""Local YOLO-World inference runner (no pose, no WebRTC)."""

import argparse
import logging
import cv2
from yolo_world_service.main import HotSwappableYOLOWorld, PromptManager
from common.messages import FrameMessage

logging.basicConfig(level=logging.INFO)


def main():
    parser = argparse.ArgumentParser(description="Local YOLO-World inference")
    parser.add_argument(
        "--yolo-model", type=str, required=True, help="Path to YOLO-World ONNX model"
    )
    parser.add_argument(
        "--prompt", type=str, default="object", help="Text prompt for detection"
    )
    parser.add_argument(
        "--source",
        type=str,
        default="0",
        help="Video source (file path or webcam index)",
    )
    args = parser.parse_args()

    cap = cv2.VideoCapture(int(args.source) if args.source.isdigit() else args.source)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open source {args.source}")

    yolo = HotSwappableYOLOWorld(model_path=args.yolo_model)
    prompt_manager = PromptManager()
    session_id = "default"
    # Update prompt (sync call to async method)
    import asyncio

    asyncio.run(prompt_manager.update_prompts(session_id, [args.prompt]))

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        rgb = frame[:, :, ::-1]  # BGR to RGB
        fm = FrameMessage.new(rgb, session_id=session_id)
        det_msg = asyncio.run(yolo.infer(fm.image, [args.prompt]))
        logging.info(
            "Frame %s detections: %s",
            fm.frame_id,
            [(d.label, d.score, d.bbox) for d in det_msg.detections],
        )

    cap.release()


if __name__ == "__main__":
    main()
