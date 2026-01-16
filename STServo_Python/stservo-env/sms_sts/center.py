import sys
import time
sys.path.append("..")
from STservo_sdk import *

# --- CONFIG ---
DEVICE_NAME = '/dev/ttyACM0'
BAUDRATE    = 1000000
SERVO_IDS   = [1, 2, 3, 4, 5, 6] 

portHandler = PortHandler(DEVICE_NAME)
packetHandler = sts(portHandler)

if not (portHandler.openPort() and portHandler.setBaudRate(BAUDRATE)):
    print("Failed to open port")
    quit()

print("Moving all servos to 2048...")

for s_id in SERVO_IDS:
    # WritePosEx(ID, Position, Speed, Acceleration)
    # 2048 is the midpoint, 500 is a safe slow speed
    packetHandler.WritePosEx(s_id, 2048, 500, 50)
    print(f"Servo {s_id} commanded to 2048")
    time.sleep(0.1) # Small delay to avoid bus congestion

print("Done. Servos should now be at center.")
portHandler.closePort()
