import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import attentionSvg from "../../../assets/roxy/roxy-attention.svg";
import roxyBackgroundPng from "../../../assets/roxy/roxy-background.png";
import thinkingSvg from "../../../assets/roxy/roxy-thinking.svg";

type MessageRole = "assistant" | "user";

type TraceSummary = {
  steps: number;
  tool_calls: number;
  errors: number;
};

type ChatMessage = {
  id: string;
  role: MessageRole;
  content: string;
  isError?: boolean;
  includeInHistory?: boolean;
};

type ConversationTurn = {
  id: string;
  userText: string;
  assistantText: string;
  isStreaming: boolean;
  isError: boolean;
  previewText: string;
};

function createId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function toPreviewText(userText: string, assistantText: string) {
  const assistantPreview = assistantText.trim();
  if (assistantPreview) return assistantPreview;

  const userPreview = userText.trim();
  if (!userPreview) return "Roxy 正在整理这轮对白...";

  return `你：${userPreview}`;
}

function buildConversationTurns(messages: ChatMessage[]): ConversationTurn[] {
  const historyMessages = messages.filter((message) => message.includeInHistory !== false);
  const turns: ConversationTurn[] = [];
  let currentTurn: ConversationTurn | null = null;

  for (const message of historyMessages) {
    if (message.role === "user") {
      currentTurn = {
        id: message.id,
        userText: message.content,
        assistantText: "",
        isStreaming: true,
        isError: false,
        previewText: toPreviewText(message.content, ""),
      };
      turns.push(currentTurn);
      continue;
    }

    if (!currentTurn) {
      currentTurn = {
        id: message.id,
        userText: "",
        assistantText: message.content,
        isStreaming: false,
        isError: Boolean(message.isError),
        previewText: toPreviewText("", message.content),
      };
      turns.push(currentTurn);
      currentTurn = null;
      continue;
    }

    currentTurn.assistantText = message.content;
    currentTurn.isError = Boolean(message.isError);
    currentTurn.isStreaming = false;
    currentTurn.previewText = toPreviewText(currentTurn.userText, message.content);
    currentTurn = null;
  }

  if (currentTurn) {
    currentTurn.previewText = toPreviewText(currentTurn.userText, currentTurn.assistantText);
  }

  return turns;
}

export default function DialogApp() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isOnline, setIsOnline] = useState(false);
  const [statusDetail, setStatusDetail] = useState("正在寻找后端连接...");
  const [isStreaming, setIsStreaming] = useState(false);
  const [showTyping, setShowTyping] = useState(false);
  const [trace, setTrace] = useState<TraceSummary | null>(null);
  const [selectedTurnId, setSelectedTurnId] = useState<string | null>(null);

  const messagesContainerRef = useRef<HTMLElement | null>(null);
  const messageInputRef = useRef<HTMLInputElement | null>(null);
  const threadIdRef = useRef(createId("thread"));
  const assistantTextContentRef = useRef("");
  const streamingMessageIdRef = useRef<string | null>(null);
  const hasBootstrappedWelcomeRef = useRef(false);

  const placeholder = useMemo(
    () => (isOnline ? "在这里写下下一句对白..." : "后端离线时暂时无法对话"),
    [isOnline]
  );

  const pushMessage = (message: ChatMessage) => {
    setMessages((prev) => [...prev, message]);
  };

  const updateMessage = (messageId: string, updater: (message: ChatMessage) => ChatMessage) => {
    setMessages((prev) => prev.map((message) => (message.id === messageId ? updater(message) : message)));
  };

  const systemMessages = useMemo(
    () => messages.filter((message) => message.includeInHistory === false),
    [messages]
  );

  const turns = useMemo(() => buildConversationTurns(messages), [messages]);
  const hasConversationTurns = turns.length > 0;
  const selectedTurn = useMemo(
    () => turns.find((turn) => turn.id === selectedTurnId) ?? null,
    [selectedTurnId, turns]
  );

  const bootstrapWelcome = () => {
    if (hasBootstrappedWelcomeRef.current) return;
    hasBootstrappedWelcomeRef.current = true;
    pushMessage({
      id: createId("assistant"),
      role: "assistant",
      content: "今天想和 Roxy 聊哪一段剧情？",
      includeInHistory: false,
    });
  };

  useEffect(() => {
    const container = messagesContainerRef.current;
    if (container) {
      container.scrollTop = container.scrollHeight;
    }
  }, [showTyping, systemMessages.length, turns.length]);

  useEffect(() => {
    if (selectedTurnId && !selectedTurn) {
      setSelectedTurnId(null);
    }
  }, [selectedTurn, selectedTurnId]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSelectedTurnId(null);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    let disposed = false;

    const init = async () => {
      try {
        const healthy = await window.electronAPI.healthCheck();
        if (!healthy) {
          throw new Error("Backend health check failed");
        }

        if (disposed) return;
        setIsOnline(true);
        setStatusDetail("后端已连接，Roxy 随时待命");
        bootstrapWelcome();

        try {
          const models = await window.electronAPI.listModels();
          if (!disposed && Array.isArray(models) && models.length > 0) {
            setStatusDetail(`已连接后端，可用模型 ${models.length} 个`);
          }
        } catch (error) {
          console.warn("Could not load models:", error);
        }
      } catch (error) {
        console.warn("Backend not available:", error);
        if (disposed) return;
        setIsOnline(false);
        setStatusDetail("后端暂未连接");
        pushMessage({
          id: createId("assistant"),
          role: "assistant",
          content: "等服务启动后，再双击我回来聊天吧。",
          isError: true,
          includeInHistory: false,
        });
      }
    };

    init();

    return () => {
      disposed = true;
    };
  }, []);

  const getConversationHistory = () =>
    messages
      .filter((message) => message.includeInHistory !== false)
      .map((message) => ({
        role: message.role,
        content: message.content.trim(),
      }))
      .filter((message) => Boolean(message.content))
      .slice(-12);

  const appendAssistantDelta = (delta: string) => {
    const streamMessageId = streamingMessageIdRef.current ?? createId("assistant");

    if (!streamingMessageIdRef.current) {
      streamingMessageIdRef.current = streamMessageId;
      pushMessage({
        id: streamMessageId,
        role: "assistant",
        content: delta,
      });
      return;
    }

    updateMessage(streamMessageId, (message) => ({
      ...message,
      content: `${message.content}${delta}`,
    }));
  };

  const finalizeAssistantMessage = (finalText: string, nextTrace: TraceSummary | null) => {
    const streamMessageId = streamingMessageIdRef.current;

    if (streamMessageId) {
      updateMessage(streamMessageId, (message) => ({
        ...message,
        content: finalText || "(empty response)",
      }));
    } else if (finalText) {
      pushMessage({
        id: createId("assistant"),
        role: "assistant",
        content: finalText,
      });
    }

    streamingMessageIdRef.current = null;
    setTrace(nextTrace);
  };

  const sendMessage = async (message: string) => {
    if (!message || isStreaming || !isOnline) return;

    assistantTextContentRef.current = "";
    streamingMessageIdRef.current = null;
    setIsStreaming(true);
    setTrace(null);

    const userMessageId = createId("user");
    pushMessage({
      id: userMessageId,
      role: "user",
      content: message,
    });
    setShowTyping(true);

    try {
      const events = await window.electronAPI.sendChatStream(
        message,
        threadIdRef.current,
        getConversationHistory()
      );

      for (const event of Array.isArray(events) ? events : []) {
        if (event.type === "start") {
          continue;
        }

        if (event.type === "delta" && typeof event.delta === "string") {
          assistantTextContentRef.current += event.delta;
          appendAssistantDelta(event.delta);
          continue;
        }

        if (event.type === "done") {
          if (event.thread_id) {
            threadIdRef.current = event.thread_id;
          }
          finalizeAssistantMessage(
            typeof event.text === "string" && event.text ? event.text : assistantTextContentRef.current,
            event.trace ?? null
          );
          continue;
        }

        if (event.type === "error") {
          throw new Error(event.error || "Unknown stream error");
        }
      }

      if (streamingMessageIdRef.current) {
        finalizeAssistantMessage(assistantTextContentRef.current, null);
      } else if (assistantTextContentRef.current) {
        pushMessage({
          id: createId("assistant"),
          role: "assistant",
          content: assistantTextContentRef.current,
        });
      }
    } catch (error) {
      console.error("Chat error:", error);
      const errorText =
        assistantTextContentRef.current ||
        `连接失败：${error instanceof Error ? error.message : "unknown error"}`;

      if (streamingMessageIdRef.current) {
        finalizeAssistantMessage(errorText, null);
      } else {
        pushMessage({
          id: createId("assistant"),
          role: "assistant",
          content: errorText,
          isError: !assistantTextContentRef.current,
        });
      }
    } finally {
      setShowTyping(false);
      setIsStreaming(false);
      setInputValue("");
      messageInputRef.current?.focus();
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await sendMessage(inputValue.trim());
  };

  const handleInputKeyDown = async (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      await sendMessage(inputValue.trim());
    }
  };

  const handleTurnKeyDown = (event: KeyboardEvent<HTMLButtonElement>, turnId: string) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setSelectedTurnId(turnId);
    }
  };

  return (
    <div className="dialog-shell">
      <div className="dialog-frame">
        <div className="window-drag-zone" aria-hidden="true" />
        <div className="background-figure" aria-hidden="true">
          <img src={roxyBackgroundPng} alt="" />
        </div>

        <div className="floating-controls">
          <button
            type="button"
            id="close-btn"
            className="floating-btn"
            aria-label="Hide dialog"
            onClick={() => window.electronAPI.closeDialog()}
          >
            <span />
          </button>
        </div>

        <main
          id="messages"
          ref={messagesContainerRef}
          className={`turns-stage${hasConversationTurns ? " has-turns" : ""}`}
        >
          {systemMessages.length > 0 ? (
            <section className="system-feed" aria-label="Roxy status">
              {systemMessages.map((message) => (
                <div key={message.id} className={`system-bubble${message.isError ? " error" : ""}`}>
                  <img src={attentionSvg} alt="" aria-hidden="true" />
                  <p>{message.content}</p>
                </div>
              ))}
            </section>
          ) : null}

          <section className="turns-feed" aria-label="Conversation previews">
            {turns.map((turn, index) => (
              <button
                key={turn.id}
                type="button"
                className={`system-bubble turn-bubble${turn.isStreaming ? " streaming" : ""}${turn.isError ? " error" : ""}`}
                onClick={() => setSelectedTurnId(turn.id)}
                onKeyDown={(event) => handleTurnKeyDown(event, turn.id)}
                aria-label={`Open turn ${index + 1} details`}
              >
                <img src={attentionSvg} alt="" aria-hidden="true" />
                <div className="turn-bubble-copy">
                  <p className="turn-preview">{turn.previewText}</p>
                  <span className="turn-meta">
                    {turn.isStreaming ? "对白生成中..." : `第 ${index + 1} 轮对白`}
                  </span>
                </div>
              </button>
            ))}
          </section>
        </main>

        <div className={`typing-indicator${showTyping ? "" : " hidden"}`} aria-live="polite">
          <div className="typing-avatar">
            <img src={thinkingSvg} alt="" aria-hidden="true" />
          </div>
          <div className="typing-bubble">
            <span />
            <span />
            <span />
          </div>
          <span className="typing-copy">Roxy 正在写下这一轮回应...</span>
        </div>

        <div className={`trace-info${trace ? "" : " hidden"}`}>
          <span>
            {trace
              ? `Steps ${trace.steps} · Tool calls ${trace.tool_calls} · Errors ${trace.errors}`
              : ""}
          </span>
        </div>

        <footer className="input-panel">
          <form id="chat-form" className="chat-form" onSubmit={handleSubmit}>
            <label className="sr-only" htmlFor="message-input">
              Chat with Roxy
            </label>
            <input
              ref={messageInputRef}
              type="text"
              id="message-input"
              className="message-input"
              placeholder={placeholder}
              autoComplete="off"
              disabled={!isOnline || isStreaming}
              value={inputValue}
              onChange={(event) => setInputValue(event.target.value)}
              onFocus={() => window.electronAPI.notifyDialogInputFocus()}
              onBlur={() => window.electronAPI.notifyDialogInputBlur()}
              onKeyDown={handleInputKeyDown}
            />
            <button
              type="submit"
              id="send-btn"
              className="send-btn"
              disabled={!isOnline || isStreaming}
              aria-label="Send message"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M4 12.5 20 4l-4.5 16-4-5-7.5-2.5Z" />
              </svg>
            </button>
          </form>
        </footer>

        <div
          className={`turn-overlay${selectedTurn ? " visible" : ""}`}
          aria-hidden={selectedTurn ? "false" : "true"}
          onClick={() => setSelectedTurnId(null)}
        >
          <div className="turn-overlay-content" role="dialog" aria-modal="true" aria-labelledby="turn-dialog-title" onClick={(event) => event.stopPropagation()}>
            <button
              type="button"
              className="overlay-close-btn"
              aria-label="Close detail view"
              onClick={() => setSelectedTurnId(null)}
            >
              <span />
            </button>

            {selectedTurn ? (
              <>
                <p id="turn-dialog-title" className="overlay-title">
                  这一轮完整对白
                </p>
                <section className="detail-bubble detail-user">
                  <div className="detail-label">YOU</div>
                  <div className="detail-text">{selectedTurn.userText || "这一轮没有用户输入。"}</div>
                </section>

                <section className={`detail-bubble detail-assistant${selectedTurn.isError ? " error" : ""}`}>
                  <div className="detail-label detail-label-roxy">ROXY</div>
                  <div className="detail-text">
                    {selectedTurn.assistantText || (selectedTurn.isStreaming ? "Roxy 正在继续写下回答..." : "(empty response)")}
                  </div>
                </section>
              </>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
