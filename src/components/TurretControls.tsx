'use client';

import { useState } from 'react';
import { 
  ArrowLeftIcon, 
  ArrowRightIcon,
  EyeIcon,
  StopIcon,
  Cog6ToothIcon
} from '@heroicons/react/24/solid';
import toast from 'react-hot-toast';
import { robotController, ROBOT_CONSTANTS } from '@/lib/robot-api';

interface TurretControlsProps {
  className?: string;
}

export default function TurretControls({ className = '' }: TurretControlsProps) {
  const [turretAngle, setTurretAngle] = useState(0);
  const [isRotating, setIsRotating] = useState(false);
  const [rotationDirection, setRotationDirection] = useState<'left' | 'right' | ''>('');
  const [rotationSpeed, setRotationSpeed] = useState(30);
  const [isScanning, setIsScanning] = useState(false);

  const rotateTurret = async (direction: 'left' | 'right') => {
    try {
      setIsRotating(true);
      setRotationDirection(direction);

      const turretSpeed = Math.floor((rotationSpeed / 100) * ROBOT_CONSTANTS.MAX_SPEED * 0.3); // Turret is slower
      const duration = 1.0; // 1 second rotation
      
      console.log(`Rotating turret ${direction} at speed ${turretSpeed} (${rotationSpeed}%)`);
      
      let response;
      if (direction === 'left') {
        response = await robotController.turretLeft(turretSpeed, duration);
      } else {
        response = await robotController.turretRight(turretSpeed, duration);
      }

      if (response.success) {
        toast.success(`Turret rotating ${direction}`);
        
        // Update local angle for visual feedback
        const angleChange = direction === 'left' ? -15 : 15;
        const newAngle = Math.max(-180, Math.min(180, turretAngle + angleChange));
        setTurretAngle(newAngle);
      } else {
        throw new Error(response.error || 'Turret command failed');
      }
      
      setTimeout(() => {
        setIsRotating(false);
        setRotationDirection('');
      }, 800);
      
    } catch (error) {
      console.error('Failed to rotate turret:', error);
      toast.error(`Failed to control turret: ${error instanceof Error ? error.message : 'Unknown error'}`);
      setIsRotating(false);
      setRotationDirection('');
    }
  };

  const centerTurret = async () => {
    try {
      setIsRotating(true);
      console.log('Stopping turret (centering)');
      
      const response = await robotController.stopTurret();
      
      if (response.success) {
        toast.success('Turret stopped');
        setTurretAngle(0); // Reset to center for visual feedback
      } else {
        throw new Error(response.error || 'Stop turret command failed');
      }
      
      setTimeout(() => {
        setIsRotating(false);
      }, 1000);
      
    } catch (error) {
      console.error('Failed to stop turret:', error);
      toast.error(`Failed to stop turret: ${error instanceof Error ? error.message : 'Unknown error'}`);
      setIsRotating(false);
    }
  };

  const toggleScan = async () => {
    try {
      const newScanState = !isScanning;
      setIsScanning(newScanState);
      
      if (newScanState) {
        toast.success('Starting turret scan mode');
        console.log('Starting 360° turret scan mode');
        // Note: Actual scanning would involve continuous rotation commands
        // This is a simulated mode for the UI
      } else {
        toast.success('Stopping turret scan');
        console.log('Stopping turret scan');
        
        // Send stop command to halt any ongoing rotation
        const response = await robotController.stopTurret();
        if (!response.success) {
          console.warn('Failed to stop turret:', response.error);
        }
      }
      
    } catch (error) {
      console.error('Failed to toggle scan:', error);
      toast.error(`Failed to control scanner: ${error instanceof Error ? error.message : 'Unknown error'}`);
      setIsScanning(false);
    }
  };

  const controlButtonClass = (direction: string) => `
    p-3 rounded-lg font-medium transition-all duration-150 flex items-center justify-center
    ${rotationDirection === direction && isRotating
      ? 'bg-purple-600 text-white scale-95 shadow-inner' 
      : 'bg-gray-600 hover:bg-gray-500 text-white hover:scale-105 shadow-lg'
    }
    ${isRotating && rotationDirection !== direction ? 'opacity-50 cursor-not-allowed' : 'active:scale-95'}
  `;

  return (
    <div className={`bg-gray-700 rounded-lg p-4 ${className}`}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white">Turret Control</h3>
        <div className={`w-2 h-2 rounded-full ${
          isScanning ? 'bg-orange-500 animate-pulse' : 
          isRotating ? 'bg-purple-500 animate-pulse' : 
          'bg-gray-500'
        }`} />
      </div>

      {/* Turret Position Display */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-2">
          <label className="text-sm font-medium text-gray-300">Angle</label>
          <span className="text-sm font-mono text-purple-400">{turretAngle}°</span>
        </div>
        
        {/* Visual angle indicator */}
        <div className="relative h-16 bg-gray-600 rounded-lg mb-2 overflow-hidden">
          <div className="absolute inset-0 flex items-center justify-center">
            <div 
              className="w-1 h-12 bg-purple-400 transition-transform duration-500"
              style={{ 
                transform: `rotate(${turretAngle}deg)`,
                transformOrigin: 'bottom center'
              }}
            />
          </div>
          <div className="absolute bottom-2 left-2 text-xs text-gray-400">-180°</div>
          <div className="absolute bottom-2 right-2 text-xs text-gray-400">+180°</div>
          <div className="absolute bottom-2 left-1/2 transform -translate-x-1/2 text-xs text-gray-400">0°</div>
        </div>
      </div>

      {/* Rotation Speed Control */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-2">
          <label className="text-sm font-medium text-gray-300">Rotation Speed</label>
          <span className="text-sm font-mono text-purple-400">{rotationSpeed}%</span>
        </div>
        <input
          type="range"
          min="10"
          max="100"
          value={rotationSpeed}
          onChange={(e) => setRotationSpeed(parseInt(e.target.value))}
          disabled={isRotating || isScanning}
          className="w-full h-2 bg-gray-600 rounded-lg appearance-none cursor-pointer slider"
        />
      </div>

      {/* Rotation Controls */}
      <div className="grid grid-cols-3 gap-2 mb-4">
        <button
          onClick={() => rotateTurret('left')}
          disabled={isRotating || isScanning}
          className={controlButtonClass('left')}
          title="Rotate Left"
        >
          <ArrowLeftIcon className="w-6 h-6" />
        </button>
        
        <button
          onClick={centerTurret}
          disabled={isRotating || isScanning}
          className="p-3 rounded-lg font-medium transition-all duration-150 flex items-center justify-center bg-blue-600 hover:bg-blue-700 text-white hover:scale-105 active:scale-95 shadow-lg"
          title="Center Turret"
        >
          <StopIcon className="w-6 h-6" />
        </button>
        
        <button
          onClick={() => rotateTurret('right')}
          disabled={isRotating || isScanning}
          className={controlButtonClass('right')}
          title="Rotate Right"
        >
          <ArrowRightIcon className="w-6 h-6" />
        </button>
      </div>

      {/* Scan Control */}
      <div className="mb-4">
        <button
          onClick={toggleScan}
          disabled={isRotating}
          className={`w-full p-3 rounded-lg font-medium transition-all duration-150 flex items-center justify-center space-x-2 ${
            isScanning 
              ? 'bg-orange-600 hover:bg-orange-700 text-white' 
              : 'bg-green-600 hover:bg-green-700 text-white'
          } hover:scale-105 active:scale-95 shadow-lg`}
          title={isScanning ? 'Stop 360° Scan' : 'Start 360° Scan'}
        >
          {isScanning ? (
            <>
              <StopIcon className="w-5 h-5" />
              <span>Stop Scan</span>
            </>
          ) : (
            <>
              <EyeIcon className="w-5 h-5" />
              <span>Start 360° Scan</span>
            </>
          )}
        </button>
      </div>

      {/* Status Display */}
      <div className="text-center text-sm">
        {isScanning ? (
          <div className="text-orange-400 font-medium">
            Scanning terrain...
          </div>
        ) : isRotating ? (
          <div className="text-purple-400 font-medium">
            Rotating {rotationDirection} at {rotationSpeed}%
          </div>
        ) : (
          <div className="text-gray-400">
            Turret ready at {turretAngle}°
          </div>
        )}
      </div>

      <style jsx>{`
        .slider::-webkit-slider-thumb {
          appearance: none;
          height: 16px;
          width: 16px;
          border-radius: 50%;
          background: #a855f7;
          cursor: pointer;
        }
        
        .slider::-moz-range-thumb {
          height: 16px;
          width: 16px;
          border-radius: 50%;
          background: #a855f7;
          cursor: pointer;
          border: none;
        }
      `}</style>
    </div>
  );
}