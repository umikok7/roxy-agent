type PetState = "idle" | "working" | "working-typing" | "react-drag" | string;

type ChatStreamEvent =
  | { type: "start" }
  | { type: "delta"; delta: string }
  | {
      type: "tool_called";
      call_id?: string;
      tool_name?: string;
      arguments?: Record<string, unknown>;
      output?: string;
      is_error?: boolean;
    }
  | {
      type: "done";
      text?: string;
      thread_id?: string;
      trace?: {
        steps: number;
        tool_calls: number;
        errors: number;
      } | null;
    }
  | { type: "error"; error?: string };

interface ElectronAPI {
  dragLock: (locked: boolean) => void;
  dragMove: () => void;
  dragEnd: () => void;
  startDragReaction: () => void;
  endDragReaction: () => void;
  openChatDialog: () => void;
  closeDialog: () => void;
  minimizeDialog: () => void;
  setDialogChatBusy: (active: boolean) => void;
  notifyDialogInputFocus: () => void;
  notifyDialogInputBlur: () => void;
  onStateChange: (callback: (state: PetState, svgPath: string) => void) => void;
  sendChatStream: (
    message: string,
    threadId?: string,
    messages?: Array<{ role: "user" | "assistant"; content: string }>
  ) => Promise<ChatStreamEvent[]>;
  sendChat: (
    message: string,
    threadId?: string,
    messages?: Array<{ role: "user" | "assistant"; content: string }>
  ) => Promise<unknown>;
  listModels: () => Promise<unknown>;
  healthCheck: () => Promise<boolean>;
}

declare global {
  interface Window {
    electronAPI: ElectronAPI;
  }
}

export {};
