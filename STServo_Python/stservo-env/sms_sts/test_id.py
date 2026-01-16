import sys
import time
sys.path.append("..")
from STservo_sdk import *

DEVICE_NAME = '/dev/ttyACM0'
portHandler = PortHandler(DEVICE_NAME)
packetHandler = sts(portHandler)

if not (portHandler.openPort() and portHandler.setBaudRate(1000000)):
    quit()

while True:
    user_input = input("\nEnter ID to wiggle (or 'q' to quit): ")
    if user_input == 'q': break
    
    try:
        s_id = int(user_input)
        print(f"Wiggling ID {s_id}...")
        
        # Move slightly +50 and back
        # Read current pos first (optional), or just wiggle relative to center
        packetHandler.WritePosEx(s_id, 2100, 1000, 50)
        time.sleep(0.5)
        packetHandler.WritePosEx(s_id, 2000, 1000, 50)
        time.sleep(0.5)
        packetHandler.WritePosEx(s_id, 2048, 1000, 50) # Return to center
        
    except ValueError:
        print("Please enter a number.")

portHandler.closePort()
