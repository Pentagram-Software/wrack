'use client';

import { useState } from 'react';
import { 
  ArrowUpIcon, 
  ArrowDownIcon, 
  ArrowLeftIcon, 
  ArrowRightIcon,
  StopIcon
} from '@heroicons/react/24/solid';
import toast from 'react-hot-toast';
import { robotController, ROBOT_CONSTANTS } from '@/lib/robot-api';

interface VehicleControlsProps {
  className?: string;
}

export default function VehicleControls({ className = '' }: VehicleControlsProps) {
  const [speed, setSpeed] = useState(50);
  const [isMoving, setIsMoving] = useState(false);
  const [currentDirection, setCurrentDirection] = useState<string>('');

  const sendCommand = async (command: string, direction: string) => {
    try {
      setIsMoving(true);
      setCurrentDirection(direction);

      const robotSpeed = Math.floor((speed / 100) * ROBOT_CONSTANTS.MAX_SPEED);
      console.log(`Sending command: ${command} at speed ${robotSpeed} (${speed}%)`);

      let response;
      switch (command) {
        case 'forward':
          response = await robotController.moveForward(robotSpeed);
          break;
        case 'backward':
          response = await robotController.moveBackward(robotSpeed);
          break;
        case 'turnLeft':
          response = await robotController.turnLeft(Math.floor(robotSpeed * 0.6)); // Slower turning
          break;
        case 'turnRight':
          response = await robotController.turnRight(Math.floor(robotSpeed * 0.6)); // Slower turning
          break;
        default:
          throw new Error(`Unknown command: ${command}`);
      }

      if (response.success) {
        toast.success(`Vehicle moving ${direction}`);
      } else {
        throw new Error(response.error || 'Command failed');
      }
      
      setTimeout(() => {
        setIsMoving(false);
        setCurrentDirection('');
      }, 1000);
      
    } catch (error) {
      console.error('Failed to send command:', error);
      toast.error(`Failed to control vehicle: ${error instanceof Error ? error.message : 'Unknown error'}`);
      setIsMoving(false);
      setCurrentDirection('');
    }
  };

  const stopVehicle = async () => {
    try {
      console.log('Emergency stop activated');
      const response = await robotController.stop();
      
      if (response.success) {
        toast.success('Vehicle stopped');
      } else {
        throw new Error(response.error || 'Stop command failed');
      }
      
      setIsMoving(false);
      setCurrentDirection('');
    } catch (error) {
      console.error('Failed to stop vehicle:', error);
      toast.error(`Failed to stop vehicle: ${error instanceof Error ? error.message : 'Unknown error'}`);
      setIsMoving(false);
      setCurrentDirection('');
    }
  };

  const controlButtonClass = (direction: string) => `
    p-3 rounded-lg font-medium transition-all duration-150 flex items-center justify-center
    ${currentDirection === direction && isMoving
      ? 'bg-blue-600 text-white scale-95 shadow-inner' 
      : 'bg-gray-600 hover:bg-gray-500 text-white hover:scale-105 shadow-lg'
    }
    ${isMoving && currentDirection !== direction ? 'opacity-50 cursor-not-allowed' : 'active:scale-95'}
  `;

  return (
    <div className={`bg-gray-700 rounded-lg p-4 ${className}`}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white">Vehicle Control</h3>
        <div className={`w-2 h-2 rounded-full ${isMoving ? 'bg-green-500 animate-pulse' : 'bg-gray-500'}`} />
      </div>

      {/* Speed Control */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-2">
          <label className="text-sm font-medium text-gray-300">Speed</label>
          <span className="text-sm font-mono text-blue-400">{speed}%</span>
        </div>
        <input
          type="range"
          min="10"
          max="100"
          value={speed}
          onChange={(e) => setSpeed(parseInt(e.target.value))}
          disabled={isMoving}
          className="w-full h-2 bg-gray-600 rounded-lg appearance-none cursor-pointer slider"
        />
        <div className="flex justify-between text-xs text-gray-400 mt-1">
          <span>10%</span>
          <span>50%</span>
          <span>100%</span>
        </div>
      </div>

      {/* Direction Controls */}
      <div className="grid grid-cols-3 gap-2 mb-4">
        {/* Top Row */}
        <div></div>
        <button
          onClick={() => sendCommand('forward', 'forward')}
          disabled={isMoving}
          className={controlButtonClass('forward')}
          title="Move Forward"
        >
          <ArrowUpIcon className="w-6 h-6" />
        </button>
        <div></div>

        {/* Middle Row */}
        <button
          onClick={() => sendCommand('turnLeft', 'left')}
          disabled={isMoving}
          className={controlButtonClass('left')}
          title="Turn Left"
        >
          <ArrowLeftIcon className="w-6 h-6" />
        </button>
        
        <button
          onClick={stopVehicle}
          className="p-3 rounded-lg font-medium transition-all duration-150 flex items-center justify-center bg-red-600 hover:bg-red-700 text-white hover:scale-105 active:scale-95 shadow-lg"
          title="Emergency Stop"
        >
          <StopIcon className="w-6 h-6" />
        </button>
        
        <button
          onClick={() => sendCommand('turnRight', 'right')}
          disabled={isMoving}
          className={controlButtonClass('right')}
          title="Turn Right"
        >
          <ArrowRightIcon className="w-6 h-6" />
        </button>

        {/* Bottom Row */}
        <div></div>
        <button
          onClick={() => sendCommand('backward', 'backward')}
          disabled={isMoving}
          className={controlButtonClass('backward')}
          title="Move Backward"
        >
          <ArrowDownIcon className="w-6 h-6" />
        </button>
        <div></div>
      </div>

      {/* Status Display */}
      <div className="text-center text-sm">
        {isMoving ? (
          <div className="text-blue-400 font-medium">
            Moving {currentDirection} at {speed}%
          </div>
        ) : (
          <div className="text-gray-400">
            Vehicle ready
          </div>
        )}
      </div>

      <style jsx>{`
        .slider::-webkit-slider-thumb {
          appearance: none;
          height: 16px;
          width: 16px;
          border-radius: 50%;
          background: #3b82f6;
          cursor: pointer;
        }
        
        .slider::-moz-range-thumb {
          height: 16px;
          width: 16px;
          border-radius: 50%;
          background: #3b82f6;
          cursor: pointer;
          border: none;
        }
      `}</style>
    </div>
  );
}