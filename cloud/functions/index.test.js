const { EventEmitter } = require('events');

let mockSocket;
let mockAuthenticateRequest;

jest.mock('net', () => ({
  Socket: jest.fn(() => mockSocket)
}));

jest.mock('@google-cloud/functions-framework', () => {
  const handlers = {};
  return {
    http: jest.fn((name, handler) => {
      handlers[name] = handler;
    }),
    _handlers: handlers
  };
});

jest.mock('cors', () => {
  return jest.fn(() => (req, res, next) => next());
});

jest.mock('./auth', () => ({
  authenticateRequest: jest.fn(() => mockAuthenticateRequest())
}));

function createMockSocket() {
  const socket = new EventEmitter();
  socket.connect = jest.fn(function(port, host, callback) {
    process.nextTick(callback);
    return this;
  });
  socket.write = jest.fn();
  socket.destroy = jest.fn();
  socket.setTimeout = jest.fn();
  return socket;
}

describe('controlRobot Cloud Function', () => {
  let handler;
  let mockReq;
  let mockRes;
  const net = require('net');
  const { authenticateRequest } = require('./auth');
  const functionsFramework = require('@google-cloud/functions-framework');

  beforeAll(() => {
    require('./index');
    handler = functionsFramework._handlers.controlRobot;
  });

  beforeEach(() => {
    jest.clearAllMocks();
    
    mockSocket = createMockSocket();
    
    mockAuthenticateRequest = jest.fn().mockReturnValue({ clientId: 'test', authenticated: true });

    mockRes = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn().mockReturnThis()
    };
  });

  describe('Authentication', () => {
    it('should return 401 when API key is missing', async () => {
      mockReq = {
        method: 'POST',
        headers: {},
        body: { command: 'forward' }
      };

      mockAuthenticateRequest = jest.fn(() => {
        throw new Error('API key is required');
      });

      await handler(mockReq, mockRes);

      expect(mockRes.status).toHaveBeenCalledWith(401);
      expect(mockRes.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'API key is required'
        })
      );
    });

    it('should return 401 when API key is invalid', async () => {
      mockReq = {
        method: 'POST',
        headers: { 'x-api-key': 'wrong-key' },
        body: { command: 'forward' }
      };

      mockAuthenticateRequest = jest.fn(() => {
        throw new Error('Invalid API key');
      });

      await handler(mockReq, mockRes);

      expect(mockRes.status).toHaveBeenCalledWith(401);
      expect(mockRes.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'Invalid API key'
        })
      );
    });
  });

  describe('Command Validation', () => {
    it('should return 400 when command is missing', async () => {
      mockReq = {
        method: 'POST',
        headers: { 'x-api-key': 'valid-key' },
        body: {}
      };

      await handler(mockReq, mockRes);

      expect(mockRes.status).toHaveBeenCalledWith(400);
      expect(mockRes.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'Command is required'
        })
      );
    });

    it('should return 400 for unknown command', async () => {
      mockReq = {
        method: 'POST',
        headers: { 'x-api-key': 'valid-key' },
        body: { command: 'unknown_command' }
      };

      await handler(mockReq, mockRes);

      expect(mockRes.status).toHaveBeenCalledWith(400);
      expect(mockRes.json).toHaveBeenCalledWith(
        expect.objectContaining({
          success: false,
          error: 'Invalid command: unknown_command'
        })
      );
    });

    it('should return 400 when speed exceeds maximum', async () => {
      mockReq = {
        method: 'POST',
        headers: { 'x-api-key': 'valid-key' },
        body: { command: 'forward', params: { speed: 3000 } }
      };

      await handler(mockReq, mockRes);

      expect(mockRes.status).toHaveBeenCalledWith(400);
      expect(mockRes.json).toHaveBeenCalledWith(
        expect.objectContaining({
          success: false,
          error: 'Speed must be between 0 and 2000'
        })
      );
    });

    it('should return 400 when duration exceeds maximum', async () => {
      mockReq = {
        method: 'POST',
        headers: { 'x-api-key': 'valid-key' },
        body: { command: 'forward', params: { duration: 15 } }
      };

      await handler(mockReq, mockRes);

      expect(mockRes.status).toHaveBeenCalledWith(400);
      expect(mockRes.json).toHaveBeenCalledWith(
        expect.objectContaining({
          success: false,
          error: 'Duration cannot exceed 10 seconds for safety'
        })
      );
    });

    it('should return 405 for non-POST methods', async () => {
      mockReq = {
        method: 'GET',
        headers: { 'x-api-key': 'valid-key' },
        body: {}
      };

      await handler(mockReq, mockRes);

      expect(mockRes.status).toHaveBeenCalledWith(405);
      expect(mockRes.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'Method not allowed'
        })
      );
    });
  });

  describe('Valid Command Dispatching', () => {
    it('should dispatch forward command successfully', async () => {
      mockReq = {
        method: 'POST',
        headers: { 'x-api-key': 'valid-key' },
        body: { command: 'forward', params: { speed: 500 } }
      };

      const robotResponse = { success: true, action: 'move', direction: 'forward' };

      const handlerPromise = handler(mockReq, mockRes);

      await new Promise(resolve => process.nextTick(resolve));
      await new Promise(resolve => process.nextTick(resolve));
      
      mockSocket.emit('data', Buffer.from(JSON.stringify(robotResponse) + '\n'));

      await handlerPromise;

      expect(net.Socket).toHaveBeenCalled();
      expect(mockSocket.connect).toHaveBeenCalled();
      expect(mockSocket.write).toHaveBeenCalledWith(
        expect.stringContaining('"action":"move"')
      );
      expect(mockRes.status).toHaveBeenCalledWith(200);
    });

    it('should dispatch stop command successfully', async () => {
      mockReq = {
        method: 'POST',
        headers: { 'x-api-key': 'valid-key' },
        body: { command: 'stop' }
      };

      const robotResponse = { success: true, action: 'stop' };

      const handlerPromise = handler(mockReq, mockRes);

      await new Promise(resolve => process.nextTick(resolve));
      await new Promise(resolve => process.nextTick(resolve));
      
      mockSocket.emit('data', Buffer.from(JSON.stringify(robotResponse) + '\n'));

      await handlerPromise;

      expect(mockRes.status).toHaveBeenCalledWith(200);
      expect(mockRes.json).toHaveBeenCalledWith(
        expect.objectContaining({
          success: true,
          command: 'stop',
          result: robotResponse
        })
      );
    });

    it('should dispatch turret_left command with correct parameters', async () => {
      mockReq = {
        method: 'POST',
        headers: { 'x-api-key': 'valid-key' },
        body: { command: 'turret_left', params: { speed: 200, duration: 1 } }
      };

      const robotResponse = { success: true, action: 'turret', direction: 'left' };

      const handlerPromise = handler(mockReq, mockRes);

      await new Promise(resolve => process.nextTick(resolve));
      await new Promise(resolve => process.nextTick(resolve));
      
      mockSocket.emit('data', Buffer.from(JSON.stringify(robotResponse) + '\n'));

      await handlerPromise;

      expect(mockSocket.write).toHaveBeenCalledWith(
        expect.stringContaining('"action":"turret"')
      );
      expect(mockSocket.write).toHaveBeenCalledWith(
        expect.stringContaining('"direction":"left"')
      );
      expect(mockRes.status).toHaveBeenCalledWith(200);
    });

    it('should dispatch get_status command successfully', async () => {
      mockReq = {
        method: 'POST',
        headers: { 'x-api-key': 'valid-key' },
        body: { command: 'get_status' }
      };

      const robotResponse = { success: true, action: 'status', battery: 80 };

      const handlerPromise = handler(mockReq, mockRes);

      await new Promise(resolve => process.nextTick(resolve));
      await new Promise(resolve => process.nextTick(resolve));
      
      mockSocket.emit('data', Buffer.from(JSON.stringify(robotResponse) + '\n'));

      await handlerPromise;

      expect(mockSocket.write).toHaveBeenCalledWith(
        expect.stringContaining('"action":"status"')
      );
      expect(mockRes.status).toHaveBeenCalledWith(200);
    });

    it('should dispatch speak command with text parameter', async () => {
      mockReq = {
        method: 'POST',
        headers: { 'x-api-key': 'valid-key' },
        body: { command: 'speak', params: { text: 'Hello world' } }
      };

      const robotResponse = { success: true, action: 'speak', text: 'Hello world' };

      const handlerPromise = handler(mockReq, mockRes);

      await new Promise(resolve => process.nextTick(resolve));
      await new Promise(resolve => process.nextTick(resolve));
      
      mockSocket.emit('data', Buffer.from(JSON.stringify(robotResponse) + '\n'));

      await handlerPromise;

      expect(mockSocket.write).toHaveBeenCalledWith(
        expect.stringContaining('"action":"speak"')
      );
      expect(mockSocket.write).toHaveBeenCalledWith(
        expect.stringContaining('"text":"Hello world"')
      );
      expect(mockRes.status).toHaveBeenCalledWith(200);
    });

    it('should dispatch joystick_control command with all parameters', async () => {
      mockReq = {
        method: 'POST',
        headers: { 'x-api-key': 'valid-key' },
        body: {
          command: 'joystick_control',
          params: { l_left: 100, l_forward: 200, r_left: -50, r_forward: 150 }
        }
      };

      const robotResponse = { success: true, action: 'joystick' };

      const handlerPromise = handler(mockReq, mockRes);

      await new Promise(resolve => process.nextTick(resolve));
      await new Promise(resolve => process.nextTick(resolve));
      
      mockSocket.emit('data', Buffer.from(JSON.stringify(robotResponse) + '\n'));

      await handlerPromise;

      expect(mockSocket.write).toHaveBeenCalledWith(
        expect.stringContaining('"action":"joystick"')
      );
      expect(mockRes.status).toHaveBeenCalledWith(200);
    });
  });

  describe('Robot Connection Failures', () => {
    it('should return 502 when robot connection times out', async () => {
      mockReq = {
        method: 'POST',
        headers: { 'x-api-key': 'valid-key' },
        body: { command: 'forward' }
      };

      const handlerPromise = handler(mockReq, mockRes);

      await new Promise(resolve => process.nextTick(resolve));
      await new Promise(resolve => process.nextTick(resolve));
      
      mockSocket.emit('timeout');

      await handlerPromise;

      expect(mockRes.status).toHaveBeenCalledWith(502);
      expect(mockRes.json).toHaveBeenCalledWith(
        expect.objectContaining({
          success: false,
          error: 'Connection timeout'
        })
      );
    });

    it('should return 502 when robot connection fails', async () => {
      mockReq = {
        method: 'POST',
        headers: { 'x-api-key': 'valid-key' },
        body: { command: 'forward' }
      };

      const handlerPromise = handler(mockReq, mockRes);

      await new Promise(resolve => process.nextTick(resolve));
      await new Promise(resolve => process.nextTick(resolve));
      
      mockSocket.emit('error', new Error('ECONNREFUSED'));

      await handlerPromise;

      expect(mockRes.status).toHaveBeenCalledWith(502);
      expect(mockRes.json).toHaveBeenCalledWith(
        expect.objectContaining({
          success: false,
          error: 'Connection error: ECONNREFUSED'
        })
      );
    });

    it('should return 502 when robot host is unreachable', async () => {
      mockReq = {
        method: 'POST',
        headers: { 'x-api-key': 'valid-key' },
        body: { command: 'stop' }
      };

      const handlerPromise = handler(mockReq, mockRes);

      await new Promise(resolve => process.nextTick(resolve));
      await new Promise(resolve => process.nextTick(resolve));
      
      mockSocket.emit('error', new Error('EHOSTUNREACH'));

      await handlerPromise;

      expect(mockRes.status).toHaveBeenCalledWith(502);
      expect(mockRes.json).toHaveBeenCalledWith(
        expect.objectContaining({
          success: false,
          error: 'Connection error: EHOSTUNREACH'
        })
      );
    });
  });

  describe('Helper Functions', () => {
    const { validateCommand, ValidationError } = require('./index');

    describe('validateCommand', () => {
      it('should accept valid commands', () => {
        expect(() => validateCommand('forward', {})).not.toThrow();
        expect(() => validateCommand('backward', {})).not.toThrow();
        expect(() => validateCommand('left', {})).not.toThrow();
        expect(() => validateCommand('right', {})).not.toThrow();
        expect(() => validateCommand('stop', {})).not.toThrow();
        expect(() => validateCommand('turret_left', {})).not.toThrow();
        expect(() => validateCommand('turret_right', {})).not.toThrow();
        expect(() => validateCommand('stop_turret', {})).not.toThrow();
        expect(() => validateCommand('get_status', {})).not.toThrow();
        expect(() => validateCommand('get_help', {})).not.toThrow();
        expect(() => validateCommand('battery', {})).not.toThrow();
        expect(() => validateCommand('beep', {})).not.toThrow();
      });

      it('should throw ValidationError for invalid commands', () => {
        expect(() => validateCommand('invalid', {})).toThrow(ValidationError);
        expect(() => validateCommand('fly', {})).toThrow(ValidationError);
        expect(() => validateCommand('', {})).toThrow(ValidationError);
      });

      it('should throw ValidationError for speed out of range', () => {
        expect(() => validateCommand('forward', { speed: -1 })).toThrow(ValidationError);
        expect(() => validateCommand('forward', { speed: 2001 })).toThrow(ValidationError);
      });

      it('should accept valid speed values', () => {
        expect(() => validateCommand('forward', { speed: 0 })).not.toThrow();
        expect(() => validateCommand('forward', { speed: 1000 })).not.toThrow();
        expect(() => validateCommand('forward', { speed: 2000 })).not.toThrow();
      });

      it('should throw ValidationError for duration exceeding limit', () => {
        expect(() => validateCommand('forward', { duration: 11 })).toThrow(ValidationError);
        expect(() => validateCommand('forward', { duration: 100 })).toThrow(ValidationError);
      });

      it('should accept valid duration values', () => {
        expect(() => validateCommand('forward', { duration: 0 })).not.toThrow();
        expect(() => validateCommand('forward', { duration: 5 })).not.toThrow();
        expect(() => validateCommand('forward', { duration: 10 })).not.toThrow();
      });

      it('should validate speak command text parameter', () => {
        expect(() => validateCommand('speak', {})).toThrow(ValidationError);
        expect(() => validateCommand('speak', { text: 123 })).toThrow(ValidationError);
        expect(() => validateCommand('speak', { text: 'a'.repeat(501) })).toThrow(ValidationError);
        expect(() => validateCommand('speak', { text: 'Hello' })).not.toThrow();
      });
    });
  });
});
