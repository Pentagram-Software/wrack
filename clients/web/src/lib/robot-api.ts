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
  private readonly proxyURL = '/api/robot';
  private connectionStatus: 'connected' | 'disconnected' | 'error' = 'disconnected';
  private lastError?: string;

  private async sendCommand(command: RobotCommand): Promise<RobotResponse> {
    try {
      const response = await fetch(this.proxyURL, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(command),
      });

      if (response.status === 401 || response.status === 403) {
        this.connectionStatus = 'error';
        const data = await response.json().catch(() => ({}));
        this.lastError = data.error ?? 'Unauthorized';
        return { success: false, error: this.lastError, message: this.lastError };
      }

      if (!response.ok) {
        this.connectionStatus = 'error';
        const errorText = await response.text();
        try {
          const errorData = JSON.parse(errorText);
          this.lastError = errorData.error || errorText;
          return { success: false, error: errorData.error || 'Request failed', message: errorData.error || errorText };
        } catch {
          this.lastError = errorText;
          return { success: false, error: errorText || 'Request failed', message: errorText };
        }
      }

      this.connectionStatus = 'connected';
      this.lastError = undefined;

      const data: RobotResponse = await response.json();
      return data;
    } catch (error) {
      this.connectionStatus = 'disconnected';
      this.lastError = error instanceof Error ? error.message : 'Unknown error';
      return { success: false, error: this.lastError, message: this.lastError };
    }
  }

  // Vehicle Movement Commands
  async moveForward(speed: number = 500, duration: number = 0): Promise<RobotResponse> {
    return this.sendCommand({ command: 'forward', params: { speed, duration } });
  }

  async moveBackward(speed: number = 500, duration: number = 0): Promise<RobotResponse> {
    return this.sendCommand({ command: 'backward', params: { speed, duration } });
  }

  async turnLeft(speed: number = 300, duration: number = 0): Promise<RobotResponse> {
    return this.sendCommand({ command: 'left', params: { speed, duration } });
  }

  async turnRight(speed: number = 300, duration: number = 0): Promise<RobotResponse> {
    return this.sendCommand({ command: 'right', params: { speed, duration } });
  }

  async stop(): Promise<RobotResponse> {
    return this.sendCommand({ command: 'stop' });
  }

  // Turret Commands
  async turretLeft(speed: number = 200, duration: number = 1.0): Promise<RobotResponse> {
    return this.sendCommand({ command: 'turret_left', params: { speed, duration } });
  }

  async turretRight(speed: number = 200, duration: number = 1.0): Promise<RobotResponse> {
    return this.sendCommand({ command: 'turret_right', params: { speed, duration } });
  }

  async stopTurret(): Promise<RobotResponse> {
    return this.sendCommand({ command: 'stop_turret' });
  }

  // Advanced Control
  async joystickControl(
    leftForward: number,
    rightForward: number,
    leftLeft: number = 0,
    rightLeft: number = 0,
  ): Promise<RobotResponse> {
    return this.sendCommand({
      command: 'joystick_control',
      params: { l_left: leftLeft, l_forward: leftForward, r_left: rightLeft, r_forward: rightForward },
    });
  }

  // Status Commands
  async getStatus(): Promise<RobotResponse> {
    return this.sendCommand({ command: 'get_status' });
  }

  async getHelp(): Promise<RobotResponse> {
    return this.sendCommand({ command: 'get_help' });
  }

  // Speech Command
  async speak(text: string): Promise<RobotResponse> {
    if (text.length > 500) {
      throw new Error('Text too long. Maximum 500 characters allowed.');
    }
    return this.sendCommand({ command: 'speak', params: { text } });
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
  DEFAULT_TURRET_DURATION: 1.0,
};
