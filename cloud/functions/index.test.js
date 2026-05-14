const net = require('net');
const EventEmitter = require('events');

jest.mock('@google-cloud/functions-framework', () => ({
  http: jest.fn()
}));

jest.mock('cors', () => {
  return () => (req, res, callback) => callback();
});

let mockAuthenticateRequest;
jest.mock('./auth', () => ({
  authenticateRequest: jest.fn((...args) => mockAuthenticateRequest(...args))
}));

const functions = require('@google-cloud/functions-framework');
const { authenticateRequest } = require('./auth');

let controlRobotHandler;

function createMockRequest(options = {}) {
  return {
    method: options.method || 'POST',
    headers: options.headers || { 'x-api-key': 'test-api-key' },
    body: options.body || {},
    connection: { remoteAddress: '127.0.0.1' }
  };
}

function createMockResponse() {
  const res = {
    statusCode: null,
    responseData: null,
    status: jest.fn(function(code) {
      this.statusCode = code;
      return this;
    }),
    json: jest.fn(function(data) {
      this.responseData = data;
      return this;
    })
  };
  return res;
}

class MockSocket extends EventEmitter {
  constructor() {
    super();
    this.destroyed = false;
    this.timeoutMs = null;
    this.connectHost = null;
    this.connectPort = null;
  }

  setTimeout(ms) {
    this.timeoutMs = ms;
  }

  connect(port, host, callback) {
    this.connectPort = port;
    this.connectHost = host;
    setImmediate(callback);
  }

  write(data) {
    this.writtenData = data;
  }

  destroy() {
    this.destroyed = true;
  }
}

let mockSocketInstance;
jest.mock('net', () => ({
  Socket: jest.fn(() => mockSocketInstance)
}));

describe('controlRobot Cloud Function', () => {
  beforeAll(() => {
    require('./index');
    controlRobotHandler = functions.http.mock.calls[0][1];
  });

  beforeEach(() => {
    jest.clearAllMocks();
    mockAuthenticateRequest = jest.fn().mockReturnValue({ clientId: 'test-client', authenticated: true });
    mockSocketInstance = new MockSocket();
  });

  describe('Valid command dispatching', () => {
    test('should dispatch forward command successfully', async () => {
      const req = createMockRequest({
        body: { command: 'forward', params: { speed: 500 } }
      });
      const res = createMockResponse();

      const handlerPromise = new Promise((resolve) => {
        const originalJson = res.json;
        res.json = function(data) {
          originalJson.call(this, data);
          resolve();
          return this;
        };

        controlRobotHandler(req, res);

        setImmediate(() => {
          mockSocketInstance.emit('data', Buffer.from('{"success":true,"action":"move"}\n'));
        });
      });

      await handlerPromise;

      expect(res.statusCode).toBe(200);
      expect(res.responseData.success).toBe(true);
      expect(res.responseData.command).toBe('forward');
    });

    test('should dispatch stop command successfully', async () => {
      const req = createMockRequest({
        body: { command: 'stop' }
      });
      const res = createMockResponse();

      const handlerPromise = new Promise((resolve) => {
        const originalJson = res.json;
        res.json = function(data) {
          originalJson.call(this, data);
          resolve();
          return this;
        };

        controlRobotHandler(req, res);

        setImmediate(() => {
          mockSocketInstance.emit('data', Buffer.from('{"success":true,"action":"stop"}\n'));
        });
      });

      await handlerPromise;

      expect(res.statusCode).toBe(200);
      expect(res.responseData.success).toBe(true);
      expect(res.responseData.command).toBe('stop');
    });

    test('should dispatch battery command successfully', async () => {
      const req = createMockRequest({
        body: { command: 'battery' }
      });
      const res = createMockResponse();

      const handlerPromise = new Promise((resolve) => {
        const originalJson = res.json;
        res.json = function(data) {
          originalJson.call(this, data);
          resolve();
          return this;
        };

        controlRobotHandler(req, res);

        setImmediate(() => {
          mockSocketInstance.emit('data', Buffer.from('{"success":true,"voltage":7200}\n'));
        });
      });

      await handlerPromise;

      expect(res.statusCode).toBe(200);
      expect(res.responseData.success).toBe(true);
      expect(res.responseData.command).toBe('battery');
    });

    test('should dispatch speak command with text parameter', async () => {
      const req = createMockRequest({
        body: { command: 'speak', params: { text: 'Hello robot' } }
      });
      const res = createMockResponse();

      const handlerPromise = new Promise((resolve) => {
        const originalJson = res.json;
        res.json = function(data) {
          originalJson.call(this, data);
          resolve();
          return this;
        };

        controlRobotHandler(req, res);

        setImmediate(() => {
          mockSocketInstance.emit('data', Buffer.from('{"success":true,"text":"Hello robot"}\n'));
        });
      });

      await handlerPromise;

      expect(res.statusCode).toBe(200);
      expect(res.responseData.success).toBe(true);
      expect(res.responseData.command).toBe('speak');
    });
  });

  describe('Authentication errors (401)', () => {
    test('should return 401 when API key is missing', async () => {
      mockAuthenticateRequest = jest.fn().mockImplementation(() => {
        throw new Error('API key is required');
      });

      const req = createMockRequest({
        headers: {}
      });
      const res = createMockResponse();

      await new Promise((resolve) => {
        const originalJson = res.json;
        res.json = function(data) {
          originalJson.call(this, data);
          resolve();
          return this;
        };
        controlRobotHandler(req, res);
      });

      expect(res.statusCode).toBe(401);
      expect(res.responseData.error).toBe('API key is required');
    });

    test('should return 401 when API key is invalid', async () => {
      mockAuthenticateRequest = jest.fn().mockImplementation(() => {
        throw new Error('Invalid API key');
      });

      const req = createMockRequest({
        headers: { 'x-api-key': 'wrong-key' }
      });
      const res = createMockResponse();

      await new Promise((resolve) => {
        const originalJson = res.json;
        res.json = function(data) {
          originalJson.call(this, data);
          resolve();
          return this;
        };
        controlRobotHandler(req, res);
      });

      expect(res.statusCode).toBe(401);
      expect(res.responseData.error).toBe('Invalid API key');
    });
  });

  describe('Unknown command errors (400)', () => {
    test('should return 400 for unknown command', async () => {
      const req = createMockRequest({
        body: { command: 'dance' }
      });
      const res = createMockResponse();

      await new Promise((resolve) => {
        const originalJson = res.json;
        res.json = function(data) {
          originalJson.call(this, data);
          resolve();
          return this;
        };
        controlRobotHandler(req, res);
      });

      expect(res.statusCode).toBe(400);
      expect(res.responseData.error).toContain('Invalid command');
    });

    test('should return 400 when command is missing', async () => {
      const req = createMockRequest({
        body: {}
      });
      const res = createMockResponse();

      await new Promise((resolve) => {
        const originalJson = res.json;
        res.json = function(data) {
          originalJson.call(this, data);
          resolve();
          return this;
        };
        controlRobotHandler(req, res);
      });

      expect(res.statusCode).toBe(400);
      expect(res.responseData.error).toBe('Command is required');
    });

    test('should return 400 for invalid speed parameter', async () => {
      const req = createMockRequest({
        body: { command: 'forward', params: { speed: 3000 } }
      });
      const res = createMockResponse();

      await new Promise((resolve) => {
        const originalJson = res.json;
        res.json = function(data) {
          originalJson.call(this, data);
          resolve();
          return this;
        };
        controlRobotHandler(req, res);
      });

      expect(res.statusCode).toBe(400);
      expect(res.responseData.error).toContain('Speed must be between 0 and 2000');
    });

    test('should return 400 for duration exceeding limit', async () => {
      const req = createMockRequest({
        body: { command: 'forward', params: { duration: 15 } }
      });
      const res = createMockResponse();

      await new Promise((resolve) => {
        const originalJson = res.json;
        res.json = function(data) {
          originalJson.call(this, data);
          resolve();
          return this;
        };
        controlRobotHandler(req, res);
      });

      expect(res.statusCode).toBe(400);
      expect(res.responseData.error).toContain('Duration cannot exceed 10 seconds');
    });

    test('should return 400 for speak command without text', async () => {
      const req = createMockRequest({
        body: { command: 'speak', params: {} }
      });
      const res = createMockResponse();

      await new Promise((resolve) => {
        const originalJson = res.json;
        res.json = function(data) {
          originalJson.call(this, data);
          resolve();
          return this;
        };
        controlRobotHandler(req, res);
      });

      expect(res.statusCode).toBe(400);
      expect(res.responseData.error).toContain('Text parameter is required');
    });
  });

  describe('Robot connection failures (502)', () => {
    test('should return 502 when robot connection times out', async () => {
      const req = createMockRequest({
        body: { command: 'forward' }
      });
      const res = createMockResponse();

      const handlerPromise = new Promise((resolve) => {
        const originalJson = res.json;
        res.json = function(data) {
          originalJson.call(this, data);
          resolve();
          return this;
        };

        controlRobotHandler(req, res);

        setImmediate(() => {
          mockSocketInstance.emit('timeout');
        });
      });

      await handlerPromise;

      expect(res.statusCode).toBe(502);
      expect(res.responseData.success).toBe(false);
      expect(res.responseData.error).toContain('timeout');
    });

    test('should return 502 when robot connection fails', async () => {
      const req = createMockRequest({
        body: { command: 'forward' }
      });
      const res = createMockResponse();

      const handlerPromise = new Promise((resolve) => {
        const originalJson = res.json;
        res.json = function(data) {
          originalJson.call(this, data);
          resolve();
          return this;
        };

        controlRobotHandler(req, res);

        setImmediate(() => {
          mockSocketInstance.emit('error', new Error('ECONNREFUSED'));
        });
      });

      await handlerPromise;

      expect(res.statusCode).toBe(502);
      expect(res.responseData.success).toBe(false);
      expect(res.responseData.error).toContain('Connection error');
    });

    test('should return 502 when robot is unreachable', async () => {
      const req = createMockRequest({
        body: { command: 'stop' }
      });
      const res = createMockResponse();

      const handlerPromise = new Promise((resolve) => {
        const originalJson = res.json;
        res.json = function(data) {
          originalJson.call(this, data);
          resolve();
          return this;
        };

        controlRobotHandler(req, res);

        setImmediate(() => {
          mockSocketInstance.emit('error', new Error('EHOSTUNREACH'));
        });
      });

      await handlerPromise;

      expect(res.statusCode).toBe(502);
      expect(res.responseData.success).toBe(false);
      expect(res.responseData.error).toContain('EHOSTUNREACH');
    });
  });

  describe('HTTP method validation', () => {
    test('should return 405 for non-POST requests', async () => {
      const req = createMockRequest({
        method: 'GET'
      });
      const res = createMockResponse();

      await new Promise((resolve) => {
        const originalJson = res.json;
        res.json = function(data) {
          originalJson.call(this, data);
          resolve();
          return this;
        };
        controlRobotHandler(req, res);
      });

      expect(res.statusCode).toBe(405);
      expect(res.responseData.error).toBe('Method not allowed');
    });
  });
});
