#!/usr/bin/env python3
"""
Object Detection with Crack Detection using Gemma 3 via OpenRouter
Detects objects from camera feed and identifies if they have cracks
"""

import cv2
import requests
import base64
import json
import os
import sys
from dotenv import load_dotenv
from pathlib import Path
import time

# Load environment variables
load_dotenv()


class CrackDetector:
    def __init__(self, api_key=None):
        """Initialize the detector with OpenRouter API key"""
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OPENROUTER_API_KEY not found. Set it in .env file or pass it as argument."
            )

        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = "qwen/qwen3-vl-8b-instruct"  # Qwen3 VL 8B with vision

    def encode_image(self, image):
        """Encode image to base64 for API request"""
        # Convert BGR to RGB
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        # Encode to JPEG
        success, buffer = cv2.imencode(".jpg", image_rgb)
        if not success:
            raise ValueError("Failed to encode image")
        # Convert to base64
        return base64.b64encode(buffer).decode("utf-8")

    def detect_objects_and_cracks(self, image):
        """
        Analyze image using Gemma 3 to detect objects and cracks
        Returns detection results with coordinates
        """
        # Encode image
        image_base64 = self.encode_image(image)

        # Get image dimensions
        height, width = image.shape[:2]

        # Prepare prompt for detection
        prompt = f"""You are a precise object detection system. Analyze this image (dimensions: {width}x{height} pixels) and identify ONLY these specific objects:
- Cube (cubic/box-shaped metal object)
- Gear (circular gear with teeth)
- Knuckle (mechanical knuckle joint)

CRITICAL INSTRUCTIONS:
1. Only detect and report objects from the list above
2. For each object, check for defects:
   - CUBE: Check for visible cracks or surface damage
   - GEAR: Check if any TEETH ARE MISSING (look for gaps in the teeth pattern)
   - KNUCKLE: Check for visible cracks or surface damage
3. Provide ACCURATE bounding box coordinates that TIGHTLY fit around the ENTIRE object

DEFECT DETECTION (IMPORTANT):
- For GEARS: Look carefully at the teeth around the circumference. Are any teeth missing or broken off? Set "has_defect" to true if teeth are missing.
- For CUBES and KNUCKLES: Look for cracks, fractures, or surface damage. Set "has_defect" to true if cracks are visible.

BOUNDING BOX ACCURACY IS CRITICAL:
- Look at the object's actual position in the image
- x1, y1 = the EXACT top-left corner pixel where the object starts
- x2, y2 = the EXACT bottom-right corner pixel where the object ends
- The bounding box must FULLY CONTAIN the entire object
- Do NOT leave parts of the object outside the box
- Measure carefully - the object MUST be inside the box

Image coordinate system:
- Top-left of image is (0, 0)
- Bottom-right of image is ({width}, {height})
- X increases left to right (0 to {width})
- Y increases top to bottom (0 to {height})

Example: If a gear occupies the center area from pixels 200,150 to 450,380:
- x1 = 200 (leftmost edge of gear)
- y1 = 150 (topmost edge of gear)  
- x2 = 450 (rightmost edge of gear)
- y2 = 380 (bottommost edge of gear)

Respond with this EXACT JSON format:
{{
  "objects": [
    {{
      "name": "cube|gear|knuckle",
      "has_defect": true/false,
      "defect_type": "missing_teeth|crack|none",
      "confidence": "high|medium|low",
      "bbox": {{
        "x1": number,
        "y1": number,
        "x2": number,
        "y2": number
      }},
      "description": "specific description of defect (e.g., '2 teeth missing on right side' or 'crack on top surface')"
    }}
  ]
}}

VERIFY: x1 < x2 and y1 < y2, all coordinates within [0,{width}] and [0,{height}]
Respond ONLY with valid JSON."""

        # Prepare API request
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 2000,
            "temperature": 0.1,  # Lower temperature for more precise/consistent coordinates
        }

        try:
            # Make API request
            response = requests.post(
                self.api_url, headers=headers, json=payload, timeout=60
            )
            response.raise_for_status()

            # Parse response
            result = response.json()
            content = result["choices"][0]["message"]["content"]

            # Extract JSON from response (handle markdown code blocks)
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            # Parse JSON
            detection_result = json.loads(content)
            return detection_result

        except requests.exceptions.RequestException as e:
            print(f"API request failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"Response: {e.response.text}")
            return None
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON response: {e}")
            print(f"Raw content: {content}")
            return None
        except Exception as e:
            print(f"Unexpected error: {e}")
            return None

    def draw_detections(self, image, detections):
        """Draw bounding boxes and labels on the image"""
        if not detections or "objects" not in detections:
            return image

        output_image = image.copy()

        for obj in detections["objects"]:
            name = obj.get("name", "Unknown")
            has_defect = obj.get(
                "has_defect", obj.get("has_crack", False)
            )  # Support both old and new format
            defect_type = obj.get("defect_type", "none")
            confidence = obj.get("confidence", "unknown")
            bbox = obj.get("bbox", {})
            description = obj.get("description", "")

            # Get bounding box coordinates (now using direct corner coordinates)
            x1 = int(bbox.get("x1", 0))
            y1 = int(bbox.get("y1", 0))
            x2 = int(bbox.get("x2", image.shape[1]))
            y2 = int(bbox.get("y2", image.shape[0]))

            # Add 5% padding to bbox to help with slightly inaccurate predictions
            width_box = x2 - x1
            height_box = y2 - y1
            padding_x = int(width_box * 0.05)
            padding_y = int(height_box * 0.05)

            x1 = x1 - padding_x
            y1 = y1 - padding_y
            x2 = x2 + padding_x
            y2 = y2 + padding_y

            # Ensure coordinates are within image bounds
            x1 = max(0, min(x1, image.shape[1]))
            y1 = max(0, min(y1, image.shape[0]))
            x2 = max(0, min(x2, image.shape[1]))
            y2 = max(0, min(y2, image.shape[0]))

            # Calculate center point for display
            center_x = (x1 + x2) // 2
            center_y = (y1 + y2) // 2

            # Choose color based on defect detection
            color = (
                (0, 0, 255) if has_defect else (0, 255, 0)
            )  # Red for defect, green for OK

            # Draw bounding box
            cv2.rectangle(output_image, (x1, y1), (x2, y2), color, 3)

            # Prepare label based on object type and defect
            if name.lower() == "gear":
                defect_status = "MISSING TEETH" if has_defect else "TEETH OK"
            else:
                defect_status = "WITH CRACK" if has_defect else "NO CRACK"

            label = f"{name.upper()} - {defect_status}"
            coord_label = f"Center: ({center_x}, {center_y})"
            bbox_label = f"BBox: ({x1},{y1})-({x2},{y2})"

            # Draw label background
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.7
            thickness = 2

            (label_w, label_h), _ = cv2.getTextSize(label, font, font_scale, thickness)
            cv2.rectangle(
                output_image,
                (x1, y1 - label_h - 15),
                (x1 + label_w + 10, y1),
                color,
                -1,
            )

            # Draw label text
            cv2.putText(
                output_image,
                label,
                (x1 + 5, y1 - 5),
                font,
                font_scale,
                (255, 255, 255),
                thickness,
            )

            # Draw coordinates below
            cv2.putText(output_image, coord_label, (x1, y2 + 20), font, 0.5, color, 1)
            cv2.putText(output_image, bbox_label, (x1, y2 + 40), font, 0.4, color, 1)

            # Draw center point
            cv2.circle(output_image, (center_x, center_y), 5, (255, 0, 255), -1)

            # Draw corner markers for better visibility
            marker_size = 15
            marker_thickness = 3
            # Top-left corner
            cv2.line(
                output_image, (x1, y1), (x1 + marker_size, y1), color, marker_thickness
            )
            cv2.line(
                output_image, (x1, y1), (x1, y1 + marker_size), color, marker_thickness
            )
            # Top-right corner
            cv2.line(
                output_image, (x2, y1), (x2 - marker_size, y1), color, marker_thickness
            )
            cv2.line(
                output_image, (x2, y1), (x2, y1 + marker_size), color, marker_thickness
            )
            # Bottom-left corner
            cv2.line(
                output_image, (x1, y2), (x1 + marker_size, y2), color, marker_thickness
            )
            cv2.line(
                output_image, (x1, y2), (x1, y2 - marker_size), color, marker_thickness
            )
            # Bottom-right corner
            cv2.line(
                output_image, (x2, y2), (x2 - marker_size, y2), color, marker_thickness
            )
            cv2.line(
                output_image, (x2, y2), (x2, y2 - marker_size), color, marker_thickness
            )

            # Print detection info
            print(f"\n{'=' * 60}")
            print(f"Object: {name.upper()}")
            if name.lower() == "gear":
                print(f"Missing Teeth: {'Yes' if has_defect else 'No'}")
            else:
                print(f"Has Crack: {'Yes' if has_defect else 'No'}")
            print(f"Defect Type: {defect_type}")
            print(f"Confidence: {confidence}")
            print(f"Center Position (x, y): ({center_x}, {center_y})")
            print(f"Bounding Box: ({x1}, {y1}) to ({x2}, {y2})")
            print(f"Width x Height: {x2 - x1} x {y2 - y1} pixels")
            print(f"Description: {description}")
            print(f"{'=' * 60}")

        return output_image


def main():
    Path("./detection").mkdir(parents=True, exist_ok=True)
    """Main function to run the detector"""
    # Check for command line arguments
    mode = "camera"  # default mode
    image_path = None

    if len(sys.argv) > 1:
        if sys.argv[1] in ["--image", "-i"] and len(sys.argv) > 2:
            mode = "image"
            image_path = sys.argv[2]
        elif sys.argv[1] in ["--help", "-h"]:
            print("Usage:")
            print("  Camera mode: python detect_cracks.py")
            print("  Image mode:  python detect_cracks.py --image <path_to_image>")
            print("  Image mode:  python detect_cracks.py -i <path_to_image>")
            return

    # Initialize detector
    try:
        detector = CrackDetector()
        print("Crack Detector initialized successfully!")
        print(f"Using model: {detector.model}")
    except ValueError as e:
        print(f"Error: {e}")
        return

    if mode == "image":
        # Process single image
        if not os.path.exists(image_path):
            print(f"Error: Image file not found: {image_path}")
            return

        print(f"\nProcessing image: {image_path}")
        image = cv2.imread(image_path)

        if image is None:
            print("Error: Failed to load image")
            return

        print("Analyzing image... This may take a moment.")
        detections = detector.detect_objects_and_cracks(image)

        if detections:
            result_image = detector.draw_detections(image, detections)

            # Save result
            output_path = f"detection/detected_{Path(image_path).name}"
            cv2.imwrite(output_path, result_image)
            print(f"\nResult saved to: {output_path}")

            # Display result
            cv2.imshow("Detection Result", result_image)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        else:
            print("No detections or error occurred")

    else:
        # Camera mode
        print("\nStarting camera mode...")
        print("Press 'c' to capture and analyze")
        print("Press 'q' to quit")

        cap = cv2.VideoCapture(2)

        if not cap.isOpened():
            print("Error: Could not open camera")
            return

        # Set camera properties
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        print("\nCamera opened successfully!")

        while True:
            ret, frame = cap.read()

            if not ret:
                print("Error: Failed to capture frame")
                break

            # Display instructions
            display_frame = frame.copy()
            cv2.putText(
                display_frame,
                "Press 'c' to capture and analyze, 'q' to quit",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
            )

            cv2.imshow("Camera Feed", display_frame)

            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                break
            elif key == ord("c"):
                print("\nCapturing and analyzing...")
                detections = detector.detect_objects_and_cracks(frame)

                if detections:
                    result_frame = detector.draw_detections(frame, detections)

                    # Save result
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    output_path = f"detection/detection_{timestamp}.jpg"
                    cv2.imwrite(output_path, result_frame)
                    print(f"\nResult saved to: {output_path}")

                    # Display result
                    cv2.imshow("Detection Result", result_frame)
                    print("\nPress any key to continue...")
                    cv2.waitKey(0)
                else:
                    print("No detections or error occurred")

        cap.release()
        cv2.destroyAllWindows()


# =============================================================================
# FLASK INTEGRATION - Singleton wrapper for GUI
# =============================================================================

_detector_instance = None


def get_detector():
    """Get or create singleton detector instance for Flask app"""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = CrackDetector()
    return _detector_instance


if __name__ == "__main__":
    main()
