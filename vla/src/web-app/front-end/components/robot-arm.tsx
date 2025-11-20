'use client'

import { useEffect, useRef, useState } from 'react'

export function RobotArm() {
  const [rotation, setRotation] = useState(0)
  const [joint1, setJoint1] = useState(0) // Base rotation
  const [joint2, setJoint2] = useState(45) // Shoulder
  const [joint3, setJoint3] = useState(-30) // Elbow
  const [joint4, setJoint4] = useState(0) // Wrist roll
  const [joint5, setJoint5] = useState(20) // Wrist pitch
  const [joint6, setJoint6] = useState(0) // Wrist yaw
  const [grip, setGrip] = useState(false)
  const animationRef = useRef<number>()

  useEffect(() => {
    let time = 0
    const animate = () => {
      time += 0.01
      setJoint1(Math.sin(time * 0.8) * 45) // Base rotation
      setJoint2(45 + Math.sin(time * 1.2) * 25) // Shoulder
      setJoint3(-30 + Math.cos(time * 1.5) * 30) // Elbow
      setJoint4(Math.sin(time * 2) * 30) // Wrist roll
      setJoint5(20 + Math.cos(time * 1.8) * 15) // Wrist pitch
      setJoint6(Math.sin(time * 2.5) * 20) // Wrist yaw
      setGrip(Math.sin(time * 2) > 0)
      
      animationRef.current = requestAnimationFrame(animate)
    }
    
    animate()
    
    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
    }
  }, [])

  return (
    <div className="relative w-full aspect-square flex items-center justify-center">
      {/* Glow effect */}
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="w-64 h-64 bg-primary/20 rounded-full blur-3xl animate-pulse" />
      </div>
      
      {/* Robot arm SVG */}
      <svg
        viewBox="0 0 400 400"
        className="relative z-10 w-full h-full"
        style={{ filter: 'drop-shadow(0 4px 20px rgba(99, 102, 241, 0.3))' }}
      >
        {/* Base */}
        <g transform={`translate(200, 350)`}>
          {/* Base platform - larger and more robust */}
          <ellipse
            cx="0"
            cy="10"
            rx="50"
            ry="15"
            className="fill-muted/80"
          />
          <rect
            x="-45"
            y="0"
            width="90"
            height="20"
            rx="4"
            className="fill-card stroke-primary"
            strokeWidth="2"
          />
          <circle
            cx="0"
            cy="10"
            r="35"
            className="fill-card stroke-primary"
            strokeWidth="3"
          />
          
          {/* Joint 1 - Base rotation */}
          <g transform={`rotate(${joint1})`}>
            {/* Base connector */}
            <circle
              cx="0"
              cy="0"
              r="25"
              className="fill-muted"
            />
            <circle
              cx="0"
              cy="0"
              r="20"
              className="fill-card stroke-accent"
              strokeWidth="2"
            />
            
            <g transform={`rotate(${joint2})`}>
              {/* Shoulder servo housing */}
              <rect
                x="-20"
                y="-10"
                width="40"
                height="20"
                rx="4"
                className="fill-accent/80 stroke-accent"
                strokeWidth="2"
              />
              
              {/* Upper arm link */}
              <rect
                x="-12"
                y="-100"
                width="24"
                height="90"
                rx="6"
                className="fill-card stroke-primary"
                strokeWidth="2"
              />
              
              {/* Servo motor indicators */}
              <circle cx="-8" cy="-50" r="3" className="fill-primary/60" />
              <circle cx="8" cy="-50" r="3" className="fill-primary/60" />
              
              <g transform={`translate(0, -100)`}>
                <circle
                  cx="0"
                  cy="0"
                  r="18"
                  className="fill-accent stroke-accent"
                  strokeWidth="2"
                />
                
                <g transform={`rotate(${joint3})`}>
                  {/* Forearm link */}
                  <rect
                    x="-10"
                    y="-80"
                    width="20"
                    height="80"
                    rx="5"
                    className="fill-card stroke-primary"
                    strokeWidth="2"
                  />
                  
                  {/* Cable management detail */}
                  <path
                    d="M -6 -70 Q -4 -60, -6 -50 Q -4 -40, -6 -30"
                    fill="none"
                    className="stroke-muted-foreground/30"
                    strokeWidth="2"
                  />
                  
                  <g transform={`translate(0, -80)`}>
                    <circle
                      cx="0"
                      cy="0"
                      r="14"
                      className="fill-accent"
                    />
                    
                    <g transform={`rotate(${joint4})`}>
                      {/* Wrist assembly */}
                      <rect
                        x="-8"
                        y="-30"
                        width="16"
                        height="30"
                        rx="4"
                        className="fill-card stroke-primary"
                        strokeWidth="1.5"
                      />
                      
                      <g transform={`translate(0, -30)`}>
                        <circle
                          cx="0"
                          cy="0"
                          r="12"
                          className="fill-primary"
                        />
                        
                        <g transform={`rotate(${joint5})`}>
                          <g transform={`translate(0, -20)`}>
                            <circle
                              cx="0"
                              cy="0"
                              r="10"
                              className="fill-accent"
                            />
                            
                            <g transform={`rotate(${joint6})`}>
                              {/* Gripper base */}
                              <rect
                                x="-8"
                                y="0"
                                width="16"
                                height="12"
                                rx="2"
                                className="fill-card stroke-primary"
                                strokeWidth="1"
                              />
                              
                              {/* Gripper fingers - parallel jaw design */}
                              <g transform={`translate(0, 12)`}>
                                {/* Left finger */}
                                <rect
                                  x={grip ? "-3" : "-7"}
                                  y="0"
                                  width="4"
                                  height="18"
                                  rx="2"
                                  className="fill-primary transition-all duration-300"
                                />
                                {/* Right finger */}
                                <rect
                                  x={grip ? "0" : "3"}
                                  y="0"
                                  width="4"
                                  height="18"
                                  rx="2"
                                  className="fill-primary transition-all duration-300"
                                />
                                
                                {/* Finger pads */}
                                <rect
                                  x={grip ? "-3" : "-7"}
                                  y="16"
                                  width="4"
                                  height="4"
                                  className="fill-accent transition-all duration-300"
                                />
                                <rect
                                  x={grip ? "0" : "3"}
                                  y="16"
                                  width="4"
                                  height="4"
                                  className="fill-accent transition-all duration-300"
                                />
                              </g>
                              
                              {/* Status LED */}
                              <circle
                                cx="0"
                                cy="3"
                                r="2"
                                className={grip ? 'fill-accent' : 'fill-muted'}
                              >
                                <animate
                                  attributeName="opacity"
                                  values="1;0.3;1"
                                  dur="2s"
                                  repeatCount="indefinite"
                                />
                              </circle>
                            </g>
                          </g>
                        </g>
                      </g>
                    </g>
                  </g>
                </g>
              </g>
            </g>
          </g>
          
          {/* Base platform details */}
          <circle
            cx="0"
            cy="10"
            r="15"
            className="fill-primary/30"
          />
        </g>
        
        {/* Decorative grid lines */}
        <defs>
          <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path
              d="M 40 0 L 0 0 0 40"
              fill="none"
              className="stroke-border/30"
              strokeWidth="1"
            />
          </pattern>
        </defs>
        <rect width="400" height="400" fill="url(#grid)" opacity="0.5" />
        
        {/* Circular range indicator */}
        <circle
          cx="200"
          cy="350"
          r="200"
          fill="none"
          className="stroke-primary/20"
          strokeWidth="1"
          strokeDasharray="4 4"
        />
      </svg>
      
      <div className="absolute top-4 right-4 space-y-2">
        <div className="flex items-center gap-2 bg-card/80 backdrop-blur-sm px-3 py-2 rounded-lg border border-border/50">
          <div className="w-2 h-2 rounded-full bg-accent animate-pulse" />
          <span className="text-xs font-mono text-foreground">6-DOF ACTIVE</span>
        </div>
        <div className="bg-card/80 backdrop-blur-sm px-3 py-2 rounded-lg border border-border/50 space-y-1">
          <div className="flex justify-between gap-3">
            <span className="text-xs font-mono text-muted-foreground">J1:</span>
            <span className="text-xs font-mono text-foreground">{joint1.toFixed(0)}°</span>
          </div>
          <div className="flex justify-between gap-3">
            <span className="text-xs font-mono text-muted-foreground">J2:</span>
            <span className="text-xs font-mono text-foreground">{joint2.toFixed(0)}°</span>
          </div>
          <div className="flex justify-between gap-3">
            <span className="text-xs font-mono text-muted-foreground">J3:</span>
            <span className="text-xs font-mono text-foreground">{joint3.toFixed(0)}°</span>
          </div>
          <div className="flex justify-between gap-3">
            <span className="text-xs font-mono text-muted-foreground">J4:</span>
            <span className="text-xs font-mono text-foreground">{joint4.toFixed(0)}°</span>
          </div>
          <div className="flex justify-between gap-3">
            <span className="text-xs font-mono text-muted-foreground">J5:</span>
            <span className="text-xs font-mono text-foreground">{joint5.toFixed(0)}°</span>
          </div>
          <div className="flex justify-between gap-3">
            <span className="text-xs font-mono text-muted-foreground">J6:</span>
            <span className="text-xs font-mono text-foreground">{joint6.toFixed(0)}°</span>
          </div>
        </div>
        <div className="bg-card/80 backdrop-blur-sm px-3 py-2 rounded-lg border border-border/50">
          <span className="text-xs font-mono text-muted-foreground">
            {grip ? 'GRIP: CLOSED' : 'GRIP: OPEN'}
          </span>
        </div>
      </div>
    </div>
  )
}
