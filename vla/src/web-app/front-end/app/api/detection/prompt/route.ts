import { NextRequest, NextResponse } from 'next/server'

const GRPC_BACKEND = process.env.GRPC_BACKEND_URL || 'http://localhost:50051'

// POST /api/detection/prompt - Set detection prompt
export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { session_id = 'default', prompt } = body

    if (!prompt) {
      return NextResponse.json(
        { error: 'Prompt is required' },
        { status: 400 }
      )
    }

    // Forward to gRPC detection service
    try {
      const response = await fetch(`${GRPC_BACKEND}/set_prompt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id, prompt }),
        signal: AbortSignal.timeout(5000),
      })

      if (response.ok) {
        return NextResponse.json({ success: true, session_id, prompt })
      }
    } catch (e) {
      console.error('gRPC prompt setting failed:', e)
    }

    // Return success even if backend is unavailable (for demo mode)
    return NextResponse.json({ success: true, session_id, prompt, demo_mode: true })

  } catch (error) {
    console.error('Detection prompt error:', error)
    return NextResponse.json(
      { error: 'Failed to set prompt' },
      { status: 500 }
    )
  }
}
