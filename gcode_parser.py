import re
import sys

def parse_gcode(file_path):
    """
    Parses a G-code file to extract movement (G0, G1) and color commands (#).

    Args:
        file_path (str): The path to the G-code file.

    Returns:
        list: A list of dictionaries representing the parsed operations,
              or None if the file cannot be read.
              Example: [{'type': 'color', 'value': '#ff0000'},
                        {'type': 'move', 'command': 'G0', 'x': 10, 'y': 5, 'z': 1, 'color': '#ff0000'}]
    """
    operations = []
    default_color = '#000000'
    current_color = default_color  # Start with default color
    last_set_color = None # Track the last color explicitly set by a command
    # Start at origin, Z=0 initially
    current_pos = {'x': 0.0, 'y': 0.0, 'z': 0.0}
    # Regex to find axis coordinates (e.g., X10.5, Y-2, Z0)
    coord_regex = re.compile(r'([XYZ])(-?\d+(?:\.\d+)?)', re.IGNORECASE)
    # Regex for hex color codes (e.g., #ff0000, #ABC)
    color_regex = re.compile(r'^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$')

    try:
        with open(file_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                # Skip empty lines and standard G-code comments (starting with ';')
                if not line or line.startswith(';'):
                    continue

                # Check for color command first
                if line.startswith('#'):
                    match = color_regex.match(line)
                    if match:
                        raw_hex_code = line
                        # Normalize 3-digit hex to 6 digits and ensure lowercase
                        if len(raw_hex_code) == 4:
                           normalized_hex = f"#{raw_hex_code[1]*2}{raw_hex_code[2]*2}{raw_hex_code[3]*2}".lower()
                        else:
                           normalized_hex = raw_hex_code.lower()

                        # Check if this color command stops the current color block
                        if normalized_hex == last_set_color:
                            current_color = default_color # Revert to default
                            last_set_color = None         # Reset last set color marker
                            # Optional: Add a 'color_stop' operation if needed for other purposes
                            # operations.append({'type': 'color_stop', 'value': normalized_hex})
                        else:
                            # This is a new color block start
                            current_color = normalized_hex
                            last_set_color = normalized_hex
                            # Optional: Add a 'color_start' operation if needed
                            # operations.append({'type': 'color_start', 'value': current_color})
                    else:
                        print(f"Warning: Line {line_num}: Invalid color format skipped: {line}", file=sys.stderr)
                    continue # Processed line, move to next

                # Check for G0 or G1 command
                command_match = re.match(r'^(G[01])\s*(.*)', line, re.IGNORECASE)
                if command_match:
                    command = command_match.group(1).upper()
                    args_str = command_match.group(2)

                    coords = {'x': None, 'y': None, 'z': None}
                    found_coords = coord_regex.findall(args_str)
                    valid_command = True

                    for axis, value in found_coords:
                        axis_lower = axis.lower()
                        if axis_lower in coords:
                            try:
                                coords[axis_lower] = float(value)
                            except ValueError:
                                print(f"Warning: Line {line_num}: Invalid coordinate value '{value}' for axis {axis.upper()}. Skipping command.", file=sys.stderr)
                                valid_command = False
                                break
                        else:
                             # Silently ignore unexpected axes like F (Feedrate), S (Spindle Speed) etc.
                             pass

                    if not valid_command:
                         continue # Skip command if coordinate parsing failed

                    # Determine target position, using current position for unspecified axes
                    target_pos = current_pos.copy()

                    if coords['x'] is not None:
                        target_pos['x'] = coords['x']
                    if coords['y'] is not None:
                        target_pos['y'] = coords['y']

                    # Handle Z coordinate based on command type and presence
                    if coords['z'] is not None:
                        target_pos['z'] = coords['z']
                    else:
                        # Z is not specified in the command
                        if command == 'G1':
                            # Assume Z=0 if not present for G1
                            target_pos['z'] = 0.0
                        elif command == 'G0':
                            # Assume Z=previous Z if not present for G0 (travel move)
                            target_pos['z'] = current_pos['z']

                    move_op = {
                        'type': 'move',
                        'command': command,
                        'x': target_pos['x'],
                        'y': target_pos['y'],
                        'z': target_pos['z'],
                        'color': current_color # Use the currently active color
                    }
                    operations.append(move_op)

                    # Update current position *after* recording the operation
                    current_pos = target_pos

                else:
                    # Optional: Warn about lines that are not comments, colors, G0 or G1
                    # print(f"Info: Line {line_num}: Non-movement/color G-code skipped: {line}", file=sys.stderr)
                    pass # Silently skip other G-code commands or malformed lines

    except FileNotFoundError:
        print(f"Error: File not found at {file_path}", file=sys.stderr)
        return None
    except IOError as e:
        print(f"Error: Could not read file {file_path}: {e}", file=sys.stderr)
        return None

    return operations

# Example Usage (for testing purposes)
if __name__ == '__main__':
    # Create a dummy G-code file for testing
    dummy_gcode_content = """
; Example G-code
G0 X10 Y10 Z5 ; Rapid move up and over
#fbbc05       ; Set color to Google Yellow
G1 Z0 F100    ; Linear move down to Z0 (color: yellow)
G1 X20 Y20    ; Linear move on XY plane (Z=0, color: yellow)
#4285f4       ; Set color to Google Blue
G0 Z5         ; Rapid move up (color: blue)
G0 X0 Y0      ; Rapid move back towards origin (Z=5, color: blue)
#ea4335       ; Set color to Google Red
G1 Z0         ; Linear move down (X=0, Y=0, color: red)
G1 X-10 Y-10  ; Linear move (Z=0, color: red)
#34a853       ; Set color to Google Green
G0 Z10        ; Rapid move up (color: green)
G0 X0 Y0      ; Rapid move to origin (Z=10, color: green)
#123          ; Short hex color (becomes #112233)
G1 Z0         ; Linear move down (color: #112233)
G99           ; Unrecognized command (should be skipped)
#invalidcolor ; Invalid color (should be skipped with warning)
G1 X10 Y10 Zbad ; Invalid coordinate (should be skipped with warning)
G1 X Y10 Z1   ; Malformed X (should skip command)
"""
    dummy_file_path = 'dummy_test.gcode'
    print(f"Creating dummy file: {dummy_file_path}")
    try:
        with open(dummy_file_path, 'w') as f:
            f.write(dummy_gcode_content)
        print("Dummy file created.")

        print("\nParsing dummy file...")
        parsed_data = parse_gcode(dummy_file_path)

        if parsed_data is not None:
            import json
            print("\nParsed Operations:")
            print(json.dumps(parsed_data, indent=2))
        else:
            print("\nParsing failed.")

    except Exception as e:
        print(f"An error occurred during testing: {e}")
    finally:
        # Clean up dummy file
        import os
        if os.path.exists(dummy_file_path):
            os.remove(dummy_file_path)
            print(f"\nDummy file {dummy_file_path} removed.")