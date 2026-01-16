import sys
import tty
import termios
sys.path.append("..")
from STservo_sdk import *

# --- CONFIGURATION ---
DEVICE_NAME = '/dev/ttyACM0'  # Setup for your Feetech Board
BAUDRATE    = 1000000
STEP_SIZE   = 100             # How far to move per keypress
SPEED       = 1050            # 70% of 1500

# --- KEYBOARD INPUT HANDLER ---
def get_key():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
        
        # Handle Arrow Keys (Escape Sequences)
        if ch == '\x1b':
            ch = sys.stdin.read(2)
            if ch == '[C': return 'RIGHT'
            if ch == '[D': return 'LEFT'
            return 'ESC'
            
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

# --- SETUP ---
portHandler = PortHandler(DEVICE_NAME)
packetHandler = sts(portHandler)

print(f"Connecting to {DEVICE_NAME}...")
if not (portHandler.openPort() and portHandler.setBaudRate(BAUDRATE)):
    print(f"Failed to open {DEVICE_NAME}. Check permissions or cable!")
    quit()

# --- STATE VARIABLES ---
selected_id = 1       # Default to ID 1
current_pos = 2048    # Placeholder

# Initial Read for the first servo
pos, res, err = packetHandler.ReadPos(selected_id)
if res == COMM_SUCCESS:
    current_pos = pos
    print(f"Connected! ID {selected_id} is at {current_pos}")
else:
    print(f"Warning: ID {selected_id} did not respond.")

print("\n--- MANUAL CONTROL INSTRUCTIONS ---")
print(" [1-6]  : Select Servo ID")
print(" [<-]   : Rotate Counter-Clockwise")
print(" [->]   : Rotate Clockwise")
print(" [q]    : Quit (or Ctrl+C)")
print("-----------------------------------")

# --- MAIN LOOP ---
try:
    while True:
        key = get_key()

        # 1. QUIT (q or Ctrl+C)
        if key == 'q' or key == '\x03':
            print("\nExiting...")
            break

        # 2. SELECT SERVO (1-6)
        elif key in ['1', '2', '3', '4', '5', '6']:
            selected_id = int(key)
            
            # Read actual position so we don't jerk the arm
            pos, res, err = packetHandler.ReadPos(selected_id)
            
            if res == COMM_SUCCESS:
                current_pos = pos
                print(f"\r > Active: ID {selected_id} | Pos: {current_pos}      ", end="")
            else:
                print(f"\r > Active: ID {selected_id} | NO RESPONSE!          ", end="")

        # 3. MOVE RIGHT (Increase Value)
        elif key == 'RIGHT':
            target = current_pos + STEP_SIZE
            if target > 4095: target = 4095
            
            # WritePosEx(ID, Position, Speed, Acceleration)
            packetHandler.WritePosEx(selected_id, target, SPEED, 50)
            current_pos = target
            print(f"\r > ID {selected_id} -> {current_pos}      ", end="")

        # 4. MOVE LEFT (Decrease Value)
        elif key == 'LEFT':
            target = current_pos - STEP_SIZE
            if target < 0: target = 0
            
            packetHandler.WritePosEx(selected_id, target, SPEED, 50)
            current_pos = target
            print(f"\r > ID {selected_id} -> {current_pos}      ", end="")

except KeyboardInterrupt:
    pass
finally:
    portHandler.closePort()
    print("\nDisconnected safely.")
