#!/usr/bin/env python
"""
One-time script to set permanent torque limits on your servos.
This protects grippers from burning out!
"""

import sys
import time
sys.path.append("..")
from STservo_sdk import *

# --- CONFIGURATION ---
DEVICE_NAME = '/dev/ttyACM0'
BAUDRATE    = 1000000

# Torque settings (0-1023, where 1023 = 100%)
GRIPPER_TORQUE_LIMIT = 410  # 40% - Safe for grippers
NORMAL_TORQUE_LIMIT  = 1023 # 100% - Full power for arm servos

# Which servo is your gripper?
GRIPPER_ID = 6

# Which servos to configure (IDs)
SERVO_IDS = [1, 2, 3, 4, 5, 6]

# Memory addresses (Feetech STS/SMS servos)
MAX_TORQUE_LIMIT_L = 16  # Low byte
MAX_TORQUE_LIMIT_H = 17  # High byte

# --- SETUP ---
portHandler = PortHandler(DEVICE_NAME)
packetHandler = sts(portHandler)

print("=" * 50)
print("  SERVO TORQUE LIMIT CONFIGURATION")
print("=" * 50)

if not (portHandler.openPort() and portHandler.setBaudRate(BAUDRATE)):
    print(f"[ERROR] Failed to open {DEVICE_NAME}")
    quit()

print(f"Connected to {DEVICE_NAME}\n")

# --- FUNCTIONS ---
def set_torque_limit(servo_id, torque_value):
    """Set max torque limit (saves to EEPROM)"""
    print(f"Configuring Servo ID {servo_id}...", end=" ")
    
    # Unlock EEPROM
    result = packetHandler.unLockEprom(servo_id)
    if result != COMM_SUCCESS:
        print("[FAILED] Could not unlock EEPROM")
        return False
    
    time.sleep(0.05)
    
    # Write torque limit (2-byte value)
    result = packetHandler.write2ByteTxRx(servo_id, MAX_TORQUE_LIMIT_L, torque_value)
    if result != COMM_SUCCESS:
        print("[FAILED] Could not write torque limit")
        return False
    
    time.sleep(0.05)
    
    # Lock EEPROM (protect settings)
    packetHandler.LockEprom(servo_id)
    time.sleep(0.05)
    
    print(f"[OK] Set to {torque_value}/1023 ({torque_value*100//1023}%)")
    return True

def read_torque_limit(servo_id):
    """Read current max torque limit"""
    # Unlock to read
    packetHandler.unLockEprom(servo_id)
    time.sleep(0.05)
    
    result, comm, err = packetHandler.read2ByteTxRx(servo_id, MAX_TORQUE_LIMIT_L)
    
    # Lock back
    packetHandler.LockEprom(servo_id)
    
    if comm == COMM_SUCCESS:
        return result
    else:
        return None

# --- MAIN ---
print("BEFORE Configuration:")
print("-" * 50)
for servo_id in SERVO_IDS:
    current = read_torque_limit(servo_id)
    if current is not None:
        print(f"  Servo {servo_id}: {current}/1023 ({current*100//1023}%)")
    else:
        print(f"  Servo {servo_id}: NO RESPONSE")

print("\n" + "=" * 50)
input("Press ENTER to configure torque limits (Ctrl+C to cancel)...")
print()

# Configure each servo
for servo_id in SERVO_IDS:
    if servo_id == GRIPPER_ID:
        set_torque_limit(servo_id, GRIPPER_TORQUE_LIMIT)
    else:
        set_torque_limit(servo_id, NORMAL_TORQUE_LIMIT)
    time.sleep(0.1)

print("\n" + "=" * 50)
print("AFTER Configuration:")
print("-" * 50)
for servo_id in SERVO_IDS:
    current = read_torque_limit(servo_id)
    if current is not None:
        indicator = " <-- GRIPPER (Limited!)" if servo_id == GRIPPER_ID else ""
        print(f"  Servo {servo_id}: {current}/1023 ({current*100//1023}%){indicator}")
    else:
        print(f"  Servo {servo_id}: NO RESPONSE")

print("\n" + "=" * 50)
print("Configuration saved to EEPROM (permanent)!")
print("Your gripper is now protected from burning out.")
print("=" * 50)

portHandler.closePort()

