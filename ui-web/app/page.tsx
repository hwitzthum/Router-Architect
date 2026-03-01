"use client";

import { KeyboardEvent, useEffect, useRef, useState } from "react";
import { apiGet } from "../lib/api";
import { toUsd } from "../lib/format";
import { useRouter } from "../lib/router-context";
import type { ProviderPayload } from "../lib/types";

export default function ChatPage() {
  const {
    conversations,
    activeId,
    setActiveId,
    activeConversation,
    createNewChat,
    deleteConversation,
    sendMessage,
    sending,
    chatError,
  } = useRouter();

  const [input, setInput] = useState("");
  const [metaSidebarOpen, setMetaSidebarOpen] = useState(true);
  const [expandedMsgId, setExpandedMsgId] = useState<string | null>(null);
  const [providerPayload, setProviderPayload] = useState<ProviderPayload | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    void apiGet<ProviderPayload>("/api/providers").then(setProviderPayload).catch(() => {});
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeConversation?.messages.length]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = "auto";
      ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`;
    }
  }, [input]);

  async function handleSend() {
    const trimmed = input.trim();
    if (!trimmed || sending) return;
    setInput("");
    await sendMessage(trimmed);
    textareaRef.current?.focus();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSend();
    }
  }

  const assistantMsgs = activeConversation?.messages.filter((m) => m.role === "assistant") ?? [];
  const totalCost = assistantMsgs.reduce((sum, m) => sum + (m.estimated_cost ?? 0), 0);
  const avgLatency =
    assistantMsgs.length > 0
      ? assistantMsgs.reduce((sum, m) => sum + (m.latency_ms ?? 0), 0) / assistantMsgs.length
      : 0;
  const modelsUsed = [...new Set(assistantMsgs.map((m) => m.model_used).filter(Boolean))];

  return (
    <div className="chat-layout">
      <aside className="conv-sidebar">
        <div className="conv-sidebar-header">
          <button type="button" className="new-chat-btn" onClick={createNewChat}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            New Chat
          </button>
        </div>
        <div className="conv-list">
          {conversations.map((conv, i) => (
            <div
              key={conv.id}
              className={`conv-item ${conv.id === activeId ? "active" : ""}`}
              style={{ animationDelay: `${i * 30}ms` }}
              onClick={() => {
                setActiveId(conv.id);
                setExpandedMsgId(null);
              }}
            >
              <span className="conv-title">{conv.title}</span>
              <span className="conv-count">{conv.messages.length}</span>
              <button
                type="button"
                className="conv-delete"
                onClick={(e) => {
                  e.stopPropagation();
                  deleteConversation(conv.id);
                }}
                aria-label="Delete conversation"
              >
                &times;
              </button>
            </div>
          ))}
        </div>
      </aside>

      <main className="chat-area">
        {chatError ? <p className="error-banner chat-error">{chatError}</p> : null}

        <div className="message-list">
          {activeConversation.messages.length === 0 ? (
            <div className="chat-empty-state">
              <div className="empty-state-glow" aria-hidden="true" />
              <div className="empty-state-icon" aria-hidden="true">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20" />
                  <line x1="2" y1="12" x2="22" y2="12" />
                </svg>
              </div>
              <h2>Route a query</h2>
              <p>Your message is classified, routed to the optimal model,<br />and delivered with full telemetry.</p>
            </div>
          ) : (
            activeConversation.messages.map((msg, i) => (
              <div
                key={msg.id}
                className={`msg ${msg.role === "user" ? "msg-user" : "msg-assistant"}`}
                style={{ animationDelay: `${i * 40}ms` }}
              >
                {msg.role === "assistant" ? (
                  <div className="msg-avatar" aria-hidden="true">R</div>
                ) : null}
                <div className="msg-body">
                  <div className="msg-content">{msg.content}</div>
                  {msg.role === "assistant" && msg.model_used ? (
                    <div className="msg-footer">
                      <button
                        type="button"
                        className="model-badge"
                        onClick={() =>
                          setExpandedMsgId(expandedMsgId === msg.id ? null : msg.id)
                        }
                      >
                        <span className="model-badge-dot" />
                        via {msg.model_used}
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className={`badge-chevron ${expandedMsgId === msg.id ? "open" : ""}`}>
                          <polyline points="6 9 12 15 18 9" />
                        </svg>
                      </button>
                      {msg.latency_ms != null ? (
                        <span className="msg-latency">{msg.latency_ms}ms</span>
                      ) : null}
                      {expandedMsgId === msg.id ? (
                        <div className="msg-meta">
                          <div className="msg-meta-item">
                            <span className="msg-meta-label">Task</span>
                            <span className="msg-meta-value">{msg.task_type}</span>
                          </div>
                          <div className="msg-meta-item">
                            <span className="msg-meta-label">Cost</span>
                            <span className="msg-meta-value">{toUsd(msg.estimated_cost ?? 0)}</span>
                          </div>
                          <div className="msg-meta-item">
                            <span className="msg-meta-label">Latency</span>
                            <span className="msg-meta-value">{msg.latency_ms} ms</span>
                          </div>
                          <div className="msg-meta-item">
                            <span className="msg-meta-label">Cache</span>
                            <span className="msg-meta-value">{msg.cache_hit ? "Hit" : "Miss"}</span>
                          </div>
                          {msg.fallback_triggered ? (
                            <div className="msg-meta-item">
                              <span className="msg-meta-label">Fallback</span>
                              <span className="msg-meta-value msg-meta-warn">Yes</span>
                            </div>
                          ) : null}
                          {msg.confidence != null ? (
                            <div className="msg-meta-item">
                              <span className="msg-meta-label">Confidence</span>
                              <span className="msg-meta-value">{(msg.confidence * 100).toFixed(0)}%</span>
                            </div>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              </div>
            ))
          )}

          {sending ? (
            <div className="msg msg-assistant">
              <div className="msg-avatar" aria-hidden="true">R</div>
              <div className="msg-body">
                <div className="msg-content loading-dots">
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            </div>
          ) : null}

          <div ref={messagesEndRef} />
        </div>

        <div className="chat-input-wrap">
          <div className="chat-input">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask anything..."
              rows={1}
              disabled={sending}
            />
            <button
              type="button"
              className="send-btn"
              onClick={() => void handleSend()}
              disabled={sending || !input.trim()}
              aria-label="Send message"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </div>
          <span className="chat-input-hint">Enter to send, Shift+Enter for newline</span>
        </div>
      </main>

      <aside className={`meta-sidebar ${metaSidebarOpen ? "open" : "closed"}`}>
        <button
          type="button"
          className="meta-toggle"
          onClick={() => setMetaSidebarOpen(!metaSidebarOpen)}
          aria-label={metaSidebarOpen ? "Close metadata sidebar" : "Open metadata sidebar"}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={metaSidebarOpen ? "chevron-open" : "chevron-closed"}>
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>
        {metaSidebarOpen ? (
          <div className="meta-content">
            <h3>Session</h3>
            <dl className="meta-stats">
              <div>
                <dt>Messages</dt>
                <dd>{activeConversation.messages.length}</dd>
              </div>
              <div>
                <dt>Total Cost</dt>
                <dd>{toUsd(totalCost)}</dd>
              </div>
              <div>
                <dt>Avg Latency</dt>
                <dd>{avgLatency > 0 ? `${Math.round(avgLatency)} ms` : "\u2014"}</dd>
              </div>
              <div>
                <dt>Models Used</dt>
                <dd>{modelsUsed.length > 0 ? modelsUsed.join(", ") : "\u2014"}</dd>
              </div>
            </dl>

            <h3>Providers</h3>
            {providerPayload ? (
              <div className="meta-providers">
                {providerPayload.providers.map((p) => (
                  <div key={p.name} className="meta-provider-row">
                    <span className={`status-dot ${p.enabled && p.healthy ? "ok" : "down"}`} />
                    <span className="meta-provider-name">{p.display_name}</span>
                    <span className="meta-provider-status">{p.enabled && p.healthy ? "Online" : "Offline"}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="empty">Loading...</p>
            )}
          </div>
        ) : null}
      </aside>
    </div>
  );
}
