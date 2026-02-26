# WebSocket vs SSE: Comparison for drTranscribe (MedLog)

## Overview

This document compares WebSocket and Server-Sent Events (SSE) as real-time communication protocols for drTranscribe — a real-time medical transcription and clinical data extraction system.

**Recommendation: WebSocket** — it is the correct choice for this project's bidirectional, session-based, binary-data communication pattern.

---

## Quick Comparison

| Dimension | WebSocket | SSE (Server-Sent Events) |
|---|---|---|
| **Direction** | Full-duplex (client ↔ server) | Server → client only |
| **Audio upload** | Audio chunks sent over the same connection | Requires separate HTTP POST per 3s chunk |
| **Connections per session** | 1 persistent connection | 2 channels: SSE stream + HTTP POST endpoint |
| **Binary data** | Native binary frame support | Text-only (`text/event-stream`); base64 required |
| **Chrome Extension (MV3)** | Works in service workers (`background.js`) | `EventSource` API unavailable in service workers |
| **Protocol overhead** | 2-byte frame header after handshake | HTTP headers on every POST + SSE stream overhead |
| **Session lifecycle** | `start_session` → audio → `stop_session` on one channel | Must correlate separate POSTs with SSE stream via session IDs |
| **Reconnection** | Manual (app-level) | Built-in auto-reconnect |
| **Proxy/load balancer** | Needs WebSocket-aware proxy | Works through standard HTTP infrastructure |
| **Horizontal scaling** | Stateful; requires sticky sessions or pub/sub layer | Stateless POSTs scale easier; SSE stream is simpler |
| **Browser support** | All modern browsers | All modern browsers (not service workers) |

---

## Decisive Factors for drTranscribe

### 1. Bidirectional communication is non-negotiable

drTranscribe sends ~16 audio chunks per minute (one every 3 seconds) from client → server, and receives extraction updates from server → client. SSE only handles server → client. Adopting SSE would require a separate HTTP upload channel, doubling connection management complexity.

**Current architecture (WebSocket):**
```
Browser ──audio_chunk──▶ FastAPI
Browser ◀──extraction───  FastAPI
         (single connection)
```

**What SSE would require:**
```
Browser ──POST /audio──▶ FastAPI    (new HTTP endpoint)
Browser ◀──EventSource── FastAPI    (SSE stream)
         (two separate channels to manage and correlate)
```

### 2. Chrome Extension compatibility

The Chrome extension's `background.js` is a Manifest V3 service worker. The `EventSource` API is **not available** in service workers. Consuming SSE would require using `fetch()` with `ReadableStream`, which:

- Loses SSE's built-in auto-reconnection (its main advantage)
- Adds parsing complexity for the `text/event-stream` format
- Makes the SSE approach strictly worse than WebSocket in this context

### 3. Single connection simplifies session state

The current `WebSocketHandler` ties session lifecycle, audio streaming, and extraction push to one connection object. With SSE + HTTP POST, the system would need to:

- Generate and manage session tokens for correlation
- Match incoming POSTs to the correct SSE stream
- Handle race conditions if audio arrives before the SSE stream connects (or vice versa)
- Manage cleanup when either channel disconnects independently

---

## When SSE Would Be the Better Choice

SSE is preferable when the use case is **server → client push only** — dashboards, notifications, live feeds, or read-only viewers. If drTranscribe only needed to push extraction results to a passive viewer (no audio upload), SSE would offer:

- Simpler infrastructure (no WebSocket-aware proxies needed)
- Built-in reconnection with `Last-Event-ID`
- Easier horizontal scaling behind standard load balancers

---

## References

- [MDN: WebSocket API](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)
- [MDN: Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
- [Chrome Extensions MV3: Service Worker APIs](https://developer.chrome.com/docs/extensions/develop/concepts/service-workers)
