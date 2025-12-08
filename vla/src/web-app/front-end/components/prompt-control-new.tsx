'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { RobotArm } from '@/components/robot-arm-new'
import { useWebRTC } from '@/hooks/use-webrtc'
import { useRobotState, useSimulatedRobotState } from '@/hooks/use-robot-state'
import { useTaskQueue, type Task, type TaskStatus } from '@/hooks/use-task-queue'
import { useToast } from '@/hooks/use-toast'
import { apiClient, type Detection, type ServiceStatus, type SystemStatus } from '@/lib/api-client'

// Configuration
const WEBRTC_ENABLED = process.env.NEXT_PUBLIC_WEBRTC_ENABLED === 'true'

interface CameraDevice {
  deviceId: string
  label: string
}

type AppMode = 'simulation' | 'real'

export function PromptControl() {
  const [prompt, setPrompt] = useState('')
  const [appMode, setAppMode] = useState<AppMode>('simulation')
  const [isChangingMode, setIsChangingMode] = useState(false)
  const [systemStatus, setSystemStatus] = useState<SystemStatus>({
    mode: 'simulation',
    robot_connected: false,
    camera_connected: false,
    grpc_connected: false,
    ros2_connected: false,
    ros2_active: false,
    webrtc_connected: false,
    services: [],
  })
  const [detections, setDetections] = useState<Detection[]>([])
  const [availableCameras, setAvailableCameras] = useState<CameraDevice[]>([])
  const [selectedCamera, setSelectedCamera] = useState<string>('')
  
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const localStreamRef = useRef<MediaStream | null>(null)
  
  // Hooks
  const { toast } = useToast()
  
  // Robot state - use simulated or real based on app mode
  const simulatedRobotState = useSimulatedRobotState()
  const realRobotState = useRobotState({ useWebSocket: false, pollingInterval: 100 })
  const robotState = appMode === 'simulation' ? simulatedRobotState : realRobotState

  // WebRTC for live video feed
  const webrtc = useWebRTC({
    sessionId: 'default',
    autoConnect: WEBRTC_ENABLED,
    onDetection: setDetections,
  })

  // Task queue management
  const {
    tasks,
    currentTask,
    isProcessing,
    submitTask,
    cancelTask,
    clearCompleted,
    queuedCount,
    completedCount,
  } = useTaskQueue({
    useWebSocket: false, // Disable WebSocket, use REST polling
    onTaskComplete: (task) => {
      toast({
        title: 'Task Completed',
        description: `"${task.prompt}" finished successfully`,
      })
    },
    onTaskError: (task, error) => {
      toast({
        title: 'Task Failed',
        description: error,
        variant: 'destructive',
      })
    },
  })

  // Enumerate available cameras on mount
  useEffect(() => {
    const enumerateCameras = async () => {
      try {
        // Request permission first to get device labels
        await navigator.mediaDevices.getUserMedia({ video: true })
          .then(stream => stream.getTracks().forEach(track => track.stop()))
        
        const devices = await navigator.mediaDevices.enumerateDevices()
        const videoDevices = devices
          .filter(device => device.kind === 'videoinput')
          .map(device => ({
            deviceId: device.deviceId,
            label: device.label || `Camera ${device.deviceId.slice(0, 8)}...`
          }))
        
        setAvailableCameras(videoDevices)
        
        // Auto-select first camera if none selected
        if (videoDevices.length > 0 && !selectedCamera) {
          setSelectedCamera(videoDevices[0].deviceId)
        }
      } catch (error) {
        console.error('[Camera] Failed to enumerate devices:', error)
      }
    }

    enumerateCameras()

    // Listen for device changes
    navigator.mediaDevices.addEventListener('devicechange', enumerateCameras)
    return () => {
      navigator.mediaDevices.removeEventListener('devicechange', enumerateCameras)
    }
  }, [selectedCamera])

  // Initialize local camera feed (fallback when WebRTC not available)
  useEffect(() => {
    const initLocalCamera = async () => {
      // Skip if WebRTC stream is already connected
      if (webrtc.stream) {
        if (videoRef.current) {
          videoRef.current.srcObject = webrtc.stream
        }
        return
      }

      // Skip if no camera selected
      if (!selectedCamera) {
        return
      }

      // Stop existing stream
      if (localStreamRef.current) {
        localStreamRef.current.getTracks().forEach(track => track.stop())
        localStreamRef.current = null
      }

      // Use selected camera
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ 
          video: { 
            deviceId: selectedCamera ? { exact: selectedCamera } : undefined,
            width: { ideal: 1280 }, 
            height: { ideal: 720 } 
          } 
        })
        localStreamRef.current = stream
        if (videoRef.current) {
          videoRef.current.srcObject = stream
        }
        setSystemStatus(prev => ({ ...prev, camera_connected: true }))
      } catch (error) {
        console.error('[Camera] Failed to access camera:', error)
        setSystemStatus(prev => ({ ...prev, camera_connected: false }))
      }
    }

    initLocalCamera()

    return () => {
      if (localStreamRef.current) {
        localStreamRef.current.getTracks().forEach(track => track.stop())
      }
    }
  }, [webrtc.stream, selectedCamera])

  // Handle camera source change
  const handleCameraChange = useCallback((deviceId: string) => {
    setSelectedCamera(deviceId)
  }, [])

  // Update video source when WebRTC connects
  useEffect(() => {
    if (webrtc.stream && videoRef.current) {
      // Stop local camera
      if (localStreamRef.current) {
        localStreamRef.current.getTracks().forEach(track => track.stop())
        localStreamRef.current = null
      }
      videoRef.current.srcObject = webrtc.stream
      setSystemStatus(prev => ({ ...prev, camera_connected: true }))
    }
  }, [webrtc.stream])

  // Fetch system status periodically
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const status = await apiClient.getSystemStatus()
        setSystemStatus(status)
        setAppMode(status.mode as AppMode)
      } catch {
        // Keep existing status on error
      }
    }

    fetchStatus()
    const interval = setInterval(fetchStatus, 5000)
    return () => clearInterval(interval)
  }, [])

  // Handle mode change
  const handleModeChange = useCallback(async (newMode: AppMode) => {
    setIsChangingMode(true)
    try {
      const response = await apiClient.setMode(newMode)
      setAppMode(response.mode as AppMode)
      toast({
        title: 'Mode Changed',
        description: `Switched to ${response.mode.toUpperCase()} mode`,
      })
      
      // Refresh status after mode change
      const status = await apiClient.getSystemStatus()
      setSystemStatus(status)
    } catch (error) {
      toast({
        title: 'Mode Change Failed',
        description: 'Could not change mode. Check backend server.',
        variant: 'destructive',
      })
    } finally {
      setIsChangingMode(false)
    }
  }, [toast])

  // Handle reconnect services
  const handleReconnect = useCallback(async () => {
    try {
      const result = await apiClient.reconnectServices()
      toast({
        title: 'Reconnection Attempted',
        description: `gRPC: ${result.results.grpc ? '✓' : '✗'}, ROS2: ${result.results.ros2 ? '✓' : '✗'}`,
      })
      
      // Refresh status
      const status = await apiClient.getSystemStatus()
      setSystemStatus(status)
    } catch (error) {
      toast({
        title: 'Reconnection Failed',
        description: 'Could not reconnect to services.',
        variant: 'destructive',
      })
    }
  }, [toast])

  // Draw detection boxes on canvas overlay
  useEffect(() => {
    const canvas = canvasRef.current
    const video = videoRef.current
    if (!canvas || !video || detections.length === 0) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // Match canvas size to video
    canvas.width = video.videoWidth || 1280
    canvas.height = video.videoHeight || 720

    // Clear previous drawings
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    // Draw detection boxes
    detections.forEach(det => {
      const [x1, y1, x2, y2] = det.bbox
      const width = x2 - x1
      const height = y2 - y1

      // Draw box
      ctx.strokeStyle = '#22c55e'
      ctx.lineWidth = 2
      ctx.strokeRect(x1, y1, width, height)

      // Draw label background
      ctx.fillStyle = '#22c55e'
      const label = `${det.label} ${(det.score * 100).toFixed(0)}%`
      const textWidth = ctx.measureText(label).width
      ctx.fillRect(x1, y1 - 20, textWidth + 8, 20)

      // Draw label text
      ctx.fillStyle = '#ffffff'
      ctx.font = '14px monospace'
      ctx.fillText(label, x1 + 4, y1 - 5)
    })
  }, [detections])

  // Handle task submission
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!prompt.trim()) return

    try {
      await submitTask(prompt.trim())
      setPrompt('')
      
      toast({
        title: 'Task Queued',
        description: `"${prompt.trim()}" added to queue`,
      })
    } catch (error) {
      toast({
        title: 'Error',
        description: 'Failed to submit task',
        variant: 'destructive',
      })
    }
  }

  // Set detection prompt when typing
  const handlePromptChange = useCallback(async (value: string) => {
    setPrompt(value)
    
    // Update detection prompt for real-time visualization in real mode
    if (value.trim() && appMode === 'real') {
      try {
        await apiClient.setPrompt('default', value.trim())
      } catch {
        // Ignore errors
      }
    }
  }, [appMode])

  const getStatusColor = (status: TaskStatus) => {
    switch (status) {
      case 'queued':
        return 'bg-muted text-muted-foreground'
      case 'processing':
        return 'bg-accent text-accent-foreground'
      case 'completed':
        return 'bg-primary/20 text-primary'
      case 'failed':
        return 'bg-destructive/20 text-destructive'
    }
  }

  const getStageStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return (
          <svg className="w-3 h-3 text-green-500" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
          </svg>
        )
      case 'running':
        return <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
      case 'failed':
        return (
          <svg className="w-3 h-3 text-red-500" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
          </svg>
        )
      default:
        return <span className="w-2 h-2 rounded-full bg-muted" />
    }
  }

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="fixed top-0 left-0 right-0 z-50 border-b border-border/50 backdrop-blur-lg bg-background/95">
        <nav className="container mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-primary rounded-lg flex items-center justify-center">
              <svg className="w-6 h-6 text-primary-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            </div>
            <div>
              <h1 className="font-bold text-lg">Lang2Pick</h1>
              <p className="text-xs text-muted-foreground">SO-ARM101 Control</p>
            </div>
          </div>

          <div className="flex items-center gap-6">
            {/* Mode Selector */}
            <div className="flex items-center gap-2">
              <Select 
                value={appMode} 
                onValueChange={(value) => handleModeChange(value as AppMode)}
                disabled={isChangingMode}
              >
                <SelectTrigger className={`w-[140px] h-8 text-xs ${appMode === 'real' ? 'border-green-500' : 'border-yellow-500'}`}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="simulation">
                    <span className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-yellow-500" />
                      Simulation
                    </span>
                  </SelectItem>
                  <SelectItem value="real">
                    <span className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-green-500" />
                      Real Robot
                    </span>
                  </SelectItem>
                </SelectContent>
              </Select>
              {appMode === 'real' && (
                <Button 
                  variant="outline" 
                  size="sm" 
                  onClick={handleReconnect}
                  className="h-8 text-xs"
                >
                  Reconnect
                </Button>
              )}
            </div>

            <div className="hidden md:flex items-center gap-4 text-sm">
              {/* Connection status indicators */}
              <div className="flex items-center gap-2" title={systemStatus.services?.find(s => s.name.includes('ROS2'))?.message || ''}>
                <div className={`w-2 h-2 rounded-full ${systemStatus.ros2_connected ? 'bg-green-500' : 'bg-red-500'}`} />
                <span className="text-muted-foreground">ROS2</span>
              </div>
              <div className="flex items-center gap-2" title={systemStatus.services?.find(s => s.name.includes('Detection'))?.message || ''}>
                <div className={`w-2 h-2 rounded-full ${systemStatus.grpc_connected ? 'bg-green-500' : 'bg-red-500'}`} />
                <span className="text-muted-foreground">Detection</span>
              </div>
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${systemStatus.camera_connected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
                <span className="text-muted-foreground">Camera</span>
              </div>
              <div className="text-muted-foreground">
                {queuedCount} Queued
              </div>
              <div className="text-muted-foreground">
                {completedCount} Completed
              </div>
            </div>
          </div>
        </nav>
      </header>

      <div className="pt-16">
        <div className="container mx-auto p-6">
          <div className="grid lg:grid-cols-2 gap-6">
            {/* Left Column - Video Feed & Robot Visualization */}
            <div className="space-y-6">
              {/* Live Video Feed */}
              <Card className="overflow-hidden border-border/50">
                <div className="bg-card/50 p-4 border-b border-border/50">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className={`w-3 h-3 rounded-full ${systemStatus.camera_connected ? 'bg-red-500 animate-pulse' : 'bg-gray-500'}`} />
                      <h2 className="font-semibold">Live Camera Feed</h2>
                      {webrtc.isConnected && (
                        <span className="text-xs bg-green-500/20 text-green-500 px-2 py-0.5 rounded">WebRTC</span>
                      )}
                      {appMode === 'simulation' && (
                        <span className="text-xs bg-yellow-500/20 text-yellow-500 px-2 py-0.5 rounded">Simulation</span>
                      )}
                      {appMode === 'real' && (
                        <span className="text-xs bg-green-500/20 text-green-500 px-2 py-0.5 rounded">Real</span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {/* Camera Source Selector */}
                      {availableCameras.length > 0 && (
                        <Select value={selectedCamera} onValueChange={handleCameraChange}>
                          <SelectTrigger className="w-[180px] h-8 text-xs">
                            <SelectValue placeholder="Select camera" />
                          </SelectTrigger>
                          <SelectContent>
                            {availableCameras.map((camera) => (
                              <SelectItem key={camera.deviceId} value={camera.deviceId}>
                                {camera.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )}
                      <span className="text-xs text-muted-foreground font-mono">1280x720</span>
                      {!webrtc.isConnected && WEBRTC_ENABLED && (
                        <Button 
                          variant="outline" 
                          size="sm" 
                          onClick={() => webrtc.connect()}
                          disabled={webrtc.isConnecting}
                        >
                          {webrtc.isConnecting ? 'Connecting...' : 'Connect WebRTC'}
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
                <div className="relative aspect-video bg-muted/50">
                  <video
                    ref={videoRef}
                    autoPlay
                    playsInline
                    muted
                    className="w-full h-full object-cover"
                  />
                  {/* Detection overlay canvas */}
                  <canvas
                    ref={canvasRef}
                    className="absolute inset-0 w-full h-full pointer-events-none"
                  />
                  
                  {/* Fallback placeholder */}
                  {!systemStatus.camera_connected && (
                    <div className="absolute inset-0 flex items-center justify-center bg-muted/90 backdrop-blur-sm">
                      <div className="text-center space-y-3">
                        <div className="w-16 h-16 mx-auto rounded-full bg-primary/20 flex items-center justify-center">
                          <svg className="w-8 h-8 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                          </svg>
                        </div>
                        <p className="text-sm text-muted-foreground">
                          {availableCameras.length === 0 ? 'No cameras found' : 'Select a camera source'}
                        </p>
                        {availableCameras.length === 0 && (
                          <Button 
                            variant="outline" 
                            size="sm"
                            onClick={() => window.location.reload()}
                          >
                            Refresh
                          </Button>
                        )}
                      </div>
                    </div>
                  )}
                  
                  {/* Detection count overlay */}
                  {detections.length > 0 && (
                    <div className="absolute top-4 left-4 bg-background/80 backdrop-blur-sm px-3 py-1 rounded-lg border border-border/50">
                      <span className="text-sm font-medium">{detections.length} object(s) detected</span>
                    </div>
                  )}
                  
                  {/* Current task overlay */}
                  {currentTask && (
                    <div className="absolute bottom-4 left-4 right-4">
                      <div className="bg-background/95 backdrop-blur-sm border border-accent/50 rounded-lg p-4">
                        {/* Header with step indicator */}
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center gap-3">
                            <div className="flex items-center justify-center w-10 h-10 rounded-full bg-accent text-accent-foreground font-bold text-lg">
                              {currentTask.currentStage + 1}
                            </div>
                            <div>
                              <p className="text-sm font-semibold text-accent">
                                {currentTask.stages[currentTask.currentStage]?.name || 'Processing...'}
                              </p>
                              <p className="text-xs text-muted-foreground">
                                Step {currentTask.currentStage + 1} of {currentTask.stages.length}
                              </p>
                            </div>
                          </div>
                          <div className="text-right">
                            <p className="text-lg font-bold text-accent">{currentTask.progress}%</p>
                            <div className="w-2 h-2 rounded-full bg-accent animate-pulse inline-block" />
                          </div>
                        </div>
                        
                        {/* Task prompt */}
                        <p className="text-sm text-muted-foreground mb-3 truncate">{currentTask.prompt}</p>
                        
                        {/* Progress bar with step markers */}
                        <div className="relative">
                          <div className="h-2 bg-muted rounded-full overflow-hidden">
                            <div
                              className="h-full bg-accent transition-all duration-300"
                              style={{ width: `${currentTask.progress}%` }}
                            />
                          </div>
                          {/* Step markers */}
                          <div className="flex justify-between mt-1">
                            {currentTask.stages.map((stage, i) => (
                              <div 
                                key={i}
                                className={`w-1.5 h-1.5 rounded-full ${
                                  i < currentTask.currentStage ? 'bg-green-500' :
                                  i === currentTask.currentStage ? 'bg-accent animate-pulse' : 'bg-muted-foreground/30'
                                }`}
                                title={stage.name}
                              />
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </Card>

              {/* Robot Arm Visualization */}
              <Card className="border-border/50">
                <div className="bg-card/50 p-4 border-b border-border/50">
                  <div className="flex items-center justify-between">
                    <h2 className="font-semibold">Robot Arm Visualization</h2>
                    <div className="flex items-center gap-2">
                      <div className={`w-2 h-2 rounded-full ${robotState.isConnected ? 'bg-green-500' : 'bg-yellow-500'}`} />
                      <span className="text-xs text-muted-foreground">
                        {robotState.isConnected ? 'Live' : appMode === 'simulation' ? 'Simulated' : 'Disconnected'}
                      </span>
                    </div>
                  </div>
                </div>
                <div className="p-6">
                  <RobotArm 
                    joints={robotState.jointsDegrees}
                    gripperOpen={robotState.gripperOpen}
                    useSimulation={appMode === 'simulation'}
                  />
                </div>
              </Card>
            </div>

            {/* Right Column - Prompt Interface & Task Queue */}
            <div className="space-y-6">
              {/* Prompt Input */}
              <Card className="border-border/50">
                <div className="bg-card/50 p-4 border-b border-border/50">
                  <h2 className="font-semibold">Command Interface</h2>
                  <p className="text-sm text-muted-foreground mt-1">
                    Send natural language commands to the robotic arm
                  </p>
                </div>
                <div className="p-6">
                  <form onSubmit={handleSubmit} className="space-y-4">
                    <div className="space-y-2">
                      <label className="text-sm font-medium">Task Prompt</label>
                      <Input
                        value={prompt}
                        onChange={(e) => handlePromptChange(e.target.value)}
                        placeholder="e.g., Pick up the red ball and place it in the blue bin"
                        className="text-base"
                      />
                    </div>
                    <Button 
                      type="submit" 
                      className="w-full font-semibold" 
                      size="lg"
                      disabled={!prompt.trim() || isProcessing}
                    >
                      <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                      </svg>
                      Add to Queue
                    </Button>
                  </form>

                  <div className="mt-6 space-y-2">
                    <h3 className="text-sm font-medium text-muted-foreground">Example Commands:</h3>
                    <div className="space-y-2">
                      {[
                        'Pick up the red ball',
                        'Move the green cube to the left',
                        'Place all bottles in the recycling bin',
                        'Grab the yellow object and lift it up'
                      ].map((example, i) => (
                        <button
                          key={i}
                          onClick={() => setPrompt(example)}
                          className="w-full text-left text-sm px-3 py-2 rounded-lg bg-muted/50 hover:bg-muted transition-colors border border-border/50"
                        >
                          {example}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </Card>

              {/* Task Queue */}
              <Card className="border-border/50">
                <div className="bg-card/50 p-4 border-b border-border/50">
                  <div className="flex items-center justify-between">
                    <div>
                      <h2 className="font-semibold">Task Queue</h2>
                      <p className="text-sm text-muted-foreground mt-1">
                        {tasks.length} total tasks
                      </p>
                    </div>
                    {completedCount > 0 && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={clearCompleted}
                        className="text-xs"
                      >
                        Clear Completed
                      </Button>
                    )}
                  </div>
                </div>
                <div className="p-4">
                  {tasks.length === 0 ? (
                    <div className="text-center py-12">
                      <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-muted/50 flex items-center justify-center">
                        <svg className="w-8 h-8 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                        </svg>
                      </div>
                      <p className="text-sm text-muted-foreground">No tasks in queue</p>
                      <p className="text-xs text-muted-foreground mt-1">Add a command to get started</p>
                    </div>
                  ) : (
                    <div className="space-y-3 max-h-[600px] overflow-y-auto">
                      {tasks.map((task) => (
                        <div
                          key={task.id}
                          className="p-4 rounded-lg border border-border/50 bg-card/50 space-y-3"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium ${getStatusColor(task.status)}`}>
                                  {task.status === 'queued' && (
                                    <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
                                  )}
                                  {task.status === 'processing' && (
                                    <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
                                  )}
                                  {task.status === 'completed' && (
                                    <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                                    </svg>
                                  )}
                                  {task.status.charAt(0).toUpperCase() + task.status.slice(1)}
                                </span>
                                <span className="text-xs text-muted-foreground font-mono">
                                  {task.timestamp.toLocaleTimeString()}
                                </span>
                              </div>
                              <p className="text-sm font-medium leading-relaxed">{task.prompt}</p>
                              
                              {/* Queued task - waiting indicator with indeterminate progress */}
                              {task.status === 'queued' && (
                                <div className="mt-2 p-2 bg-muted/30 border border-muted rounded-lg">
                                  <div className="flex items-center gap-2 mb-2">
                                    <svg className="w-4 h-4 text-muted-foreground animate-spin" fill="none" viewBox="0 0 24 24">
                                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                    </svg>
                                    <span className="text-sm text-muted-foreground">Waiting to start...</span>
                                  </div>
                                  {/* Indeterminate progress bar */}
                                  <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                                    <div className="h-full w-1/3 bg-muted-foreground/50 rounded-full animate-pulse" 
                                         style={{ animation: 'indeterminate 1.5s ease-in-out infinite' }} />
                                  </div>
                                </div>
                              )}
                              
                              {/* Current Step & Phase Display */}
                              {task.status === 'processing' && (
                                <div className="mt-2 p-2 bg-accent/10 border border-accent/20 rounded-lg">
                                  <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                      <span className="text-lg font-bold text-accent">
                                        Step {task.currentStage + 1}
                                      </span>
                                      <span className="text-xs text-muted-foreground">
                                        of {task.stages.length}
                                      </span>
                                    </div>
                                    <span className="text-xs font-mono text-muted-foreground">
                                      {task.progress}%
                                    </span>
                                  </div>
                                  <div className="mt-1 flex items-center gap-2">
                                    <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
                                    <span className="text-sm font-medium text-accent">
                                      {task.stages[task.currentStage]?.name || 'Processing...'}
                                    </span>
                                  </div>
                                </div>
                              )}
                              
                              {/* Completed task summary */}
                              {task.status === 'completed' && (
                                <div className="mt-2 text-xs text-green-600 flex items-center gap-1">
                                  <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                                  </svg>
                                  Completed all {task.stages.length} stages
                                </div>
                              )}
                            </div>
                            
                            {/* Cancel button for queued/processing tasks */}
                            {(task.status === 'queued' || task.status === 'processing') && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => cancelTask(task.id)}
                                className="text-xs text-muted-foreground hover:text-destructive"
                              >
                                Cancel
                              </Button>
                            )}
                          </div>

                          {/* Task stages for processing tasks */}
                          {task.status === 'processing' && (
                            <div className="space-y-2">
                              {/* Progress bar */}
                              <div className="h-2 bg-muted rounded-full overflow-hidden">
                                <div
                                  className="h-full bg-accent transition-all duration-300"
                                  style={{ width: `${task.progress}%` }}
                                />
                              </div>
                              
                              {/* Stage list with step numbers */}
                              <div className="grid grid-cols-2 gap-1 mt-2">
                                {task.stages.map((stage, i) => (
                                  <div
                                    key={i}
                                    className={`flex items-center gap-1.5 text-xs px-2 py-1.5 rounded ${
                                      stage.status === 'running' ? 'bg-accent/20 border border-accent/30' :
                                      stage.status === 'completed' ? 'bg-green-500/10' : 'bg-muted/50'
                                    }`}
                                  >
                                    <span className={`w-5 h-5 flex items-center justify-center rounded-full text-[10px] font-bold ${
                                      stage.status === 'running' ? 'bg-accent text-accent-foreground' :
                                      stage.status === 'completed' ? 'bg-green-500 text-white' : 'bg-muted-foreground/20 text-muted-foreground'
                                    }`}>
                                      {stage.status === 'completed' ? '✓' : i + 1}
                                    </span>
                                    {getStageStatusIcon(stage.status)}
                                    <span className={`truncate ${stage.status === 'running' ? 'font-medium' : ''}`}>
                                      {stage.name}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Error message for failed tasks */}
                          {task.status === 'failed' && task.error && (
                            <p className="text-xs text-destructive">{task.error}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </Card>
            </div>
          </div>

          {/* Service Status Panel */}
          <Card className="mt-6 border-border/50">
            <div className="bg-card/50 p-4 border-b border-border/50">
              <div className="flex items-center justify-between">
                <h2 className="font-semibold">Service Connections</h2>
                <span className={`text-xs px-2 py-1 rounded ${
                  appMode === 'simulation' 
                    ? 'bg-yellow-500/20 text-yellow-500' 
                    : 'bg-green-500/20 text-green-500'
                }`}>
                  {appMode === 'simulation' ? 'SIMULATION MODE' : 'REAL MODE'}
                </span>
              </div>
            </div>
            <div className="p-4">
              <div className="grid md:grid-cols-3 gap-4">
                {(systemStatus.services || []).map((service, idx) => (
                  <div 
                    key={idx}
                    className={`p-4 rounded-lg border ${
                      service.connected 
                        ? 'border-green-500/30 bg-green-500/5' 
                        : 'border-red-500/30 bg-red-500/5'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium text-sm">{service.name}</span>
                      <div className={`w-3 h-3 rounded-full ${
                        service.connected ? 'bg-green-500' : 'bg-red-500'
                      }`} />
                    </div>
                    <p className="text-xs text-muted-foreground">{service.message}</p>
                    {service.url && (
                      <p className="text-xs text-muted-foreground/70 font-mono mt-1">{service.url}</p>
                    )}
                  </div>
                ))}
              </div>
              
              {/* Mode description */}
              <div className="mt-4 p-4 bg-muted/30 rounded-lg">
                <h3 className="text-sm font-medium mb-2">
                  {appMode === 'simulation' ? '🎮 Simulation Mode' : '🤖 Real Mode'}
                </h3>
                <p className="text-xs text-muted-foreground">
                  {appMode === 'simulation' 
                    ? 'All services are simulated. Joint states update with sine wave animation. Task processing runs through all 11 MoveIt stages with simulated delays. Perfect for testing and demos.'
                    : 'Connected to real services. Detection uses YOLO-World gRPC service for object detection. Robot commands are sent to the SO-101 arm via ROS2/MoveIt. Ensure all services are running before submitting tasks.'
                  }
                </p>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
