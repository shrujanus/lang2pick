import { NextResponse } from 'next/server'

// Backend service URLs - configure via environment
const GRPC_BACKEND = process.env.GRPC_BACKEND_URL || 'http://localhost:50051'
const ROS2_BRIDGE = process.env.ROS2_BRIDGE_URL || 'http://localhost:9090'

export interface SystemStatus {
  robot_connected: boolean
  camera_connected: boolean
  grpc_connected: boolean
  ros2_active: boolean
  current_task?: string
  timestamp: number
}

async function checkGrpcConnection(): Promise<boolean> {
  try {
    const response = await fetch(`${GRPC_BACKEND}/health`, { 
      method: 'GET',
      signal: AbortSignal.timeout(2000),
    })
    return response.ok
  } catch {
    return false
  }
}

async function checkRos2Connection(): Promise<boolean> {
  try {
    const response = await fetch(`${ROS2_BRIDGE}/`, {
      method: 'GET', 
      signal: AbortSignal.timeout(2000),
    })
    return response.ok
  } catch {
    return false
  }
}

export async function GET() {
  try {
    const [grpcConnected, ros2Active] = await Promise.all([
      checkGrpcConnection(),
      checkRos2Connection(),
    ])

    const status: SystemStatus = {
      robot_connected: ros2Active,
      camera_connected: true, // Will be updated by WebRTC connection status
      grpc_connected: grpcConnected,
      ros2_active: ros2Active,
      timestamp: Date.now(),
    }

    return NextResponse.json(status)
  } catch (error) {
    // Return default status on error
    const status: SystemStatus = {
      robot_connected: false,
      camera_connected: false,
      grpc_connected: false,
      ros2_active: false,
      timestamp: Date.now(),
    }
    
    return NextResponse.json(status)
  }
}
