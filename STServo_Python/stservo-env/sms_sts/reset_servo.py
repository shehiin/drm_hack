#!/usr/bin/env python
"""
SERVO FACTORY RESET - Restores all settings to defaults
"""
import sys
import time
sys.path.append("..")
from STservo_sdk import *

# --- CONFIG ---
DEVICE_NAME = '/dev/ttyACM0'
BAUDRATE = 1000000

# Which servo to reset? (Change this!)
SERVO_ID = 6

# --- MEMORY ADDRESSES ---
MIN_ANGLE_LIMIT = 9      # 2 bytes
MAX_ANGLE_LIMIT = 11     # 2 bytes
MAX_TORQUE = 16          # 2 bytes (some servos)
TORQUE_LIMIT = 34        # 2 bytes (some servos)
TORQUE_ENABLE = 40       # 1 byte
MODE = 33                # 1 byte
LOCK = 55                # 1 byte

# --- FACTORY DEFAULTS ---
DEFAULT_MIN_ANGLE = 0
DEFAULT_MAX_ANGLE = 4095
DEFAULT_MAX_TORQUE = 1023  # 100%
DEFAULT_MODE = 0           # Position mode

# --- SETUP ---
print("=" * 50)
print("       SERVO FACTORY RESET")
print("=" * 50)
print(f"Target: Servo ID {SERVO_ID}")
print(f"Port: {DEVICE_NAME}")
print("=" * 50)

portHandler = PortHandler(DEVICE_NAME)
packetHandler = sts(portHandler)

if not (portHandler.openPort() and portHandler.setBaudRate(BAUDRATE)):
    print("[ERROR] Failed to open port!")
    quit()

print("[OK] Port opened\n")

# --- CHECK IF SERVO RESPONDS ---
print("Step 1: Checking servo connection...")
pos, comm, err = packetHandler.ReadPos(SERVO_ID)
if comm != COMM_SUCCESS:
    print(f"[WARNING] Servo {SERVO_ID} not responding!")
    print("Trying anyway...\n")
else:
    print(f"[OK] Servo {SERVO_ID} found at position {pos}\n")

# --- UNLOCK EEPROM ---
print("Step 2: Unlocking EEPROM...")
packetHandler.unLockEprom(SERVO_ID)
time.sleep(0.1)
print("[OK] EEPROM unlocked\n")

# --- RESET TORQUE ENABLE (turn off motor) ---
print("Step 3: Disabling torque...")
packetHandler.write1ByteTxRx(SERVO_ID, TORQUE_ENABLE, 0)
time.sleep(0.1)
print("[OK] Torque disabled\n")

# --- RESET MODE ---
print("Step 4: Setting position mode...")
packetHandler.write1ByteTxRx(SERVO_ID, MODE, DEFAULT_MODE)
time.sleep(0.1)
print("[OK] Mode set to position control\n")

# --- RESET ANGLE LIMITS ---
print("Step 5: Resetting angle limits...")
packetHandler.write2ByteTxRx(SERVO_ID, MIN_ANGLE_LIMIT, DEFAULT_MIN_ANGLE)
time.sleep(0.05)
packetHandler.write2ByteTxRx(SERVO_ID, MAX_ANGLE_LIMIT, DEFAULT_MAX_ANGLE)
time.sleep(0.05)
print(f"[OK] Angle limits: {DEFAULT_MIN_ANGLE} - {DEFAULT_MAX_ANGLE}\n")

# --- RESET TORQUE LIMIT ---
print("Step 6: Resetting torque limit to 100%...")
packetHandler.write2ByteTxRx(SERVO_ID, MAX_TORQUE, DEFAULT_MAX_TORQUE)
time.sleep(0.05)
packetHandler.write2ByteTxRx(SERVO_ID, TORQUE_LIMIT, DEFAULT_MAX_TORQUE)
time.sleep(0.05)
print(f"[OK] Torque limit: {DEFAULT_MAX_TORQUE}/1023 (100%)\n")

# --- RE-ENABLE TORQUE ---
print("Step 7: Re-enabling torque...")
packetHandler.write1ByteTxRx(SERVO_ID, TORQUE_ENABLE, 1)
time.sleep(0.1)
print("[OK] Torque enabled\n")

# --- LOCK EEPROM ---
print("Step 8: Locking EEPROM...")
packetHandler.LockEprom(SERVO_ID)
time.sleep(0.1)
print("[OK] EEPROM locked\n")

# --- VERIFY ---
print("Step 9: Verifying...")
pos, comm, err = packetHandler.ReadPos(SERVO_ID)
if comm == COMM_SUCCESS:
    print(f"[OK] Servo {SERVO_ID} responding! Position: {pos}")
else:
    print(f"[FAIL] Servo {SERVO_ID} still not responding")

print("\n" + "=" * 50)
print("       RESET COMPLETE")
print("=" * 50)
print(f"Servo {SERVO_ID} restored to factory defaults:")
print(f"  - Angle range: 0 - 4095")
print(f"  - Torque: 100%")
print(f"  - Mode: Position control")
print("=" * 50)

# --- TEST MOVE ---
print("\nTest move? (y/n): ", end="")
try:
    if input().lower() == 'y':
        print("Moving to center (2048)...")
        packetHandler.WritePosEx(SERVO_ID, 2048, 500, 50)
        time.sleep(2)
        pos, _, _ = packetHandler.ReadPos(SERVO_ID)
        print(f"Position now: {pos}")
except:
    pass

portHandler.closePort()
print("\nDone!")


