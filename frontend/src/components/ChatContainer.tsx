"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
import {
  ConversationDetail,
  ConversationSummary,
  Message,
  ModelInfo,
  SubagentEvent,
} from "@/types/chat";
import { MessageBubble } from "./MessageBubble";
import { ChatInput } from "./ChatInput";
import { ModelSelector } from "./ModelSelector";
import { ConversationSidebar } from "./ConversationSidebar";
import {
  createConversation,
  fetchConversation,
  fetchConversations,
  fetchModels,
  sendMessageStream,
} from "@/lib/api";

let messageIdCounter = 0;

function generateMessageId(): string {
  return `msg-${Date.now()}-${++messageIdCounter}`;
}

function buildMessagesFromConversation(detail: ConversationDetail): Message[] {
  return detail.messages.map((item) => ({
    id: item.id,
    role: item.role,
    content: item.content,
    timestamp: new Date(item.created_at),
  }));
}

function sortConversations(items: ConversationSummary[]): ConversationSummary[] {
  return [...items].sort(
    (left, right) =>
      new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime()
  );
}

function upsertConversation(
  items: ConversationSummary[],
  nextItem: ConversationSummary
): ConversationSummary[] {
  const nextList = items.filter((item) => item.thread_id !== nextItem.thread_id);
  nextList.unshift(nextItem);
  return sortConversations(nextList);
}

function getConversationTitle(conversation: ConversationSummary | null): string {
  return conversation?.title?.trim() || "New conversation";
}

const ACTIVE_THREAD_STORAGE_KEY = "agent-harness-active-thread-id";

export function ChatContainer() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [availableModels, setAvailableModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [isModelsLoading, setIsModelsLoading] = useState(true);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [isConversationListLoading, setIsConversationListLoading] = useState(true);
  const [isConversationLoading, setIsConversationLoading] = useState(false);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const threadIdRef = useRef<string | null>(null);
  const loadingThreadRef = useRef<string | null>(null);

  const activeConversation = useMemo(
    () => conversations.find((item) => item.thread_id === activeThreadId) ?? null,
    [conversations, activeThreadId]
  );

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  useEffect(() => {
    const loadModels = async () => {
      try {
        const models = await fetchModels();
        setAvailableModels(models);
        const defaultModel = models.find((item) => item.default)?.name ?? models[0]?.name ?? "";
        setSelectedModel(defaultModel);
      } catch (error) {
        console.error("Error loading models:", error);
      } finally {
        setIsModelsLoading(false);
      }
    };

    void loadModels();
  }, []);

  useEffect(() => {
    const loadConversations = async () => {
      setIsConversationListLoading(true);
      try {
        const items = sortConversations(await fetchConversations());
        setConversations(items);

        const storedThreadId = window.localStorage.getItem(ACTIVE_THREAD_STORAGE_KEY);
        if (storedThreadId && items.some((item) => item.thread_id === storedThreadId)) {
          setActiveThreadId(storedThreadId);
          threadIdRef.current = storedThreadId;
          return;
        }

        if (items[0]) {
          setActiveThreadId(items[0].thread_id);
          threadIdRef.current = items[0].thread_id;
          window.localStorage.setItem(ACTIVE_THREAD_STORAGE_KEY, items[0].thread_id);
        } else {
          setActiveThreadId(null);
          threadIdRef.current = null;
          window.localStorage.removeItem(ACTIVE_THREAD_STORAGE_KEY);
        }
      } catch (error) {
        console.error("Error loading conversations:", error);
      } finally {
        setIsConversationListLoading(false);
      }
    };

    void loadConversations();
  }, []);

  useEffect(() => {
    const threadId = activeThreadId;
    if (!threadId) {
      return;
    }
    if (loadingThreadRef.current === threadId) {
      return;
    }

    let isCancelled = false;
    loadingThreadRef.current = threadId;

    const loadConversationDetail = async () => {
      setIsConversationLoading(true);
      try {
        const detail = await fetchConversation(threadId);
        if (isCancelled) {
          return;
        }
        setMessages(buildMessagesFromConversation(detail));
        setConversations((prev) =>
          upsertConversation(prev, {
            thread_id: detail.thread_id,
            title: detail.title,
            created_at: detail.created_at,
            updated_at: detail.updated_at,
            last_message_preview: detail.last_message_preview,
            message_count: detail.message_count,
          })
        );
      } catch (error) {
        if (!isCancelled) {
          console.error("Error loading conversation detail:", error);
        }
      } finally {
        if (!isCancelled) {
          setIsConversationLoading(false);
        }
        loadingThreadRef.current = null;
      }
    };

    void loadConversationDetail();

    return () => {
      isCancelled = true;
    };
  }, [activeThreadId]);

  const handleSelectConversation = useCallback(
    (threadId: string) => {
      threadIdRef.current = threadId;
      setActiveThreadId(threadId);
      setIsMobileSidebarOpen(false);
      window.localStorage.setItem(ACTIVE_THREAD_STORAGE_KEY, threadId);
    },
    []
  );

  const handleCreateConversation = useCallback(async () => {
    try {
      const created = await createConversation();
      setConversations((prev) => upsertConversation(prev, created));
      setMessages([]);
      threadIdRef.current = created.thread_id;
      setActiveThreadId(created.thread_id);
      setIsMobileSidebarOpen(false);
      window.localStorage.setItem(ACTIVE_THREAD_STORAGE_KEY, created.thread_id);
    } catch (error) {
      console.error("Error creating conversation:", error);
    }
  }, []);

  const handleSendMessage = async (content: string) => {
    const currentThreadId = threadIdRef.current;
    const previousMessages = messages
      .filter((item) => item.role === "user" || item.role === "assistant")
      .map((item) => ({
        role: item.role,
        content: item.content,
      }));

    const userMessage: Message = {
      id: generateMessageId(),
      role: "user",
      content,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    const assistantMessageId = generateMessageId();
    const assistantMessage: Message = {
      id: assistantMessageId,
      role: "assistant",
      content: "",
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, assistantMessage]);

    try {
      await sendMessageStream(
        {
          message: content,
          model: selectedModel || undefined,
          thread_id: currentThreadId || undefined,
          messages: currentThreadId ? undefined : previousMessages,
        },
        {
          onDelta: (delta) => {
            flushSync(() => {
              setMessages((prev) =>
                prev.map((message) =>
                  message.id === assistantMessageId
                    ? { ...message, content: `${message.content}${delta}` }
                    : message
                )
              );
            });
          },
          onTaskEvent: (event) => {
            setMessages((prev) => {
              const taskId = event.task_id;
              const existingIndex = prev.findIndex(
                (m) => m.role === "subagent" && m.taskId === taskId
              );

              const newEvent: SubagentEvent = {
                ...event,
                timestamp: new Date(),
              };

              if (existingIndex !== -1) {
                const updated = [...prev];
                updated[existingIndex] = {
                  ...updated[existingIndex],
                  subagentEvents: [
                    ...(updated[existingIndex].subagentEvents || []),
                    newEvent,
                  ],
                };
                return updated;
              }
              return [
                ...prev,
                {
                  id: generateMessageId(),
                  role: "subagent",
                  content: "",
                  timestamp: new Date(),
                  taskId: taskId,
                  subagentEvents: [newEvent],
                },
              ];
            });
          },
          onDone: async ({ text, thread_id }) => {
            const resolvedThreadId = thread_id || currentThreadId || null;
            if (resolvedThreadId) {
              threadIdRef.current = resolvedThreadId;
              setActiveThreadId(resolvedThreadId);
              window.localStorage.setItem(ACTIVE_THREAD_STORAGE_KEY, resolvedThreadId);
              try {
                const detail = await fetchConversation(resolvedThreadId);
                setConversations((prev) =>
                  upsertConversation(prev, {
                    thread_id: detail.thread_id,
                    title: detail.title,
                    created_at: detail.created_at,
                    updated_at: detail.updated_at,
                    last_message_preview: detail.last_message_preview,
                    message_count: detail.message_count,
                  })
                );
              } catch (error) {
                console.error("Error refreshing conversation summary:", error);
                setConversations((prev) =>
                  sortConversations(
                    prev.map((item) =>
                      item.thread_id === resolvedThreadId
                        ? {
                            ...item,
                            updated_at: new Date().toISOString(),
                            last_message_preview: text.trim() || item.last_message_preview,
                            message_count: item.message_count + 2,
                          }
                        : item
                    )
                  )
                );
              }
            }
          },
          onError: (error) => {
            console.error("Stream error:", error);
          },
        }
      );

      setMessages((prev) =>
        prev.map((message) =>
          message.id === assistantMessageId && !message.content
            ? { ...message, content: "(empty response)" }
            : message
        )
      );
    } catch (error) {
      console.error("Error sending message:", error);
      setMessages((prev) =>
        prev.map((message) =>
          message.id === assistantMessageId
            ? { ...message, content: "Sorry, I encountered an error. Please try again." }
            : message
        )
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-full bg-zinc-50 dark:bg-black">
      <ConversationSidebar
        conversations={conversations}
        activeThreadId={activeThreadId}
        isLoading={isConversationListLoading}
        disabled={isLoading}
        onSelectConversation={handleSelectConversation}
        onCreateConversation={() => {
          void handleCreateConversation();
        }}
        className="hidden xl:flex"
      />

      {isMobileSidebarOpen && (
        <div className="fixed inset-0 z-40 flex xl:hidden">
          <button
            type="button"
            aria-label="Close conversation history"
            className="flex-1 bg-black/30 backdrop-blur-[1px]"
            onClick={() => setIsMobileSidebarOpen(false)}
          />
          <ConversationSidebar
            conversations={conversations}
            activeThreadId={activeThreadId}
            isLoading={isConversationListLoading}
            disabled={isLoading}
            onSelectConversation={handleSelectConversation}
            onCreateConversation={() => {
              void handleCreateConversation();
            }}
            className="relative z-50 h-full w-[88vw] max-w-[320px] shadow-2xl"
          />
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-zinc-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setIsMobileSidebarOpen(true)}
              disabled={isLoading}
              className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-zinc-200 text-zinc-600 transition-colors hover:bg-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-300 xl:hidden dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h10" />
              </svg>
            </button>
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900">
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                />
              </svg>
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-base font-semibold text-zinc-900 dark:text-zinc-100">
                {getConversationTitle(activeConversation)}
              </h1>
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                {isModelsLoading
                  ? "Loading..."
                  : activeConversation
                    ? `${activeConversation.message_count} messages saved`
                    : `${availableModels.length} models available`}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => {
                void handleCreateConversation();
              }}
              disabled={isLoading}
              className="rounded-full border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-700 transition-colors hover:bg-zinc-50 focus:outline-none focus:ring-2 focus:ring-zinc-300 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
            >
              New
            </button>
            <ModelSelector
              models={availableModels}
              selectedModel={selectedModel}
              onModelChange={setSelectedModel}
              disabled={isLoading || isModelsLoading}
            />
          </div>
        </header>

        <div className="flex-1 overflow-y-auto px-4 py-8">
          <div className="mx-auto max-w-3xl">
            {isConversationLoading ? (
              <div className="space-y-4 py-8">
                {[0, 1, 2].map((item) => (
                  <div key={item} className="flex justify-start">
                    <div className="w-full max-w-[70%] rounded-2xl bg-zinc-100 px-4 py-4 dark:bg-zinc-800">
                      <div className="h-4 w-3/4 animate-pulse rounded bg-zinc-200 dark:bg-zinc-700" />
                      <div className="mt-2 h-4 w-full animate-pulse rounded bg-zinc-200 dark:bg-zinc-700" />
                    </div>
                  </div>
                ))}
              </div>
            ) : messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16">
                <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-zinc-100 dark:bg-zinc-800">
                  <svg
                    className="h-8 w-8 text-zinc-500 dark:text-zinc-400"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
                    />
                  </svg>
                </div>
                <h2 className="mb-2 text-xl font-semibold text-zinc-900 dark:text-zinc-100">
                  {activeThreadId ? "Continue this conversation" : "Start a conversation"}
                </h2>
                <p className="mb-8 max-w-md text-center text-sm text-zinc-500 dark:text-zinc-400">
                  {activeThreadId
                    ? "This thread is ready for your next message."
                    : "Ask me anything and I&apos;ll help you with coding, analysis, or any questions you have."}
                </p>
                <div className="flex flex-wrap justify-center gap-2">
                  {["Write a hello world function", "Explain this code", "Help me debug"].map(
                    (suggestion) => (
                      <button
                        key={suggestion}
                        onClick={() => handleSendMessage(suggestion)}
                        disabled={isLoading}
                        className="rounded-full border border-zinc-200 bg-white px-4 py-2 text-sm text-zinc-700 transition-colors hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
                      >
                        {suggestion}
                      </button>
                    )
                  )}
                </div>
              </div>
            ) : (
              messages.map((message) => <MessageBubble key={message.id} message={message} />)
            )}
            {isLoading && (
              <div className="mb-4 flex justify-start">
                <div className="rounded-2xl bg-zinc-100 px-4 py-3 dark:bg-zinc-800">
                  <div className="flex gap-1">
                    <div className="h-2 w-2 animate-bounce rounded-full bg-zinc-400" />
                    <div
                      className="h-2 w-2 animate-bounce rounded-full bg-zinc-400"
                      style={{ animationDelay: "0.1s" }}
                    />
                    <div
                      className="h-2 w-2 animate-bounce rounded-full bg-zinc-400"
                      style={{ animationDelay: "0.2s" }}
                    />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        <div className="border-t border-zinc-200 bg-white px-4 py-4 dark:border-zinc-800 dark:bg-zinc-900">
          <div className="mx-auto max-w-3xl">
            <ChatInput onSendMessage={handleSendMessage} disabled={isLoading || isConversationLoading} />
          </div>
        </div>
      </div>
    </div>
  );
}
