"""WebRTC client tailored for Windows hosts.

Captures a media stream from a DirectShow camera (or local file) and publishes
it to the ingress WebRTC server for testing Vision Language Assistant.
"""

import argparse
import asyncio
import json
import logging
import os
import pathlib
import platform
from typing import Optional

import aiohttp
import cv2
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.contrib.media import MediaPlayer
from av import VideoFrame

logging.basicConfig(level=logging.INFO)


def _is_windows() -> bool:
    return os.name == "nt" or platform.system().lower() == "windows"


class CameraVideoTrack(VideoStreamTrack):
    """Video stream backed by OpenCV for USB cameras on Windows."""

    def __init__(self, index: int, video_size: Optional[str], fps: Optional[int]):
        super().__init__()
        self._cap = cv2.VideoCapture(index, cv2.CAP_DSHOW if _is_windows() else 0)
        if not self._cap.isOpened():
            raise RuntimeError(f"Unable to open camera index {index}")

        width = height = None
        if video_size and "x" in video_size:
            try:
                width, height = map(int, video_size.lower().split("x"))
            except ValueError as exc:
                raise ValueError(
                    f"Invalid video size '{video_size}', expected WIDTHxHEIGHT"
                ) from exc

        if width:
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        if height:
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if fps:
            self._cap.set(cv2.CAP_PROP_FPS, fps)
        self._target_fps = fps

    def _read_frame(self):
        ret, frame = self._cap.read()
        if not ret:
            raise RuntimeError("Failed to read frame from camera")
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return frame

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        loop = asyncio.get_running_loop()
        frame = await loop.run_in_executor(None, self._read_frame)
        video_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        video_frame.pts = pts
        video_frame.time_base = time_base
        return video_frame

    async def stop(self):
        await super().stop()
        if self._cap.isOpened():
            self._cap.release()


def _build_media_player(
    source: str, video_size: Optional[str], fps: Optional[int]
) -> MediaPlayer:
    """Create a MediaPlayer configured for Windows DirectShow devices."""
    player_kwargs = {}
    stream_source = source

    # Treat an existing file path as-is, otherwise assume a DirectShow device.
    if not pathlib.Path(source).expanduser().exists():
        if _is_windows():
            # DirectShow expects device names prefixed by "video=".
            if not source.startswith("video="):
                stream_source = f"video={source}"
            player_kwargs["format"] = "dshow"
        else:
            logging.warning("Source %s not found, attempting to open as is.", source)

    options = {}
    if video_size:
        options["video_size"] = video_size
    if fps:
        options["framerate"] = str(fps)
    if options:
        player_kwargs["options"] = options

    return MediaPlayer(stream_source, **player_kwargs)


async def run(
    server_url: str,
    source: Optional[str],
    session_id: str,
    video_size: Optional[str],
    fps: Optional[int],
    camera_index: Optional[int],
):
    pc = RTCPeerConnection()
    closeables = []

    if source:
        player = _build_media_player(source, video_size, fps)
        closeables.append(player)
        if player.video:
            pc.addTrack(player.video)
        else:
            raise RuntimeError(f"No video track available from source '{source}'")
    else:
        if camera_index is None:
            raise ValueError("Either --source or --camera-index must be provided")
        camera_track = CameraVideoTrack(camera_index, video_size, fps)
        closeables.append(camera_track)
        pc.addTrack(camera_track)

    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)

    payload = {
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type,
        "session_id": session_id,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(server_url, data=json.dumps(payload)) as resp:
            resp.raise_for_status()
            ans = await resp.json()

    await pc.setRemoteDescription(
        RTCSessionDescription(sdp=ans["sdp"], type=ans["type"])
    )
    logging.info("Connected to WebRTC ingress, streaming from %s", source)

    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        pass
    finally:
        await pc.close()
        for closeable in closeables:
            stop = getattr(closeable, "stop", None)
            if asyncio.iscoroutinefunction(stop):
                await stop()
            elif callable(stop):
                stop()


def main():
    if _is_windows():
        # Windows requires the selector event loop for aiortc.
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]

    parser = argparse.ArgumentParser(description="Windows-friendly WebRTC client")
    parser.add_argument(
        "--server",
        default="http://localhost:8080/offer",
        help="Signaling URL for the ingress server",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Path to a media file or DirectShow camera name. If omitted, --camera-index is used.",
    )
    parser.add_argument(
        "--camera-index",
        type=int,
        default=0,
        help="OpenCV camera index for USB cameras",
    )
    parser.add_argument(
        "--session-id",
        default="default",
        help="Session identifier that gRPC uses to match streams",
    )
    parser.add_argument(
        "--video-size",
        default="1280x720",
        help="Desired capture resolution WIDTHxHEIGHT",
    )
    parser.add_argument("--fps", type=int, default=30, help="Capture framerate")
    args = parser.parse_args()

    asyncio.run(
        run(
            args.server,
            args.source,
            args.session_id,
            args.video_size,
            args.fps,
            args.camera_index,
        )
    )


if __name__ == "__main__":
    main()
