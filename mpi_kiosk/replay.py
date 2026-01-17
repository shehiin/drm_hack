#!/usr/bin/env python3
"""
Replay pick demo then move to inspect position
Usage: python3 replay.py [dataset_folder]
"""

import sys
import os
import time
import json

sys.path.append("/home/shehin/Desktop/drm_hack/STServo_Python/stservo-env")
from scservo_sdk import *

DEVICENAME = "/dev/ttyACM0"
BAUDRATE = 1000000
SPEED = 600
ACC = 40

# Inspect position (gripper stays same as pick)
# [base, shoulder, elbow, wrist, wrist_rot, gripper]
INSPECT_POS = [1860, 2207, 2048, 2048, 2048, None]  # None = keep gripper


def main():
    # Find dataset
    if len(sys.argv) >= 2:
        session = sys.argv[1]
    else:
        datasets_dir = "datasets"
        if not os.path.exists(datasets_dir):
            print("No datasets folder!")
            return 1
        sessions = [
            s
            for s in sorted(os.listdir(datasets_dir))
            if os.path.exists(os.path.join(datasets_dir, s, "trajectory.json"))
        ]
        if not sessions:
            print("No valid datasets!")
            return 1
        session = os.path.join(datasets_dir, sessions[-1])
        print(f"Using: {session}")

    # Load trajectory
    traj_file = os.path.join(session, "trajectory.json")
    with open(traj_file, "r") as f:
        data = json.load(f)

    trajectory = data["trajectory"]
    final_gripper = data.get("final_gripper", 2048)
    print(f"Loaded {len(trajectory)} frames, gripper closes to {final_gripper}")

    # Init servo
    port = PortHandler(DEVICENAME)
    if not port.openPort() or not port.setBaudRate(BAUDRATE):
        print("Servo failed!")
        return 1
    servo = sms_sts(port)
    print("Servo OK")

    # Go to start
    start_pos = trajectory[0]["pos"]
    print(f"Moving to start: {start_pos}")
    for i, pos in enumerate(start_pos):
        servo.WritePosEx(i + 1, pos, SPEED, ACC)
        time.sleep(0.01)
    time.sleep(2)

    input("Press ENTER to replay...")

    # Replay pick sequence
    print("\n=== REPLAYING PICK ===")
    start_time = time.time()

    for i, point in enumerate(trajectory):
        while time.time() - start_time < point["t"]:
            time.sleep(0.01)

        pos = point["pos"]
        for j, p in enumerate(pos):
            servo.WritePosEx(j + 1, p, SPEED * 2, ACC)

        if i % 20 == 0:
            print(f"  Frame {i}/{len(trajectory)}")

    # Close gripper
    print(f"Closing gripper to {final_gripper}")
    servo.WritePosEx(6, final_gripper, 600, ACC)
    time.sleep(0.5)

    # Move to inspect (keep gripper closed)
    print("\n=== MOVING TO INSPECT ===")
    print(f"Inspect pos: {INSPECT_POS}")
    for i, pos in enumerate(INSPECT_POS):
        if pos is not None:  # Skip gripper (None)
            servo.WritePosEx(i + 1, pos, SPEED, ACC)
            time.sleep(0.01)

    print("\n=== DONE ===")
    time.sleep(2)

    port.closePort()
    return 0


if __name__ == "__main__":
    sys.exit(main())
