"""
MPI Robotic Inspection System - Flask Backend
Main application server with API routes
"""

import os
import cv2
import base64
import json
from datetime import datetime
from flask import Flask, render_template, Response, jsonify, request
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import local modules
from camera import CameraHandler, get_camera, reset_camera
from detector import CrackDetector, get_detector
from robot_controller import get_robot, RobotState

app = Flask(__name__)

# Application state
app_state = {
    "selected_object": None,
    "last_inspection": None,
    "inspection_image": None,  # Base64 encoded
    "logs": [],
}


def add_log(message: str, level: str = "info"):
    """Add entry to system log"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = {"timestamp": timestamp, "message": message, "level": level}
    app_state["logs"].append(entry)
    # Keep only last 100 logs
    if len(app_state["logs"]) > 100:
        app_state["logs"] = app_state["logs"][-100:]
    print(f"[{timestamp}] [{level.upper()}] {message}")


# =============================================================================
# PAGE ROUTES
# =============================================================================


@app.route("/")
def index():
    """Serve main GUI"""
    return render_template("index.html")


# =============================================================================
# CAMERA API
# =============================================================================


@app.route("/api/cameras")
def list_cameras():
    """List available camera devices"""
    cameras = CameraHandler.list_available_cameras()
    return jsonify({"cameras": cameras})


@app.route("/api/camera/select", methods=["POST"])
def select_camera():
    """Switch to a different camera"""
    data = request.get_json()
    device_id = data.get("device_id", 0)

    camera = get_camera()
    camera.stop()
    reset_camera()

    camera = get_camera(device_id)
    success = camera.start()

    if success:
        add_log(f"Switched to camera {device_id}")
        return jsonify({"success": True, "device_id": device_id})
    else:
        add_log(f"Failed to connect to camera {device_id}", "error")
        return jsonify({"success": False, "error": "Failed to connect to camera"}), 400


@app.route("/api/camera/status")
def camera_status():
    """Get camera connection status"""
    camera = get_camera()
    return jsonify({"connected": camera.is_connected, "device_id": camera.device_id})


@app.route("/video_feed")
def video_feed():
    """MJPEG video stream"""
    camera = get_camera()
    if not camera.is_connected:
        camera.start()

    if not camera.is_connected:
        # Return a placeholder image
        return Response(
            b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
            + _get_no_camera_image()
            + b"\r\n",
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    return Response(
        camera.generate_mjpeg(), mimetype="multipart/x-mixed-replace; boundary=frame"
    )


def _get_no_camera_image():
    """Generate a 'no camera' placeholder image"""
    import numpy as np

    img = np.zeros((480, 640, 3), dtype=np.uint8)
    img[:] = (40, 40, 40)  # Dark gray

    # Add text
    font = cv2.FONT_HERSHEY_SIMPLEX
    text = "NO CAMERA CONNECTED"
    text_size = cv2.getTextSize(text, font, 0.8, 2)[0]
    text_x = (640 - text_size[0]) // 2
    text_y = (480 + text_size[1]) // 2
    cv2.putText(img, text, (text_x, text_y), font, 0.8, (100, 100, 100), 2)

    _, buffer = cv2.imencode(".jpg", img)
    return buffer.tobytes()


# =============================================================================
# INSPECTION API
# =============================================================================


@app.route("/api/inspect", methods=["POST"])
def run_inspection():
    """Run defect inspection on current camera frame"""
    data = request.get_json() or {}
    target_object = data.get("object") or app_state.get("selected_object")

    add_log(f"Starting inspection for: {target_object or 'any object'}")

    # Get camera frame
    camera = get_camera()
    if not camera.is_connected:
        add_log("Camera not connected", "error")
        return jsonify({"success": False, "error": "Camera not connected"}), 400

    frame = camera.capture_still()
    if frame is None:
        add_log("Failed to capture frame", "error")
        return jsonify({"success": False, "error": "Failed to capture frame"}), 400

    add_log("Frame captured, running AI detection...")

    # Run detection
    try:
        detector = get_detector()
        detections = detector.detect_objects_and_cracks(frame)

        if detections is None:
            add_log("Detection failed - no response from API", "error")
            return jsonify({"success": False, "error": "Detection failed"}), 500

        # Draw detections on image (returns just the annotated image)
        annotated_frame = detector.draw_detections(frame, detections)

        # Build summary from detections
        objects_list = detections.get("objects", [])
        summary = {
            "total": len(objects_list),
            "defects": sum(1 for obj in objects_list if obj.get("has_defect", False)),
            "objects": objects_list,
        }

        # Encode annotated image to base64
        _, buffer = cv2.imencode(".jpg", annotated_frame)
        image_base64 = base64.b64encode(buffer).decode("utf-8")

        # Store results
        app_state["last_inspection"] = {
            "timestamp": datetime.now().isoformat(),
            "target_object": target_object,
            "detections": detections,
            "summary": summary,
        }
        app_state["inspection_image"] = image_base64

        # Log results
        if summary["total"] == 0:
            add_log("No objects detected in frame", "warning")
        else:
            defect_status = "DEFECTS FOUND" if summary["defects"] > 0 else "NO DEFECTS"
            add_log(
                f"Detection complete: {summary['total']} object(s), {defect_status}",
                "error" if summary["defects"] > 0 else "success",
            )

            for obj in summary["objects"]:
                status = "DEFECT" if obj.get("has_defect", False) else "OK"
                add_log(
                    f"  - {obj.get('name', 'unknown').upper()}: {status} ({obj.get('confidence', 'unknown')})"
                )

        return jsonify(
            {
                "success": True,
                "image": image_base64,
                "detections": detections,
                "summary": summary,
            }
        )

    except Exception as e:
        add_log(f"Detection error: {str(e)}", "error")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/inspection/last")
def get_last_inspection():
    """Get results of last inspection"""
    if app_state["last_inspection"] is None:
        return jsonify({"success": False, "error": "No inspection performed yet"}), 404

    return jsonify(
        {
            "success": True,
            "inspection": app_state["last_inspection"],
            "image": app_state["inspection_image"],
        }
    )


# =============================================================================
# ROBOT API
# =============================================================================


@app.route("/api/robot/status")
def robot_status():
    """Get robot status"""
    robot = get_robot()
    return jsonify(robot.get_status())


@app.route("/api/robot/pickup", methods=["POST"])
def robot_pickup():
    """Request robot to pick up an object"""
    data = request.get_json()
    object_name = data.get("object")

    if not object_name:
        return jsonify({"success": False, "error": "No object specified"}), 400

    if object_name.lower() not in ["cube", "gear", "knuckle"]:
        return jsonify({"success": False, "error": "Invalid object type"}), 400

    robot = get_robot()
    success = robot.request_pickup(object_name)

    if success:
        app_state["selected_object"] = object_name.lower()
        add_log(f"Robot pickup requested: {object_name.upper()}")
        return jsonify({"success": True, "object": object_name})
    else:
        add_log(f"Robot busy, cannot pickup {object_name}", "warning")
        return jsonify({"success": False, "error": "Robot is busy"}), 400


@app.route("/api/robot/complete", methods=["POST"])
def robot_complete():
    """Signal inspection complete, return object"""
    data = request.get_json() or {}
    return_object = data.get("return_object", True)

    robot = get_robot()
    success = robot.complete_inspection(return_object)

    if success:
        add_log("Inspection complete, returning object")
        return jsonify({"success": True})
    else:
        return jsonify(
            {"success": False, "error": "Robot not in inspection position"}
        ), 400


@app.route("/api/robot/home", methods=["POST"])
def robot_home():
    """Move robot to home position"""
    robot = get_robot()
    success = robot.home()

    if success:
        add_log("Robot moving to home position")
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": "Robot is busy"}), 400


@app.route("/api/robot/reset", methods=["POST"])
def robot_reset():
    """Reset robot error state"""
    robot = get_robot()
    robot.reset_error()
    add_log("Robot error cleared")
    return jsonify({"success": True})


# =============================================================================
# STATE API
# =============================================================================


@app.route("/api/select", methods=["POST"])
def select_object():
    """Select object type for inspection (without robot movement)"""
    data = request.get_json()
    object_name = data.get("object")

    if object_name and object_name.lower() in ["cube", "gear", "knuckle"]:
        app_state["selected_object"] = object_name.lower()
        add_log(f"Selected object: {object_name.upper()}")
        return jsonify({"success": True, "object": object_name})
    else:
        return jsonify({"success": False, "error": "Invalid object type"}), 400


@app.route("/api/state")
def get_state():
    """Get current application state"""
    robot = get_robot()
    camera = get_camera()

    return jsonify(
        {
            "selected_object": app_state["selected_object"],
            "has_inspection": app_state["last_inspection"] is not None,
            "robot": robot.get_status(),
            "camera_connected": camera.is_connected,
        }
    )


@app.route("/api/logs")
def get_logs():
    """Get system logs"""
    return jsonify({"logs": app_state["logs"]})


@app.route("/api/reset", methods=["POST"])
def reset_state():
    """Reset application state for new inspection"""
    app_state["selected_object"] = None
    app_state["last_inspection"] = None
    app_state["inspection_image"] = None
    add_log("System reset for new inspection")
    return jsonify({"success": True})


# =============================================================================
# STARTUP
# =============================================================================


def initialize():
    """Initialize application"""
    add_log("MPI Robotic Inspection System v1.0 starting...")

    # Try to start camera - default to camera 2 first (common for external USB cameras)
    for device_id in [2, 0, 1, 4]:
        reset_camera()
        camera = get_camera(device_id)
        if camera.start():
            add_log(f"Camera {device_id} connected")
            break
    else:
        add_log("No camera detected - use camera input to connect manually", "warning")

    # Check API key
    if os.getenv("OPENROUTER_API_KEY"):
        add_log("OpenRouter API key configured")
    else:
        add_log("WARNING: OPENROUTER_API_KEY not set in .env", "warning")

    add_log("System ready")


if __name__ == "__main__":
    initialize()
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)
