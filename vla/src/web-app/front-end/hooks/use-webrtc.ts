'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { webrtcClient, type Detection } from '@/lib/api-client'

interface UseWebRTCOptions {
  sessionId?: string
  autoConnect?: boolean
  onDetection?: (detections: Detection[]) => void
}

interface UseWebRTCReturn {
  stream: MediaStream | null
  isConnected: boolean
  isConnecting: boolean
  error: string | null
  connect: () => Promise<void>
  disconnect: () => void
  detections: Detection[]
}

export function useWebRTC(options: UseWebRTCOptions = {}): UseWebRTCReturn {
  const { sessionId = 'default', autoConnect = false, onDetection } = options
  
  const [stream, setStream] = useState<MediaStream | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [isConnecting, setIsConnecting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [detections, setDetections] = useState<Detection[]>([])
  
  const onDetectionRef = useRef(onDetection)
  onDetectionRef.current = onDetection

  const connect = useCallback(async () => {
    if (isConnecting || isConnected) return
    
    setIsConnecting(true)
    setError(null)

    try {
      await webrtcClient.connect(
        { sessionId },
        (remoteStream) => {
          setStream(remoteStream)
          setIsConnected(true)
          setIsConnecting(false)
        }
      )

      // Set up detection callback
      webrtcClient.onDetection((dets) => {
        setDetections(dets)
        onDetectionRef.current?.(dets)
      })
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Connection failed'
      setError(message)
      setIsConnecting(false)
      setIsConnected(false)
    }
  }, [sessionId, isConnecting, isConnected])

  const disconnect = useCallback(() => {
    webrtcClient.disconnect()
    setStream(null)
    setIsConnected(false)
    setDetections([])
  }, [])

  // Auto-connect on mount if enabled
  useEffect(() => {
    if (autoConnect) {
      connect()
    }

    return () => {
      disconnect()
    }
  }, [autoConnect]) // eslint-disable-line react-hooks/exhaustive-deps

  return {
    stream,
    isConnected,
    isConnecting,
    error,
    connect,
    disconnect,
    detections,
  }
}
