export type MessageRole = "user" | "assistant";

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: Date;
}

export interface ChatResponse {
  text: string;
  trace: {
    steps: number;
    tool_calls: number;
    errors: number;
  };
}

export interface ChatHistoryMessage {
  role: MessageRole;
  content: string;
}

export interface ChatRequest {
  message: string;
  model?: string;
  thread_id?: string;
  messages?: ChatHistoryMessage[];
}

export interface ModelInfo {
  name: string;
  display_name: string;
  provider: string;
  supports_vision: boolean;
  default: boolean;
}
