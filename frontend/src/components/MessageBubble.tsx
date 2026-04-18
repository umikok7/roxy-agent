"use client";

import { Message } from "@/types/chat";

interface MessageBubbleProps {
  message: Message;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  const formattedTime = (() => {
    const h = message.timestamp.getHours().toString().padStart(2, "0");
    const m = message.timestamp.getMinutes().toString().padStart(2, "0");
    return `${h}:${m}`;
  })();

  return (
    <div
      className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}
    >
      <div
        className={`max-w-[70%] rounded-2xl px-4 py-3 ${
          isUser
            ? "bg-zinc-900 text-zinc-50 dark:bg-zinc-100 dark:text-zinc-900"
            : "bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100"
        }`}
      >
        <div className="prose prose-sm max-w-none dark:prose-invert">
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>
        <div
          className={`text-xs mt-1 ${
            isUser ? "text-zinc-500" : "text-zinc-400"
          }`}
        >
          {formattedTime}
        </div>
      </div>
    </div>
  );
}