"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { apiPost } from "./api";
import type {
  ClassificationResult,
  Conversation,
  Message,
  RouteResult,
} from "./types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function generateId(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function createConversation(): Conversation {
  return {
    id: generateId(),
    title: "New Chat",
    messages: [],
    created_at: new Date().toISOString(),
  };
}

const STORAGE_KEY = "router_conversations";

function loadConversationsFromStorage(): Conversation[] | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Conversation[];
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
  } catch {
    /* ignore corrupt data */
  }
  return null;
}

function saveConversations(conversations: Conversation[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations));
  } catch {
    /* quota exceeded — silently ignore */
  }
}

// ---------------------------------------------------------------------------
// Context shape
// ---------------------------------------------------------------------------

type RouterContextValue = {
  // Conversations
  conversations: Conversation[];
  activeId: string;
  setActiveId: (id: string) => void;
  activeConversation: Conversation;
  createNewChat: () => void;
  deleteConversation: (id: string) => void;

  // Sending
  sendMessage: (text: string) => Promise<void>;
  sending: boolean;
  chatError: string | null;

  // Latest results (shared with Dashboard)
  lastClassification: ClassificationResult | null;
  lastRouteResult: RouteResult | null;
  lastPrompt: string | null;
};

const RouterContext = createContext<RouterContextValue | null>(null);

export function useRouter(): RouterContextValue {
  const ctx = useContext(RouterContext);
  if (!ctx) throw new Error("useRouter must be used within RouterProvider");
  return ctx;
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function RouterProvider({ children }: { children: ReactNode }) {
  // Start empty — hydrate from localStorage after mount to avoid SSR mismatch
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string>("");
  const [hydrated, setHydrated] = useState(false);
  const [sending, setSending] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);

  const [lastClassification, setLastClassification] =
    useState<ClassificationResult | null>(null);
  const [lastRouteResult, setLastRouteResult] = useState<RouteResult | null>(null);
  const [lastPrompt, setLastPrompt] = useState<string | null>(null);

  // Keep a ref so sendMessage always sees the latest conversations
  const convsRef = useRef(conversations);
  convsRef.current = conversations;

  // Hydrate from localStorage on mount (client only)
  useEffect(() => {
    const stored = loadConversationsFromStorage();
    if (stored && stored.length > 0) {
      setConversations(stored);
      setActiveId(stored[0].id);
    } else {
      const fresh = createConversation();
      setConversations([fresh]);
      setActiveId(fresh.id);
    }
    setHydrated(true);
  }, []);

  // Persist to localStorage whenever conversations change (skip initial empty state)
  useEffect(() => {
    if (hydrated && conversations.length > 0) {
      saveConversations(conversations);
    }
  }, [conversations, hydrated]);

  // Fallback conversation for pre-hydration render
  const fallback: Conversation = { id: "", title: "", messages: [], created_at: "" };
  const activeConversation =
    conversations.find((c) => c.id === activeId) ?? conversations[0] ?? fallback;

  const updateConversation = useCallback(
    (id: string, updater: (c: Conversation) => Conversation) => {
      setConversations((prev) => prev.map((c) => (c.id === id ? updater(c) : c)));
    },
    [],
  );

  const createNewChat = useCallback(() => {
    const conv = createConversation();
    setConversations((prev) => [conv, ...prev]);
    setActiveId(conv.id);
    setChatError(null);
  }, []);

  const deleteConversation = useCallback(
    (id: string) => {
      setConversations((prev) => {
        const next = prev.filter((c) => c.id !== id);
        if (next.length === 0) {
          const fresh = createConversation();
          setActiveId(fresh.id);
          return [fresh];
        }
        if (activeId === id) {
          setActiveId(next[0].id);
        }
        return next;
      });
    },
    [activeId],
  );

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || sending) return;

      const convId = activeId;
      const userMsg: Message = {
        id: generateId(),
        role: "user",
        content: trimmed,
        timestamp: new Date().toISOString(),
      };

      // Set title from first user message + append user msg
      updateConversation(convId, (c) => ({
        ...c,
        title: c.messages.length === 0 ? trimmed.slice(0, 50) : c.title,
        messages: [...c.messages, userMsg],
      }));

      setSending(true);
      setChatError(null);
      setLastPrompt(trimmed);

      try {
        // Fire classification in parallel with route
        const currentConv = convsRef.current.find((c) => c.id === convId);
        const history = [...(currentConv?.messages ?? []), userMsg];
        const apiMessages = history.map((m) => ({
          role: m.role,
          content: m.content,
        }));

        const [routeRes, classifyRes] = await Promise.all([
          apiPost<RouteResult>("/api/route", { messages: apiMessages }),
          apiPost<ClassificationResult>("/api/classify", {
            prompt: trimmed,
          }).catch(() => null),
        ]);

        // Store shared results for Dashboard
        setLastRouteResult(routeRes);
        if (classifyRes) setLastClassification(classifyRes);

        const assistantMsg: Message = {
          id: generateId(),
          role: "assistant",
          content: routeRes.response,
          timestamp: new Date().toISOString(),
          model_used: routeRes.model_used,
          task_type: routeRes.task_type,
          estimated_cost: routeRes.estimated_cost,
          latency_ms: routeRes.latency_ms,
          cache_hit: routeRes.cache_hit,
          fallback_triggered: routeRes.fallback_triggered,
          confidence: routeRes.confidence,
        };

        updateConversation(convId, (c) => ({
          ...c,
          messages: [...c.messages, assistantMsg],
        }));
      } catch (err) {
        setChatError(
          err instanceof Error ? err.message : "Failed to get response.",
        );
      } finally {
        setSending(false);
      }
    },
    [activeId, sending, updateConversation],
  );

  return (
    <RouterContext.Provider
      value={{
        conversations,
        activeId,
        setActiveId,
        activeConversation,
        createNewChat,
        deleteConversation,
        sendMessage,
        sending,
        chatError,
        lastClassification,
        lastRouteResult,
        lastPrompt,
      }}
    >
      {children}
    </RouterContext.Provider>
  );
}
