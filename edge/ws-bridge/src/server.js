#!/usr/bin/env node
/**
 * WebSocket bridge between the Raspberry Pi UDP video stream and browser clients.
 *
 * Architecture:
 *   Raspberry Pi (UDP :9999) ──► [this process] ──WebSocket──► Browser
 *
 * Each complete video frame received over UDP is forwarded to every connected
 * WebSocket client as a binary message with a 1-byte type prefix:
 *   0x01  H.264 NAL bitstream bytes
 *   0x02  Raw JPEG bytes (extracted from pickle if necessary)
 *
 * Usage:
 *   node src/server.js [options]
 *
 * Environment variables (all optional, values shown are defaults):
 *   PI_HOST=127.0.0.1    Raspberry Pi IP or hostname
 *   PI_PORT=9999         UDP port of the Pi streamer
 *   WS_PORT=8765         WebSocket server port
 *   LOG_LEVEL=info       'debug' | 'info' | 'warn' | 'error'
 */

'use strict';

const dgram = require('dgram');
const http = require('http');
const { WebSocketServer } = require('ws');
const {
  MSG_REGISTER_CLIENT,
  MSG_KEEPALIVE,
  MSG_DISCONNECT,
  MSG_REGISTERED,
  SERVER_PORT,
  KEEPALIVE_INTERVAL_MS,
  parseFrameStart,
  parseChunk,
  FrameAssembler,
} = require('./udpProtocol');
const { prepareWsPayload } = require('./frameExtractor');

// ─── Config ──────────────────────────────────────────────────────────────────

const PI_HOST = process.env.PI_HOST || '127.0.0.1';
const PI_PORT = parseInt(process.env.PI_PORT || String(SERVER_PORT), 10);
const WS_PORT = parseInt(process.env.WS_PORT || '8765', 10);
const LOG_LEVEL = process.env.LOG_LEVEL || 'info';

const LEVELS = { debug: 0, info: 1, warn: 2, error: 3 };
const currentLevel = LEVELS[LOG_LEVEL] ?? LEVELS.info;

function log(level, ...args) {
  if ((LEVELS[level] ?? 0) >= currentLevel) {
    console[level === 'debug' ? 'log' : level](`[ws-bridge] [${level}]`, ...args);
  }
}

// ─── Bridge server factory ────────────────────────────────────────────────────

/**
 * Create a new bridge server instance.
 *
 * @param {{
 *   piHost?: string,
 *   piPort?: number,
 *   wsPort?: number,
 *   onFrame?: (type: number, payload: Buffer, clientCount: number) => void,
 * }} [options]
 * @returns {{
 *   start: () => Promise<void>,
 *   stop: () => Promise<void>,
 *   getClientCount: () => number,
 *   getFrameCount: () => number,
 * }}
 */
function createBridgeServer(options = {}) {
  const piHost = options.piHost ?? PI_HOST;
  const piPort = options.piPort ?? PI_PORT;
  const wsPort = options.wsPort ?? WS_PORT;

  let udpSocket = null;
  let wss = null;
  let httpServer = null;
  let keepaliveTimer = null;
  let frameCount = 0;
  let clientCount = 0;

  const assembler = new FrameAssembler();

  // ─── UDP → WS forwarding ──────────────────────────────────────────────────

  function handleUdpMessage(msg) {
    if (msg.equals(MSG_REGISTERED)) {
      log('info', `Registered with Pi UDP server at ${piHost}:${piPort}`);
      return;
    }

    const frameStart = parseFrameStart(msg);
    if (frameStart) {
      assembler.handleFrameStart(frameStart);
      assembler.pruneStale();
      return;
    }

    const chunk = parseChunk(msg);
    if (chunk) {
      const completeFrame = assembler.handleChunk(chunk);
      if (completeFrame) {
        frameCount++;
        const wsMsg = prepareWsPayload(completeFrame);
        if (!wsMsg) {
          log('debug', 'Frame skipped — unknown format');
          return;
        }
        if (options.onFrame) {
          options.onFrame(wsMsg.type, wsMsg.payload, clientCount);
        }
        if (wss) {
          for (const client of wss.clients) {
            if (client.readyState === 1 /* OPEN */) {
              client.send(wsMsg.payload, { binary: true });
            }
          }
        }
      }
    }
  }

  // ─── Lifecycle ────────────────────────────────────────────────────────────

  function start() {
    return new Promise((resolve, reject) => {
      // HTTP server for health endpoint
      httpServer = http.createServer((req, res) => {
        if (req.url === '/health') {
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({
            status: 'ok',
            clients: clientCount,
            frames: frameCount,
            pi: `${piHost}:${piPort}`,
          }));
        } else {
          res.writeHead(404);
          res.end('Not found');
        }
      });

      // WebSocket server
      wss = new WebSocketServer({ server: httpServer });

      wss.on('connection', (ws, req) => {
        clientCount++;
        const remote = req.socket.remoteAddress;
        log('info', `Browser connected from ${remote} (total: ${clientCount})`);

        ws.on('close', () => {
          clientCount--;
          log('info', `Browser disconnected (total: ${clientCount})`);
        });

        ws.on('error', (err) => {
          log('warn', 'WebSocket client error:', err.message);
        });

        ws.on('message', (data) => {
          // Browser → bridge control messages (text JSON)
          try {
            const msg = JSON.parse(data.toString());
            if (msg.type === 'ping') {
              ws.send(JSON.stringify({ type: 'pong' }));
            }
          } catch {
            // Ignore non-JSON messages
          }
        });
      });

      // UDP socket
      udpSocket = dgram.createSocket('udp4');

      udpSocket.on('error', (err) => {
        log('error', 'UDP socket error:', err.message);
        reject(err);
      });

      udpSocket.on('message', handleUdpMessage);

      udpSocket.bind(() => {
        log('info', `UDP socket bound, registering with Pi at ${piHost}:${piPort}`);
        udpSocket.send(MSG_REGISTER_CLIENT, piPort, piHost);

        keepaliveTimer = setInterval(() => {
          udpSocket.send(MSG_KEEPALIVE, piPort, piHost);
          log('debug', 'Sent KEEPALIVE to Pi');
        }, KEEPALIVE_INTERVAL_MS);
      });

      httpServer.listen(wsPort, () => {
        log('info', `WebSocket bridge listening on ws://0.0.0.0:${wsPort}`);
        log('info', `Health check: http://localhost:${wsPort}/health`);
        resolve();
      });

      httpServer.on('error', reject);
    });
  }

  function stop() {
    return new Promise((resolve) => {
      if (keepaliveTimer) {
        clearInterval(keepaliveTimer);
        keepaliveTimer = null;
      }

      if (udpSocket) {
        try { udpSocket.send(MSG_DISCONNECT, piPort, piHost); } catch { /* ignore */ }
        udpSocket.close();
        udpSocket = null;
      }

      if (wss) {
        wss.close(() => {
          if (httpServer) {
            httpServer.close(() => resolve());
          } else {
            resolve();
          }
        });
      } else if (httpServer) {
        httpServer.close(() => resolve());
      } else {
        resolve();
      }
    });
  }

  return {
    start,
    stop,
    getClientCount: () => clientCount,
    getFrameCount: () => frameCount,
  };
}

// ─── CLI entry point ─────────────────────────────────────────────────────────

if (require.main === module) {
  const server = createBridgeServer();
  server.start().catch((err) => {
    log('error', 'Failed to start bridge server:', err.message);
    process.exit(1);
  });

  process.on('SIGINT', async () => {
    log('info', 'Shutting down…');
    await server.stop();
    process.exit(0);
  });

  process.on('SIGTERM', async () => {
    log('info', 'Shutting down…');
    await server.stop();
    process.exit(0);
  });
}

module.exports = { createBridgeServer };
