import sys
import tty
import termios
import json
import time
import signal
sys.path.append("..")
from STservo_sdk import *

DEVICE_NAME = '/dev/ttyACM0'
BAUDRATE    = 1000000
NUM_SERVOS  = 5

cleanup_done = False

def get_key():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
        if ch == '\x1b':
            ch = sys.stdin.read(2)
            if ch == '[C': return 'RIGHT'
            if ch == '[D': return 'LEFT'
            if ch == '[A': return 'UP'
            if ch == '[B': return 'DOWN'
            return 'ESC'
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

portHandler = PortHandler(DEVICE_NAME)
packetHandler = sts(portHandler)

print(f"Connecting to {DEVICE_NAME}...")
if not (portHandler.openPort() and portHandler.setBaudRate(BAUDRATE)):
    print(f"Failed to open {DEVICE_NAME}!")
    quit()

print("Connected!")

def cleanup(recorder=None):
    global cleanup_done
    if cleanup_done:
        return
    cleanup_done = True
    
    print("\n\nShutting down...")
    
    try:
        lock_all_servos(packetHandler, NUM_SERVOS)
    except:
        pass
    
    if recorder:
        try:
            recorder.save_to_file()
        except:
            print("Could not save positions")
    
    try:
        portHandler.closePort()
        print("Port closed")
    except:
        pass
    
    print("Cleanup complete. Goodbye!\n")

def signal_handler(sig, frame, recorder=None):
    cleanup(recorder)
    sys.exit(0)

def unlock_all_servos(packet_handler, num_servos):
    print("Unlocking all servos...")
    for servo_id in range(1, num_servos + 1):
        try:
            packet_handler.EnableTorque(servo_id, 0)
            time.sleep(0.01)
        except:
            print(f"Failed to unlock servo {servo_id}")
    print("All servos unlocked - you can now move them by hand!")

def lock_all_servos(packet_handler, num_servos):
    print("Locking all servos...")
    for servo_id in range(1, num_servos + 1):
        try:
            packet_handler.EnableTorque(servo_id, 1)
            time.sleep(0.01)
        except:
            pass
    print("All servos locked")

class PositionRecorder:
    def __init__(self, packet_handler, num_servos):
        self.packet_handler = packet_handler
        self.num_servos = num_servos
        self.saved_positions = {}
        self.load_positions()
    
    def read_all_servos(self):
        positions = []
        for servo_id in range(1, self.num_servos + 1):
            pos, res, err = self.packet_handler.ReadPos(servo_id)
            if res == COMM_SUCCESS:
                positions.append(pos)
            else:
                positions.append(None)
        return positions
    
    def display_current_positions(self):
        positions = self.read_all_servos()
        pos_str = " | ".join([f"ID{i+1}:{p if p else '???'}" for i, p in enumerate(positions)])
        return pos_str
    
    def save_current_position(self, position_name):
        print(f"\nRecording position '{position_name}'...")
        positions = self.read_all_servos()
        
        if None in positions:
            print("Failed: Some servos not responding")
            return False
        
        self.saved_positions[position_name] = positions
        print(f"Saved: {positions}")
        return True
    
    def save_to_file(self, filename='robot_positions.json'):
        with open(filename, 'w') as f:
            json.dump(self.saved_positions, f, indent=2)
        print(f"Saved {len(self.saved_positions)} positions to {filename}")
    
    def load_positions(self, filename='robot_positions.json'):
        try:
            with open(filename, 'r') as f:
                self.saved_positions = json.load(f)
            print(f"Loaded {len(self.saved_positions)} existing positions")
        except FileNotFoundError:
            print("No saved positions found (will create new file)")
            self.saved_positions = {}
    
    def list_positions(self):
        if not self.saved_positions:
            print("\nNo positions saved yet")
            return
        
        print("\nSaved Positions:")
        print("-" * 70)
        for name, positions in self.saved_positions.items():
            print(f"  {name:20s} : {positions}")
        print("-" * 70)
    
    def delete_position(self, position_name):
        if position_name in self.saved_positions:
            del self.saved_positions[position_name]
            print(f"Deleted '{position_name}'")
            return True
        else:
            print(f"Position '{position_name}' not found")
            return False

def manual_teaching_mode(recorder):
    signal.signal(signal.SIGINT, lambda s, f: signal_handler(s, f, recorder))
    
    print("\n" + "="*70)
    print("MANUAL TEACHING MODE - Move arm by hand")
    print("="*70)
    print("\nCONTROLS:")
    print("  [SPACE]   : Save current position")
    print("  [r]       : Refresh/show current positions")
    print("  [l]       : List saved positions")
    print("  [d]       : Delete a position")
    print("  [u]       : Toggle lock/unlock all servos")
    print("  [q]       : Quit and save")
    print("  [Ctrl+C]  : Emergency exit")
    print("-" * 70)
    
    unlock_all_servos(packetHandler, NUM_SERVOS)
    servos_locked = False
    
    try:
        while True:
            key = get_key()
            
            if key == 'q':
                print("\n")
                confirm = input("Save and quit? (y/n): ").strip().lower()
                if confirm == 'y':
                    cleanup(recorder)
                    break
                else:
                    print("Cancelled. Press any key to continue...")
                    get_key()
                    continue
            
            elif key == 'u':
                if servos_locked:
                    unlock_all_servos(packetHandler, NUM_SERVOS)
                    servos_locked = False
                else:
                    lock_all_servos(packetHandler, NUM_SERVOS)
                    servos_locked = True
            
            elif key == 'r':
                pos_str = recorder.display_current_positions()
                print(f"\rCurrent: {pos_str}")
            
            elif key == ' ':
                print("\n")
                pos_str = recorder.display_current_positions()
                print(f"Current positions: {pos_str}")
                name = input("Enter position name (or blank to cancel): ").strip()
                if name:
                    recorder.save_current_position(name)
                print("Press any key to continue...")
                get_key()
            
            elif key == 'l':
                recorder.list_positions()
                print("\nPress any key to continue...")
                get_key()
            
            elif key == 'd':
                print("\n")
                recorder.list_positions()
                name = input("\nEnter position name to delete (or blank to cancel): ").strip()
                if name:
                    recorder.delete_position(name)
                    recorder.save_to_file()
                print("Press any key to continue...")
                get_key()
    
    except KeyboardInterrupt:
        cleanup(recorder)
    except Exception as e:
        print(f"\nError: {e}")
        cleanup(recorder)

def keyboard_teaching_mode(recorder):
    signal.signal(signal.SIGINT, lambda s, f: signal_handler(s, f, recorder))
    
    selected_id = 1
    current_pos = 2048
    step_size = 100
    speed = 1050
    
    lock_all_servos(packetHandler, NUM_SERVOS)
    
    pos, res, err = packetHandler.ReadPos(selected_id)
    if res == COMM_SUCCESS:
        current_pos = pos
    
    print("\n" + "="*70)
    print("KEYBOARD TEACHING MODE")
    print("="*70)
    print("\nCONTROLS:")
    print("  [1-5/6]   : Select Servo ID")
    print("  [<- ->]   : Rotate selected servo")
    print("  [+ -]     : Increase/Decrease step size")
    print("  [SPACE]   : Save current position")
    print("  [l]       : List saved positions")
    print("  [d]       : Delete a position")
    print("  [q]       : Quit and save")
    print("  [Ctrl+C]  : Emergency exit")
    print("-" * 70)
    print(f"Active: ID {selected_id} | Pos: {current_pos} | Step: {step_size}\n")
    
    try:
        while True:
            key = get_key()
            
            if key == 'q':
                print("\n")
                confirm = input("Save and quit? (y/n): ").strip().lower()
                if confirm == 'y':
                    cleanup(recorder)
                    break
                continue
            
            elif key in ['1', '2', '3', '4', '5', '6']:
                selected_id = int(key)
                pos, res, err = packetHandler.ReadPos(selected_id)
                if res == COMM_SUCCESS:
                    current_pos = pos
                    print(f"\rActive: ID {selected_id} | Pos: {current_pos} | Step: {step_size}     ", end="")
            
            elif key == 'RIGHT':
                target = min(current_pos + step_size, 4095)
                packetHandler.WritePosEx(selected_id, target, speed, 50)
                current_pos = target
                print(f"\rID {selected_id} | Pos: {current_pos} | Step: {step_size}     ", end="")
            
            elif key == 'LEFT':
                target = max(current_pos - step_size, 0)
                packetHandler.WritePosEx(selected_id, target, speed, 50)
                current_pos = target
                print(f"\rID {selected_id} | Pos: {current_pos} | Step: {step_size}     ", end="")
            
            elif key == '+' or key == '=':
                step_size = min(step_size + 50, 500)
                print(f"\rID {selected_id} | Pos: {current_pos} | Step: {step_size}     ", end="")
            
            elif key == '-' or key == '_':
                step_size = max(step_size - 50, 10)
                print(f"\rID {selected_id} | Pos: {current_pos} | Step: {step_size}     ", end="")
            
            elif key == ' ':
                print("\n")
                name = input("Enter position name: ").strip()
                if name:
                    recorder.save_current_position(name)
                print("Press any key to continue...")
                get_key()
                print(f"\rActive: ID {selected_id} | Pos: {current_pos} | Step: {step_size}     ", end="")
            
            elif key == 'l':
                recorder.list_positions()
                print("\nPress any key to continue...")
                get_key()
                print(f"\rActive: ID {selected_id} | Pos: {current_pos} | Step: {step_size}     ", end="")
            
            elif key == 'd':
                print("\n")
                recorder.list_positions()
                name = input("\nEnter position name to delete: ").strip()
                if name:
                    recorder.delete_position(name)
                    recorder.save_to_file()
                print("Press any key to continue...")
                get_key()
                print(f"\rActive: ID {selected_id} | Pos: {current_pos} | Step: {step_size}     ", end="")
    
    except KeyboardInterrupt:
        cleanup(recorder)
    except Exception as e:
        print(f"\nError: {e}")
        cleanup(recorder)

def teaching_mode():
    recorder = PositionRecorder(packetHandler, NUM_SERVOS)
    
    print("\n" + "="*70)
    print("ROBOT TEACHING MODE")
    print("="*70)
    print("\nChoose Teaching Method:")
    print("  [1] MANUAL MODE  - Unlock servos, move by hand")
    print("  [2] CONTROL MODE - Use keyboard to control servos")
    print()
    
    mode = input("Select mode (1 or 2): ").strip()
    
    if mode == '1':
        manual_teaching_mode(recorder)
    elif mode == '2':
        keyboard_teaching_mode(recorder)
    else:
        print("Invalid choice!")
        cleanup(recorder)

if __name__ == "__main__":
    try:
        teaching_mode()
    except KeyboardInterrupt:
        cleanup()
    except Exception as e:
        print(f"\nFatal error: {e}")
        cleanup()
    finally:
        sys.exit(0)
