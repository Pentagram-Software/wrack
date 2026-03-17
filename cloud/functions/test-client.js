const axios = require('axios');

const CLOUD_FUNCTION_URL = 'https://europe-central2-wrack-control.cloudfunctions.net/controlRobot';
const API_KEY = process.env.API_KEY || 'your-api-key-here';

async function testRobotCommand(command, params = {}) {
  try {
    const payload = {
      command,
      params
    };
    
    console.log(`\n--- Sending Command ---`);
    console.log('Command:', command);
    console.log('Parameters:', params);
    console.log('Full message sent to Cloud Function:');
    console.log(JSON.stringify(payload, null, 2));
    console.log('URL:', CLOUD_FUNCTION_URL);
    console.log('Headers:', {
      'Content-Type': 'application/json',
      'X-API-Key': API_KEY
    });
    
    const response = await axios.post(CLOUD_FUNCTION_URL, payload, {
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY
      }
    });
    
    console.log('\n--- Response Received ---');
    console.log(JSON.stringify(response.data, null, 2));
    return response.data;
    
  } catch (error) {
    console.error('\n--- Error ---');
    console.error('Error:', error.response?.data || error.message);
    return null;
  }
}

async function runTests() {
  console.log('Starting robot control tests using EV3 protocol...\n');
  
  // Test robot status first
  console.log('=== Testing Robot Status ===');
  await testRobotCommand('get_status');
  await new Promise(resolve => setTimeout(resolve, 1000));
  
  // Complete movement sequence test
  console.log('\n=== Complete Movement Sequence Test ===');
  
  console.log('1. Move FORWARD (speed: 400, duration: 2 seconds)...');
  await testRobotCommand('forward', { speed: 400, duration: 2 });
  await new Promise(resolve => setTimeout(resolve, 2500));
  
  console.log('2. Turn LEFT (speed: 300, duration: 1 second)...');
  await testRobotCommand('left', { speed: 300, duration: 1 });
  await new Promise(resolve => setTimeout(resolve, 1500));
  
  console.log('3. Turn RIGHT (speed: 300, duration: 1 second)...');
  await testRobotCommand('right', { speed: 300, duration: 1 });
  await new Promise(resolve => setTimeout(resolve, 1500));
  
  console.log('4. Turn turret LEFT (speed: 200, duration: 1 second)...');
  await testRobotCommand('turret_left', { speed: 200, duration: 1 });
  await new Promise(resolve => setTimeout(resolve, 1500));
  
  console.log('5. Turn turret RIGHT (speed: 200, duration: 1 second)...');
  await testRobotCommand('turret_right', { speed: 200, duration: 1 });
  await new Promise(resolve => setTimeout(resolve, 1500));
  
  console.log('6. Move BACKWARD (speed: 400, duration: 2 seconds)...');
  await testRobotCommand('backward', { speed: 400, duration: 2 });
  await new Promise(resolve => setTimeout(resolve, 2500));
  
  console.log('7. STOP all motors...');
  await testRobotCommand('stop');
  
  console.log('\n=== Test Sequence Completed! ===');
  console.log('Expected sequence:');
  console.log('- Vehicle moved forward (or backward if motors reversed)');
  console.log('- Vehicle turned left');
  console.log('- Vehicle turned right');
  console.log('- Turret turned left');
  console.log('- Turret turned right');
  console.log('- Vehicle moved backward (or forward if motors reversed)');
  console.log('\nIf directions are wrong, check motor wiring/polarity on the robot.');
}

// Example mobile app integration
class MindstormsController {
  constructor(cloudFunctionUrl, apiKey) {
    this.url = cloudFunctionUrl;
    this.apiKey = apiKey;
  }
  
  async sendCommand(command, params = {}) {
    try {
      const response = await axios.post(this.url, {
        command,
        params
      }, {
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': this.apiKey
        },
        timeout: 10000
      });
      
      return response.data;
    } catch (error) {
      throw new Error(`Robot command failed: ${error.response?.data?.error || error.message}`);
    }
  }
  
  async moveForward(speed = 500, duration = 0) {
    return this.sendCommand('forward', { speed, duration });
  }
  
  async moveBackward(speed = 500, duration = 0) {
    return this.sendCommand('backward', { speed, duration });
  }
  
  async turnLeft(speed = 300, duration = 0) {
    return this.sendCommand('left', { speed, duration });
  }
  
  async turnRight(speed = 300, duration = 0) {
    return this.sendCommand('right', { speed, duration });
  }
  
  async turretLeft(speed = 200, duration = 0) {
    return this.sendCommand('turret_left', { speed, duration });
  }
  
  async turretRight(speed = 200, duration = 0) {
    return this.sendCommand('turret_right', { speed, duration });
  }
  
  async stop() {
    return this.sendCommand('stop');
  }
  
  async getStatus() {
    return this.sendCommand('get_status');
  }
  
  async getHelp() {
    return this.sendCommand('get_help');
  }
  
  async joystickControl(l_left = 0, l_forward = 0, r_left = 0, r_forward = 0) {
    return this.sendCommand('joystick_control', { l_left, l_forward, r_left, r_forward });
  }
}

if (require.main === module) {
  runTests();
}

module.exports = { testRobotCommand, MindstormsController };