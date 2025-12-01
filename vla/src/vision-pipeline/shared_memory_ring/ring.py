"""Minimal shared-memory ring buffer.

This is CPU-backed to keep the pipeline runnable without CUDA. Replace the
storage layer with CUDA IPC or GPU buffers for production.
"""

import multiprocessing.shared_memory as shm
import threading
import numpy as np


class SharedMemoryRing:
    def __init__(self, size, frame_shape, dtype="uint8"):
        self.size = size
        self.frame_shape = frame_shape
        self.dtype = dtype
        self.lock = threading.Lock()
        self.head = 0
        self.tail = 0
        self.buffer = [None] * size
        self.use_shm = True
        try:
            self.shm_blocks = [
                shm.SharedMemory(create=True, size=self._frame_nbytes())
                for _ in range(size)
            ]
        except PermissionError:
            # Fallback in restricted environments
            self.use_shm = False
            self.shm_blocks = [
                np.empty(self.frame_shape, dtype=self.dtype) for _ in range(size)
            ]

    def _frame_nbytes(self):
        return int(np.prod(self.frame_shape)) * np.dtype(self.dtype).itemsize

    def publish_frame(self, frame_np):
        """Copy frame into shared memory slot and return slot id + handle."""
        with self.lock:
            slot_id = self.head
            shm_block = self.shm_blocks[slot_id]
            if self.use_shm:
                np_frame = np.ndarray(
                    self.frame_shape, dtype=self.dtype, buffer=shm_block.buf
                )
                handle = shm_block.name
            else:
                np_frame = shm_block
                handle = f"slot-{slot_id}"
            np.copyto(np_frame, frame_np)
            self.buffer[slot_id] = {"shm_handle": handle, "shape": self.frame_shape}
            self.head = (self.head + 1) % self.size
            return slot_id, handle

    def get_frame(self, slot_id):
        """Return a numpy view of the frame for a given slot id."""
        with self.lock:
            shm_block = self.shm_blocks[slot_id]
            if self.use_shm:
                return np.ndarray(
                    self.frame_shape, dtype=self.dtype, buffer=shm_block.buf
                )
            return shm_block

    def get_shm_handle(self, slot_id):
        with self.lock:
            return self.buffer[slot_id]["shm_handle"]

    def cleanup(self):
        if self.use_shm:
            for block in self.shm_blocks:
                block.close()
                block.unlink()
