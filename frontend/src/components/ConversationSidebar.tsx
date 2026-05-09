"use client";

import { ConversationSummary } from "@/types/chat";

interface ConversationSidebarProps {
  conversations: ConversationSummary[];
  activeThreadId: string | null;
  isLoading: boolean;
  disabled?: boolean;
  onSelectConversation: (threadId: string) => void;
  onCreateConversation: () => void;
  className?: string;
}

function formatRelativeTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }

  const diffMs = Date.now() - date.getTime();
  const diffMinutes = Math.floor(diffMs / 60000);
  if (diffMinutes < 1) return "Just now";
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

function getConversationTitle(conversation: ConversationSummary): string {
  return conversation.title?.trim() || "New conversation";
}

export function ConversationSidebar({
  conversations,
  activeThreadId,
  isLoading,
  disabled = false,
  onSelectConversation,
  onCreateConversation,
  className = "",
}: ConversationSidebarProps) {
  return (
    <aside
      className={`w-[320px] shrink-0 border-r border-zinc-200 bg-white/90 backdrop-blur flex flex-col dark:border-zinc-800 dark:bg-zinc-950/90 ${className}`}
    >
      <div className="border-b border-zinc-200 px-4 py-4 dark:border-zinc-800">
        <button
          type="button"
          onClick={onCreateConversation}
          disabled={disabled}
          className="flex w-full items-center justify-center rounded-2xl bg-zinc-900 px-4 py-3 text-sm font-medium text-zinc-50 transition-colors hover:bg-zinc-800 focus:outline-none focus:ring-2 focus:ring-zinc-400 focus:ring-offset-2 focus:ring-offset-white dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200 dark:focus:ring-zinc-600 dark:focus:ring-offset-zinc-950"
        >
          New conversation
        </button>
      </div>

      <div className="flex items-center justify-between px-4 pb-3 pt-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-400 dark:text-zinc-500">
            History
          </p>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            Pick up where you left off
          </p>
        </div>
        <div className="rounded-full border border-zinc-200 px-2.5 py-1 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
          {conversations.length}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
        {isLoading ? (
          <div className="space-y-2 px-1">
            {[0, 1, 2, 3].map((item) => (
              <div
                key={item}
                className="rounded-2xl border border-zinc-200/80 bg-zinc-50 px-3 py-3 dark:border-zinc-800 dark:bg-zinc-900/80"
              >
                <div className="h-4 w-32 animate-pulse rounded bg-zinc-200 dark:bg-zinc-800" />
                <div className="mt-2 h-3 w-full animate-pulse rounded bg-zinc-100 dark:bg-zinc-900" />
                <div className="mt-1 h-3 w-20 animate-pulse rounded bg-zinc-100 dark:bg-zinc-900" />
              </div>
            ))}
          </div>
        ) : conversations.length === 0 ? (
          <div className="px-3 py-8 text-sm text-zinc-500 dark:text-zinc-400">
            No saved conversations yet.
          </div>
        ) : (
          <div className="space-y-2">
            {conversations.map((conversation) => {
              const isActive = conversation.thread_id === activeThreadId;
              return (
                <button
                  key={conversation.thread_id}
                  type="button"
                  disabled={disabled}
                  onClick={() => onSelectConversation(conversation.thread_id)}
                  className={`w-full rounded-2xl border px-3 py-3 text-left transition-all focus:outline-none focus:ring-2 focus:ring-zinc-400 ${
                    isActive
                      ? "border-zinc-900 bg-zinc-900 text-zinc-50 shadow-sm dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900"
                      : "border-zinc-200 bg-zinc-50/80 text-zinc-900 hover:border-zinc-300 hover:bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-900/70 dark:text-zinc-100 dark:hover:border-zinc-700 dark:hover:bg-zinc-900"
                  } ${disabled ? "cursor-not-allowed opacity-70" : ""}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{getConversationTitle(conversation)}</p>
                      <p
                        className={`mt-1 line-clamp-2 text-xs leading-5 ${
                          isActive ? "text-zinc-300 dark:text-zinc-700" : "text-zinc-500 dark:text-zinc-400"
                        }`}
                      >
                        {conversation.last_message_preview?.trim() || "Open this conversation to continue chatting."}
                      </p>
                    </div>
                    <span
                      className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] ${
                        isActive
                          ? "bg-white/10 text-zinc-200 dark:bg-zinc-900/10 dark:text-zinc-700"
                          : "bg-white text-zinc-500 dark:bg-zinc-950 dark:text-zinc-400"
                      }`}
                    >
                      {conversation.message_count}
                    </span>
                  </div>
                  <div
                    className={`mt-3 flex items-center justify-between text-[11px] ${
                      isActive ? "text-zinc-400 dark:text-zinc-600" : "text-zinc-400 dark:text-zinc-500"
                    }`}
                  >
                    <span>{formatRelativeTime(conversation.updated_at)}</span>
                    <span>{conversation.thread_id.slice(-6)}</span>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </aside>
  );
}
