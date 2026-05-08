import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent as ReactKeyboardEvent } from "react";
import attentionSvg from "../../../assets/roxy/roxy-attention.svg";
import roxyBackgroundPng from "../../../assets/roxy/roxy-background.png";
import thinkingSvg from "../../../assets/roxy/roxy-thinking.svg";

type MessageRole = "assistant" | "user";

type TraceSummary = {
  steps: number;
  tool_calls: number;
  errors: number;
};

type ToolCallEvent = {
  callId: string;
  toolName: string;
  arguments: Record<string, unknown>;
  output: string;
  isError: boolean;
};

type ChatMessage = {
  id: string;
  role: MessageRole;
  content: string;
  isError?: boolean;
  includeInHistory?: boolean;
  toolEvents?: ToolCallEvent[];
  trace?: TraceSummary | null;
};

type ConversationTurn = {
  id: string;
  userText: string;
  assistantText: string;
  reasoningText: string;
  finalAnswerText: string;
  isStreaming: boolean;
  isError: boolean;
  previewText: string;
  toolEvents: ToolCallEvent[];
  trace: TraceSummary | null;
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

function parseAssistantContent(rawText: string) {
  const text = rawText.trim();
  if (!text) {
    return {
      reasoningText: "",
      finalAnswerText: "",
    };
  }

  const taggedPatterns = [
    /<think>([\s\S]*?)<\/think>\s*([\s\S]*)/i,
    /<analysis>([\s\S]*?)<\/analysis>\s*([\s\S]*)/i,
  ];

  for (const pattern of taggedPatterns) {
    const match = text.match(pattern);
    if (match) {
      return {
        reasoningText: match[1]?.trim() ?? "",
        finalAnswerText: match[2]?.trim() ?? "",
      };
    }
  }

  const headingPatterns = [
    /(?:^|\n)(?:thinking|thought process|analysis|思考过程|推理过程)[:：]\s*([\s\S]*?)(?:\n(?:final answer|answer|最终答案|结论)[:：]\s*)([\s\S]*)$/i,
  ];

  for (const pattern of headingPatterns) {
    const match = text.match(pattern);
    if (match) {
      return {
        reasoningText: match[1]?.trim() ?? "",
        finalAnswerText: match[2]?.trim() ?? "",
      };
    }
  }

  return {
    reasoningText: "",
    finalAnswerText: text,
  };
}

function buildConversationTurns(messages: ChatMessage[]): ConversationTurn[] {
  const historyMessages = messages.filter((message) => message.includeInHistory !== false);
  const turns: ConversationTurn[] = [];
  let currentTurn: ConversationTurn | null = null;

  for (const message of historyMessages) {
    if (message.role === "user") {
      const parsedAssistant = parseAssistantContent("");
      currentTurn = {
        id: message.id,
        userText: message.content,
        assistantText: "",
        reasoningText: parsedAssistant.reasoningText,
        finalAnswerText: parsedAssistant.finalAnswerText,
        isStreaming: true,
        isError: false,
        previewText: toPreviewText(message.content, parsedAssistant.finalAnswerText),
        toolEvents: [],
        trace: null,
      };
      turns.push(currentTurn);
      continue;
    }

    if (!currentTurn) {
      const parsedAssistant = parseAssistantContent(message.content);
      currentTurn = {
        id: message.id,
        userText: "",
        assistantText: message.content,
        reasoningText: parsedAssistant.reasoningText,
        finalAnswerText: parsedAssistant.finalAnswerText,
        isStreaming: false,
        isError: Boolean(message.isError),
        previewText: toPreviewText("", parsedAssistant.finalAnswerText),
        toolEvents: message.toolEvents ?? [],
        trace: message.trace ?? null,
      };
      turns.push(currentTurn);
      currentTurn = null;
      continue;
    }

    const parsedAssistant = parseAssistantContent(message.content);
    currentTurn.assistantText = message.content;
    currentTurn.reasoningText = parsedAssistant.reasoningText;
    currentTurn.finalAnswerText = parsedAssistant.finalAnswerText;
    currentTurn.isError = Boolean(message.isError);
    currentTurn.isStreaming = false;
    currentTurn.previewText = toPreviewText(currentTurn.userText, parsedAssistant.finalAnswerText);
    currentTurn.toolEvents = message.toolEvents ?? [];
    currentTurn.trace = message.trace ?? null;
    currentTurn = null;
  }

  if (currentTurn) {
    currentTurn.previewText = toPreviewText(currentTurn.userText, currentTurn.finalAnswerText);
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
  const [expandedToolIds, setExpandedToolIds] = useState<Record<string, boolean>>({});
  const [showReasoning, setShowReasoning] = useState(false);

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
    setExpandedToolIds({});
    setShowReasoning(false);
  }, [selectedTurnId]);

  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
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

  const appendToolEvent = (event: ToolCallEvent) => {
    const streamMessageId = streamingMessageIdRef.current;
    if (!streamMessageId) return;

    updateMessage(streamMessageId, (message) => ({
      ...message,
      toolEvents: [...(message.toolEvents ?? []), event],
    }));
  };

  const finalizeAssistantMessage = (finalText: string, nextTrace: TraceSummary | null) => {
    const streamMessageId = streamingMessageIdRef.current;

    if (streamMessageId) {
      updateMessage(streamMessageId, (message) => ({
        ...message,
        content: finalText || "(empty response)",
        trace: nextTrace,
      }));
    } else if (finalText) {
      pushMessage({
        id: createId("assistant"),
        role: "assistant",
        content: finalText,
        trace: nextTrace,
      });
    }

    streamingMessageIdRef.current = null;
    setTrace(nextTrace);
  };

  const sendMessage = async (message: string) => {
    if (!message || isStreaming || !isOnline) return;

    assistantTextContentRef.current = "";
    streamingMessageIdRef.current = null;
    let hasFinalizedAssistantMessage = false;
    setIsStreaming(true);
    setTrace(null);
    window.electronAPI.setDialogChatBusy(true);

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

        if (event.type === "tool_called") {
          appendToolEvent({
            callId: typeof event.call_id === "string" && event.call_id ? event.call_id : createId("tool"),
            toolName: typeof event.tool_name === "string" && event.tool_name ? event.tool_name : "unknown_tool",
            arguments: event.arguments && typeof event.arguments === "object" ? event.arguments : {},
            output: typeof event.output === "string" ? event.output : "",
            isError: Boolean(event.is_error),
          });
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
          hasFinalizedAssistantMessage = true;
          continue;
        }

        if (event.type === "error") {
          throw new Error(event.error || "Unknown stream error");
        }
      }

      if (!hasFinalizedAssistantMessage && streamingMessageIdRef.current) {
        finalizeAssistantMessage(assistantTextContentRef.current, null);
      } else if (!hasFinalizedAssistantMessage && assistantTextContentRef.current) {
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
      window.electronAPI.setDialogChatBusy(false);
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

  const handleInputKeyDown = async (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      await sendMessage(inputValue.trim());
    }
  };

  const handleTurnKeyDown = (event: ReactKeyboardEvent<HTMLButtonElement>, turnId: string) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setSelectedTurnId(turnId);
    }
  };

  const toggleToolDetails = (callId: string) => {
    setExpandedToolIds((prev) => ({
      ...prev,
      [callId]: !prev[callId],
    }));
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
                  <div className="turn-meta-row">
                    <span className="turn-meta">
                      {turn.isStreaming ? "对白生成中..." : `第 ${index + 1} 轮对白`}
                    </span>
                    {turn.toolEvents.length > 0 ? (
                      <span className="turn-tool-pill">
                        {turn.toolEvents.length} 次 tool call
                      </span>
                    ) : null}
                  </div>
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
            {selectedTurn ? (
              <>
                <div className="overlay-header">
                  <div>
                    <p id="turn-dialog-title" className="overlay-title">
                      这一轮完整对白
                    </p>
                    <p className="overlay-subtitle">
                      {selectedTurn.trace
                        ? `Steps ${selectedTurn.trace.steps} · Tool calls ${selectedTurn.trace.tool_calls} · Errors ${selectedTurn.trace.errors}`
                        : "查看本轮完整回复与执行细节"}
                    </p>
                  </div>
                  <button
                    type="button"
                    className="overlay-close-btn"
                    aria-label="Close detail view"
                    onClick={() => setSelectedTurnId(null)}
                  >
                    <span />
                  </button>
                </div>

                <div className="overlay-body">
                  <section className="detail-bubble detail-user">
                    <div className="detail-label">YOU</div>
                    <div className="detail-text">{selectedTurn.userText || "这一轮没有用户输入。"}</div>
                  </section>

                  <section className={`detail-bubble detail-assistant${selectedTurn.isError ? " error" : ""}`}>
                    {selectedTurn.reasoningText ? (
                      <div className="reasoning-panel">
                        <button
                          type="button"
                          className="reasoning-toggle"
                          onClick={() => setShowReasoning((prev) => !prev)}
                          aria-expanded={showReasoning}
                        >
                          <span className="detail-label detail-label-thinking">THINK</span>
                          <span className="reasoning-summary">
                            {showReasoning ? "收起思考过程" : "展开思考过程"}
                          </span>
                          <span className={`reasoning-chevron${showReasoning ? " expanded" : ""}`}>⌄</span>
                        </button>
                        {showReasoning ? (
                          <div className="reasoning-body">
                            <div className="detail-text detail-text-muted">{selectedTurn.reasoningText}</div>
                          </div>
                        ) : null}
                      </div>
                    ) : null}

                    <div className="answer-panel">
                      <div className="detail-label detail-label-roxy">FINAL ANSWER</div>
                      <div className="detail-text">
                        {selectedTurn.finalAnswerText || selectedTurn.assistantText || (selectedTurn.isStreaming ? "Roxy 正在继续写下回答..." : "(empty response)")}
                      </div>
                    </div>
                  </section>

                  {selectedTurn.toolEvents.length > 0 ? (
                    <section className="detail-bubble detail-tools">
                      <div className="detail-tools-header">
                        <div>
                          <div className="detail-label detail-label-tools">TOOL CALLS</div>
                          <p className="detail-tools-summary">
                            点击展开
                          </p>
                        </div>
                        <span className="tool-count-badge">{selectedTurn.toolEvents.length}</span>
                      </div>

                      <div className="tool-list">
                        {selectedTurn.toolEvents.map((toolEvent, toolIndex) => {
                          const isExpanded = Boolean(expandedToolIds[toolEvent.callId]);
                          return (
                            <article key={toolEvent.callId} className={`tool-card${toolEvent.isError ? " error" : ""}`}>
                              <button
                                type="button"
                                className="tool-card-trigger"
                                onClick={() => toggleToolDetails(toolEvent.callId)}
                                aria-expanded={isExpanded}
                              >
                                <div className="tool-card-main">
                                  <span className={`tool-status-dot${toolEvent.isError ? " error" : ""}`} />
                                  <div className="tool-card-copy">
                                    <span className="tool-card-title">{toolEvent.toolName}</span>
                                    <span className="tool-card-meta">
                                      Tool #{toolIndex + 1} · {Object.keys(toolEvent.arguments).length} args
                                    </span>
                                  </div>
                                </div>
                                <span className={`tool-chevron${isExpanded ? " expanded" : ""}`}>⌄</span>
                              </button>

                              {isExpanded ? (
                                <div className="tool-card-details">
                                  <div className="tool-code-block">
                                    <span className="tool-code-label">Arguments</span>
                                    <pre>{JSON.stringify(toolEvent.arguments, null, 2)}</pre>
                                  </div>
                                  <div className="tool-code-block">
                                    <span className="tool-code-label">Output</span>
                                    <pre>{toolEvent.output || "(empty output)"}</pre>
                                  </div>
                                </div>
                              ) : null}
                            </article>
                          );
                        })}
                      </div>
                    </section>
                  ) : null}
                </div>
              </>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
