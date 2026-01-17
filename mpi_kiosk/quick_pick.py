#!/usr/bin/env python3
"""
Quick Pick - Record pick demos
Records from scan position until gripper closes (LB press)
"""

import sys
import os
import time
import json

os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame

sys.path.append("/home/shehin/Desktop/drm_hack/STServo_Python/stservo-env")
from scservo_sdk import *

import cv2

# =============================================================================
# CONFIG
# =============================================================================

DEVICENAME = "/dev/ttyACM0"
BAUDRATE = 1000000
CAMERA_DEVICE = 2

SERVO_LIMITS = {
    1: [500, 3500],
    2: [500, 3500],
    3: [500, 3500],
    4: [500, 3500],
    5: [500, 3500],
    6: [500, 3500],
}

# Positions [base, shoulder, elbow, wrist, wrist_rot, gripper]
SCAN_POS = [2048, 1628, 1988, 2856, 2048, 2048]

# Movement
SPEED = 800
ACC = 40
DEADZONE = 0.15
STEP = 8
RECORD_FPS = 10

# Gripper - load from calibration
GRIPPER_OPEN = 2048
GRIPPER_CLOSE_CUBE = 2048
GRIPPER_CLOSE_OTHER = 2048


def load_calibration():
    global GRIPPER_OPEN, GRIPPER_CLOSE_CUBE, GRIPPER_CLOSE_OTHER
    try:
        with open("gripper_calibration.json", "r") as f:
            cal = json.load(f)
            GRIPPER_OPEN = cal.get("open", 2048)
            GRIPPER_CLOSE_CUBE = cal.get("close_cube", 2048)
            GRIPPER_CLOSE_OTHER = cal.get("close_other", 2048)
            print(
                f"Gripper: open={GRIPPER_OPEN}, cube={GRIPPER_CLOSE_CUBE}, other={GRIPPER_CLOSE_OTHER}"
            )
    except:
        print("No gripper calibration! Run with --calibrate")


def apply_deadzone(val):
    if abs(val) < DEADZONE:
        return 0.0
    sign = 1 if val > 0 else -1
    return sign * (abs(val) - DEADZONE) / (1.0 - DEADZONE)


# =============================================================================
# ARM
# =============================================================================


class Arm:
    def __init__(self, port, servo):
        self.port = port
        self.servo = servo
        self.pos = [2048] * 6

    def read_positions(self):
        for i in range(6):
            try:
                pos, res, err = self.servo.ReadPos(i + 1)
                if res == COMM_SUCCESS:
                    self.pos[i] = pos
            except:
                pass
        return self.pos

    def move(self, servo_id, position, speed=SPEED):
        limits = SERVO_LIMITS.get(servo_id, [500, 3500])
        position = max(limits[0], min(limits[1], int(position)))
        try:
            self.servo.WritePosEx(servo_id, position, speed, ACC)
            self.pos[servo_id - 1] = position
        except:
            pass

    def move_all(self, positions, speed=SPEED):
        for i, pos in enumerate(positions):
            if pos is not None:
                self.move(i + 1, pos, speed)
                time.sleep(0.01)

    def move_delta(self, servo_id, delta):
        if delta == 0:
            return
        current = self.pos[servo_id - 1]
        self.move(servo_id, current + delta)

    def get_positions(self):
        return list(self.pos)


# =============================================================================
# RECORDER
# =============================================================================


class Recorder:
    def __init__(self):
        self.recording = False
        self.session_dir = None
        self.frames_dir = None
        self.trajectory = []
        self.frame_count = 0
        self.start_time = 0
        self.last_record = 0
        self.object_type = None

    def start(self, object_type):
        os.makedirs("datasets", exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self.session_dir = f"datasets/{object_type}_{timestamp}"
        self.frames_dir = f"{self.session_dir}/frames"
        os.makedirs(self.frames_dir, exist_ok=True)

        self.trajectory = []
        self.frame_count = 0
        self.start_time = time.time()
        self.object_type = object_type
        self.recording = True
        print(f"\n>>> RECORDING: {object_type}")

    def stop(self, final_gripper_pos):
        if not self.recording:
            return None
        self.recording = False

        # Save - include final gripper position
        data = {
            "object_type": self.object_type,
            "duration": time.time() - self.start_time,
            "frames": self.frame_count,
            "final_gripper": final_gripper_pos,
            "trajectory": self.trajectory,
        }
        with open(f"{self.session_dir}/trajectory.json", "w") as f:
            json.dump(data, f, indent=2)

        print(f">>> SAVED: {self.session_dir}")
        return self.session_dir

    def record(self, camera, positions):
        if not self.recording:
            return

        now = time.time()
        if now - self.last_record < 1.0 / RECORD_FPS:
            return
        self.last_record = now

        ret, frame = camera.read()
        if not ret:
            return

        cv2.imwrite(f"{self.frames_dir}/frame_{self.frame_count:05d}.jpg", frame)

        self.trajectory.append(
            {
                "t": round(now - self.start_time, 3),
                "frame": self.frame_count,
                "pos": positions,
            }
        )
        self.frame_count += 1


# =============================================================================
# CALIBRATE
# =============================================================================


def calibrate(arm, joystick):
    print("\n" + "=" * 50)
    print("GRIPPER CALIBRATION")
    print("=" * 50)
    print("Left Stick Y = move gripper")
    print("A = save OPEN | B = save CLOSE (cube) | X = save CLOSE (other)")
    print("START = finish")
    print("=" * 50)

    open_val = close_cube = close_other = None
    gripper_pos = arm.pos[5]
    prev_a = prev_b = prev_x = False

    while True:
        pygame.event.pump()

        if joystick.get_button(7):
            break

        ly = apply_deadzone(-joystick.get_axis(1))
        if ly != 0:
            gripper_pos += ly * 15  # Bigger steps
            gripper_pos = max(500, min(3500, gripper_pos))  # Full range
            arm.move(6, int(gripper_pos), 600)
            print(f"Gripper: {int(gripper_pos)}")  # Show value

        a, b, x = joystick.get_button(0), joystick.get_button(1), joystick.get_button(2)
        if a and not prev_a:
            open_val = int(gripper_pos)
            print(f"OPEN = {open_val}")
        if b and not prev_b:
            close_cube = int(gripper_pos)
            print(f"CLOSE (cube) = {close_cube}")
        if x and not prev_x:
            close_other = int(gripper_pos)
            print(f"CLOSE (other) = {close_other}")
        prev_a, prev_b, prev_x = a, b, x

        time.sleep(0.02)

    if open_val and close_cube and close_other:
        with open("gripper_calibration.json", "w") as f:
            json.dump(
                {
                    "open": open_val,
                    "close_cube": close_cube,
                    "close_other": close_other,
                },
                f,
            )
        print("Saved!")
        return True
    print("Incomplete!")
    return False


# =============================================================================
# REPLAY
# =============================================================================


def replay_trajectory(arm, camera, trajectory_file):
    """Replay a recorded trajectory"""
    print(f"\nLoading {trajectory_file}...")
    
    with open(trajectory_file, "r") as f:
        data = json.load(f)
    
    trajectory = data.get("trajectory", [])
    object_type = data.get("object_type", "unknown")
    
    print(f"Object: {object_type}")
    print(f"Frames: {len(trajectory)}")
    print(f"Duration: {data.get('duration', 0):.1f}s")
    print("\nPress any key to start replay (or wait 3s)...")
    
    # Wait for input or timeout
    import select
    i, o, e = select.select([sys.stdin], [], [], 3.0)
    if i:
        sys.stdin.read(1)
    
    print("REPLAYING...")
    start_time = time.time()
    
    for i, frame_data in enumerate(trajectory):
        target_time = frame_data["t"]
        positions = frame_data["pos"]
        
        # Wait until we should execute this frame
        while time.time() - start_time < target_time:
            time.sleep(0.01)
        
        # Move to position
        arm.move_all(positions, SPEED)
        
        print(f"Frame {i}/{len(trajectory)}: t={target_time:.2f}s", end="\r")
    
    print(f"\nReplay complete! Final position: {arm.pos}")


# =============================================================================
# MAIN
# =============================================================================


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--calibrate", action="store_true")
    parser.add_argument("--replay", type=str, help="Replay trajectory file")
    args = parser.parse_args()

    pygame.init()
    pygame.joystick.init()
    if pygame.joystick.get_count() == 0:
        print("No controller!")
        return 1
    joystick = pygame.joystick.Joystick(0)
    joystick.init()

    port = PortHandler(DEVICENAME)
    if not port.openPort() or not port.setBaudRate(BAUDRATE):
        print("Servo port failed!")
        return 1
    servo = sms_sts(port)
    arm = Arm(port, servo)
    arm.read_positions()
    print(f"Servo OK: {arm.pos}")

    if args.calibrate:
        result = calibrate(arm, joystick)
        port.closePort()
        pygame.quit()
        return 0 if result else 1

    if args.replay:
        camera = cv2.VideoCapture(CAMERA_DEVICE)
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        replay_trajectory(arm, camera, args.replay)
        
        camera.release()
        port.closePort()
        pygame.quit()
        return 0

    load_calibration()

    camera = cv2.VideoCapture(CAMERA_DEVICE)
    if not camera.isOpened():
        print("Camera failed!")
        port.closePort()
        return 1
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    # Go to scan
    print("Moving to SCAN...")
    arm.move_all(SCAN_POS, 600)
    time.sleep(2)
    arm.read_positions()

    recorder = Recorder()
    object_types = ["cube", "knuckle", "gear"]
    obj_index = 0
    object_type = object_types[0]

    prev_x = prev_lb = prev_rb = False
    prev_dpad = (0, 0)
    last_display = 0

    print("\n" + "=" * 50)
    print("RECORD PICK DEMOS")
    print("=" * 50)
    print("D-Pad L/R = switch object type")
    print("X = start/stop recording")
    print("L1 = close gripper | R1 = open gripper")
    print("A = go to scan")
    print("START = quit")
    print("=" * 50)
    print("\nPRESS X TO START/STOP RECORDING")
    print("Current object: " + object_type.upper())
    print("=" * 50)

    try:
        while True:
            pygame.event.pump()

            if joystick.get_button(7):
                break

            # D-pad = object type
            dpad = joystick.get_hat(0) if joystick.get_numhats() > 0 else (0, 0)
            if dpad[0] != prev_dpad[0] and dpad[0] != 0:
                obj_index = (obj_index + (1 if dpad[0] > 0 else -1)) % len(object_types)
                object_type = object_types[obj_index]
                print(f"Object: {object_type}")
            prev_dpad = dpad

            # X = start/stop recording
            x = joystick.get_button(2)
            if x and not prev_x:
                if not recorder.recording:
                    recorder.start(object_type)
                else:
                    recorder.stop(arm.pos[5])
            prev_x = x

            # A = scan
            if joystick.get_button(0):
                arm.move_all(SCAN_POS, 600)

            # Teleop - all 6 servos
            lx = apply_deadzone(joystick.get_axis(0))
            ly = apply_deadzone(-joystick.get_axis(1))
            rx = apply_deadzone(joystick.get_axis(3))
            ry = apply_deadzone(-joystick.get_axis(4))
            lt = (joystick.get_axis(2) + 1) / 2
            rt = (joystick.get_axis(5) + 1) / 2

            if lx:
                arm.move_delta(1, lx * STEP)
            if ly:
                arm.move_delta(2, ly * STEP)
            if rx:
                arm.move_delta(3, rx * STEP)
            if ry:
                arm.move_delta(4, ry * STEP)
            if rt > 0.1:
                arm.move_delta(5, rt * STEP)
            elif lt > 0.1:
                arm.move_delta(5, -lt * STEP)
            
            # Gripper (servo 6) via L1/R1 buttons
            if joystick.get_button(5):  # R1 = open
                arm.move_delta(6, STEP)
            if joystick.get_button(4):  # L1 = close
                arm.move_delta(6, -STEP)

            # Record
            recorder.record(camera, arm.get_positions())

            # Display
            if time.time() - last_display > 0.2:
                os.system("clear")
                print(f"Object: {object_type.upper()}")
                if recorder.recording:
                    print(f"*** RECORDING *** Frames: {recorder.frame_count}")
                    print("PRESS X TO STOP AND SAVE")
                else:
                    print("Press X to start recording")
                print(f"Pos: {arm.pos}")
                last_display = time.time()

            time.sleep(0.02)

    except KeyboardInterrupt:
        pass
    finally:
        camera.release()
        port.closePort()
        pygame.quit()

    return 0


if __name__ == "__main__":
    sys.exit(main())
