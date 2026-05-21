import type {
  ConnectionStatus,
  GoalStateWsPayload,
  InboundEvent,
  OutboundImageGeneration,
  OutboundMedia,
  ToolProgressEvent,
} from "./types";
import type {
  ErrorHandler,
  EventHandler,
  NanobotClientLike,
  RuntimeModelHandler,
  SessionUpdateHandler,
  StatusHandler,
  StreamError,
  Unsubscribe,
} from "./nanobot-client";

const WS_OPEN = 1;
const WS_CLOSING = 2;
const MAX_PENDING_INBOUND = 2000;

type ColearnWsFrame = {
  event?: string;
  chat_id?: string;
  type?: string;
  session_id?: string;
  turn_id?: string;
  content?: string;
  timestamp?: number;
  metadata?: Record<string, unknown>;
  seq?: number;
};

function colearnMetadata(frame: ColearnWsFrame): Record<string, unknown> {
  return frame.metadata ?? {};
}

function colearnToolEvents(frame: ColearnWsFrame): ToolProgressEvent[] | undefined {
  const toolEvents = colearnMetadata(frame).tool_events;
  return Array.isArray(toolEvents) ? (toolEvents as ToolProgressEvent[]) : undefined;
}

function colearnLatencyMs(frame: ColearnWsFrame): number | undefined {
  const value = colearnMetadata(frame).latency_ms;
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? Math.round(value) : undefined;
}

function colearnStatus(frame: ColearnWsFrame): string {
  return String(colearnMetadata(frame).status ?? "").trim().toLowerCase();
}

function colearnPhase(frame: ColearnWsFrame): string {
  return String(colearnMetadata(frame).phase ?? "").trim().toLowerCase();
}

function colearnTraceText(frame: ColearnWsFrame): string {
  const metadata = colearnMetadata(frame);
  const toolName = typeof metadata.tool_name === "string" ? metadata.tool_name : "";
  if (frame.type === "tool_call" && toolName) {
    const args = metadata.args ?? {};
    return `${toolName}(${JSON.stringify(args)})`;
  }
  const content = typeof frame.content === "string" ? frame.content.trim() : "";
  if (content) return content;
  if (toolName) return toolName;
  return String(frame.type ?? "progress");
}

export interface ColearnWsClientOptions {
  url: string;
  baseUrl?: string;
  reconnect?: boolean;
  socketFactory?: (url: string) => WebSocket;
  maxBackoffMs?: number;
}

export class ColearnWsClient implements NanobotClientLike {
  private socket: WebSocket | null = null;
  private statusHandlers = new Set<StatusHandler>();
  private runtimeModelHandlers = new Set<RuntimeModelHandler>();
  private sessionUpdateHandlers = new Set<SessionUpdateHandler>();
  private errorHandlers = new Set<ErrorHandler>();
  private chatHandlers = new Map<string, Set<EventHandler>>();
  private pendingInboundByChat = new Map<string, InboundEvent[]>();
  private pendingFrames: Record<string, unknown>[] = [];
  private runStartedAtByChatId = new Map<string, number>();
  private goalStateByChatId = new Map<string, GoalStateWsPayload>();
  private activeTurnIdByChatId = new Map<string, string>();
  private latestSeqByTurnId = new Map<string, number>();
  private sawDeltaByTurnId = new Set<string>();
  private finalizedTurnIds = new Set<string>();
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private intentionallyClosed = false;
  private status_: ConnectionStatus = "idle";
  private defaultChatId_: string | null = null;
  private readonly shouldReconnect: boolean;
  private readonly maxBackoffMs: number;
  private readonly socketFactory: (url: string) => WebSocket;
  private currentUrl: string;
  private currentBaseUrl: string;

  constructor(options: ColearnWsClientOptions) {
    this.currentUrl = options.url;
    this.currentBaseUrl = options.baseUrl ?? "";
    this.shouldReconnect = options.reconnect ?? true;
    this.maxBackoffMs = options.maxBackoffMs ?? 15_000;
    this.socketFactory = options.socketFactory ?? ((url) => new WebSocket(url));
  }

  get status(): ConnectionStatus {
    return this.status_;
  }

  get defaultChatId(): string | null {
    return this.defaultChatId_;
  }

  updateUrl(url: string): void {
    this.currentUrl = url;
  }

  onStatus(handler: StatusHandler): Unsubscribe {
    this.statusHandlers.add(handler);
    handler(this.status_);
    return () => this.statusHandlers.delete(handler);
  }

  onRuntimeModelUpdate(handler: RuntimeModelHandler): Unsubscribe {
    this.runtimeModelHandlers.add(handler);
    return () => this.runtimeModelHandlers.delete(handler);
  }

  onSessionUpdate(handler: SessionUpdateHandler): Unsubscribe {
    this.sessionUpdateHandlers.add(handler);
    return () => this.sessionUpdateHandlers.delete(handler);
  }

  onError(handler: ErrorHandler): Unsubscribe {
    this.errorHandlers.add(handler);
    return () => this.errorHandlers.delete(handler);
  }

  getRunStartedAt(chatId: string): number | null {
    return this.runStartedAtByChatId.get(chatId) ?? null;
  }

  getGoalState(chatId: string): GoalStateWsPayload | undefined {
    return this.goalStateByChatId.get(chatId);
  }

  onChat(chatId: string, handler: EventHandler): Unsubscribe {
    let handlers = this.chatHandlers.get(chatId);
    if (!handlers) {
      handlers = new Set();
      this.chatHandlers.set(chatId, handlers);
    }
    handlers.add(handler);
    const pending = this.pendingInboundByChat.get(chatId);
    if (pending && pending.length > 0) {
      this.pendingInboundByChat.delete(chatId);
      for (const event of pending) handler(event);
    }
    this.attach(chatId);
    return () => {
      const current = this.chatHandlers.get(chatId);
      if (!current) return;
      current.delete(handler);
      if (current.size === 0) this.chatHandlers.delete(chatId);
    };
  }

  connect(): void {
    if (this.socket && this.socket.readyState < WS_CLOSING) return;
    this.intentionallyClosed = false;
    this.setStatus("connecting");
    const socket = this.socketFactory(this.currentUrl);
    this.socket = socket;
    socket.onopen = () => this.handleOpen();
    socket.onmessage = (event) => this.handleMessage(event);
    socket.onerror = () => this.setStatus("error");
    socket.onclose = (event) => this.handleClose(event);
  }

  close(): void {
    this.intentionallyClosed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    const socket = this.socket;
    this.socket = null;
    try {
      socket?.close();
    } catch {
      // ignore
    }
    this.setStatus("closed");
  }

  async newChat(): Promise<string> {
    const res = await fetch(`${this.currentBaseUrl}/api/v1/sessions`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_id: "default-project",
        project_title: "CoLearn",
        title: "",
      }),
    });
    if (!res.ok) {
      throw new Error(`newChat failed: HTTP ${res.status}`);
    }
    const body = (await res.json()) as {
      session?: { session_id?: string; id?: string };
      session_id?: string;
      id?: string;
    };
    const sessionId =
      String(body.session?.session_id ?? body.session?.id ?? body.session_id ?? body.id ?? "").trim();
    if (!sessionId) {
      throw new Error("newChat response missing session_id");
    }
    this.defaultChatId_ = sessionId;
    return sessionId;
  }

  attach(chatId: string): void {
    if (!chatId || this.socket?.readyState !== WS_OPEN) return;
    if (this.activeTurnIdByChatId.has(chatId)) {
      this.resumeActiveTurn(chatId);
      return;
    }
    this.rawSend({ type: "attach", chat_id: chatId });
  }

  sendMessage(
    chatId: string,
    content: string,
    media?: OutboundMedia[],
    options?: { imageGeneration?: OutboundImageGeneration },
  ): void {
    if (!chatId) return;
    if (content.trim() === "/stop") {
      const activeTurnId = this.activeTurnIdByChatId.get(chatId);
      if (activeTurnId) {
        this.queueSend({ type: "cancel_turn", turn_id: activeTurnId });
      }
      return;
    }
    const attachments = (media ?? []).map((item) => ({
      kind: "image",
      data_url: item.data_url,
      name: item.name ?? "",
    }));
    const frame: Record<string, unknown> = {
      type: "start_turn",
      session_id: chatId,
      project_id: "default-project",
      project_title: "CoLearn",
      content,
      language: "zh",
      attachments,
    };
    if (options?.imageGeneration) {
      frame.config = { image_generation: options.imageGeneration };
    }
    this.queueSend(frame);
  }

  private setStatus(status: ConnectionStatus): void {
    if (this.status_ === status) return;
    this.status_ = status;
    for (const handler of this.statusHandlers) handler(status);
  }

  private handleOpen(): void {
    this.setStatus("open");
    this.reconnectAttempts = 0;
    const queued = this.pendingFrames.splice(0);
    for (const frame of queued) this.rawSend(frame);
    for (const chatId of this.chatHandlers.keys()) {
      this.attach(chatId);
    }
  }

  private handleClose(_event?: { code?: number }): void {
    this.socket = null;
    if (this.intentionallyClosed || !this.shouldReconnect) {
      this.setStatus("closed");
      return;
    }
    this.scheduleReconnect();
  }

  private scheduleReconnect(): void {
    this.setStatus("reconnecting");
    const attempt = this.reconnectAttempts++;
    const delay = Math.min(500 * 2 ** attempt, this.maxBackoffMs);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  private handleMessage(ev: MessageEvent): void {
    let frame: ColearnWsFrame;
    try {
      frame = JSON.parse(typeof ev.data === "string" ? ev.data : "") as ColearnWsFrame;
    } catch {
      return;
    }
    if (frame.event === "session_updated") {
      const updatedChatId = String(frame.chat_id ?? frame.session_id ?? "").trim();
      if (updatedChatId) this.emitSessionUpdate(updatedChatId);
      return;
    }
    const sessionId = String(frame.session_id ?? "").trim();
    const turnId = String(frame.turn_id ?? "").trim();
    const seq = typeof frame.seq === "number" ? Math.floor(frame.seq) : undefined;
    const timestampSeconds =
      typeof frame.timestamp === "number" && Number.isFinite(frame.timestamp)
        ? frame.timestamp
        : Date.now() / 1000;
    if (turnId && seq !== undefined && Number.isFinite(seq)) {
      const prior = this.latestSeqByTurnId.get(turnId) ?? -1;
      if (seq > prior) this.latestSeqByTurnId.set(turnId, seq);
    }

    if (frame.type === "session" && sessionId) {
      this.defaultChatId_ = sessionId;
      if (turnId) {
        this.activeTurnIdByChatId.set(sessionId, turnId);
        this.sawDeltaByTurnId.delete(turnId);
        this.finalizedTurnIds.delete(turnId);
      }
      const startedAt = Math.floor(timestampSeconds);
      this.runStartedAtByChatId.set(sessionId, startedAt);
      this.dispatch(sessionId, {
        event: "goal_status",
        chat_id: sessionId,
        status: "running",
        started_at: startedAt,
      });
      return;
    }

    if (frame.type === "content_delta" && sessionId) {
      if (turnId) this.sawDeltaByTurnId.add(turnId);
      this.dispatch(sessionId, {
        event: "delta",
        chat_id: sessionId,
        text: String(frame.content ?? ""),
      });
      return;
    }

    if (frame.type === "reasoning_delta" && sessionId) {
      this.dispatch(sessionId, {
        event: "reasoning_delta",
        chat_id: sessionId,
        text: String(frame.content ?? ""),
      });
      return;
    }

    if (frame.type === "reasoning_end" && sessionId) {
      this.dispatch(sessionId, { event: "reasoning_end", chat_id: sessionId });
      return;
    }

    if (frame.type === "stream_end" && sessionId) {
      this.dispatch(sessionId, { event: "stream_end", chat_id: sessionId });
      return;
    }

    if (frame.type === "content" && sessionId) {
      if (turnId && this.finalizedTurnIds.has(turnId)) return;
      const sawDelta = turnId ? this.sawDeltaByTurnId.has(turnId) : false;
      if (!sawDelta && String(frame.content ?? "").trim()) {
        this.dispatch(sessionId, {
          event: "message",
          chat_id: sessionId,
          text: String(frame.content ?? ""),
          tool_events: colearnToolEvents(frame),
          latency_ms: colearnLatencyMs(frame),
        });
      }
      return;
    }

    if (frame.type === "turn_state" && sessionId) {
      const status = colearnStatus(frame);
      const phase = colearnPhase(frame);
      if (status === "running") {
        const startedAt = Math.floor(timestampSeconds);
        this.runStartedAtByChatId.set(sessionId, startedAt);
        this.dispatch(sessionId, {
          event: "goal_status",
          chat_id: sessionId,
          status: "running",
          started_at: startedAt,
        });
        return;
      }
      if (["completed", "cancelled", "failed", "rejected", "missing"].includes(status)) {
        if (turnId) {
          if (this.finalizedTurnIds.has(turnId)) return;
          this.finalizedTurnIds.add(turnId);
        }
        this.activeTurnIdByChatId.delete(sessionId);
        this.runStartedAtByChatId.delete(sessionId);
        if (turnId) this.sawDeltaByTurnId.delete(turnId);
        if (turnId) this.latestSeqByTurnId.delete(turnId);
        this.dispatch(sessionId, {
          event: "goal_status",
          chat_id: sessionId,
          status: "idle",
        });
        if (status === "failed" || status === "rejected" || status === "missing") {
          this.dispatch(sessionId, {
            event: "message",
            chat_id: sessionId,
            text: colearnTraceText(frame),
            kind: "progress",
            tool_events: colearnToolEvents(frame),
          });
        }
        if (status !== "missing") {
          this.dispatch(sessionId, {
            event: "turn_end",
            chat_id: sessionId,
            latency_ms: colearnLatencyMs(frame),
          });
        }
        return;
      }
      if (phase || String(frame.content ?? "").trim()) {
        this.dispatch(sessionId, {
          event: "message",
          chat_id: sessionId,
          text: colearnTraceText(frame),
          kind: "progress",
          tool_events: colearnToolEvents(frame),
        });
      }
      return;
    }

    if (frame.type === "done" && sessionId) {
      if (turnId) {
        if (this.finalizedTurnIds.has(turnId)) return;
        this.finalizedTurnIds.add(turnId);
      }
      this.activeTurnIdByChatId.delete(sessionId);
      this.runStartedAtByChatId.delete(sessionId);
      if (turnId) this.sawDeltaByTurnId.delete(turnId);
      if (turnId) this.latestSeqByTurnId.delete(turnId);
      this.dispatch(sessionId, {
        event: "goal_status",
        chat_id: sessionId,
        status: "idle",
      });
      this.dispatch(sessionId, {
        event: "turn_end",
        chat_id: sessionId,
        latency_ms: colearnLatencyMs(frame),
      });
      return;
    }

    if (frame.type === "error" && sessionId) {
      if (turnId) {
        if (this.finalizedTurnIds.has(turnId)) return;
        this.finalizedTurnIds.add(turnId);
      }
      this.activeTurnIdByChatId.delete(sessionId);
      this.runStartedAtByChatId.delete(sessionId);
      if (turnId) this.latestSeqByTurnId.delete(turnId);
      if (turnId) this.sawDeltaByTurnId.delete(turnId);
      this.dispatch(sessionId, {
        event: "goal_status",
        chat_id: sessionId,
        status: "idle",
      });
      this.dispatch(sessionId, {
        event: "message",
        chat_id: sessionId,
        text: String(frame.content ?? "Request failed."),
        kind: "progress",
        tool_events: colearnToolEvents(frame),
      });
      return;
    }

    if (sessionId && frame.type) {
      this.dispatch(sessionId, {
        event: "message",
        chat_id: sessionId,
        text: colearnTraceText(frame),
        kind: frame.type === "tool_call" ? "tool_hint" : "progress",
        tool_events: colearnToolEvents(frame),
      });
    }
  }

  private emitSessionUpdate(chatId: string): void {
    for (const handler of this.sessionUpdateHandlers) handler(chatId);
  }

  private dispatch(chatId: string, event: InboundEvent): void {
    const handlers = this.chatHandlers.get(chatId);
    if (handlers && handlers.size > 0) {
      for (const handler of handlers) handler(event);
      return;
    }
    const queued = this.pendingInboundByChat.get(chatId) ?? [];
    queued.push(event);
    if (queued.length > MAX_PENDING_INBOUND) {
      queued.splice(0, queued.length - MAX_PENDING_INBOUND);
    }
    this.pendingInboundByChat.set(chatId, queued);
  }

  private queueSend(frame: Record<string, unknown>): void {
    if (this.socket?.readyState === WS_OPEN) {
      this.rawSend(frame);
    } else {
      this.pendingFrames.push(frame);
    }
  }

  private rawSend(frame: Record<string, unknown>): void {
    if (!this.socket) return;
    try {
      this.socket.send(JSON.stringify(frame));
    } catch {
      this.pendingFrames.push(frame);
    }
  }

  private resumeActiveTurn(chatId: string): void {
    const turnId = this.activeTurnIdByChatId.get(chatId);
    if (!turnId) return;
    const afterSeq = (this.latestSeqByTurnId.get(turnId) ?? -1) + 1;
    this.queueSend({
      type: "subscribe_turn",
      turn_id: turnId,
      after_seq: afterSeq,
    });
  }
}

export function emitNoopError(_error: StreamError): void {}
