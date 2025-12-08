"""
REST API Backend Server for Lang2Pick Web Application

This server provides:
- REST endpoints for task management
- WebSocket for real-time updates (joint states, task progress)
- Bridge to gRPC detection service
- Bridge to ROS2 via rosbridge

Run with: uvicorn rest_api_server:app --host 0.0.0.0 --port 8000 --reload
"""

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set
from enum import Enum

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import grpc
import aiohttp

# Import generated gRPC stubs (if available)
try:
    from proto import detector_pb2, detector_pb2_grpc
    GRPC_AVAILABLE = True
except ImportError:
    GRPC_AVAILABLE = False
    logging.warning("gRPC proto files not found, running in stub mode")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# Configuration
# ============================================================================

GRPC_DETECTION_HOST = "localhost:50051"
WEBRTC_SIGNALING_HOST = "localhost:8080"
ROS2_BRIDGE_HOST = "localhost:9090"

# ============================================================================
# Data Models
# ============================================================================

class TaskStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStageModel(BaseModel):
    name: str
    status: StageStatus = StageStatus.PENDING
    progress: float = 0.0
    message: Optional[str] = None


class DetectionModel(BaseModel):
    bbox: tuple[float, float, float, float]
    score: float
    label: str


class PoseModel(BaseModel):
    quaternion: tuple[float, float, float, float]
    translation: tuple[float, float, float]
    confidence: float


class TaskModel(BaseModel):
    task_id: str
    prompt: str
    status: TaskStatus = TaskStatus.QUEUED
    progress: float = 0.0
    stages: List[TaskStageModel] = []
    current_stage: int = 0
    detections: Optional[List[DetectionModel]] = None
    pose: Optional[PoseModel] = None
    error: Optional[str] = None
    created_at: float = 0.0
    updated_at: float = 0.0


class SubmitTaskRequest(BaseModel):
    prompt: str
    session_id: str = "default"


class SetPromptRequest(BaseModel):
    session_id: str = "default"
    prompt: str


class JointStateModel(BaseModel):
    shoulder_pan: float = 0.0
    shoulder_lift: float = 0.0
    elbow_flex: float = 0.0
    wrist_flex: float = 0.0
    wrist_roll: float = 0.0
    gripper: float = 0.0
    timestamp: float = 0.0


class SystemStatusModel(BaseModel):
    robot_connected: bool = False
    camera_connected: bool = False
    grpc_connected: bool = False
    ros2_active: bool = False
    current_task: Optional[str] = None
    timestamp: float = 0.0


# ============================================================================
# Default Task Stages (MoveIt Task Constructor)
# ============================================================================

DEFAULT_STAGES = [
    TaskStageModel(name="Initializing"),
    TaskStageModel(name="Object Detection"),
    TaskStageModel(name="Pose Estimation"),
    TaskStageModel(name="Open Gripper"),
    TaskStageModel(name="Move to Pick"),
    TaskStageModel(name="Approach Object"),
    TaskStageModel(name="Close Gripper"),
    TaskStageModel(name="Lift Object"),
    TaskStageModel(name="Move to Place"),
    TaskStageModel(name="Lower Object"),
    TaskStageModel(name="Open Gripper"),
    TaskStageModel(name="Retreat"),
    TaskStageModel(name="Return Home"),
]

# ============================================================================
# In-Memory Storage
# ============================================================================

tasks: Dict[str, TaskModel] = {}
active_connections: Set[WebSocket] = set()
current_joint_state = JointStateModel(timestamp=time.time())
system_status = SystemStatusModel(timestamp=time.time())

# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Lang2Pick API",
    description="REST API for Lang2Pick robotic arm control",
    version="1.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# WebSocket Manager
# ============================================================================

async def broadcast_message(message_type: str, data: dict):
    """Broadcast a message to all connected WebSocket clients."""
    message = json.dumps({
        "type": message_type,
        "data": data,
        "timestamp": time.time() * 1000,
    })
    
    disconnected = set()
    for ws in active_connections:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.add(ws)
    
    active_connections.difference_update(disconnected)


# ============================================================================
# gRPC Client
# ============================================================================

class DetectionClient:
    """Client for gRPC detection service."""
    
    def __init__(self, host: str = GRPC_DETECTION_HOST):
        self.host = host
        self.channel = None
        self.stub = None
    
    async def connect(self):
        if not GRPC_AVAILABLE:
            return False
        try:
            self.channel = grpc.aio.insecure_channel(self.host)
            self.stub = detector_pb2_grpc.DetectorStub(self.channel)
            return True
        except Exception as e:
            logger.error(f"gRPC connection failed: {e}")
            return False
    
    async def set_prompt(self, session_id: str, prompt: str) -> bool:
        if not self.stub:
            return False
        try:
            request = detector_pb2.PromptRequest(session_id=session_id, prompt=prompt)
            await self.stub.SetPrompt(request)
            return True
        except Exception as e:
            logger.error(f"SetPrompt failed: {e}")
            return False
    
    async def get_detections(self, session_id: str) -> List[DetectionModel]:
        """Get latest detections (would subscribe to stream in production)."""
        # Stub implementation
        return []


detection_client = DetectionClient()

# ============================================================================
# ROS2 Bridge Client
# ============================================================================

class ROS2BridgeClient:
    """Client for rosbridge WebSocket protocol."""
    
    def __init__(self, host: str = ROS2_BRIDGE_HOST):
        self.url = f"ws://{host}"
        self.http_url = f"http://{host}"
        self.ws = None
        self.connected = False
    
    async def connect(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.http_url, timeout=2) as response:
                    self.connected = response.status == 200
        except Exception:
            self.connected = False
        return self.connected
    
    async def call_service(self, service: str, service_type: str, args: dict) -> dict:
        """Call a ROS2 service via rosbridge."""
        if not self.connected:
            await self.connect()
        
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "op": "call_service",
                    "service": service,
                    "type": service_type,
                    "args": args,
                }
                async with session.post(
                    f"{self.http_url}/call_service",
                    json=payload,
                    timeout=30
                ) as response:
                    if response.status == 200:
                        return await response.json()
        except Exception as e:
            logger.error(f"ROS2 service call failed: {e}")
        return {}
    
    async def get_joint_states(self) -> JointStateModel:
        """Get current joint states from ROS2."""
        # In production, this would subscribe to /joint_states topic
        # For now, return simulated values
        t = time.time()
        return JointStateModel(
            shoulder_pan=0.785 * asyncio.get_event_loop().time() % 1.57 - 0.785,
            shoulder_lift=0.785,
            elbow_flex=-0.524,
            wrist_flex=0.0,
            wrist_roll=0.349,
            gripper=0.1,
            timestamp=t,
        )


ros2_client = ROS2BridgeClient()

# ============================================================================
# Background Tasks
# ============================================================================

async def joint_state_publisher():
    """Periodically publish joint states to WebSocket clients."""
    global current_joint_state
    
    while True:
        try:
            # Get joint state from ROS2 or simulate
            if ros2_client.connected:
                current_joint_state = await ros2_client.get_joint_states()
            else:
                # Simulate joint movement
                t = time.time()
                current_joint_state = JointStateModel(
                    shoulder_pan=0.785 * (t * 0.8 % 2 - 1),
                    shoulder_lift=0.785 + 0.436 * (t * 1.2 % 2 - 1),
                    elbow_flex=-0.524 + 0.524 * (t * 1.5 % 2 - 1),
                    wrist_flex=0.524 * (t * 2 % 2 - 1),
                    wrist_roll=0.349 + 0.262 * (t * 1.8 % 2 - 1),
                    gripper=0.7 if int(t * 2) % 2 == 0 else 0.1,
                    timestamp=t,
                )
            
            await broadcast_message("joint_state", current_joint_state.model_dump())
        except Exception as e:
            logger.error(f"Joint state publisher error: {e}")
        
        await asyncio.sleep(0.05)  # 20Hz update rate


async def process_task(task_id: str):
    """Process a task through all stages."""
    task = tasks.get(task_id)
    if not task:
        return
    
    try:
        task.status = TaskStatus.PROCESSING
        tasks[task_id] = task
        await broadcast_message("task_update", task.model_dump())
        
        for i, stage in enumerate(task.stages):
            task.current_stage = i
            task.stages[i].status = StageStatus.RUNNING
            task.progress = (i / len(task.stages)) * 100
            tasks[task_id] = task
            await broadcast_message("task_update", task.model_dump())
            
            # Simulate stage execution
            await asyncio.sleep(0.5 + 0.5 * (i % 3))
            
            # Stage-specific processing
            if stage.name == "Object Detection":
                # Would call detection_client.set_prompt() and get detections
                task.detections = [
                    DetectionModel(bbox=(100, 100, 200, 200), score=0.95, label="object")
                ]
            elif stage.name == "Pose Estimation":
                task.pose = PoseModel(
                    quaternion=(1.0, 0.0, 0.0, 0.0),
                    translation=(0.15, 0.0, 0.05),
                    confidence=0.92,
                )
            elif stage.name == "Move to Pick" and task.pose:
                # Call ROS2 pick_place service
                await ros2_client.call_service(
                    "/pick_place",
                    "so101_planner/srv/PickPlace",
                    {
                        "pick_pose": {
                            "header": {"frame_id": "world"},
                            "pose": {
                                "position": {
                                    "x": task.pose.translation[0],
                                    "y": task.pose.translation[1],
                                    "z": task.pose.translation[2],
                                },
                                "orientation": {
                                    "x": task.pose.quaternion[1],
                                    "y": task.pose.quaternion[2],
                                    "z": task.pose.quaternion[3],
                                    "w": task.pose.quaternion[0],
                                },
                            },
                        },
                        "place_pose": {
                            "header": {"frame_id": "world"},
                            "pose": {
                                "position": {"x": 0.3, "y": 0.0, "z": 0.1},
                                "orientation": {"x": 0, "y": 0, "z": 0, "w": 1},
                            },
                        },
                        "object_id": "object",
                    }
                )
            
            task.stages[i].status = StageStatus.COMPLETED
            task.stages[i].progress = 100.0
            tasks[task_id] = task
            await broadcast_message("task_update", task.model_dump())
        
        task.status = TaskStatus.COMPLETED
        task.progress = 100.0
        task.updated_at = time.time()
        tasks[task_id] = task
        await broadcast_message("task_update", task.model_dump())
        
    except Exception as e:
        logger.error(f"Task processing error: {e}")
        task.status = TaskStatus.FAILED
        task.error = str(e)
        tasks[task_id] = task
        await broadcast_message("task_update", task.model_dump())


# ============================================================================
# REST Endpoints
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize connections and background tasks on startup."""
    # Connect to services
    await detection_client.connect()
    await ros2_client.connect()
    
    # Update system status
    global system_status
    system_status.grpc_connected = GRPC_AVAILABLE
    system_status.ros2_active = ros2_client.connected
    
    # Start background tasks
    asyncio.create_task(joint_state_publisher())
    
    logger.info("Lang2Pick API server started")


@app.get("/api/status", response_model=SystemStatusModel)
async def get_status():
    """Get system status."""
    system_status.timestamp = time.time()
    system_status.ros2_active = ros2_client.connected
    system_status.grpc_connected = GRPC_AVAILABLE
    
    # Check for current processing task
    processing_tasks = [t for t in tasks.values() if t.status == TaskStatus.PROCESSING]
    system_status.current_task = processing_tasks[0].task_id if processing_tasks else None
    
    return system_status


@app.get("/api/tasks", response_model=List[TaskModel])
async def list_tasks():
    """List all tasks."""
    return sorted(tasks.values(), key=lambda t: t.created_at, reverse=True)


@app.post("/api/tasks", response_model=TaskModel)
async def submit_task(request: SubmitTaskRequest):
    """Submit a new task."""
    task_id = f"task-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    now = time.time()
    
    task = TaskModel(
        task_id=task_id,
        prompt=request.prompt,
        status=TaskStatus.QUEUED,
        stages=[TaskStageModel(name=s.name) for s in DEFAULT_STAGES],
        created_at=now,
        updated_at=now,
    )
    
    tasks[task_id] = task
    
    # Start processing in background
    asyncio.create_task(process_task(task_id))
    
    return task


@app.get("/api/tasks/{task_id}", response_model=TaskModel)
async def get_task(task_id: str):
    """Get task by ID."""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    """Cancel a task."""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status in [TaskStatus.QUEUED, TaskStatus.PROCESSING]:
        task.status = TaskStatus.FAILED
        task.error = "Cancelled by user"
        task.updated_at = time.time()
        tasks[task_id] = task
        await broadcast_message("task_update", task.model_dump())
    
    return {"success": True}


@app.get("/api/robot/joints", response_model=JointStateModel)
async def get_joints():
    """Get current joint state."""
    return current_joint_state


@app.post("/api/robot/home")
async def home_robot():
    """Send robot to home position."""
    await ros2_client.call_service(
        "/move_to_named_pose",
        "std_srvs/srv/Trigger",
        {"pose_name": "init"}
    )
    return {"success": True}


@app.post("/api/robot/stop")
async def stop_robot():
    """Emergency stop."""
    await ros2_client.call_service(
        "/emergency_stop",
        "std_srvs/srv/Trigger",
        {}
    )
    return {"success": True}


@app.post("/api/detection/prompt")
async def set_detection_prompt(request: SetPromptRequest):
    """Set detection prompt for a session."""
    success = await detection_client.set_prompt(request.session_id, request.prompt)
    return {"success": success, "session_id": request.session_id, "prompt": request.prompt}


@app.get("/api/detection/{session_id}", response_model=List[DetectionModel])
async def get_detections(session_id: str):
    """Get detections for a session."""
    return await detection_client.get_detections(session_id)


# ============================================================================
# WebSocket Endpoint
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await websocket.accept()
    active_connections.add(websocket)
    logger.info(f"WebSocket connected. Total connections: {len(active_connections)}")
    
    try:
        # Send initial state
        await websocket.send_text(json.dumps({
            "type": "joint_state",
            "data": current_joint_state.model_dump(),
            "timestamp": time.time() * 1000,
        }))
        
        await websocket.send_text(json.dumps({
            "type": "system_status",
            "data": system_status.model_dump(),
            "timestamp": time.time() * 1000,
        }))
        
        # Keep connection alive and handle incoming messages
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                message = json.loads(data)
                
                # Handle client messages
                if message.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                    
            except asyncio.TimeoutError:
                # Send keepalive
                await websocket.send_text(json.dumps({"type": "keepalive"}))
                
    except WebSocketDisconnect:
        pass
    finally:
        active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(active_connections)}")


# ============================================================================
# Health Check
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "grpc_connected": GRPC_AVAILABLE,
        "ros2_connected": ros2_client.connected,
        "active_websockets": len(active_connections),
        "timestamp": time.time(),
    }


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
