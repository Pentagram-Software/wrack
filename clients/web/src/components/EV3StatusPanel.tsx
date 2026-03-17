'use client';

import { useState, useEffect } from 'react';
import { Battery100Icon, WifiIcon, CpuChipIcon, ChevronDownIcon, ChevronRightIcon } from '@heroicons/react/24/solid';
import { robotController } from '@/lib/robot-api';

interface EV3Motor {
  id: string;
  name: string;
  deviceName: string;
  port: string;
  available: boolean;
  angle: number;
  speed: number;
  stalled: boolean;
}

interface EV3Sensor {
  id: string;
  name: string;
  type: string;
  port: string;
  available: boolean;
  value: string;
}

interface EV3Status {
  isConnected: boolean;
  batteryLevel: number;
  batteryVoltage: number;
  cpuUsage: number;
  kernelVersion: string;
  ipAddress: string;
  lastUpdate: Date;
}

export default function EV3StatusPanel() {
  const [isMounted, setIsMounted] = useState(false);
  const [ev3Status, setEV3Status] = useState<EV3Status>({
    isConnected: false,
    batteryLevel: 0,
    batteryVoltage: 0,
    cpuUsage: 0,
    kernelVersion: 'Unknown',
    ipAddress: 'Unknown',
    lastUpdate: new Date()
  });

  const [statusExpanded, setStatusExpanded] = useState(true);
  const [motorsExpanded, setMotorsExpanded] = useState(true);
  const [sensorsExpanded, setSensorsExpanded] = useState(true);

  const [motors, setMotors] = useState<EV3Motor[]>([]);
  const [sensors, setSensors] = useState<EV3Sensor[]>([]);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  useEffect(() => {
    const fetchRobotStatus = async () => {
      try {
        const response = await robotController.getStatus();
        const connectionStatus = robotController.getConnectionStatus();

        console.log('📊 Status response:', response);

        if (response.success && response.result?.device_info) {
          const deviceInfo = response.result.device_info;
          const battery = deviceInfo.battery;
          const ipAddresses = deviceInfo.ip_addresses || [];

          // Update EV3 Status
          setEV3Status({
            isConnected: connectionStatus === 'connected',
            batteryLevel: battery?.percentage || 0,
            batteryVoltage: battery?.voltage_v || 0,
            cpuUsage: deviceInfo.cpu_usage_percent || 0,
            kernelVersion: deviceInfo.kernel || 'Unknown',
            ipAddress: ipAddresses.length > 0 ? ipAddresses[0] : 'Unknown',
            lastUpdate: new Date(),
          });

          // Update Motors from API response
          const motorsData: EV3Motor[] = [];
          if (deviceInfo.motors) {
            Object.entries(deviceInfo.motors).forEach(([key, motor]: [string, any]) => {
              motorsData.push({
                id: key,
                name: key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
                deviceName: key,
                port: motor.port || 'Unknown',
                available: motor.available || false,
                angle: motor.angle_degrees || 0,
                speed: motor.speed_deg_per_sec || 0,
                stalled: motor.stalled || false,
              });
            });
          }
          setMotors(motorsData);

          // Update Sensors from API response
          const sensorsData: EV3Sensor[] = [];
          if (deviceInfo.sensors) {
            if (deviceInfo.sensors.ultrasonic) {
              const us = deviceInfo.sensors.ultrasonic;
              sensorsData.push({
                id: 'ultrasonic',
                name: 'Ultrasonic Sensor',
                type: 'distance',
                port: us.port || 'Unknown',
                available: us.available || false,
                value: us.available ? `${us.distance_cm?.toFixed(1) || 0} cm` : 'N/A',
              });
            }
            if (deviceInfo.sensors.gyro) {
              const gyro = deviceInfo.sensors.gyro;
              sensorsData.push({
                id: 'gyro',
                name: 'Gyro Sensor',
                type: 'angle',
                port: gyro.port || 'Unknown',
                available: gyro.available || false,
                value: gyro.available ? `${gyro.angle_degrees || 0}° (${gyro.speed_deg_per_sec || 0}°/s)` : 'N/A',
              });
            }
            if (deviceInfo.sensors.pixy_camera) {
              const pixy = deviceInfo.sensors.pixy_camera;
              sensorsData.push({
                id: 'pixy_camera',
                name: 'Pixy Camera',
                type: 'camera',
                port: pixy.port || 'Unknown',
                available: pixy.available || false,
                value: pixy.available ? 'Active' : 'N/A',
              });
            }
          }
          setSensors(sensorsData);
        } else {
          // If no device_info, just update connection status
          setEV3Status(prev => ({
            ...prev,
            isConnected: connectionStatus === 'connected',
            lastUpdate: new Date(),
          }));
        }

      } catch (error) {
        console.error('Failed to fetch robot status:', error);
        setEV3Status(prev => ({
          ...prev,
          isConnected: false,
          lastUpdate: new Date()
        }));
        // Don't clear motors and sensors on error, keep last known state
      }
    };

    // Fetch status immediately
    fetchRobotStatus();

    // Then fetch every 5 seconds
    const interval = setInterval(fetchRobotStatus, 5000);

    return () => clearInterval(interval);
  }, []);

  const getStatusColor = (available: boolean) => {
    return available ? 'text-green-400' : 'text-gray-400';
  };

  const getStatusBg = (available: boolean) => {
    return available ? 'bg-green-500' : 'bg-gray-500';
  };

  return (
    <div className="space-y-6">
      {/* EV3 Connection Status */}
      <div className="bg-gray-700 rounded-lg p-4">
        <button 
          onClick={() => setStatusExpanded(!statusExpanded)}
          className="flex items-center justify-between w-full text-left hover:text-blue-400 transition-colors mb-4"
        >
          <div className="flex items-center space-x-2">
            {statusExpanded ? (
              <ChevronDownIcon className="w-5 h-5 text-white" />
            ) : (
              <ChevronRightIcon className="w-5 h-5 text-white" />
            )}
            <h2 className="text-xl font-semibold text-white">EV3 Brick Status</h2>
          </div>
          
          <div className="flex items-center space-x-2">
            <span className="text-sm text-gray-400">
              {ev3Status.isConnected ? 'Connected' : 'Disconnected'}
            </span>
            <div className={`w-3 h-3 rounded-full ${ev3Status.isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
          </div>
        </button>
        
        {statusExpanded && (
          <>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-3">
                <div className="flex items-center space-x-2">
                  <Battery100Icon className="w-5 h-5 text-yellow-400" />
                  <span className="text-sm text-gray-300">Battery</span>
                  <span className="text-sm font-medium text-white">{ev3Status.batteryLevel}%</span>
                </div>

                <div className="flex items-center space-x-2">
                  <Battery100Icon className="w-5 h-5 text-purple-400" />
                  <span className="text-sm text-gray-300">Voltage</span>
                  <span className="text-sm font-medium text-white">{ev3Status.batteryVoltage.toFixed(2)}V</span>
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex items-center space-x-2">
                  <CpuChipIcon className="w-5 h-5 text-blue-400" />
                  <span className="text-sm text-gray-300">CPU</span>
                  <span className="text-sm font-medium text-white">{ev3Status.cpuUsage}%</span>
                </div>

                <div className="flex items-center space-x-2">
                  <WifiIcon className="w-5 h-5 text-green-400" />
                  <span className="text-sm text-gray-300">IP</span>
                  <span className="text-sm font-medium text-white">{ev3Status.ipAddress}</span>
                </div>
              </div>
            </div>

            <div className="mt-4 pt-3 border-t border-gray-600">
              <div className="flex justify-between items-center text-xs">
                <div className="text-gray-400">
                  <span className="font-semibold">Kernel:</span> {ev3Status.kernelVersion}
                </div>
                <div className="text-gray-400">
                  <span className="font-semibold">Updated:</span> {isMounted ? ev3Status.lastUpdate.toLocaleTimeString() : '--:--:--'}
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Motors */}
      <div className="bg-gray-700 rounded-lg p-4">
        <button
          onClick={() => setMotorsExpanded(!motorsExpanded)}
          className="flex items-center justify-between w-full text-left hover:text-blue-400 transition-colors mb-4"
        >
          <div className="flex items-center space-x-2">
            {motorsExpanded ? (
              <ChevronDownIcon className="w-5 h-5 text-white" />
            ) : (
              <ChevronRightIcon className="w-5 h-5 text-white" />
            )}
            <h3 className="text-lg font-semibold text-white">Motors</h3>
            <span className="text-sm text-gray-400">
              ({motors.filter(m => m.available).length}/{motors.length})
            </span>
          </div>

          <div className="flex space-x-1">
            {motors.map((motor) => (
              <div
                key={motor.id}
                className={`w-2 h-2 rounded-full ${getStatusBg(motor.available)}`}
                title={`${motor.name}: ${motor.available ? 'available' : 'unavailable'}`}
              />
            ))}
          </div>
        </button>

        {motorsExpanded && (
          <div className="space-y-3">
            {motors.length === 0 ? (
              <div className="text-gray-400 text-sm text-center py-4">No motor data available</div>
            ) : (
              motors.map((motor) => (
                <div key={motor.id} className="flex items-center justify-between p-3 bg-gray-600 rounded">
                  <div className="flex items-center space-x-3 flex-1">
                    <div className={`w-8 h-8 ${motor.available ? 'bg-blue-500' : 'bg-gray-500'} rounded flex items-center justify-center text-white font-bold text-xs`}>
                      ⚙️
                    </div>
                    <div className="flex-1">
                      <div className="text-white font-medium">{motor.name}</div>
                      <div className="text-gray-300 text-sm">{motor.port}</div>
                      {motor.available && (
                        <div className="text-blue-300 text-xs font-mono mt-1">
                          Angle: {motor.angle}° | Speed: {motor.speed}°/s
                          {motor.stalled && <span className="text-red-400 ml-2">STALLED</span>}
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    <span className={`text-sm ${getStatusColor(motor.available)}`}>
                      {motor.available ? 'available' : 'unavailable'}
                    </span>
                    <div className={`w-2 h-2 rounded-full ${getStatusBg(motor.available)}`} />
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* Sensors */}
      <div className="bg-gray-700 rounded-lg p-4">
        <button
          onClick={() => setSensorsExpanded(!sensorsExpanded)}
          className="flex items-center justify-between w-full text-left hover:text-blue-400 transition-colors mb-4"
        >
          <div className="flex items-center space-x-2">
            {sensorsExpanded ? (
              <ChevronDownIcon className="w-5 h-5 text-white" />
            ) : (
              <ChevronRightIcon className="w-5 h-5 text-white" />
            )}
            <h3 className="text-lg font-semibold text-white">Sensors</h3>
            <span className="text-sm text-gray-400">
              ({sensors.filter(s => s.available).length}/{sensors.length})
            </span>
          </div>

          <div className="flex space-x-1">
            {sensors.map((sensor) => (
              <div
                key={sensor.id}
                className={`w-2 h-2 rounded-full ${getStatusBg(sensor.available)}`}
                title={`${sensor.name}: ${sensor.available ? 'available' : 'unavailable'} - ${sensor.value}`}
              />
            ))}
          </div>
        </button>

        {sensorsExpanded && (
          <div className="space-y-3">
            {sensors.length === 0 ? (
              <div className="text-gray-400 text-sm text-center py-4">No sensor data available</div>
            ) : (
              sensors.map((sensor) => (
                <div key={sensor.id} className="flex items-center justify-between p-3 bg-gray-600 rounded">
                  <div className="flex items-center space-x-3 flex-1">
                    <div className={`w-8 h-8 ${sensor.available ? 'bg-green-500' : 'bg-gray-500'} rounded flex items-center justify-center text-white font-bold text-xs`}>
                      {sensor.type === 'distance' ? '📏' : sensor.type === 'angle' ? '🧭' : '📷'}
                    </div>
                    <div className="flex-1">
                      <div className="text-white font-medium">{sensor.name}</div>
                      <div className="text-gray-300 text-sm">{sensor.port}</div>
                      {sensor.available && (
                        <div className="text-blue-300 text-xs font-mono mt-1">{sensor.value}</div>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    <span className={`text-sm ${getStatusColor(sensor.available)}`}>
                      {sensor.available ? 'available' : 'unavailable'}
                    </span>
                    <div className={`w-2 h-2 rounded-full ${getStatusBg(sensor.available)}`} />
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}