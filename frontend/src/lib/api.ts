import {
  ChatRequest,
  ChatResponse,
  ConversationDetail,
  ConversationSummary,
  ModelInfo,
  StreamTraceInfo,
} from "@/types/chat";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "/api";

export async function sendMessage(request: ChatRequest): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  return response.json();
}

interface StreamHandlers {
  onStart?: () => void;
  onDelta: (delta: string) => void;
  onTaskEvent?: (event: {
    type: "task_started" | "task_running" | "task_completed" | "task_failed" | "task_timed_out";
    task_id: string;
    description?: string;
    subagent_type?: string;
    message?: string;
    result?: string;
    error?: string;
  }) => void;
  onDone?: (payload: { text: string; trace: StreamTraceInfo; thread_id?: string }) => void;
  onError?: (error: string) => void;
}

async function yieldToBrowser(): Promise<void> {
  await new Promise<void>((resolve) => {
    if (typeof window !== "undefined" && typeof window.requestAnimationFrame === "function") {
      window.requestAnimationFrame(() => resolve());
      return;
    }
    setTimeout(resolve, 0);
  });
}

export async function sendMessageStream(request: ChatRequest, handlers: StreamHandlers): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  if (!response.body) {
    throw new Error("ReadableStream is not supported by this browser.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";

    for (const rawEvent of events) {
      const dataLine = rawEvent
        .split("\n")
        .find((line) => line.startsWith("data:"));

      if (!dataLine) {
        continue;
      }

      const payloadText = dataLine.slice(5).trim();
      if (!payloadText) {
        continue;
      }

      let payload: unknown;
      try {
        payload = JSON.parse(payloadText);
      } catch {
        continue;
      }

      if (!payload || typeof payload !== "object") {
        continue;
      }

      const event = payload as {
        type?: string;
        delta?: string;
        error?: string;
        text?: string;
        trace?: StreamTraceInfo;
        thread_id?: string;
        task_id?: string;
        description?: string;
        subagent_type?: string;
        message?: string;
        result?: string;
      };

      if (event.type === "start") {
        handlers.onStart?.();
      } else if (event.type === "delta" && typeof event.delta === "string") {
        handlers.onDelta(event.delta);
        await yieldToBrowser();
      } else if (
        (event.type === "task_started" ||
          event.type === "task_running" ||
          event.type === "task_completed" ||
          event.type === "task_failed" ||
          event.type === "task_timed_out") &&
        typeof event.task_id === "string"
      ) {
        handlers.onTaskEvent?.({
          type: event.type,
          task_id: event.task_id,
          description: event.description,
          subagent_type: event.subagent_type,
          message: event.message,
          result: event.result,
          error: event.error,
        });
      } else if (event.type === "done" && typeof event.text === "string" && event.trace) {
        handlers.onDone?.({ text: event.text, trace: event.trace, thread_id: event.thread_id });
      } else if (event.type === "error") {
        handlers.onError?.(event.error ?? "Unknown stream error");
        throw new Error(event.error ?? "Unknown stream error");
      }
    }
  }
}

export async function fetchModels(): Promise<ModelInfo[]> {
  const response = await fetch(`${API_BASE_URL}/models`);
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  return response.json();
}

export async function fetchConversations(): Promise<ConversationSummary[]> {
  const response = await fetch(`${API_BASE_URL}/conversations`);
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  return response.json();
}

export async function fetchConversation(threadId: string): Promise<ConversationDetail> {
  const response = await fetch(`${API_BASE_URL}/conversations/${encodeURIComponent(threadId)}`);
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  return response.json();
}

export async function createConversation(): Promise<ConversationSummary> {
  const response = await fetch(`${API_BASE_URL}/conversations/create`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  return response.json();
}
