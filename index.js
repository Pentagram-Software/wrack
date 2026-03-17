const functions = require('@google-cloud/functions-framework');
const cors = require('cors');
const net = require('net');
const { authenticateRequest } = require('./auth');

const corsHandler = cors({
  origin: true,
  methods: ['POST', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization', 'X-API-Key']
});

const ROBOT_HOST = process.env.ROBOT_HOST || 'YOUR_ROBOT_IP';
const ROBOT_PORT = process.env.ROBOT_PORT || 27700;
const CONNECTION_TIMEOUT = 5000;

function sendCommandToRobot(action, direction = null, speed = null, duration = null, params = {}) {
  return new Promise((resolve, reject) => {
    const client = new net.Socket();
    
    client.setTimeout(CONNECTION_TIMEOUT);
    
    // Build command in the format expected by the existing EV3 RemoteController
    let command = { action };
    
    if (direction) command.direction = direction;
    if (speed !== null) command.speed = speed;
    if (duration !== null) command.duration = duration;
    
    // Add any additional parameters
    Object.assign(command, params);
    
    const message = JSON.stringify(command);

    client.connect(ROBOT_PORT, ROBOT_HOST, () => {
      console.log(`Connected to robot at ${ROBOT_HOST}:${ROBOT_PORT}`);
      console.log(`Sending to robot: ${JSON.stringify(command)}`);
      
      // Send command immediately with newline (required by EV3 protocol)
      const fullMessage = message + '\n';
      console.log(`Sending full message: ${JSON.stringify(fullMessage)}`);
      client.write(fullMessage);
      
      // Wait for response - accumulate data chunks
      let buffer = '';
      client.on('data', (data) => {
        const chunk = data.toString();
        buffer += chunk;

        console.log('=== DATA EVENT ===');
        console.log(`Raw chunk bytes: ${data.length}`);
        console.log(`Raw chunk hex: ${data.toString('hex')}`);
        console.log(`Chunk as string: ${chunk}`);
        console.log(`Buffer length: ${buffer.length}`);
        console.log(`Full buffer: ${buffer}`);
        console.log('==================');

        // Split by newlines to process complete messages
        const messages = buffer.split('\n');
        console.log(`Split into ${messages.length} parts`);

        // Keep the last incomplete message in the buffer
        buffer = messages.pop() || '';
        console.log(`Remaining in buffer: "${buffer}"`);

        // Process each complete message
        for (let i = 0; i < messages.length; i++) {
          const message = messages[i];
          console.log(`\n--- Message ${i + 1} ---`);
          console.log(`Length: ${message.length}`);
          console.log(`Content: ${message}`);
          console.log(`Trimmed: ${message.trim()}`);

          if (!message.trim()) {
            console.log('Empty message, skipping');
            continue;
          }

          // Skip welcome messages and non-JSON informational messages
          if (message.includes('Welcome') ||
              message.includes('Send JSON') ||
              message.startsWith('Supported:') ||
              message.startsWith('Command received:')) {
            console.log('SKIPPING: Informational message detected');
            continue;
          }

          // Try to parse as JSON - only accept JSON responses
          try {
            const parsed = JSON.parse(message);
            console.log(`SUCCESS: Parsed JSON: ${JSON.stringify(parsed)}`);
            console.log(`Resolving with parsed data and destroying connection`);
            client.destroy();
            resolve(parsed);
            return;
          } catch (error) {
            console.log(`PARSE ERROR: ${error.message}`);
            console.log(`Not JSON, skipping: ${message}`);
            // Skip non-JSON messages, continue waiting for JSON response
            continue;
          }
        }
        console.log('End of data event handler, waiting for more data...');
      });
    });

    client.on('timeout', () => {
      client.destroy();
      reject(new Error('Connection timeout'));
    });

    client.on('error', (error) => {
      reject(new Error(`Connection error: ${error.message}`));
    });

    client.on('close', () => {
      console.log('Connection to robot closed');
    });
  });
}

function validateCommand(command, params) {
  const validCommands = [
    'forward',
    'backward',
    'left',
    'right',
    'turret_left',
    'turret_right',
    'stop',
    'stop_turret',
    'get_status',
    'joystick_control',
    'get_help',
    'speak',
    'battery',
    'beep'
  ];

  if (!validCommands.includes(command)) {
    throw new Error(`Invalid command: ${command}`);
  }

  if (params.speed && (params.speed < 0 || params.speed > 2000)) {
    throw new Error('Speed must be between 0 and 2000');
  }

  if (params.duration && params.duration > 10) {
    throw new Error('Duration cannot exceed 10 seconds for safety');
  }

  if (command === 'speak') {
    if (!params.text || typeof params.text !== 'string') {
      throw new Error('Text parameter is required for speak command');
    }
    if (params.text.length > 500) {
      throw new Error('Text length cannot exceed 500 characters');
    }
  }
}

functions.http('controlRobot', (req, res) => {
  corsHandler(req, res, async () => {
    try {
      if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
      }

      // Authenticate the request
      try {
        authenticateRequest(req);
      } catch (authError) {
        return res.status(401).json({ error: authError.message });
      }

      const { command, params = {} } = req.body;

      if (!command) {
        return res.status(400).json({ error: 'Command is required' });
      }

      validateCommand(command, params);

      console.log(`Executing command: ${command}`, params);
      
      // Convert simplified commands to EV3 protocol format
      let action, direction, speed, duration, extraParams = {};
      
      switch (command) {
        case 'forward':
          action = 'move';
          direction = 'forward';
          speed = params.speed || 500;
          duration = params.duration || 0;
          break;
        case 'backward':
          action = 'move';
          direction = 'backward';
          speed = params.speed || 500;
          duration = params.duration || 0;
          break;
        case 'left':
          action = 'move';
          direction = 'left';
          speed = params.speed || 300;
          duration = params.duration || 0;
          break;
        case 'right':
          action = 'move';
          direction = 'right';
          speed = params.speed || 300;
          duration = params.duration || 0;
          break;
        case 'turret_left':
          action = 'turret';
          direction = 'left';
          speed = params.speed || 200;
          duration = params.duration || 0;
          break;
        case 'turret_right':
          action = 'turret';
          direction = 'right';
          speed = params.speed || 200;
          duration = params.duration || 0;
          break;
        case 'stop':
          action = 'stop';
          break;
        case 'stop_turret':
          action = 'stop_turret';
          break;
        case 'get_status':
          action = 'status';
          break;
        case 'get_help':
          action = 'help';
          break;
        case 'joystick_control':
          action = 'joystick';
          extraParams = {
            l_left: params.l_left || 0,
            l_forward: params.l_forward || 0,
            r_left: params.r_left || 0,
            r_forward: params.r_forward || 0
          };
          break;
        case 'speak':
          action = 'speak';
          extraParams = {
            text: params.text
          };
          break;
        case 'battery':
          action = 'battery';
          break;
        case 'beep':
          action = 'beep';
          if (params.frequency !== undefined || params.duration !== undefined) {
            extraParams = {};
            if (params.frequency !== undefined) extraParams.frequency = params.frequency;
            if (params.duration !== undefined) extraParams.duration = params.duration;
          }
          break;
        default:
          return res.status(400).json({ error: `Unsupported command: ${command}` });
      }
      
      const result = await sendCommandToRobot(action, direction, speed, duration, extraParams);
      
      res.status(200).json({
        success: true,
        command,
        result,
        timestamp: new Date().toISOString()
      });

    } catch (error) {
      console.error('Error:', error.message);
      
      res.status(500).json({
        success: false,
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  });
});