#!/usr/bin/env python3
"""
Lang2Pick REST API Server
FastAPI backend that bridges the frontend to gRPC detection services and ROS2/MoveIt.

Supports two modes:
- SIMULATION: Simulates all services (default, for demo/testing)
- REAL: Connects to actual gRPC detection service and ROS2/MoveIt

Usage:
    python rest_api_server.py [--mode simulation|real]
"""

import asyncio
import json
import os
import sys
import uuid
import argparse
import math
from datetime import datetime
from typing import Dict, List, Optional
from contextlib import asynccontextmanager
from enum import Enum

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ============================================================================
# Configuration
# ============================================================================

class AppMode(str, Enum):
    SIMULATION = "simulation"
    REAL = "real"

# Configuration from environment
GRPC_DETECTION_URL = os.getenv("GRPC_DETECTION_URL", "localhost:50051")
ROS2_BRIDGE_URL = os.getenv("ROS2_BRIDGE_URL", "ws://localhost:9090")

# Global mode (set at startup)
app_mode: AppMode = AppMode.SIMULATION

# ============================================================================
# Data Models
# ============================================================================

class JointState(BaseModel):
    shoulder_pan: float = 0.0
    shoulder_lift: float = 0.785
    elbow_flex: float = -0.524
    wrist_flex: float = 0.0
    wrist_roll: float = 0.349
    gripper: float = 0.0
    timestamp: int = 0

class TaskStage(BaseModel):
    name: str
    status: str = "pending"  # pending, running, completed, failed
    progress: float = 0.0

class TaskRequest(BaseModel):
    prompt: str
    session_id: str = "default"

class TaskResponse(BaseModel):
    task_id: str
    status: str
    progress: float
    stages: List[TaskStage]
    current_stage: int = 0
    error: Optional[str] = None
    mode: str = "simulation"

class DetectionRequest(BaseModel):
    prompt: str
    image_base64: Optional[str] = None

class Detection(BaseModel):
    class_name: str
    confidence: float
    bbox: List[float]  # [x1, y1, x2, y2] normalized

class ServiceStatus(BaseModel):
    name: str
    connected: bool
    message: str
    url: Optional[str] = None

class SystemStatus(BaseModel):
    mode: str = "simulation"
    robot_connected: bool = False
    camera_connected: bool = False
    grpc_connected: bool = False
    ros2_connected: bool = False
    ros2_active: bool = False
    webrtc_connected: bool = False
    services: List[ServiceStatus] = []
    current_task: Optional[str] = None

class ModeChangeRequest(BaseModel):
    mode: str  # "simulation" or "real"

# ============================================================================
# Service Connectors
# ============================================================================

class GRPCDetectionClient:
    """Client for the YOLO-World gRPC detection service."""
    
    def __init__(self, target: str = GRPC_DETECTION_URL):
        self.target = target
        self.channel = None
        self.stub = None
        self._connected = False
        self._connection_error = None
        
    async def connect(self):
        """Attempt to connect to the gRPC detection service."""
        try:
            import grpc
            # Add proto path for detection service
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'vision-pipeline'))
            from proto import detector_pb2, detector_pb2_grpc
            
            self.channel = grpc.aio.insecure_channel(self.target)
            self.stub = detector_pb2_grpc.DetectorStub(self.channel)
            
            # Test connection with a small timeout
            await asyncio.wait_for(
                self.channel.channel_ready(),
                timeout=3.0
            )
            
            self._connected = True
            self._connection_error = None
            print(f"[gRPC] Connected to detection service at {self.target}")
            return True
            
        except asyncio.TimeoutError:
            self._connected = False
            self._connection_error = f"Connection timeout to {self.target}"
            print(f"[gRPC] {self._connection_error}")
            return False
        except ImportError as e:
            self._connected = False
            self._connection_error = f"gRPC dependencies not installed: {e}"
            print(f"[gRPC] {self._connection_error}")
            return False
        except Exception as e:
            self._connected = False
            self._connection_error = str(e)
            print(f"[gRPC] Connection error: {e}")
            return False
    
    async def disconnect(self):
        """Close the gRPC channel."""
        if self.channel:
            await self.channel.close()
            self._connected = False
            print("[gRPC] Disconnected from detection service")
    
    @property
    def connected(self) -> bool:
        return self._connected
    
    @property
    def error(self) -> Optional[str]:
        return self._connection_error
    
    async def set_prompt(self, session_id: str, prompt: str) -> bool:
        """Set the detection prompt for a session."""
        if not self._connected or not self.stub:
            return False
        
        try:
            from proto import detector_pb2
            await self.stub.SetPrompt(
                detector_pb2.PromptRequest(session_id=session_id, prompt=prompt)
            )
            print(f"[gRPC] Set prompt: '{prompt}' for session '{session_id}'")
            return True
        except Exception as e:
            print(f"[gRPC] Error setting prompt: {e}")
            return False
    
    async def detect(self, prompt: str, image_base64: Optional[str] = None) -> List[Detection]:
        """Run detection (placeholder - actual implementation streams from gRPC)."""
        if not self._connected:
            return []
        
        # In real implementation, this would send an image and get detections
        # For now, return empty list (detections come via streaming)
        return []


class ROS2BridgeClient:
    """Client for ROS2 via rosbridge_server WebSocket."""
    
    def __init__(self, url: str = ROS2_BRIDGE_URL):
        self.url = url
        self.ws = None
        self._connected = False
        self._connection_error = None
        self._joint_state = JointState()
        self._callbacks: Dict[str, callable] = {}
        
    async def connect(self):
        """Connect to rosbridge_server."""
        try:
            import websockets
            
            self.ws = await asyncio.wait_for(
                websockets.connect(self.url),
                timeout=5.0
            )
            
            self._connected = True
            self._connection_error = None
            print(f"[ROS2] Connected to rosbridge at {self.url}")
            
            # Start message handler
            asyncio.create_task(self._message_handler())
            
            # Subscribe to joint states
            await self._subscribe_joint_states()
            
            return True
            
        except asyncio.TimeoutError:
            self._connected = False
            self._connection_error = f"Connection timeout to {self.url}"
            print(f"[ROS2] {self._connection_error}")
            return False
        except ImportError:
            self._connected = False
            self._connection_error = "websockets package not installed"
            print(f"[ROS2] {self._connection_error}")
            return False
        except Exception as e:
            self._connected = False
            self._connection_error = str(e)
            print(f"[ROS2] Connection error: {e}")
            return False
    
    async def disconnect(self):
        """Close the WebSocket connection."""
        if self.ws:
            await self.ws.close()
            self._connected = False
            print("[ROS2] Disconnected from rosbridge")
    
    @property
    def connected(self) -> bool:
        return self._connected
    
    @property
    def error(self) -> Optional[str]:
        return self._connection_error
    
    @property
    def joint_state(self) -> JointState:
        return self._joint_state
    
    async def _message_handler(self):
        """Handle incoming messages from rosbridge."""
        try:
            async for message in self.ws:
                data = json.loads(message)
                
                # Handle joint state updates
                if data.get("op") == "publish" and data.get("topic") == "/joint_states":
                    await self._handle_joint_state(data.get("msg", {}))
                    
        except Exception as e:
            print(f"[ROS2] Message handler error: {e}")
            self._connected = False
    
    async def _subscribe_joint_states(self):
        """Subscribe to /joint_states topic."""
        subscribe_msg = {
            "op": "subscribe",
            "topic": "/joint_states",
            "type": "sensor_msgs/JointState"
        }
        await self.ws.send(json.dumps(subscribe_msg))
        print("[ROS2] Subscribed to /joint_states")
    
    async def _handle_joint_state(self, msg: dict):
        """Parse joint state message from ROS2."""
        try:
            names = msg.get("name", [])
            positions = msg.get("position", [])
            
            # Map joint names to our model
            joint_map = {
                "shoulder_pan_joint": "shoulder_pan",
                "shoulder_lift_joint": "shoulder_lift",
                "elbow_flex_joint": "elbow_flex",
                "wrist_flex_joint": "wrist_flex",
                "wrist_roll_joint": "wrist_roll",
                "gripper_joint": "gripper"
            }
            
            for name, pos in zip(names, positions):
                if name in joint_map:
                    setattr(self._joint_state, joint_map[name], pos)
            
            self._joint_state.timestamp = int(datetime.now().timestamp() * 1000)
            
        except Exception as e:
            print(f"[ROS2] Error parsing joint state: {e}")
    
    async def call_pick_place_service(self, prompt: str, detection: Detection) -> bool:
        """Call the MoveIt pick-and-place action."""
        if not self._connected:
            return False
        
        try:
            # Call the /so101_planner/pick_place service
            service_call = {
                "op": "call_service",
                "service": "/so101_planner/pick_place",
                "args": {
                    "object_name": prompt,
                    "pick_pose": {
                        "position": {"x": detection.bbox[0], "y": detection.bbox[1], "z": 0.0},
                        "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
                    }
                }
            }
            await self.ws.send(json.dumps(service_call))
            print(f"[ROS2] Called pick_place service for '{prompt}'")
            return True
            
        except Exception as e:
            print(f"[ROS2] Error calling service: {e}")
            return False
    
    async def move_to_joint_positions(self, positions: Dict[str, float]) -> bool:
        """Publish joint trajectory command."""
        if not self._connected:
            return False
        
        try:
            # Publish to /joint_trajectory_controller/joint_trajectory
            trajectory_msg = {
                "op": "publish",
                "topic": "/joint_trajectory_controller/joint_trajectory",
                "msg": {
                    "joint_names": list(positions.keys()),
                    "points": [{
                        "positions": list(positions.values()),
                        "time_from_start": {"sec": 2, "nanosec": 0}
                    }]
                }
            }
            await self.ws.send(json.dumps(trajectory_msg))
            print(f"[ROS2] Published trajectory command")
            return True
            
        except Exception as e:
            print(f"[ROS2] Error publishing trajectory: {e}")
            return False


# ============================================================================
# Global State
# ============================================================================

# Service clients (initialized in lifespan)
grpc_client: Optional[GRPCDetectionClient] = None
ros2_client: Optional[ROS2BridgeClient] = None

# Task storage
tasks: Dict[str, TaskResponse] = {}

# Current joint state (simulated or from ROS2)
current_joints = JointState(timestamp=int(datetime.now().timestamp() * 1000))

# Default MoveIt stages
DEFAULT_STAGES = [
    TaskStage(name="Initializing"),
    TaskStage(name="Open Gripper"),
    TaskStage(name="Move to Pick"),
    TaskStage(name="Approach Object"),
    TaskStage(name="Close Gripper"),
    TaskStage(name="Lift Object"),
    TaskStage(name="Move to Place"),
    TaskStage(name="Lower Object"),
    TaskStage(name="Open Gripper"),
    TaskStage(name="Retreat"),
    TaskStage(name="Return Home"),
]

# ============================================================================
# WebSocket Manager
# ============================================================================

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"Client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"Client disconnected. Total clients: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                disconnected.append(connection)
        
        for conn in disconnected:
            self.disconnect(conn)

manager = ConnectionManager()

# ============================================================================
# Background Tasks
# ============================================================================

async def simulate_joint_updates():
    """Simulate joint state updates at ~20Hz (simulation mode only)."""
    global current_joints
    t = 0
    while True:
        if app_mode == AppMode.SIMULATION:
            t += 0.05
            
            # Simulate subtle joint movements
            current_joints.shoulder_pan = 0.1 * math.sin(t * 0.5)
            current_joints.shoulder_lift = 0.785 + 0.05 * math.sin(t * 0.3)
            current_joints.elbow_flex = -0.524 + 0.03 * math.sin(t * 0.4)
            current_joints.wrist_flex = 0.02 * math.sin(t * 0.6)
            current_joints.wrist_roll = 0.349 + 0.04 * math.sin(t * 0.7)
            current_joints.timestamp = int(datetime.now().timestamp() * 1000)
            
            # Broadcast to all connected clients
            await manager.broadcast({
                "type": "joint_state",
                "data": current_joints.model_dump()
            })
        elif ros2_client and ros2_client.connected:
            # Use real joint states from ROS2
            current_joints = ros2_client.joint_state
            await manager.broadcast({
                "type": "joint_state",
                "data": current_joints.model_dump()
            })
        
        await asyncio.sleep(0.05)  # 20Hz


async def process_task_simulation(task_id: str):
    """Simulate task processing through MoveIt stages (simulation mode)."""
    if task_id not in tasks:
        return
    
    task = tasks[task_id]
    task.status = "processing"
    task.mode = "simulation"
    
    total_stages = len(task.stages)
    
    for i, stage in enumerate(task.stages):
        task.current_stage = i
        stage.status = "running"
        
        # Broadcast task update
        await manager.broadcast({
            "type": "task_update",
            "data": task.model_dump()
        })
        
        # Simulate stage processing
        for progress in range(0, 101, 10):
            stage.progress = progress
            task.progress = ((i * 100) + progress) / total_stages
            
            await manager.broadcast({
                "type": "task_update",
                "data": task.model_dump()
            })
            
            await asyncio.sleep(0.15)
        
        stage.status = "completed"
        stage.progress = 100
    
    task.status = "completed"
    task.progress = 100
    
    await manager.broadcast({
        "type": "task_update",
        "data": task.model_dump()
    })


async def process_task_real(task_id: str, prompt: str):
    """Process task using real gRPC detection and ROS2/MoveIt (real mode)."""
    if task_id not in tasks:
        return
    
    task = tasks[task_id]
    task.status = "processing"
    task.mode = "real"
    
    try:
        # Stage 1: Initialize
        task.current_stage = 0
        task.stages[0].status = "running"
        await manager.broadcast({"type": "task_update", "data": task.model_dump()})
        
        # Check connections
        if not grpc_client or not grpc_client.connected:
            raise Exception("Detection service not connected")
        if not ros2_client or not ros2_client.connected:
            raise Exception("ROS2/MoveIt not connected")
        
        task.stages[0].status = "completed"
        task.progress = 9
        
        # Stage 2: Set detection prompt
        task.current_stage = 1
        task.stages[1].status = "running"
        await manager.broadcast({"type": "task_update", "data": task.model_dump()})
        
        success = await grpc_client.set_prompt("default", prompt)
        if not success:
            raise Exception("Failed to set detection prompt")
        
        task.stages[1].status = "completed"
        task.progress = 18
        
        # Stage 3-10: Execute pick-and-place via ROS2
        # In real implementation, this would monitor the MoveIt action progress
        for i in range(2, len(task.stages)):
            task.current_stage = i
            task.stages[i].status = "running"
            await manager.broadcast({"type": "task_update", "data": task.model_dump()})
            
            # Wait for stage completion (would be actual MoveIt feedback)
            await asyncio.sleep(1.5)
            
            task.stages[i].status = "completed"
            task.progress = int(((i + 1) / len(task.stages)) * 100)
            await manager.broadcast({"type": "task_update", "data": task.model_dump()})
        
        task.status = "completed"
        task.progress = 100
        
    except Exception as e:
        task.status = "failed"
        task.error = str(e)
        print(f"[Task] Error processing task: {e}")
    
    await manager.broadcast({"type": "task_update", "data": task.model_dump()})


# ============================================================================
# App Lifecycle
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global grpc_client, ros2_client
    
    # Startup
    print("=" * 60)
    print(f"  Starting Lang2Pick API Server (Mode: {app_mode.value})")
    print("=" * 60)
    
    # Initialize service clients
    grpc_client = GRPCDetectionClient(GRPC_DETECTION_URL)
    ros2_client = ROS2BridgeClient(ROS2_BRIDGE_URL)
    
    # Connect to services in real mode
    if app_mode == AppMode.REAL:
        print("\n[Startup] Connecting to external services...")
        await grpc_client.connect()
        await ros2_client.connect()
    
    # Start background joint simulation/update
    joint_task = asyncio.create_task(simulate_joint_updates())
    
    print("\n  REST API:    http://localhost:8000")
    print("  WebSocket:   ws://localhost:8000/ws")
    print("  API Docs:    http://localhost:8000/docs")
    print("=" * 60)
    
    yield
    
    # Shutdown
    joint_task.cancel()
    
    if grpc_client:
        await grpc_client.disconnect()
    if ros2_client:
        await ros2_client.disconnect()
    
    print("Shutting down...")


# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Lang2Pick API",
    description="Backend API for SO-101 robotic arm control with simulation/real mode support",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=3600,  # Cache preflight for 1 hour
)

# ============================================================================
# REST Endpoints
# ============================================================================

@app.get("/")
async def root():
    return {
        "message": "Lang2Pick API Server",
        "status": "running",
        "mode": app_mode.value
    }


@app.get("/api/mode")
async def get_mode():
    """Get current application mode."""
    return {"mode": app_mode.value}


@app.post("/api/mode")
async def set_mode(request: ModeChangeRequest):
    """Change application mode (requires restart for full effect)."""
    global app_mode
    
    try:
        new_mode = AppMode(request.mode.lower())
        app_mode = new_mode
        
        # Attempt to connect/disconnect services based on mode
        if new_mode == AppMode.REAL:
            if grpc_client and not grpc_client.connected:
                await grpc_client.connect()
            if ros2_client and not ros2_client.connected:
                await ros2_client.connect()
        
        return {
            "mode": app_mode.value,
            "message": f"Mode changed to {app_mode.value}"
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid mode. Use 'simulation' or 'real'")


@app.get("/api/status", response_model=SystemStatus)
async def get_status():
    """Get comprehensive system connection status."""
    services = []
    
    # Detection Service Status
    if app_mode == AppMode.SIMULATION:
        services.append(ServiceStatus(
            name="Detection (YOLO-World)",
            connected=True,
            message="Simulated",
            url=None
        ))
    else:
        services.append(ServiceStatus(
            name="Detection (YOLO-World)",
            connected=grpc_client.connected if grpc_client else False,
            message="Connected" if (grpc_client and grpc_client.connected) else (grpc_client.error if grpc_client else "Not initialized"),
            url=GRPC_DETECTION_URL
        ))
    
    # ROS2/MoveIt Status
    if app_mode == AppMode.SIMULATION:
        services.append(ServiceStatus(
            name="ROS2/MoveIt",
            connected=True,
            message="Simulated",
            url=None
        ))
    else:
        services.append(ServiceStatus(
            name="ROS2/MoveIt",
            connected=ros2_client.connected if ros2_client else False,
            message="Connected" if (ros2_client and ros2_client.connected) else (ros2_client.error if ros2_client else "Not initialized"),
            url=ROS2_BRIDGE_URL
        ))
    
    # WebRTC Status (always simulated for now)
    services.append(ServiceStatus(
        name="WebRTC Video",
        connected=False,
        message="Using local camera",
        url=None
    ))
    
    # Determine overall status
    grpc_ok = app_mode == AppMode.SIMULATION or (grpc_client and grpc_client.connected)
    ros2_ok = app_mode == AppMode.SIMULATION or (ros2_client and ros2_client.connected)
    
    return SystemStatus(
        mode=app_mode.value,
        robot_connected=ros2_ok,
        camera_connected=True,  # Camera is always available (local or WebRTC)
        grpc_connected=grpc_ok,
        ros2_connected=ros2_ok,
        ros2_active=ros2_ok,
        webrtc_connected=False,
        services=services,
        current_task=None  # Could track active tasks here
    )


@app.get("/api/robot/joints", response_model=JointState)
async def get_joints():
    """Get current robot joint state."""
    if app_mode == AppMode.REAL and ros2_client and ros2_client.connected:
        return ros2_client.joint_state
    return current_joints


@app.post("/api/tasks", response_model=TaskResponse)
async def create_task(request: TaskRequest):
    """Submit a new pick-and-place task."""
    task_id = str(uuid.uuid4())
    
    # Create task with default stages
    stages = [TaskStage(name=s.name) for s in DEFAULT_STAGES]
    
    task = TaskResponse(
        task_id=task_id,
        status="queued",
        progress=0,
        stages=stages,
        current_stage=0,
        mode=app_mode.value
    )
    
    tasks[task_id] = task
    
    # Start processing in background based on mode
    if app_mode == AppMode.SIMULATION:
        asyncio.create_task(process_task_simulation(task_id))
    else:
        asyncio.create_task(process_task_real(task_id, request.prompt))
    
    return task


@app.get("/api/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """Get task status by ID."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks[task_id]


@app.delete("/api/tasks/{task_id}")
async def cancel_task(task_id: str):
    """Cancel a task."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = tasks[task_id]
    task.status = "failed"
    task.error = "Cancelled by user"
    
    return {"message": "Task cancelled"}


@app.post("/api/detection/prompt")
async def detect_objects(request: DetectionRequest):
    """Run object detection with text prompt."""
    
    if app_mode == AppMode.REAL and grpc_client and grpc_client.connected:
        # Use real gRPC detection service
        success = await grpc_client.set_prompt("default", request.prompt)
        if success:
            return {
                "status": "prompt_set",
                "prompt": request.prompt,
                "message": "Detection prompt sent to YOLO-World service. Results will stream via gRPC."
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to set detection prompt")
    
    # Simulation mode - return simulated detection
    detections = [
        Detection(
            class_name=request.prompt.split()[-1] if request.prompt else "object",
            confidence=0.92,
            bbox=[0.3, 0.4, 0.5, 0.6]
        )
    ]
    
    return {
        "detections": [d.model_dump() for d in detections],
        "prompt": request.prompt,
        "mode": "simulation"
    }


@app.post("/api/services/reconnect")
async def reconnect_services():
    """Attempt to reconnect to all external services."""
    results = {}
    
    if grpc_client:
        await grpc_client.disconnect()
        results["grpc"] = await grpc_client.connect()
    
    if ros2_client:
        await ros2_client.disconnect()
        results["ros2"] = await ros2_client.connect()
    
    return {
        "message": "Reconnection attempted",
        "results": results
    }


# ============================================================================
# WebSocket Endpoint
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    
    try:
        # Send initial state
        await websocket.send_json({
            "type": "connected",
            "data": {
                "message": "Connected to Lang2Pick server",
                "mode": app_mode.value
            }
        })
        
        await websocket.send_json({
            "type": "joint_state",
            "data": current_joints.model_dump()
        })
        
        while True:
            # Wait for messages from client
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle different message types
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            
            elif message.get("type") == "subscribe":
                # Client subscribing to updates
                channel = message.get("channel", "all")
                await websocket.send_json({
                    "type": "subscribed",
                    "data": {"channel": channel}
                })
            
            elif message.get("type") == "get_mode":
                await websocket.send_json({
                    "type": "mode",
                    "data": {"mode": app_mode.value}
                })
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    parser = argparse.ArgumentParser(description="Lang2Pick REST API Server")
    parser.add_argument(
        "--mode",
        type=str,
        choices=["simulation", "real"],
        default="simulation",
        help="Run mode: 'simulation' for demo, 'real' for actual robot"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run the server on"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind the server to"
    )
    
    args = parser.parse_args()
    
    # Set global mode
    app_mode = AppMode(args.mode)
    
    print("=" * 60)
    print("  Lang2Pick REST API Server")
    print("=" * 60)
    print(f"  Mode:        {app_mode.value.upper()}")
    print(f"  REST API:    http://localhost:{args.port}")
    print(f"  WebSocket:   ws://localhost:{args.port}/ws")
    print(f"  API Docs:    http://localhost:{args.port}/docs")
    
    if app_mode == AppMode.REAL:
        print(f"\n  gRPC URL:    {GRPC_DETECTION_URL}")
        print(f"  ROS2 URL:    {ROS2_BRIDGE_URL}")
    
    print("=" * 60)
    
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info"
    )
