import type { ProcessResult, QueryResponse, Source, TimelineEvent } from "../types/api";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  path: string;

  constructor(message: string, status: number, path: string) {
    super(message);
    this.status = status;
    this.path = path;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    let message = `Request failed with HTTP ${response.status}`;
    try {
      const payload = await response.json();
      message = payload.detail ?? message;
    } catch {
      // Keep the generic message.
    }
    if (response.status === 404 && path.endsWith("/events")) {
      message = "Event endpoint unavailable.";
    } else if (response.status === 404 && path === "/api/query") {
      message = "Query endpoint unavailable.";
    } else if (response.status === 404 && path.startsWith("/api/sources/")) {
      message = "Source not found.";
    }
    throw new ApiError(message, response.status, path);
  }
  return response.json() as Promise<T>;
}

export function mediaUrl(observationId: string): string {
  return `${API_BASE}/api/media/observations/${observationId}`;
}

export function getSources(): Promise<Source[]> {
  return request<Source[]>("/api/sources");
}

export function getSource(sourceId: string): Promise<Source> {
  return request<Source>(`/api/sources/${sourceId}`);
}

export function uploadSource(file: File): Promise<Source> {
  const formData = new FormData();
  formData.append("file", file);
  return request<Source>("/api/sources/upload", {
    method: "POST",
    body: formData
  });
}

export function processSource(sourceId: string): Promise<ProcessResult> {
  return request<ProcessResult>(`/api/sources/${sourceId}/process`, {
    method: "POST"
  });
}

export async function deleteSource(sourceId: string): Promise<void> {
  await fetch(`${API_BASE}/api/sources/${sourceId}`, {
    method: "DELETE"
  }).then(async (response) => {
    if (!response.ok) {
      let message = `Request failed with HTTP ${response.status}`;
      try {
        const payload = await response.json();
        message = payload.detail ?? message;
      } catch {
        // Keep the generic message.
      }
      throw new ApiError(message, response.status, `/api/sources/${sourceId}`);
    }
  });
}

export function askQuestion(sourceId: string, question: string): Promise<QueryResponse> {
  return request<QueryResponse>("/api/query", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ source_id: sourceId, question })
  });
}

export function getEvents(sourceId: string): Promise<TimelineEvent[]> {
  return request<TimelineEvent[]>(`/api/sources/${sourceId}/events`);
}
