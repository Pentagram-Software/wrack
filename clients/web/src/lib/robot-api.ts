interface RobotCommand {
  command: string;
  params?: Record<string, any>;
}

interface RobotResponse {
  success: boolean;
  command?: string;
  result?: any;
  error?: string;
  message?: string;
  timestamp?: string;
}

class RobotController {
  private baseURL: string;
  private apiKey: string;
  private connectionStatus: 'connected' | 'disconnected' | 'error' = 'disconnected';
  private lastError?: string;

  constructor() {
    this.baseURL = process.env.NEXT_PUBLIC_GCP_FUNCTION_URL || 'https://europe-central2-wrack-control.cloudfunctions.net/controlRobot';
    this.apiKey = process.env.NEXT_PUBLIC_API_KEY || 'abc123def456ghi789jkl012mno345pq';
    
    console.log('🔧 Robot API initialized:');
    console.log('📍 URL:', this.baseURL);
    console.log('🔑 API Key:', this.apiKey ? this.apiKey.substring(0, 8) + '...' : 'NOT SET');
  }

  private async sendCommand(command: RobotCommand): Promise<RobotResponse> {
    console.log('🚀 Sending command:', command);
    console.log('📍 To URL:', this.baseURL);
    
    try {
      const response = await fetch(this.baseURL, {
        method: 'POST',
        mode: 'cors',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': this.apiKey,
        },
        body: JSON.stringify(command),
      });

      console.log('📡 Response status:', response.status, response.statusText);

      if (!response.ok) {
        this.connectionStatus = 'error';
        const errorText = await response.text();
        console.log('❌ Response error:', errorText);

        // Try to parse error as JSON
        try {
          const errorData = JSON.parse(errorText);
          this.lastError = errorData.error || errorText;
          return {
            success: false,
            error: errorData.error || 'Request failed',
            message: errorData.error || errorText,
          };
        } catch {
          this.lastError = errorText;
          return {
            success: false,
            error: errorText || 'Request failed',
            message: errorText,
          };
        }
      }

      this.connectionStatus = 'connected';
      this.lastError = undefined;
      console.log('✅ Connection successful');

      const data: RobotResponse = await response.json();
      console.log('📦 Response data:', data);
      return data;
    } catch (error) {
      this.connectionStatus = 'disconnected';
      this.lastError = error instanceof Error ? error.message : 'Unknown error';
      console.log('💥 Connection error:', this.lastError);

      // Return error response instead of throwing
      return {
        success: false,
        error: this.lastError,
        message: this.lastError,
      };
    }
  }

  // Vehicle Movement Commands
  async moveForward(speed: number = 500, duration: number = 0): Promise<RobotResponse> {
    return this.sendCommand({
      command: 'forward',
      params: { speed, duration }
    });
  }

  async moveBackward(speed: number = 500, duration: number = 0): Promise<RobotResponse> {
    return this.sendCommand({
      command: 'backward',
      params: { speed, duration }
    });
  }

  async turnLeft(speed: number = 300, duration: number = 0): Promise<RobotResponse> {
    return this.sendCommand({
      command: 'left',
      params: { speed, duration }
    });
  }

  async turnRight(speed: number = 300, duration: number = 0): Promise<RobotResponse> {
    return this.sendCommand({
      command: 'right',
      params: { speed, duration }
    });
  }

  async stop(): Promise<RobotResponse> {
    return this.sendCommand({
      command: 'stop'
    });
  }

  // Turret Commands
  async turretLeft(speed: number = 200, duration: number = 1.0): Promise<RobotResponse> {
    return this.sendCommand({
      command: 'turret_left',
      params: { speed, duration }
    });
  }

  async turretRight(speed: number = 200, duration: number = 1.0): Promise<RobotResponse> {
    return this.sendCommand({
      command: 'turret_right',
      params: { speed, duration }
    });
  }

  async stopTurret(): Promise<RobotResponse> {
    return this.sendCommand({
      command: 'stop_turret'
    });
  }

  // Advanced Control
  async joystickControl(leftForward: number, rightForward: number, leftLeft: number = 0, rightLeft: number = 0): Promise<RobotResponse> {
    return this.sendCommand({
      command: 'joystick_control',
      params: {
        l_left: leftLeft,
        l_forward: leftForward,
        r_left: rightLeft,
        r_forward: rightForward
      }
    });
  }

  // Status Commands
  async getStatus(): Promise<RobotResponse> {
    return this.sendCommand({
      command: 'get_status'
    });
  }

  async getHelp(): Promise<RobotResponse> {
    return this.sendCommand({
      command: 'get_help'
    });
  }

  // Speech Command
  async speak(text: string): Promise<RobotResponse> {
    if (text.length > 500) {
      throw new Error('Text too long. Maximum 500 characters allowed.');
    }
    return this.sendCommand({
      command: 'speak',
      params: { text }
    });
  }

  // Connection Status
  getConnectionStatus(): 'connected' | 'disconnected' | 'error' {
    return this.connectionStatus;
  }

  getLastError(): string | undefined {
    return this.lastError;
  }
}

// Export singleton instance
export const robotController = new RobotController();

// Export types for use in components
export type { RobotResponse, RobotCommand };

// Export speed constants (matching iPhone app)
export const ROBOT_CONSTANTS = {
  DEFAULT_TURN_SPEED: 300,
  DEFAULT_MOVE_SPEED: 500,
  MAX_SPEED: 2000,
  SPEED_MULTIPLIER: 20.0,
  DEFAULT_TURRET_SPEED: 200,
  DEFAULT_TURRET_DURATION: 1.0
};