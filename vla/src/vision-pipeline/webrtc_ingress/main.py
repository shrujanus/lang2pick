"""Minimal WebRTC ingress using aiortc.

Expose an /offer endpoint that accepts an SDP offer, responds with an answer,
and pushes received video frames into an asyncio queue as FrameMessage objects.
Downstream consumers can read from the returned queue to run inference.
"""

import asyncio
import logging
from typing import Tuple
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRelay

from common.messages import FrameMessage

logging.basicConfig(level=logging.INFO)

relay = MediaRelay()


async def create_webrtc_app(frame_queue: asyncio.Queue) -> web.Application:
    pcs = set()

    async def offer(request: web.Request) -> web.Response:
        params = await request.json()
        sdp = params["sdp"]
        typ = params["type"]
        session_id = params.get("session_id", "default")

        pc = RTCPeerConnection()
        pcs.add(pc)

        @pc.on("track")
        async def on_track(track):
            if track.kind != "video":
                return
            logging.info("Video track received for session %s", session_id)
            local_track = relay.subscribe(track)
            while True:
                frame = await local_track.recv()
                img = frame.to_ndarray(format="rgb24")
                await frame_queue.put(FrameMessage.new(img, session_id=session_id))

        await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type=typ))
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        return web.json_response(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        )

    async def on_shutdown(app):
        coros = [pc.close() for pc in pcs]
        await asyncio.gather(*coros)
        pcs.clear()

    app = web.Application()
    app.router.add_post("/offer", offer)
    app.on_shutdown.append(on_shutdown)
    return app


async def main(
    host: str = "0.0.0.0", port: int = 8080
) -> Tuple[asyncio.Queue, web.AppRunner]:
    frame_queue: asyncio.Queue = asyncio.Queue()
    app = await create_webrtc_app(frame_queue)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    logging.info("WebRTC ingress signaling server on http://%s:%s/offer", host, port)
    await site.start()
    return frame_queue, runner


if __name__ == "__main__":

    async def _demo():
        frame_queue, runner = await main()
        # Drain a few frames to demonstrate reception.
        while True:
            msg: FrameMessage = await frame_queue.get()
            logging.info("Received frame %s (%s)", msg.frame_id, msg.image.shape)

    asyncio.run(_demo())
