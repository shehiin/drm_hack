#!/usr/bin/env python
"""
Xbox Controller Arm Control
Controls: LStick=base/shoulder, RStick=elbow/wrist, Triggers=wrist_rot, Bumpers=gripper
D-Pad=speed, A=center, B=e-stop, Start=quit
"""

import sys
import os
import time

os.environ['SDL_VIDEODRIVER'] = 'dummy'
import pygame

sys.path.append("..")
from scservo_sdk import *

# CONFIG
DEVICENAME = '/dev/ttyACM0'
BAUDRATE = 1000000

SERVO_CONFIG = {
    'base':        1,
    'shoulder':    2,
    'elbow':       3,
    'wrist_pitch': 4,
    'wrist_rot':   5,
    'gripper':     6,
}

SERVO_LIMITS = {
    1: [500, 3500, 2048],
    2: [500, 3500, 2048],
    3: [500, 3500, 2048],
    4: [500, 3500, 2048],
    5: [500, 3500, 2048],
    6: [1500, 2500, 2048],
}

# Movement
DEFAULT_SPEED = 1000
MAX_SPEED = 2500
MIN_SPEED = 200
SPEED_STEP = 150
MOVING_ACC = 40
DEADZONE = 0.15
UPDATE_RATE = 50  # Reduced from 100 to avoid flooding
STEP_SIZE = 6

# Axis/button mapping
AXIS_LX, AXIS_LY, AXIS_LT = 0, 1, 2
AXIS_RX, AXIS_RY, AXIS_RT = 3, 4, 5
BTN_A, BTN_B, BTN_LB, BTN_RB, BTN_START = 0, 1, 4, 5, 7

# Timing constants
POSITION_SYNC_INTERVAL = 2.0  # Sync actual positions every 2 seconds
SERVO_TIMEOUT_THRESHOLD = 3  # Mark dead after 3 consecutive failures
SERVO_RECOVERY_INTERVAL = 5.0  # Try to recover dead servos every 5 seconds
MIN_POSITION_CHANGE = 2  # Minimum change to send command (reduces noise)


def apply_deadzone(value, deadzone):
    if abs(value) < deadzone:
        return 0.0
    sign = 1 if value > 0 else -1
    return sign * (abs(value) - deadzone) / (1.0 - deadzone)


def normalize_trigger(value):
    return (value + 1.0) / 2.0


class ArmController:
    def __init__(self, port_handler, packet_handler):
        self.port = port_handler
        self.servo = packet_handler
        self.positions = {}  # Will be populated from actual servo positions
        self.target_positions = {}  # What we're trying to reach
        self.last_sent_positions = {}  # Last position we sent to each servo
        self.speed = DEFAULT_SPEED
        self.emergency_stop = False
        self.servo_errors = {sid: 0 for sid in SERVO_LIMITS}  # Error count per servo
        self.dead_servos = set()  # Servos that stopped responding
        self.last_sync_time = 0
        self.last_recovery_time = 0
        self.initialized = False

    def read_servo_position(self, servo_id):
        """Read actual position from servo with error handling"""
        try:
            pos, comm_result, error = self.servo.ReadPos(servo_id)
            if comm_result == COMM_SUCCESS and error == 0:
                self.servo_errors[servo_id] = 0  # Reset error count on success
                if servo_id in self.dead_servos:
                    self.dead_servos.remove(servo_id)
                    print(f"Servo {servo_id} recovered!")
                return pos
            else:
                self._handle_servo_error(servo_id, f"read error: comm={comm_result}, err={error}")
                return None
        except Exception as e:
            self._handle_servo_error(servo_id, str(e))
            return None

    def _handle_servo_error(self, servo_id, error_msg):
        """Track servo errors and mark as dead if too many failures"""
        self.servo_errors[servo_id] += 1
        if self.servo_errors[servo_id] >= SERVO_TIMEOUT_THRESHOLD:
            if servo_id not in self.dead_servos:
                self.dead_servos.add(servo_id)
                print(f"Servo {servo_id} marked as DEAD ({error_msg})")

    def initialize_servos(self):
        """Read all servo positions on startup - CRITICAL for proper operation"""
        print("Initializing servos...")
        print("Reading current positions from all servos...")
        
        for servo_id in SERVO_LIMITS:
            # Try a few times to read each servo
            pos = None
            for attempt in range(3):
                pos = self.read_servo_position(servo_id)
                if pos is not None:
                    break
                time.sleep(0.05)
            
            if pos is not None:
                # Clamp to valid range
                limits = SERVO_LIMITS[servo_id]
                pos = max(limits[0], min(limits[1], pos))
                self.positions[servo_id] = pos
                self.target_positions[servo_id] = pos
                self.last_sent_positions[servo_id] = pos
                print(f"  Servo {servo_id}: position {pos} OK")
            else:
                # Use center as fallback
                center = SERVO_LIMITS[servo_id][2]
                self.positions[servo_id] = center
                self.target_positions[servo_id] = center
                self.last_sent_positions[servo_id] = center
                print(f"  Servo {servo_id}: FAILED to read, using center {center}")
        
        self.initialized = True
        self.last_sync_time = time.time()
        print(f"Initialization complete. Dead servos: {self.dead_servos or 'None'}")
        time.sleep(0.5)  # Give servos time to stabilize

    def sync_positions(self):
        """Periodically read actual positions to stay in sync"""
        if time.time() - self.last_sync_time < POSITION_SYNC_INTERVAL:
            return
        
        self.last_sync_time = time.time()
        
        for servo_id in SERVO_LIMITS:
            if servo_id in self.dead_servos:
                continue
            
            pos = self.read_servo_position(servo_id)
            if pos is not None:
                limits = SERVO_LIMITS[servo_id]
                pos = max(limits[0], min(limits[1], pos))
                # Only update if significantly different (servo might still be moving)
                if abs(pos - self.positions[servo_id]) > 50:
                    self.positions[servo_id] = pos

    def try_recover_dead_servos(self):
        """Attempt to recover servos that stopped responding"""
        if not self.dead_servos:
            return
        
        if time.time() - self.last_recovery_time < SERVO_RECOVERY_INTERVAL:
            return
        
        self.last_recovery_time = time.time()
        
        for servo_id in list(self.dead_servos):
            print(f"Attempting to recover servo {servo_id}...")
            pos = self.read_servo_position(servo_id)
            if pos is not None:
                self.positions[servo_id] = pos
                self.target_positions[servo_id] = pos
                self.last_sent_positions[servo_id] = pos
                # dead_servos removal happens in read_servo_position on success

    def update_servo(self, servo_id, position):
        """Send position command to servo with error handling"""
        if servo_id is None or servo_id in self.dead_servos:
            return False
        
        limits = SERVO_LIMITS.get(servo_id, [0, 4095, 2048])
        position = max(limits[0], min(limits[1], int(position)))
        
        # Only send if position changed significantly
        last_sent = self.last_sent_positions.get(servo_id, 0)
        if abs(position - last_sent) < MIN_POSITION_CHANGE:
            return True  # No need to send, already there
        
        self.target_positions[servo_id] = position
        
        try:
            self.servo.WritePosEx(servo_id, position, self.speed, MOVING_ACC)
            self.positions[servo_id] = position
            self.last_sent_positions[servo_id] = position
            self.servo_errors[servo_id] = 0  # Reset on success
            return True
        except Exception as e:
            self._handle_servo_error(servo_id, str(e))
            return False

    def move_servo(self, servo_id, delta):
        """Move servo by delta amount"""
        if servo_id is None or delta == 0 or servo_id in self.dead_servos:
            return
        
        # Round delta to avoid tiny movements
        delta = int(delta)
        if abs(delta) < 1:
            return
        
        current = self.positions.get(servo_id, SERVO_LIMITS[servo_id][2])
        self.update_servo(servo_id, current + delta)

    def center_all(self):
        """Center all servos (only ones that are alive)"""
        print("Centering all servos...")
        for servo_id in SERVO_LIMITS:
            if servo_id not in self.dead_servos:
                center = SERVO_LIMITS[servo_id][2]
                self.update_servo(servo_id, center)
                time.sleep(0.02)  # Small delay between commands

    def adjust_speed(self, delta):
        self.speed = max(MIN_SPEED, min(MAX_SPEED, self.speed + delta))
        print(f"Speed: {self.speed}")


def print_status(joystick, arm):
    os.system('clear' if os.name != 'nt' else 'cls')
    
    lx = apply_deadzone(joystick.get_axis(AXIS_LX), DEADZONE)
    ly = apply_deadzone(-joystick.get_axis(AXIS_LY), DEADZONE)
    rx = apply_deadzone(joystick.get_axis(AXIS_RX), DEADZONE)
    ry = apply_deadzone(-joystick.get_axis(AXIS_RY), DEADZONE)
    lt = normalize_trigger(joystick.get_axis(AXIS_LT))
    rt = normalize_trigger(joystick.get_axis(AXIS_RT))
    
    print("=" * 55)
    print("XBOX ARM CONTROL")
    print("=" * 55)
    print(f"Speed: {arm.speed}  |  E-Stop: {'ON' if arm.emergency_stop else 'OFF'}")
    if arm.dead_servos:
        print(f"DEAD SERVOS: {sorted(arm.dead_servos)} (will auto-retry)")
    print(f"\nInput: LStick({lx:+.2f},{ly:+.2f}) RStick({rx:+.2f},{ry:+.2f}) Trig({lt:.2f},{rt:.2f})")
    print("\nServos:")
    for name, sid in SERVO_CONFIG.items():
        if sid:
            pos = arm.positions.get(sid, 0)
            limits = SERVO_LIMITS.get(sid, [0, 4095, 2048])
            pct = (pos - limits[0]) / (limits[1] - limits[0]) * 100
            bar = "#" * int(pct / 5) + "-" * (20 - int(pct / 5))
            status = "DEAD" if sid in arm.dead_servos else ""
            print(f"  {name:12} [{bar}] {pos:4d} {status}")
    print("-" * 55)
    print("D-Pad=speed | A=center | B=e-stop | Y=resync | Start=quit")


def main():
    print("Xbox Arm Controller")
    print("-" * 40)
    
    pygame.init()
    pygame.joystick.init()
    
    if pygame.joystick.get_count() == 0:
        print("No controller found!")
        return 1
    
    joystick = pygame.joystick.Joystick(0)
    joystick.init()
    print(f"Controller: {joystick.get_name()}")
    
    portHandler = PortHandler(DEVICENAME)
    packetHandler = sms_sts(portHandler)
    
    if not portHandler.openPort():
        print(f"Failed to open {DEVICENAME}")
        pygame.quit()
        return 1
    
    if not portHandler.setBaudRate(BAUDRATE):
        print("Failed to set baudrate")
        portHandler.closePort()
        pygame.quit()
        return 1
    
    print(f"Connected to {DEVICENAME}")
    
    arm = ArmController(portHandler, packetHandler)
    
    # CRITICAL: Initialize servos by reading their current positions
    arm.initialize_servos()
    
    prev_a, prev_b, prev_y, prev_dpad = False, False, False, (0, 0)
    last_display = 0
    
    BTN_Y = 3  # Y button for manual resync
    
    try:
        while True:
            pygame.event.pump()
            
            if joystick.get_button(BTN_START):
                print("Quitting...")
                break
            
            # A = center
            a = joystick.get_button(BTN_A)
            if a and not prev_a:
                arm.center_all()
            prev_a = a
            
            # B = e-stop toggle
            b = joystick.get_button(BTN_B)
            if b and not prev_b:
                arm.emergency_stop = not arm.emergency_stop
                print("E-STOP" if arm.emergency_stop else "E-Stop released")
            prev_b = b
            
            # Y = manual resync (useful if things get weird)
            y = joystick.get_button(BTN_Y)
            if y and not prev_y:
                print("Manual resync requested...")
                arm.dead_servos.clear()
                arm.servo_errors = {sid: 0 for sid in SERVO_LIMITS}
                arm.initialize_servos()
            prev_y = y
            
            # D-pad = speed
            dpad = joystick.get_hat(0) if joystick.get_numhats() > 0 else (0, 0)
            if dpad[1] == 1 and prev_dpad[1] != 1:
                arm.adjust_speed(SPEED_STEP)
            elif dpad[1] == -1 and prev_dpad[1] != -1:
                arm.adjust_speed(-SPEED_STEP)
            prev_dpad = dpad
            
            # Periodic maintenance
            arm.sync_positions()
            arm.try_recover_dead_servos()
            
            if not arm.emergency_stop:
                cfg = SERVO_CONFIG
                
                # Sticks control incremental movement
                lx = apply_deadzone(joystick.get_axis(AXIS_LX), DEADZONE)
                ly = apply_deadzone(-joystick.get_axis(AXIS_LY), DEADZONE)
                rx = apply_deadzone(joystick.get_axis(AXIS_RX), DEADZONE)
                ry = apply_deadzone(-joystick.get_axis(AXIS_RY), DEADZONE)
                
                # Only send commands if there's actual input
                if lx != 0:
                    arm.move_servo(cfg['base'], lx * STEP_SIZE)
                if ly != 0:
                    arm.move_servo(cfg['shoulder'], ly * STEP_SIZE)
                if rx != 0:
                    arm.move_servo(cfg['elbow'], rx * STEP_SIZE)
                if ry != 0:
                    arm.move_servo(cfg['wrist_pitch'], ry * STEP_SIZE)
                
                # Triggers for wrist rotation
                if cfg['wrist_rot'] and cfg['wrist_rot'] not in arm.dead_servos:
                    lt = normalize_trigger(joystick.get_axis(AXIS_LT))
                    rt = normalize_trigger(joystick.get_axis(AXIS_RT))
                    if rt > 0.1:
                        arm.move_servo(cfg['wrist_rot'], rt * STEP_SIZE)
                    elif lt > 0.1:
                        arm.move_servo(cfg['wrist_rot'], -lt * STEP_SIZE)
                
                # Bumpers for gripper
                if cfg['gripper'] and cfg['gripper'] not in arm.dead_servos:
                    limits = SERVO_LIMITS.get(cfg['gripper'], [0, 4095, 2048])
                    if joystick.get_button(BTN_RB):
                        arm.update_servo(cfg['gripper'], limits[1])
                    elif joystick.get_button(BTN_LB):
                        arm.update_servo(cfg['gripper'], limits[0])
            
            if time.time() - last_display > 0.2:
                print_status(joystick, arm)
                last_display = time.time()
            
            time.sleep(1.0 / UPDATE_RATE)
            
    except KeyboardInterrupt:
        print("Interrupted")
    finally:
        portHandler.closePort()
        pygame.quit()
        print("Done")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
