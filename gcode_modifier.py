import math
import sys
from collections import defaultdict
import copy # Needed for deep copies

# --- Constants ---
DEFAULT_Z_UP = 5.0  # Default height for travel moves
DEFAULT_Z_DOWN = 0.0 # Default height for drawing moves
DEFAULT_FEED_RATE_MOVE = 3000 # Example feed rate for G0
DEFAULT_FEED_RATE_DRAW = 1000 # Example feed rate for G1
LINE_SPACING = 0.5 # Default spacing between generated lines for Vertical/Horizontal strategies (in mm)
def distance(p1, p2):
    """Calculate Euclidean distance between two points (x, y)."""
    return math.sqrt((p1['x'] - p2['x'])**2 + (p1['y'] - p2['y'])**2)

def extract_segments(parsed_data):
    """
    Extracts drawing segments (G1 moves with Z <= 0) from parsed G-code data.

    Args:
        parsed_data (list): The list of dictionaries from parse_gcode.

    Returns:
        dict: A dictionary where keys are colors and values are lists of segments.
              Each segment is a dict {'start': {'x':_, 'y':_}, 'end': {'x':_, 'y':_}, 'color': _}.
    """
    segments_by_color = defaultdict(list)
    current_pos = {'x': 0.0, 'y': 0.0, 'z': 0.0}
    is_pen_down = False

    for item in parsed_data:
        if item['type'] != 'move':
            continue # Skip non-move commands for segment extraction

        command = item['command']
        target_pos = {'x': item['x'], 'y': item['y'], 'z': item['z']}
        color = item['color']

        # Update pen state based on Z
        new_pen_down = (target_pos['z'] is not None and target_pos['z'] <= DEFAULT_Z_DOWN + 1e-6) # Tolerance for float comparison

        # If it's a drawing move (G1 and pen becomes/stays down)
        if command == 'G1' and new_pen_down:
            # Check if position actually changed
            if target_pos['x'] != current_pos['x'] or target_pos['y'] != current_pos['y']:
                 segment = {
                     'start': {'x': current_pos['x'], 'y': current_pos['y']},
                     'end': {'x': target_pos['x'], 'y': target_pos['y']},
                     'color': color
                 }
                 segments_by_color[color].append(segment)

        # Update current position for the next iteration
        current_pos = target_pos
        is_pen_down = new_pen_down # Update pen state after processing move

    return segments_by_color


def find_nearest_segment(current_point, segments_set):
    """Finds the segment in the set closest to the current point."""
    nearest_segment = None
    min_dist_sq = float('inf')

    for segment in segments_set:
        # Check distance to start point of the segment
        dist_sq = (segment['start']['x'] - current_point['x'])**2 + (segment['start']['y'] - current_point['y'])**2
        if dist_sq < min_dist_sq:
            min_dist_sq = dist_sq
            nearest_segment = segment

    return nearest_segment, math.sqrt(min_dist_sq) if nearest_segment else float('inf')


# --- Optimization Strategies ---

def optimize_shortest_path(segments_by_color):
    """
    Optimizes the path using a nearest-neighbor approach across all colors dynamically.

    Args:
        segments_by_color (dict): Segments grouped by color.

    Returns:
        list: An ordered list of segments representing the optimized path.
    """
    print("Applying Shortest Path optimization (Nearest Neighbor)...")
    optimized_path = []
    current_point = {'x': 0.0, 'y': 0.0} # Assume starting at origin

    # Create mutable sets of segments for each color
    remaining_segments = {color: set(tuple(sorted(seg.items())) for seg in segments)
                          for color, segments in segments_by_color.items() if segments}
    # Convert tuples back to dicts when needed
    def tuple_to_dict(seg_tuple):
        return dict(seg_tuple)

    total_segments = sum(len(s) for s in remaining_segments.values())
    processed_count = 0

    while remaining_segments:
        nearest_overall_segment = None
        nearest_color = None
        min_overall_dist = float('inf')

        # Find the nearest start point among all remaining segments of all colors
        for color, segments_set in remaining_segments.items():
            if not segments_set:
                continue
            
            # Find the nearest segment *within this color* from the *current global position*
            nearest_in_color, dist_in_color = find_nearest_segment(current_point, (tuple_to_dict(s) for s in segments_set))

            if dist_in_color < min_overall_dist:
                min_overall_dist = dist_in_color
                nearest_overall_segment = nearest_in_color # This is a dict
                nearest_color = color

        if nearest_overall_segment is None:
            break # No more segments left

        # --- Process the chosen color block using nearest neighbor ---
        print(f"  Switching to color {nearest_color}. Nearest segment starts at ({nearest_overall_segment['start']['x']:.2f}, {nearest_overall_segment['start']['y']:.2f})")
        
        # Move to the start of the nearest segment found
        current_point = nearest_overall_segment['start']
        current_color_set = remaining_segments[nearest_color]
        
        # Start processing this color block from the nearest segment
        current_segment_in_color = nearest_overall_segment # Dict
        
        while current_segment_in_color:
            # Add the current segment to the final path
            optimized_path.append(current_segment_in_color)
            processed_count += 1
            
            # Remove it from the remaining set (convert back to tuple for set removal)
            current_segment_tuple = tuple(sorted(current_segment_in_color.items()))
            current_color_set.remove(current_segment_tuple)

            # Update current position to the end of the segment just added
            current_point = current_segment_in_color['end']

            # Find the nearest *remaining* segment *within the same color*
            if not current_color_set:
                 current_segment_in_color = None # No more segments of this color
            else:
                 # Find the next segment starting closest to the *end* of the last one
                 next_segment_in_color, _ = find_nearest_segment(current_point, (tuple_to_dict(s) for s in current_color_set))
                 current_segment_in_color = next_segment_in_color # This is a dict

        # If the set for this color is now empty, remove the color key
        if not current_color_set:
            print(f"  Finished color {nearest_color}.")
            del remaining_segments[nearest_color]

    print(f"Shortest Path optimization complete. Processed {processed_count}/{total_segments} segments.")
    if processed_count != total_segments:
         print(f"Warning: Mismatch in processed segments! Expected {total_segments}, got {processed_count}")

# ... (optimize_shortest_path remains the same) ...


def get_color_bounds(segments):
    """Calculates the bounding box for a list of segments."""
    if not segments:
        return None
    min_x, min_y = float('inf'), float('inf')
    max_x, max_y = float('-inf'), float('-inf')
    for seg in segments:
        min_x = min(min_x, seg['start']['x'], seg['end']['x'])
        max_x = max(max_x, seg['start']['x'], seg['end']['x'])
        min_y = min(min_y, seg['start']['y'], seg['end']['y'])
        max_y = max(max_y, seg['start']['y'], seg['end']['y'])
    return {'min_x': min_x, 'min_y': min_y, 'max_x': max_x, 'max_y': max_y}


def optimize_vertical(segments_by_color):
    """
    Generates vertical line segments covering the bounding box of each color,
    sorted left-to-right.

    Args:
        segments_by_color (dict): Segments grouped by color.

    Returns:
        list: An ordered list of generated vertical segments.
    """
    print("Applying Vertical Lines optimization (Bounding Box Scan)...")
    generated_segments = []

    for color, original_segments in segments_by_color.items():
        bounds = get_color_bounds(original_segments)
        if not bounds:
            continue
        print(f"  Processing color {color} bounds: ({bounds['min_x']:.2f},{bounds['min_y']:.2f}) to ({bounds['max_x']:.2f},{bounds['max_y']:.2f})")

        x = bounds['min_x']
        while x <= bounds['max_x']:
            # Create vertical segment for this x
            segment = {
                'start': {'x': x, 'y': bounds['min_y']},
                'end': {'x': x, 'y': bounds['max_y']},
                'color': color
            }
            generated_segments.append(segment)
            x += LINE_SPACING # Move to the next vertical line

    # Sort primarily by start X (left-to-right), then by start Y (top-to-bottom, though less relevant for pure vertical)
    generated_segments.sort(key=lambda seg: (seg['start']['x'], seg['start']['y']))

    print(f"Vertical Lines optimization generated {len(generated_segments)} segments.")
    # Note: This is a simplified approach using bounding boxes. It doesn't respect the actual shapes
    # defined by the original segments within the bounds.
    return generated_segments


def optimize_horizontal(segments_by_color):
    """
    Generates horizontal line segments covering the bounding box of each color,
    sorted top-to-bottom.

    Args:
        segments_by_color (dict): Segments grouped by color.

    Returns:
        list: An ordered list of generated horizontal segments.
    """
    print("Applying Horizontal Lines optimization (Bounding Box Scan)...")
    generated_segments = []

    for color, original_segments in segments_by_color.items():
        bounds = get_color_bounds(original_segments)
        if not bounds:
            continue
        print(f"  Processing color {color} bounds: ({bounds['min_x']:.2f},{bounds['min_y']:.2f}) to ({bounds['max_x']:.2f},{bounds['max_y']:.2f})")

        y = bounds['min_y'] # Start from the bottom Y
        while y <= bounds['max_y']:
            # Create horizontal segment for this y
            segment = {
                'start': {'x': bounds['min_x'], 'y': y},
                'end': {'x': bounds['max_x'], 'y': y},
                'color': color
            }
            generated_segments.append(segment)
            y += LINE_SPACING # Move to the next horizontal line

    # Sort primarily by start Y (top-to-bottom), then by start X (left-to-right)
    # Note: Sorting by Y descending might be more intuitive for "top-to-bottom"
    # generated_segments.sort(key=lambda seg: (-seg['start']['y'], seg['start']['x']))
    # Let's stick to ascending Y for now (bottom-to-top) as it matches vertical's ascending X
    generated_segments.sort(key=lambda seg: (seg['start']['y'], seg['start']['x']))


    print(f"Horizontal Lines optimization generated {len(generated_segments)} segments.")
    # Note: This is a simplified approach using bounding boxes.
    return generated_segments


# --- G-code Generation ---

def generate_gcode(optimized_segments):
    """
    Generates a G-code string from an ordered list of segments.

    Args:
        optimized_segments (list): The ordered list of segment dictionaries.

    Returns:
        str: The generated G-code string.
    """
    gcode_lines = [
        "; G-code generated by GCodeVisualizerApp Modifier",
        "G90 ; Use absolute coordinates",
        "G21 ; Set units to millimeters",
        f"G0 Z{DEFAULT_Z_UP:.3f} F{DEFAULT_FEED_RATE_MOVE:.0f} ; Ensure tool is up initially",
        "G0 X0 Y0 ; Move to origin"
    ]
    current_pos = {'x': 0.0, 'y': 0.0, 'z': DEFAULT_Z_UP}
    current_color = None

    for i, segment in enumerate(optimized_segments):
        segment_color = segment['color']
        start_point = segment['start']
        end_point = segment['end']

        # 1. Color Change (if needed)
        if segment_color != current_color:
            # Raise tool before color change
            if current_pos['z'] <= DEFAULT_Z_DOWN + 1e-6:
                 gcode_lines.append(f"G0 Z{DEFAULT_Z_UP:.3f} ; Raise tool for color change")
                 current_pos['z'] = DEFAULT_Z_UP
            gcode_lines.append(f"{segment_color} ; Change color")
            current_color = segment_color

        # 2. Move to Start of Segment (if not already there)
        # Check if we are close enough to the start point
        dist_to_start = math.sqrt((current_pos['x'] - start_point['x'])**2 + (current_pos['y'] - start_point['y'])**2)

        if dist_to_start > 1e-3: # Tolerance for floating point comparison
            # Ensure tool is up before travel move
            if current_pos['z'] <= DEFAULT_Z_DOWN + 1e-6:
                 gcode_lines.append(f"G0 Z{DEFAULT_Z_UP:.3f} ; Raise tool for travel")
                 current_pos['z'] = DEFAULT_Z_UP
            # Travel move (G0)
            gcode_lines.append(f"G0 X{start_point['x']:.3f} Y{start_point['y']:.3f} ; Travel to segment start")
            current_pos['x'] = start_point['x']
            current_pos['y'] = start_point['y']

        # 3. Lower Tool (if needed)
        if current_pos['z'] > DEFAULT_Z_DOWN + 1e-6:
            gcode_lines.append(f"G1 Z{DEFAULT_Z_DOWN:.3f} F{DEFAULT_FEED_RATE_DRAW:.0f} ; Lower tool") # Use drawing feed rate for Z down
            current_pos['z'] = DEFAULT_Z_DOWN

        # 4. Draw Segment (G1)
        gcode_lines.append(f"G1 X{end_point['x']:.3f} Y{end_point['y']:.3f} F{DEFAULT_FEED_RATE_DRAW:.0f} ; Draw segment")
        current_pos['x'] = end_point['x']
        current_pos['y'] = end_point['y']

    # Add final lift
    gcode_lines.append(f"G0 Z{DEFAULT_Z_UP:.3f} ; Final lift")
    gcode_lines.append("G0 X0 Y0 ; Return to origin")
    gcode_lines.append("M2 ; End of program")

    return "\n".join(gcode_lines)


# --- Main Modification Function ---

def modify_gcode(parsed_data, strategy):
    """
    Parses, optimizes, and generates modified G-code based on the selected strategy.

    Args:
        parsed_data (list): The list of dictionaries from parse_gcode.
        strategy (str): The selected optimization strategy ("Shortest Path", "Vertical", "Horizontal").

    Returns:
        str: The modified G-code string, or an error message string.
    """
    print(f"Starting modification process with strategy: {strategy}")
    if not parsed_data:
        return "; Error: No parsed G-code data provided."

    try:
        # 1. Extract relevant segments for optimization
        segments_by_color = extract_segments(parsed_data)
        if not any(segments_by_color.values()):
             return "; Info: No drawing segments (G1 with Z<=0) found in the G-code."
        print(f"Extracted segments for {len(segments_by_color)} colors.")

        # 2. Apply selected optimization strategy
        optimized_segments = []
        if strategy == "Shortest Path":
            optimized_segments = optimize_shortest_path(segments_by_color)
        elif strategy == "Vertical":
            optimized_segments = optimize_vertical(segments_by_color)
        elif strategy == "Horizontal":
            optimized_segments = optimize_horizontal(segments_by_color)
        else:
            return f"; Error: Unknown optimization strategy '{strategy}'."

        if not optimized_segments:
             return "; Error: Optimization failed or produced no segments."
        print(f"Optimization resulted in {len(optimized_segments)} segments.")

        # 3. Generate G-code from the optimized path
        modified_gcode = generate_gcode(optimized_segments)
        print("G-code generation complete.")
        return modified_gcode

    except Exception as e:
        print(f"Error during G-code modification: {e}", file=sys.stderr)
        # Optionally include traceback for debugging
        # import traceback
        # traceback.print_exc()
        return f"; Error during modification: {e}"