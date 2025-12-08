'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { 
  wsClient, 
  apiClient, 
  type TaskResponse, 
  type TaskStage,
  type PickPlaceRequest,
  type WebSocketMessage 
} from '@/lib/api-client'

export type TaskStatus = 'queued' | 'processing' | 'completed' | 'failed'

export interface Task {
  id: string
  prompt: string
  status: TaskStatus
  progress: number
  timestamp: Date
  stages: TaskStage[]
  currentStage: number
  error?: string
}

interface UseTaskQueueOptions {
  useWebSocket?: boolean
  onTaskComplete?: (task: Task) => void
  onTaskError?: (task: Task, error: string) => void
}

interface UseTaskQueueReturn {
  tasks: Task[]
  currentTask: Task | null
  isProcessing: boolean
  submitTask: (prompt: string) => Promise<Task>
  cancelTask: (taskId: string) => Promise<void>
  clearCompleted: () => void
  queuedCount: number
  completedCount: number
}

// Default MoveIt Task Constructor stages for pick-and-place
const DEFAULT_STAGES: TaskStage[] = [
  { name: 'Initializing', status: 'pending', progress: 0 },
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

export function useTaskQueue(options: UseTaskQueueOptions = {}): UseTaskQueueReturn {
  const { useWebSocket = true, onTaskComplete, onTaskError } = options

  const [tasks, setTasks] = useState<Task[]>([])
  const unsubscribeRef = useRef<(() => void) | null>(null)
  const callbacksRef = useRef({ onTaskComplete, onTaskError })
  
  callbacksRef.current = { onTaskComplete, onTaskError }

  const currentTask = tasks.find(t => t.status === 'processing') || null
  const isProcessing = currentTask !== null
  const queuedCount = tasks.filter(t => t.status === 'queued').length
  const completedCount = tasks.filter(t => t.status === 'completed').length

  // Convert API response to internal Task format
  const taskResponseToTask = (response: TaskResponse, prompt: string): Task => ({
    id: response.task_id,
    prompt,
    status: response.status,
    progress: response.progress,
    timestamp: new Date(),
    stages: response.stages || DEFAULT_STAGES,
    currentStage: response.current_stage || 0,
    error: response.error,
  })

  // Handle WebSocket task updates
  const handleTaskUpdate = useCallback((message: WebSocketMessage) => {
    if (message.type === 'task_update') {
      const update = message.data as TaskResponse
      
      setTasks(prev => prev.map(task => {
        if (task.id === update.task_id) {
          const updatedTask: Task = {
            ...task,
            status: update.status,
            progress: update.progress,
            stages: update.stages || task.stages,
            currentStage: update.current_stage || task.currentStage,
            error: update.error,
          }

          // Trigger callbacks
          if (update.status === 'completed') {
            callbacksRef.current.onTaskComplete?.(updatedTask)
          } else if (update.status === 'failed' && update.error) {
            callbacksRef.current.onTaskError?.(updatedTask, update.error)
          }

          return updatedTask
        }
        return task
      }))
    }
  }, [])

  // Submit a new task
  const submitTask = useCallback(async (prompt: string): Promise<Task> => {
    const request: PickPlaceRequest = {
      prompt,
      session_id: 'default',
    }

    try {
      const response = await apiClient.submitTask(request)
      const task = taskResponseToTask(response, prompt)
      
      setTasks(prev => [...prev, task])
      return task
    } catch (e) {
      // Create a local task for demo/fallback
      const localTask: Task = {
        id: `local-${Date.now()}`,
        prompt,
        status: 'queued',
        progress: 0,
        timestamp: new Date(),
        stages: [...DEFAULT_STAGES],
        currentStage: 0,
      }
      
      setTasks(prev => [...prev, localTask])
      
      // Simulate task processing for demo
      simulateTaskProcessing(localTask.id)
      
      return localTask
    }
  }, [])

  // Simulate task processing when backend is unavailable
  const simulateTaskProcessing = useCallback((taskId: string) => {
    let stageIndex = 0
    let progress = 0

    const interval = setInterval(() => {
      setTasks(prev => prev.map(task => {
        if (task.id !== taskId) return task

        progress += 2
        
        // Update current stage based on progress
        const newStageIndex = Math.min(
          Math.floor(progress / (100 / DEFAULT_STAGES.length)),
          DEFAULT_STAGES.length - 1
        )

        const updatedStages = task.stages.map((stage, i) => ({
          ...stage,
          status: i < newStageIndex ? 'completed' as const :
                  i === newStageIndex ? 'running' as const : 'pending' as const,
          progress: i < newStageIndex ? 100 :
                   i === newStageIndex ? (progress % (100 / DEFAULT_STAGES.length)) * DEFAULT_STAGES.length : 0,
        }))

        if (progress >= 100) {
          clearInterval(interval)
          const completedTask: Task = {
            ...task,
            status: 'completed',
            progress: 100,
            stages: updatedStages.map(s => ({ ...s, status: 'completed' as const, progress: 100 })),
            currentStage: DEFAULT_STAGES.length - 1,
          }
          callbacksRef.current.onTaskComplete?.(completedTask)
          return completedTask
        }

        return {
          ...task,
          status: 'processing' as const,
          progress: Math.min(progress, 100),
          stages: updatedStages,
          currentStage: newStageIndex,
        }
      }))
    }, 200)
  }, [])

  // Cancel a task
  const cancelTask = useCallback(async (taskId: string): Promise<void> => {
    try {
      await apiClient.cancelTask(taskId)
    } catch {
      // Handle locally if API fails
    }
    
    setTasks(prev => prev.map(task =>
      task.id === taskId ? { ...task, status: 'failed' as const, error: 'Cancelled' } : task
    ))
  }, [])

  // Clear completed tasks
  const clearCompleted = useCallback(() => {
    setTasks(prev => prev.filter(t => t.status !== 'completed'))
  }, [])

  // Poll for task updates when WebSocket is disabled
  useEffect(() => {
    if (useWebSocket) {
      // Use WebSocket for real-time updates
      wsClient.connect()
      unsubscribeRef.current = wsClient.subscribe('task_update', handleTaskUpdate)
      return () => {
        if (unsubscribeRef.current) {
          unsubscribeRef.current()
        }
      }
    } else {
      // Use REST polling for task updates
      const pollTasks = async () => {
        const activeTasks = tasks.filter(t => t.status === 'queued' || t.status === 'processing')
        
        // Store callbacks to trigger after state update
        const callbacksToTrigger: Array<() => void> = []
        
        for (const task of activeTasks) {
          try {
            const response = await apiClient.getTask(task.id)
            
            setTasks(prev => prev.map(t => {
              if (t.id === task.id) {
                const updatedTask: Task = {
                  ...t,
                  status: response.status,
                  progress: Math.round(response.progress),
                  stages: response.stages || t.stages,
                  currentStage: response.current_stage || t.currentStage,
                  error: response.error,
                }
                
                // Schedule callbacks to run after state update (not during)
                if (response.status === 'completed' && t.status !== 'completed') {
                  callbacksToTrigger.push(() => callbacksRef.current.onTaskComplete?.(updatedTask))
                } else if (response.status === 'failed' && response.error && t.status !== 'failed') {
                  callbacksToTrigger.push(() => callbacksRef.current.onTaskError?.(updatedTask, response.error!))
                }
                
                return updatedTask
              }
              return t
            }))
          } catch {
            // Task might not exist or API error - ignore
          }
        }
        
        // Trigger callbacks after state updates are done
        setTimeout(() => {
          callbacksToTrigger.forEach(cb => cb())
        }, 0)
      }

      // Poll every 300ms for smooth progress updates
      const interval = setInterval(pollTasks, 300)
      return () => clearInterval(interval)
    }
  }, [useWebSocket, handleTaskUpdate, tasks])

  return {
    tasks,
    currentTask,
    isProcessing,
    submitTask,
    cancelTask,
    clearCompleted,
    queuedCount,
    completedCount,
  }
}
