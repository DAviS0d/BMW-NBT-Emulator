import { parseWireMessage, type ClientMessage, type ServerMessage, type WireMessage } from './protocol';

export type ConnectionState = 'connecting' | 'open' | 'closed';

export interface ConnectionHandlers {
  onWire: (message: WireMessage) => void;
  onServer: (message: ServerMessage) => void;
  onState: (state: ConnectionState) => void;
  onBytes?: (count: number) => void;
}

/** Reconnecting WebSocket client for the playport server. */
export class Connection {
  private socket: WebSocket | null = null;
  private retryTimer: number | null = null;
  private retryDelayMs = 500;
  private stopped = false;

  constructor(
    private readonly token: string,
    private readonly handlers: ConnectionHandlers,
  ) {}

  connect(): void {
    this.stopped = false;
    this.open();
  }

  private open(): void {
    this.handlers.onState('connecting');
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${scheme}://${location.host}/ws?token=${encodeURIComponent(this.token)}`;
    const socket = new WebSocket(url);
    socket.binaryType = 'arraybuffer';
    this.socket = socket;

    socket.addEventListener('open', () => {
      this.retryDelayMs = 500;
      this.handlers.onState('open');
    });
    socket.addEventListener('message', (event: MessageEvent<string | ArrayBuffer>) => {
      if (typeof event.data === 'string') {
        try {
          this.handlers.onServer(JSON.parse(event.data) as ServerMessage);
        } catch {
          // Ignore malformed control messages.
        }
        return;
      }
      this.handlers.onBytes?.(event.data.byteLength);
      const message = parseWireMessage(event.data);
      if (message) this.handlers.onWire(message);
    });
    socket.addEventListener('close', () => {
      if (this.socket === socket) this.socket = null;
      this.handlers.onState('closed');
      this.scheduleReconnect();
    });
    socket.addEventListener('error', () => {
      socket.close();
    });
  }

  private scheduleReconnect(): void {
    if (this.stopped || this.retryTimer !== null) return;
    this.retryTimer = window.setTimeout(() => {
      this.retryTimer = null;
      this.open();
    }, this.retryDelayMs);
    this.retryDelayMs = Math.min(this.retryDelayMs * 2, 5000);
  }

  send(message: ClientMessage): void {
    const socket = this.socket;
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify(message));
  }

  sendBinary(payload: Uint8Array): void {
    const socket = this.socket;
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    socket.send(payload);
  }

  close(): void {
    this.stopped = true;
    if (this.retryTimer !== null) {
      window.clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
    this.socket?.close();
    this.socket = null;
  }
}
