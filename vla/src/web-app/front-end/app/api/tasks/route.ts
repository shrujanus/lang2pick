import { NextRequest, NextResponse } from 'next/server'

// In-memory task store (replace with Redis/DB in production)
const tasks = new Map<string, TaskData>()

// ROS2 Bridge URL for calling pick_place service
const ROS2_BRIDGE = process.env.ROS2_BRIDGE_URL || 'http://localhost:9090'
const GRPC_BACKEND = process.env.GRPC_BACKEND_URL || 'http://localhost:50051'

interface TaskData {
  task_id: string
  prompt: string
  status: 'queued' | 'processing' | 'completed' | 'failed'
  progress: number
  stages: TaskStage[]
  current_stage: number
  created_at: number
  updated_at: number
  error?: string
  detections?: Detection[]
  pose?: PoseEstimate
}

interface TaskStage {
  name: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress: number
  message?: string
}

interface Detection {
  bbox: [number, number, number, number]
  score: number
  label: string
}

interface PoseEstimate {
  quaternion: [number, number, number, number]
  translation: [number, number, number]
  confidence: number
}

// Default MoveIt Task Constructor stages
const DEFAULT_STAGES: TaskStage[] = [
  { name: 'Initializing', status: 'pending', progress: 0 },
  { name: 'Object Detection', status: 'pending', progress: 0 },
  { name: 'Pose Estimation', status: 'pending', progress: 0 },
  { name: 'Open Gripper', status: 'pending', progress: 0 },
  { name: 'Move to Pick', status: 'pending', progress: 0 },
  { name: 'Approach Object', status: 'pending', progress: 0 },
  { name: 'Close Gripper', status: 'pending', progress: 0 },
  { name: 'Lift Object', status: 'pending', progress: 0 },
  { name: 'Move to Place', status: 'pending', progress: 0 },
  { name: 'Lower Object', status: 'pending', progress: 0 },
  { name: 'Open Gripper', status: 'pending', progress: 0 },
  { name: 'Retreat', status: 'pending', progress: 0 },
  { name: 'Return Home', status: 'pending', progress: 0 },
]

function generateTaskId(): string {
  return `task-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
}

// GET /api/tasks - List all tasks
export async function GET() {
  const taskList = Array.from(tasks.values())
    .sort((a, b) => b.created_at - a.created_at)
  
  return NextResponse.json(taskList)
}

// POST /api/tasks - Submit a new task
export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { prompt, session_id = 'default' } = body

    if (!prompt || typeof prompt !== 'string') {
      return NextResponse.json(
        { error: 'Prompt is required' },
        { status: 400 }
      )
    }

    const taskId = generateTaskId()
    const now = Date.now()

    const task: TaskData = {
      task_id: taskId,
      prompt,
      status: 'queued',
      progress: 0,
      stages: DEFAULT_STAGES.map(s => ({ ...s })),
      current_stage: 0,
      created_at: now,
      updated_at: now,
    }

    tasks.set(taskId, task)

    // Start task processing in background
    processTask(taskId, prompt, session_id)

    return NextResponse.json(task, { status: 201 })
  } catch (error) {
    console.error('Task submission error:', error)
    return NextResponse.json(
      { error: 'Failed to submit task' },
      { status: 500 }
    )
  }
}

// Background task processing
async function processTask(taskId: string, prompt: string, sessionId: string) {
  const task = tasks.get(taskId)
  if (!task) return

  try {
    // Stage 0: Initializing
    updateTaskStage(taskId, 0, 'running')
    task.status = 'processing'
    tasks.set(taskId, task)

    // Stage 1: Object Detection via gRPC
    updateTaskStage(taskId, 0, 'completed')
    updateTaskStage(taskId, 1, 'running')
    
    const detections = await runDetection(sessionId, prompt)
    if (detections.length > 0) {
      task.detections = detections
    }
    
    updateTaskStage(taskId, 1, 'completed')

    // Stage 2: Pose Estimation
    updateTaskStage(taskId, 2, 'running')
    
    if (task.detections && task.detections.length > 0) {
      const pose = await runPoseEstimation(sessionId, task.detections[0])
      task.pose = pose
    }
    
    updateTaskStage(taskId, 2, 'completed')

    // Stages 3-12: MoveIt Task Constructor via ROS2 Bridge
    for (let i = 3; i < DEFAULT_STAGES.length; i++) {
      updateTaskStage(taskId, i, 'running')
      
      // Call ROS2 pick_place service
      if (i === 4 && task.pose) {
        await callPickPlaceService(task.pose, prompt)
      }
      
      // Simulate stage completion time
      await delay(500 + Math.random() * 500)
      
      updateTaskStage(taskId, i, 'completed')
      
      // Update overall progress
      task.progress = Math.round(((i + 1) / DEFAULT_STAGES.length) * 100)
      task.current_stage = i
      tasks.set(taskId, task)
    }

    // Mark as completed
    task.status = 'completed'
    task.progress = 100
    tasks.set(taskId, task)

  } catch (error) {
    console.error(`Task ${taskId} failed:`, error)
    task.status = 'failed'
    task.error = error instanceof Error ? error.message : 'Unknown error'
    tasks.set(taskId, task)
  }
}

function updateTaskStage(taskId: string, stageIndex: number, status: TaskStage['status']) {
  const task = tasks.get(taskId)
  if (!task) return

  task.stages[stageIndex].status = status
  task.stages[stageIndex].progress = status === 'completed' ? 100 : status === 'running' ? 50 : 0
  task.updated_at = Date.now()
  tasks.set(taskId, task)
}

async function runDetection(sessionId: string, prompt: string): Promise<Detection[]> {
  try {
    // Call gRPC detection service
    const response = await fetch(`${GRPC_BACKEND}/detect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, prompt }),
      signal: AbortSignal.timeout(10000),
    })

    if (response.ok) {
      const data = await response.json()
      return data.detections || []
    }
  } catch (e) {
    console.error('Detection service error:', e)
  }

  // Return mock detection for demo
  return [{
    bbox: [100, 100, 200, 200],
    score: 0.95,
    label: prompt.split(' ').slice(-2).join(' '),
  }]
}

async function runPoseEstimation(sessionId: string, detection: Detection): Promise<PoseEstimate> {
  try {
    const response = await fetch(`${GRPC_BACKEND}/pose`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, detection }),
      signal: AbortSignal.timeout(10000),
    })

    if (response.ok) {
      return await response.json()
    }
  } catch (e) {
    console.error('Pose estimation error:', e)
  }

  // Return mock pose for demo
  const cx = (detection.bbox[0] + detection.bbox[2]) / 2
  const cy = (detection.bbox[1] + detection.bbox[3]) / 2
  
  return {
    quaternion: [1, 0, 0, 0],
    translation: [cx / 1000, cy / 1000, 0.1], // Normalize to meters
    confidence: detection.score,
  }
}

async function callPickPlaceService(pose: PoseEstimate, objectId: string): Promise<void> {
  try {
    // Call ROS2 service via rosbridge
    const response = await fetch(`${ROS2_BRIDGE}/call_service`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        service: '/pick_place',
        type: 'so101_planner/srv/PickPlace',
        args: {
          pick_pose: {
            header: { frame_id: 'world' },
            pose: {
              position: {
                x: pose.translation[0],
                y: pose.translation[1],
                z: pose.translation[2],
              },
              orientation: {
                x: pose.quaternion[1],
                y: pose.quaternion[2],
                z: pose.quaternion[3],
                w: pose.quaternion[0],
              },
            },
          },
          place_pose: {
            header: { frame_id: 'world' },
            pose: {
              position: { x: 0.3, y: 0.0, z: 0.1 },
              orientation: { x: 0, y: 0, z: 0, w: 1 },
            },
          },
          object_id: objectId,
        },
      }),
      signal: AbortSignal.timeout(30000),
    })

    if (!response.ok) {
      console.error('ROS2 service call failed:', await response.text())
    }
  } catch (e) {
    console.error('ROS2 bridge error:', e)
    // Continue execution - this might be in simulation mode
  }
}

function delay(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}

// Export for use in other routes
export { tasks }
