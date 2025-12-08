import { NextRequest, NextResponse } from 'next/server'
import { tasks } from '../route'

// GET /api/tasks/[taskId] - Get task by ID
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ taskId: string }> }
) {
  const { taskId } = await params
  const task = tasks.get(taskId)

  if (!task) {
    return NextResponse.json(
      { error: 'Task not found' },
      { status: 404 }
    )
  }

  return NextResponse.json(task)
}

// DELETE /api/tasks/[taskId] - Delete/Cancel task
export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ taskId: string }> }
) {
  const { taskId } = await params
  const task = tasks.get(taskId)

  if (!task) {
    return NextResponse.json(
      { error: 'Task not found' },
      { status: 404 }
    )
  }

  // Can only cancel queued or processing tasks
  if (task.status === 'queued' || task.status === 'processing') {
    task.status = 'failed'
    task.error = 'Cancelled by user'
    tasks.set(taskId, task)
  }

  return NextResponse.json({ success: true })
}
