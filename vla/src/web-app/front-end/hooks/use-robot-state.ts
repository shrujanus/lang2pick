'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { 
  wsClient, 
  apiClient, 
  type JointState, 
  type WebSocketMessage,
  radToDeg 
} from '@/lib/api-client'

interface UseRobotStateOptions {
  pollingInterval?: number // Fallback polling interval in ms
  useWebSocket?: boolean
}

interface UseRobotStateReturn {
  joints: JointState | null
  jointsDegrees: JointsDegrees | null
  isConnected: boolean
  error: string | null
  gripperOpen: boolean
  refresh: () => Promise<void>
}

export interface JointsDegrees {
  joint1: number // shoulder_pan
  joint2: number // shoulder_lift
  joint3: number // elbow_flex
  joint4: number // wrist_flex
  joint5: number // wrist_roll
  joint6: number // gripper
}

const DEFAULT_JOINTS: JointState = {
  shoulder_pan: 0,
  shoulder_lift: 0.785, // ~45 degrees
  elbow_flex: -0.524, // ~-30 degrees
  wrist_flex: 0,
  wrist_roll: 0.349, // ~20 degrees
  gripper: 0,
  timestamp: Date.now(),
}

export function useRobotState(options: UseRobotStateOptions = {}): UseRobotStateReturn {
  const { pollingInterval = 100, useWebSocket = true } = options

  const [joints, setJoints] = useState<JointState | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const unsubscribeRef = useRef<(() => void) | null>(null)

  // Convert radians to degrees for visualization
  const jointsDegrees: JointsDegrees | null = joints ? {
    joint1: radToDeg(joints.shoulder_pan),
    joint2: radToDeg(joints.shoulder_lift),
    joint3: radToDeg(joints.elbow_flex),
    joint4: radToDeg(joints.wrist_flex),
    joint5: radToDeg(joints.wrist_roll),
    joint6: radToDeg(joints.gripper),
  } : null

  const gripperOpen = joints ? joints.gripper < 0.3 : true

  // Fetch joint state via REST API
  const fetchJointState = useCallback(async () => {
    try {
      const state = await apiClient.getJointState()
      setJoints(state)
      setIsConnected(true)
      setError(null)
    } catch (e) {
      // On error, use default values for demo
      if (!joints) {
        setJoints(DEFAULT_JOINTS)
      }
      setError(e instanceof Error ? e.message : 'Failed to fetch joint state')
      setIsConnected(false)
    }
  }, [joints])

  // Handle WebSocket joint state updates
  const handleJointUpdate = useCallback((message: WebSocketMessage) => {
    if (message.type === 'joint_state') {
      setJoints(message.data as JointState)
      setIsConnected(true)
      setError(null)
    }
  }, [])

  useEffect(() => {
    if (useWebSocket) {
      // Connect via WebSocket for real-time updates
      wsClient.connect()
      unsubscribeRef.current = wsClient.subscribe('joint_state', handleJointUpdate)

      // Initial fetch
      fetchJointState()
    } else {
      // Fall back to polling
      fetchJointState()
      pollingRef.current = setInterval(fetchJointState, pollingInterval)
    }

    return () => {
      if (unsubscribeRef.current) {
        unsubscribeRef.current()
      }
      if (pollingRef.current) {
        clearInterval(pollingRef.current)
      }
    }
  }, [useWebSocket, pollingInterval, handleJointUpdate, fetchJointState])

  return {
    joints,
    jointsDegrees,
    isConnected,
    error,
    gripperOpen,
    refresh: fetchJointState,
  }
}

// Simulated robot state for demo/development
export function useSimulatedRobotState(): UseRobotStateReturn {
  const [joints, setJoints] = useState<JointState>(DEFAULT_JOINTS)
  const animationRef = useRef<number | null>(null)
  const timeRef = useRef(0)

  useEffect(() => {
    const animate = () => {
      timeRef.current += 0.016 // ~60fps
      const t = timeRef.current

      setJoints({
        shoulder_pan: Math.sin(t * 0.8) * 0.785, // ±45°
        shoulder_lift: 0.785 + Math.sin(t * 1.2) * 0.436, // 45° ± 25°
        elbow_flex: -0.524 + Math.cos(t * 1.5) * 0.524, // -30° ± 30°
        wrist_flex: Math.sin(t * 2) * 0.524, // ±30°
        wrist_roll: 0.349 + Math.cos(t * 1.8) * 0.262, // 20° ± 15°
        gripper: Math.sin(t * 2) > 0 ? 0.7 : 0.1,
        timestamp: Date.now(),
      })

      animationRef.current = requestAnimationFrame(animate)
    }

    animationRef.current = requestAnimationFrame(animate)

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
    }
  }, [])

  const jointsDegrees: JointsDegrees = {
    joint1: radToDeg(joints.shoulder_pan),
    joint2: radToDeg(joints.shoulder_lift),
    joint3: radToDeg(joints.elbow_flex),
    joint4: radToDeg(joints.wrist_flex),
    joint5: radToDeg(joints.wrist_roll),
    joint6: radToDeg(joints.gripper),
  }

  return {
    joints,
    jointsDegrees,
    isConnected: true,
    error: null,
    gripperOpen: joints.gripper < 0.3,
    refresh: async () => {},
  }
}
