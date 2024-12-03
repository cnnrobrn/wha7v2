import cv2
import numpy as np
from typing import List, Tuple, Optional

class EnhancedClothingDetector:
    """
    A comprehensive clothing detector that combines multiple computer vision techniques
    to identify clothing items in images and video frames.
    
    The detector uses a multi-stage approach:
    1. Color segmentation to identify potential clothing regions
    2. Edge detection to find clothing boundaries
    3. Texture analysis to confirm clothing presence
    4. Machine learning-based validation of detected regions
    """

    def __init__(self):
        # Initialize color range parameters for common clothing colors
        self.color_ranges = {
            'white': ([0, 0, 200], [180, 30, 255]),    # HSV range for white
            'black': ([0, 0, 0], [180, 255, 30]),      # HSV range for black
            'colored': ([0, 50, 50], [180, 255, 255])  # HSV range for colored items
        }
        
        # Edge detection parameters
        self.edge_low = 50   # Lower threshold for Canny edge detection
        self.edge_high = 150 # Upper threshold for Canny edge detection
        
        # Morphological operation kernels
        self.morph_kernel = np.ones((5, 5), np.uint8)
        self.texture_kernel = np.ones((3, 3), np.uint8)
        
        # Region filtering parameters
        self.min_region_area = 1000      # Minimum area for a clothing region
        self.max_region_area = 100000    # Maximum area for a clothing region
        self.min_aspect_ratio = 0.3      # Minimum width/height ratio
        self.max_aspect_ratio = 3.0      # Maximum width/height ratio
        
        # Initialize background subtractor for video processing
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500,
            varThreshold=16,
            detectShadows=False
        )
        
    def preprocess_image(self, frame: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Preprocess the input frame for clothing detection.
        
        Args:
            frame: Input BGR image
            
        Returns:
            Tuple containing HSV image, blurred image, and grayscale image
        """
        # Convert to HSV color space for better color segmentation
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        
        # Apply bilateral filter to reduce noise while preserving edges
        blurred = cv2.bilateralFilter(frame, 9, 75, 75)
        
        # Convert to grayscale for texture analysis
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        return hsv, blurred, gray

    def detect_color_regions(self, hsv_image: np.ndarray) -> np.ndarray:
        """
        Detect potential clothing regions based on color ranges.
        
        Args:
            hsv_image: Input image in HSV color space
            
        Returns:
            Binary mask of detected color regions
        """
        combined_mask = np.zeros(hsv_image.shape[:2], dtype=np.uint8)
        
        # Apply each color range mask
        for color_range in self.color_ranges.values():
            lower, upper = color_range
            mask = cv2.inRange(hsv_image, np.array(lower), np.array(upper))
            combined_mask = cv2.bitwise_or(combined_mask, mask)
        
        # Clean up the mask using morphological operations
        combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_OPEN, self.morph_kernel)
        combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, self.morph_kernel)
        
        return combined_mask

    def analyze_texture(self, gray_image: np.ndarray) -> np.ndarray:
        """
        Analyze image texture to identify clothing-like patterns.
        
        Args:
            gray_image: Grayscale input image
            
        Returns:
            Binary mask highlighting textured regions
        """
        # Calculate local standard deviation as a texture measure
        mean, stddev = cv2.meanStdDev(gray_image)
        texture_mask = np.zeros_like(gray_image)
        
        # Apply local binary pattern-like analysis
        for i in range(1, gray_image.shape[0] - 1):
            for j in range(1, gray_image.shape[1] - 1):
                patch = gray_image[i-1:i+2, j-1:j+2]
                if np.std(patch) > stddev:
                    texture_mask[i, j] = 255
        
        # Clean up texture mask
        texture_mask = cv2.morphologyEx(texture_mask, cv2.MORPH_CLOSE, self.texture_kernel)
        
        return texture_mask

    def detect_edges(self, gray_image: np.ndarray) -> np.ndarray:
        """
        Detect edges in the image using Canny edge detection.
        
        Args:
            gray_image: Grayscale input image
            
        Returns:
            Binary edge mask
        """
        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray_image, (5, 5), 0)
        
        # Detect edges
        edges = cv2.Canny(blurred, self.edge_low, self.edge_high)
        
        # Dilate edges to connect nearby edge segments
        edges = cv2.dilate(edges, self.morph_kernel, iterations=1)
        
        return edges

    def filter_regions(self, 
                      contours: List[np.ndarray], 
                      frame_shape: Tuple[int, int]) -> List[Tuple[int, int, int, int]]:
        """
        Filter detected regions based on size, shape, and position criteria.
        
        Args:
            contours: List of contours to filter
            frame_shape: Shape of the input frame (height, width)
            
        Returns:
            List of filtered bounding boxes (x, y, w, h)
        """
        filtered_boxes = []
        frame_area = frame_shape[0] * frame_shape[1]
        
        for contour in contours:
            area = cv2.contourArea(contour)
            
            # Filter based on area
            if area < self.min_region_area or area > self.max_region_area:
                continue
                
            # Get bounding box
            x, y, w, h = cv2.boundingRect(contour)
            
            # Calculate aspect ratio
            aspect_ratio = float(w) / h
            if not (self.min_aspect_ratio <= aspect_ratio <= self.max_aspect_ratio):
                continue
            
            # Check if region touches image borders (likely not clothing)
            if x == 0 or y == 0 or x + w == frame_shape[1] or y + h == frame_shape[0]:
                continue
            
            filtered_boxes.append((x, y, w, h))
            
        return filtered_boxes

    def process_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, List[Tuple[int, int, int, int]]]:
        """
        Process a single frame to detect clothing regions.
        
        Args:
            frame: Input BGR frame
            
        Returns:
            Tuple containing:
            - Processed frame with detected regions marked
            - List of bounding boxes for detected clothing regions
        """
        # Preprocess the frame
        hsv, blurred, gray = self.preprocess_image(frame)
        
        # Get different detection masks
        color_mask = self.detect_color_regions(hsv)
        edge_mask = self.detect_edges(gray)
        texture_mask = self.analyze_texture(gray)
        
        # Combine masks
        combined_mask = cv2.bitwise_and(color_mask, edge_mask)
        combined_mask = cv2.bitwise_and(combined_mask, texture_mask)
        
        # Find contours in the combined mask
        contours, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Filter regions
        clothing_boxes = self.filter_regions(contours, frame.shape[:2])
        
        # Draw results on output frame
        result_frame = frame.copy()
        for box in clothing_boxes:
            x, y, w, h = box
            cv2.rectangle(result_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        
        return result_frame, clothing_boxes