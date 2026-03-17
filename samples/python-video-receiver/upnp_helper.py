#!/usr/bin/env python3
"""
UPnP Port Mapping Helper - Automatically open ports for UDP video client
"""

import socket
import time

def try_upnp_port_mapping(port):
    """Try to open port using UPnP (requires miniupnpc)"""
    try:
        import miniupnpc
        
        upnp = miniupnpc.UPnP()
        upnp.discoverdelay = 200
        
        print(f"Discovering UPnP devices...")
        devices = upnp.discover()
        print(f"Found {devices} UPnP device(s)")
        
        upnp.selectigd()
        
        # Get external IP
        external_ip = upnp.externalipaddress()
        print(f"External IP: {external_ip}")
        
        # Get local IP
        local_ip = socket.gethostbyname(socket.gethostname())
        
        # Add port mapping
        result = upnp.addportmapping(
            port,           # external port
            'UDP',          # protocol
            local_ip,       # internal IP
            port,           # internal port
            'UDP Video Client',  # description
            ''              # remote host (empty = any)
        )
        
        if result:
            print(f"✅ Successfully opened UDP port {port}")
            print(f"External: {external_ip}:{port} → Internal: {local_ip}:{port}")
            return True
        else:
            print(f"❌ Failed to open UDP port {port}")
            return False
            
    except ImportError:
        print("❌ miniupnpc not installed. Install with: pip install miniupnpc")
        return False
    except Exception as e:
        print(f"❌ UPnP error: {e}")
        return False

def remove_upnp_port_mapping(port):
    """Remove UPnP port mapping"""
    try:
        import miniupnpc
        
        upnp = miniupnpc.UPnP()
        upnp.discoverdelay = 200
        upnp.discover()
        upnp.selectigd()
        
        result = upnp.deleteportmapping(port, 'UDP')
        if result:
            print(f"✅ Removed UDP port mapping for {port}")
        else:
            print(f"❌ Failed to remove UDP port mapping for {port}")
            
    except Exception as e:
        print(f"❌ UPnP removal error: {e}")

if __name__ == "__main__":
    port = 8888
    print("UDP Video Client - UPnP Port Mapping")
    print("1. Open port mapping")
    print("2. Remove port mapping")
    
    choice = input("Choose (1-2): ").strip()
    
    if choice == "1":
        try_upnp_port_mapping(port)
    elif choice == "2":
        remove_upnp_port_mapping(port)
    else:
        print("Invalid choice")
