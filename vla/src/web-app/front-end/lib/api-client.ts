/**
 * API Client for Lang2Pick Web Application
 * 
 * Provides:
 * - REST API client for task management
 * - WebSocket client for real-time updates
 * - WebRTC client for video streaming
 */

// ============================================================================
// Configuration
// ============================================================================

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws'
const WEBRTC_SIGNALING_URL = process.env.NEXT_PUBLIC_WEBRTC_URL || 'http://localhost:8080/offer'

// ============================================================================
// Types
// ============================================================================

export interface JointState {
  shoulder_pan: number
  shoulder_lift: number
  elbow_flex: number
  wrist_flex: number
  wrist_roll: number
  gripper: number
  timestamp: number
}

export interface Detection {
  bbox: [number, number, number, number]
  score: number
  label: string
}

export interface PoseEstimate {
  quaternion: [number, number, number, number]
  translation: [number, number, number]
  confidence: number
}

export interface TaskStage {
  name: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress: number
  message?: string
}

export interface TaskResponse {
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

export interface PickPlaceRequest {
  prompt: string
  session_id?: string
}

export interface ServiceStatus {
  name: string
  connected: boolean
  latency_ms?: number
}

export interface SystemStatus {
  mode: 'simulation' | 'real'
  robot_connected: boolean
  camera_connected: boolean
  grpc_connected: boolean
  ros2_connected: boolean
  ros2_active: boolean
  webrtc_connected: boolean
  services: ServiceStatus[]
  timestamp?: number
}

export interface WebSocketMessage {
  type: string
  data: unknown
  timestamp: number
}

// ============================================================================
// Utilities
// ============================================================================

export function radToDeg(rad: number): number {
  return rad * (180 / Math.PI)
}

export function degToRad(deg: number): number {
  return deg * (Math.PI / 180)
}

// ============================================================================
// REST API Client
// ============================================================================

class APIClient {
  private baseUrl: string

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl
  }

  private async fetch<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    })

    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`)
    }

    return response.json()
  }

  // System Status
  async getSystemStatus(): Promise<SystemStatus> {
    try {
      return await this.fetch<SystemStatus>('/api/status')
    } catch {
      // Return default status when API unavailable
      return {
        mode: 'simulation',
        robot_connected: false,
        camera_connected: false,
        grpc_connected: false,
        ros2_connected: false,
        ros2_active: false,
        webrtc_connected: false,
        services: [],
      }
    }
  }

  async setMode(mode: 'simulation' | 'real'): Promise<{ mode: string }> {
    return this.fetch('/api/mode', {
      method: 'POST',
      body: JSON.stringify({ mode }),
    })
  }

  async reconnectServices(): Promise<{ results: { grpc: boolean; ros2: boolean } }> {
    return this.fetch('/api/reconnect', { method: 'POST' })
  }

  // Tasks
  async getTasks(): Promise<TaskResponse[]> {
    return this.fetch<TaskResponse[]>('/api/tasks')
  }

  async getTask(taskId: string): Promise<TaskResponse> {
    return this.fetch<TaskResponse>(`/api/tasks/${taskId}`)
  }

  async submitTask(request: PickPlaceRequest): Promise<TaskResponse> {
    return this.fetch<TaskResponse>('/api/tasks', {
      method: 'POST',
      body: JSON.stringify(request),
    })
  }

  async cancelTask(taskId: string): Promise<void> {
    await this.fetch(`/api/tasks/${taskId}/cancel`, { method: 'POST' })
  }

  // Robot
  async getJointState(): Promise<JointState> {
    return this.fetch<JointState>('/api/robot/joints')
  }

  async homeRobot(): Promise<void> {
    await this.fetch('/api/robot/home', { method: 'POST' })
  }

  async stopRobot(): Promise<void> {
    await this.fetch('/api/robot/stop', { method: 'POST' })
  }

  // Detection
  async setPrompt(sessionId: string, prompt: string): Promise<void> {
    await this.fetch('/api/detection/prompt', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, prompt }),
    })
  }

  async getDetections(sessionId: string): Promise<Detection[]> {
    return this.fetch<Detection[]>(`/api/detection/${sessionId}`)
  }
}

export const apiClient = new APIClient()

// ============================================================================
// WebSocket Client
// ============================================================================

type MessageHandler = (message: WebSocketMessage) => void

class WebSocketClient {
  private url: string
  private ws: WebSocket | null = null
  private handlers: Map<string, Set<MessageHandler>> = new Map()
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private reconnectDelay = 1000

  constructor(url: string = WS_URL) {
    this.url = url
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return
    }

    try {
      this.ws = new WebSocket(this.url)

      this.ws.onopen = () => {
        console.log('[WebSocket] Connected')
        this.reconnectAttempts = 0
      }

      this.ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data)
          this.dispatch(message)
        } catch (e) {
          console.error('[WebSocket] Failed to parse message:', e)
        }
      }

      this.ws.onclose = () => {
        console.log('[WebSocket] Disconnected')
        this.scheduleReconnect()
      }

      this.ws.onerror = (error) => {
        console.error('[WebSocket] Error:', error)
      }
    } catch (e) {
      console.error('[WebSocket] Connection failed:', e)
      this.scheduleReconnect()
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.log('[WebSocket] Max reconnect attempts reached')
      return
    }

    this.reconnectAttempts++
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1)

    setTimeout(() => {
      console.log(`[WebSocket] Reconnecting (attempt ${this.reconnectAttempts})...`)
      this.connect()
    }, delay)
  }

  disconnect(): void {
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }

  subscribe(messageType: string, handler: MessageHandler): () => void {
    if (!this.handlers.has(messageType)) {
      this.handlers.set(messageType, new Set())
    }
    this.handlers.get(messageType)!.add(handler)

    // Return unsubscribe function
    return () => {
      this.handlers.get(messageType)?.delete(handler)
    }
  }

  private dispatch(message: WebSocketMessage): void {
    const handlers = this.handlers.get(message.type)
    if (handlers) {
      handlers.forEach((handler) => handler(message))
    }

    // Also dispatch to wildcard handlers
    const wildcardHandlers = this.handlers.get('*')
    if (wildcardHandlers) {
      wildcardHandlers.forEach((handler) => handler(message))
    }
  }

  send(type: string, data: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type, data }))
    }
  }
}

export const wsClient = new WebSocketClient()

// ============================================================================
// WebRTC Client
// ============================================================================

interface WebRTCOptions {
  sessionId: string
}

type DetectionCallback = (detections: Detection[]) => void
type StreamCallback = (stream: MediaStream) => void

class WebRTCClient {
  private pc: RTCPeerConnection | null = null
  private signalingUrl: string
  private detectionCallback: DetectionCallback | null = null
  private dataChannel: RTCDataChannel | null = null

  constructor(signalingUrl: string = WEBRTC_SIGNALING_URL) {
    this.signalingUrl = signalingUrl
  }

  async connect(options: WebRTCOptions, onStream: StreamCallback): Promise<void> {
    const { sessionId } = options

    // Create peer connection
    this.pc = new RTCPeerConnection({
      iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
    })

    // Handle incoming tracks
    this.pc.ontrack = (event) => {
      if (event.streams && event.streams[0]) {
        onStream(event.streams[0])
      }
    }

    // Create data channel for detections
    this.dataChannel = this.pc.createDataChannel('detections')
    this.dataChannel.onmessage = (event) => {
      try {
        const detections = JSON.parse(event.data) as Detection[]
        this.detectionCallback?.(detections)
      } catch (e) {
        console.error('[WebRTC] Failed to parse detections:', e)
      }
    }

    // Create offer
    const offer = await this.pc.createOffer({
      offerToReceiveVideo: true,
      offerToReceiveAudio: false,
    })
    await this.pc.setLocalDescription(offer)

    // Wait for ICE gathering
    await new Promise<void>((resolve) => {
      if (this.pc!.iceGatheringState === 'complete') {
        resolve()
      } else {
        const checkState = () => {
          if (this.pc!.iceGatheringState === 'complete') {
            this.pc!.removeEventListener('icegatheringstatechange', checkState)
            resolve()
          }
        }
        this.pc!.addEventListener('icegatheringstatechange', checkState)
      }
    })

    // Send offer to signaling server
    const response = await fetch(this.signalingUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sdp: this.pc.localDescription!.sdp,
        type: this.pc.localDescription!.type,
        session_id: sessionId,
      }),
    })

    if (!response.ok) {
      throw new Error(`Signaling failed: ${response.status}`)
    }

    const answer = await response.json()
    await this.pc.setRemoteDescription(new RTCSessionDescription(answer))
  }

  onDetection(callback: DetectionCallback): void {
    this.detectionCallback = callback
  }

  disconnect(): void {
    if (this.dataChannel) {
      this.dataChannel.close()
      this.dataChannel = null
    }
    if (this.pc) {
      this.pc.close()
      this.pc = null
    }
  }
}

export const webrtcClient = new WebRTCClient()
