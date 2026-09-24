// Render's Blueprint passes the backend's bare host (no https://), so add it.
const rawApiUrl: string = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
const API_URL = (/^https?:\/\//.test(rawApiUrl) ? rawApiUrl : `https://${rawApiUrl}`).replace(/\/+$/, '')

/** One row of data/yale_som_classes.json, as served by GET /api/courses. */
export interface Course {
  'Course ID': string
  'Course Number': string
  'Course Title': string
  Section: string
  'Course Category': string
  'Course Type': string
  'Bid Or Permission': string
  'Course Session': string
  Daytimes: string
  Room: string
  Units: string
  'Faculty 1': string
  'Faculty 1 Email': string
  Syllabus: string
  'Old Syllabus': string
  'Course Description': string
  faculty_bio: string
  Visible: string
}

export interface CoursesResponse {
  count: number
  courses: Course[]
}

export interface ChatReply {
  reply: string
  tools_used: string[]
}

async function request<T>(path: string, init?: RequestInit, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { ...init, signal })
  if (!res.ok) throw new Error(`Server returned ${res.status}`)
  return res.json() as Promise<T>
}

export function fetchCourses(q: string, signal?: AbortSignal): Promise<CoursesResponse> {
  const query = q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ''
  return request<CoursesResponse>(`/api/courses${query}`, undefined, signal)
}

export function sendChat(message: string): Promise<ChatReply> {
  return request<ChatReply>('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })
}
