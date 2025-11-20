'use client'

import { useState, useRef, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { RobotArm } from '@/components/robot-arm'

type TaskStatus = 'queued' | 'processing' | 'completed' | 'failed'

interface Task {
  id: string
  prompt: string
  status: TaskStatus
  progress: number
  timestamp: Date
}

export function PromptControl() {
  const [prompt, setPrompt] = useState('')
  const [tasks, setTasks] = useState<Task[]>([])
  const [currentTask, setCurrentTask] = useState<Task | null>(null)
  const [isProcessing, setIsProcessing] = useState(false)
  const videoRef = useRef<HTMLVideoElement>(null)

  // Initialize webcam feed
  useEffect(() => {
    const initCamera = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ 
          video: { width: 1280, height: 720 } 
        })
        if (videoRef.current) {
          videoRef.current.srcObject = stream
        }
      } catch (error) {
        console.log('[v0] Camera not available, using placeholder')
      }
    }
    initCamera()
  }, [])

  // Process task queue
  useEffect(() => {
    if (isProcessing || tasks.length === 0) return

    const nextTask = tasks.find(t => t.status === 'queued')
    if (!nextTask) {
      setIsProcessing(false)
      return
    }

    setIsProcessing(true)
    setCurrentTask(nextTask)

    // Update task to processing
    setTasks(prev =>
      prev.map(t => t.id === nextTask.id ? { ...t, status: 'processing' as TaskStatus } : t)
    )

    // Simulate task execution with progress updates
    let progress = 0
    const interval = setInterval(() => {
      progress += 5

      setTasks(prev =>
        prev.map(t =>
          t.id === nextTask.id ? { ...t, progress: Math.min(progress, 100) } : t
        )
      )

      if (progress >= 100) {
        clearInterval(interval)
        setTasks(prev =>
          prev.map(t =>
            t.id === nextTask.id
              ? { ...t, status: 'completed' as TaskStatus, progress: 100 }
              : t
          )
        )
        setIsProcessing(false)
        setCurrentTask(null)
      }
    }, 200)

    return () => clearInterval(interval)
  }, [tasks, isProcessing])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!prompt.trim()) return

    const newTask: Task = {
      id: `task-${Date.now()}`,
      prompt: prompt.trim(),
      status: 'queued',
      progress: 0,
      timestamp: new Date(),
    }

    setTasks(prev => [...prev, newTask])
    setPrompt('')
  }

  const clearCompleted = () => {
    setTasks(prev => prev.filter(t => t.status !== 'completed'))
  }

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

  const queuedCount = tasks.filter(t => t.status === 'queued').length
  const completedCount = tasks.filter(t => t.status === 'completed').length

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
            <div className="hidden md:flex items-center gap-4 text-sm">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-accent animate-pulse" />
                <span className="text-muted-foreground">System Active</span>
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
                      <div className="w-3 h-3 rounded-full bg-red-500 animate-pulse" />
                      <h2 className="font-semibold">Live Camera Feed</h2>
                    </div>
                    <span className="text-xs text-muted-foreground font-mono">1280x720</span>
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
                  {/* Fallback placeholder */}
                  <div className="absolute inset-0 flex items-center justify-center bg-muted/90 backdrop-blur-sm">
                    <div className="text-center space-y-3">
                      <div className="w-16 h-16 mx-auto rounded-full bg-primary/20 flex items-center justify-center">
                        <svg className="w-8 h-8 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                        </svg>
                      </div>
                      <p className="text-sm text-muted-foreground">Camera Initializing...</p>
                    </div>
                  </div>
                  
                  {/* Current task overlay */}
                  {currentTask && (
                    <div className="absolute bottom-4 left-4 right-4">
                      <div className="bg-background/95 backdrop-blur-sm border border-border/50 rounded-lg p-3">
                        <div className="flex items-center gap-2 mb-2">
                          <div className="w-2 h-2 rounded-full bg-accent animate-pulse" />
                          <span className="text-sm font-medium">Processing Task</span>
                        </div>
                        <p className="text-sm text-muted-foreground mb-2">{currentTask.prompt}</p>
                        <div className="space-y-1">
                          <div className="flex justify-between text-xs text-muted-foreground">
                            <span>Progress</span>
                            <span>{currentTask.progress}%</span>
                          </div>
                          <div className="h-2 bg-muted rounded-full overflow-hidden">
                            <div
                              className="h-full bg-accent transition-all duration-300"
                              style={{ width: `${currentTask.progress}%` }}
                            />
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
                  <h2 className="font-semibold">Robot Arm Visualization</h2>
                </div>
                <div className="p-6">
                  <RobotArm />
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
                        onChange={(e) => setPrompt(e.target.value)}
                        placeholder="e.g., Pick up the red ball and place it in the blue bin"
                        className="text-base"
                      />
                    </div>
                    <Button type="submit" className="w-full font-semibold" size="lg">
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
                            </div>
                          </div>

                          {task.status === 'processing' && (
                            <div className="space-y-1">
                              <div className="flex justify-between text-xs text-muted-foreground">
                                <span>Executing task...</span>
                                <span>{task.progress}%</span>
                              </div>
                              <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                                <div
                                  className="h-full bg-accent transition-all duration-300"
                                  style={{ width: `${task.progress}%` }}
                                />
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </Card>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
