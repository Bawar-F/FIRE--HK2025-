#!/usr/bin/env python3
"""
Test client that simulates Arduino master via network connection to Pi's UART bridge
"""
import socket
import time

PI_IP = "10.57.7.118"
BRIDGE_PORT = 5000

def send_command(sock, command):
    """Send command and read response"""
    print(f"→ Sending: {command}")
    sock.sendall(f"{command}\r\n".encode())
    time.sleep(0.2)
    
    try:
        response = sock.recv(1024).decode().strip()
        print(f"← Response: {response}")
        return response
    except:
        return None

def main():
    print("=" * 60)
    print("UART Test Client - Mac simulating Arduino")
    print("=" * 60)
    
    try:
        print(f"\n📡 Connecting to Pi bridge at {PI_IP}:{BRIDGE_PORT}...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((PI_IP, BRIDGE_PORT))
        print("✓ Connected!\n")
        
        # Test sequence
        print("🔥 Testing UART commands:\n")
        
        send_command(sock, "STATUS")
        time.sleep(1)
        
        send_command(sock, "START")
        time.sleep(2)
        
        send_command(sock, "STATUS")
        time.sleep(8)  # Let it capture
        
        send_command(sock, "STATUS")
        time.sleep(1)
        
        send_command(sock, "RESULTS")
        time.sleep(1)
        
        send_command(sock, "RESET")
        time.sleep(1)
        
        send_command(sock, "STATUS")
        
        print("\n✅ Test sequence complete!")
        
    except ConnectionRefusedError:
        print(f"❌ Could not connect to {PI_IP}:{BRIDGE_PORT}")
        print("   Make sure network_uart_bridge.py is running on the Pi")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        try:
            sock.close()
        except:
            pass

if __name__ == "__main__":
    main()
