import { NextResponse } from 'next/server'

// ROS2 Bridge WebSocket URL
const ROS2_BRIDGE = process.env.ROS2_BRIDGE_URL || 'http://localhost:9090'

export interface JointState {
  shoulder_pan: number
  shoulder_lift: number
  elbow_flex: number
  wrist_flex: number
  wrist_roll: number
  gripper: number
  timestamp: number
}

// Cache for latest joint state
let cachedJointState: JointState | null = null
let lastFetchTime = 0
const CACHE_TTL = 50 // ms

async function fetchJointStateFromROS2(): Promise<JointState> {
  try {
    // Call rosbridge to get joint states
    const response = await fetch(`${ROS2_BRIDGE}/call_service`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        op: 'call_service',
        service: '/get_joint_states',
        type: 'sensor_msgs/JointState',
      }),
      signal: AbortSignal.timeout(2000),
    })

    if (response.ok) {
      const data = await response.json()
      
      // Parse ROS2 JointState message
      if (data.values && data.values.position) {
        const positions = data.values.position
        const names = data.values.name || []
        
        const jointMap: Record<string, number> = {}
        names.forEach((name: string, i: number) => {
          jointMap[name] = positions[i] || 0
        })

        return {
          shoulder_pan: jointMap['shoulder_pan'] || 0,
          shoulder_lift: jointMap['shoulder_lift'] || 0,
          elbow_flex: jointMap['elbow_flex'] || 0,
          wrist_flex: jointMap['wrist_flex'] || 0,
          wrist_roll: jointMap['wrist_roll'] || 0,
          gripper: jointMap['gripper'] || 0,
          timestamp: Date.now(),
        }
      }
    }
  } catch (e) {
    console.error('Failed to fetch joint state from ROS2:', e)
  }

  // Return default/simulated joint state
  return getSimulatedJointState()
}

function getSimulatedJointState(): JointState {
  const t = Date.now() / 1000

  return {
    shoulder_pan: Math.sin(t * 0.8) * 0.785,
    shoulder_lift: 0.785 + Math.sin(t * 1.2) * 0.436,
    elbow_flex: -0.524 + Math.cos(t * 1.5) * 0.524,
    wrist_flex: Math.sin(t * 2) * 0.524,
    wrist_roll: 0.349 + Math.cos(t * 1.8) * 0.262,
    gripper: Math.sin(t * 2) > 0 ? 0.7 : 0.1,
    timestamp: Date.now(),
  }
}

export async function GET() {
  const now = Date.now()

  // Use cached value if fresh enough
  if (cachedJointState && (now - lastFetchTime) < CACHE_TTL) {
    return NextResponse.json(cachedJointState)
  }

  // Fetch new joint state
  const jointState = await fetchJointStateFromROS2()
  
  // Update cache
  cachedJointState = jointState
  lastFetchTime = now

  return NextResponse.json(jointState)
}
