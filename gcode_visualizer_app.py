import tkinter as tk
from tkinter import filedialog, messagebox
import math

# Attempt to import the parser, handle potential errors
try:
    from gcode_parser import parse_gcode
except ImportError:
    messagebox.showerror("Import Error", "Could not find gcode_parser.py. Make sure it's in the same directory.")
    exit()
except Exception as e:
    messagebox.showerror("Import Error", f"An error occurred importing gcode_parser: {e}")
    exit()

class GCodeVisualizerApp:
    def __init__(self, master):
        self.master = master
        master.title("G-Code 2D Visualizer")
        master.geometry("800x650") # Adjusted size

        self.canvas_width = 780
        self.canvas_height = 550
        self.padding = 20 # Padding around the drawing

        # --- GUI Elements ---
        self.top_frame = tk.Frame(master)
        self.top_frame.pack(pady=5, fill=tk.X) # Fill horizontally

        self.load_button = tk.Button(self.top_frame, text="Load G-Code File", command=self.load_file)
        self.load_button.pack(side=tk.LEFT, padx=5)

        # Line Width Input
        self.line_width_label = tk.Label(self.top_frame, text="Line Width (mm):")
        self.line_width_label.pack(side=tk.LEFT, padx=(10, 2))
        self.line_width_entry = tk.Entry(self.top_frame, width=5)
        self.line_width_entry.pack(side=tk.LEFT, padx=(0, 5))
        self.line_width_entry.insert(0, "10") # Default value

        self.status_label = tk.Label(self.top_frame, text="Select a G-code file to visualize.")
        # Pack status label to the right to keep it separate
        self.status_label.pack(side=tk.RIGHT, padx=5)


        self.canvas = tk.Canvas(master, width=self.canvas_width, height=self.canvas_height, bg="white", relief=tk.SUNKEN, borderwidth=1)
        self.canvas.pack(pady=10, padx=10, fill=tk.BOTH, expand=True) # Allow canvas to expand

        # --- Visualization State ---
        self.parsed_data = None
        self.bounds = None # (min_x, min_y, max_x, max_y)
        self.scale = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0

    def load_file(self):
        """Opens a file dialog and attempts to parse and draw the selected G-code file."""
        filepath = filedialog.askopenfilename(
            title="Select G-Code File",
            filetypes=(("G-Code Files", "*.gcode *.nc *.ngc *.tap *.txt"), ("All Files", "*.*"))
        )
        if not filepath:
            self.status_label.config(text="File selection cancelled.")
            return

        self.status_label.config(text=f"Loading: {filepath.split('/')[-1]}...")
        self.master.update_idletasks() # Update GUI to show status

        try:
            self.parsed_data = parse_gcode(filepath)
            if not self.parsed_data:
                # Handle case where parser returns empty list but no error
                self.status_label.config(text=f"File loaded but contains no plottable data: {filepath.split('/')[-1]}")
                self.clear_canvas()
                self.bounds = None
                self.parsed_data = None # Ensure clean state
                return
                # raise ValueError("Parser returned no data.") # Alternative: treat as error

            self.status_label.config(text=f"Successfully parsed: {filepath.split('/')[-1]}")
            self.calculate_bounds_and_scale()
            self.draw_gcode() # This will now use the line width from the entry
        except FileNotFoundError:
            messagebox.showerror("Error", f"File not found: {filepath}")
            self.status_label.config(text="Error: File not found.")
            self.clear_canvas()
            self.parsed_data = None
        except Exception as e:
            messagebox.showerror("Parsing Error", f"Failed to parse G-code file:\n{e}")
            self.status_label.config(text=f"Error parsing file: {e}")
            self.clear_canvas()
            self.parsed_data = None # Clear data on error

    def calculate_bounds_and_scale(self):
        """Calculates the bounding box of the G-code path and the scaling factor."""
        if not self.parsed_data:
            self.bounds = None
            self.scale = 1.0
            self.offset_x = self.canvas_width / 2
            self.offset_y = self.canvas_height / 2
            return

        min_x, min_y = float('inf'), float('inf')
        max_x, max_y = float('-inf'), float('-inf')
        has_coords = False

        current_x, current_y = 0.0, 0.0 # Assume starting at origin

        for item in self.parsed_data:
            # Only consider moves (G0/G1) for bounds calculation
            command = item.get('command')
            if command in ['G0', 'G1']:
                x = item.get('x', current_x)
                y = item.get('y', current_y)

                # Update bounds only if coordinates are present in the command
                if 'x' in item or 'y' in item:
                     # Initial point
                    if not has_coords:
                        min_x, max_x = x, x
                        min_y, max_y = y, y
                        has_coords = True
                    else:
                        min_x = min(min_x, x)
                        max_x = max(max_x, x)
                        min_y = min(min_y, y)
                        max_y = max(max_y, y)

                current_x, current_y = x, y # Update current position for next iteration


        if not has_coords: # Handle files without moves
             self.bounds = (0, 0, 0, 0)
             self.scale = 1.0
             self.offset_x = self.canvas_width / 2
             self.offset_y = self.canvas_height / 2
             return

        self.bounds = (min_x, min_y, max_x, max_y)

        # Calculate scale
        data_width = max_x - min_x
        data_height = max_y - min_y

        available_width = self.canvas_width - 2 * self.padding
        available_height = self.canvas_height - 2 * self.padding

        # Avoid division by zero and handle single points/lines
        if data_width <= 1e-6 and data_height <= 1e-6: # Effectively zero size
             self.scale = 1.0 # Or some default zoom
        elif data_width <= 1e-6: # Vertical line
             self.scale = available_height / data_height if data_height > 1e-6 else 1.0
        elif data_height <= 1e-6: # Horizontal line
             self.scale = available_width / data_width if data_width > 1e-6 else 1.0
        else:
             scale_x = available_width / data_width
             scale_y = available_height / data_height
             self.scale = min(scale_x, scale_y)

        # Ensure scale is positive
        self.scale = max(1e-6, self.scale) # Prevent zero or negative scale

        # Calculate offset to center the drawing
        scaled_width = data_width * self.scale
        scaled_height = data_height * self.scale
        # Offset based on the scaled bounding box center and canvas center
        self.offset_x = (available_width - scaled_width) / 2 - (min_x * self.scale) + self.padding
        # Invert Y for canvas coordinates (origin top-left) and calculate offset
        # The offset_y calculation needs to map the logical max_y to the top edge (considering padding)
        # and logical min_y to the bottom edge (considering padding).
        # A simpler way is often to calculate the canvas coordinates directly in transform_coords.
        # Let's refine transform_coords instead of relying solely on offset_y here.
        # self.offset_y = (available_height - scaled_height) / 2 + (max_y * self.scale) + self.padding # This might be complex


    def transform_coords(self, x, y):
        """Applies scaling and offset to G-code coordinates for canvas drawing."""
        if self.bounds is None or self.scale <= 1e-9: # Check for valid scale
            # Return center if no bounds/scale, or original if scale is too small
            return self.canvas_width / 2, self.canvas_height / 2

        # Apply scale and offset for X
        # Map min_x to left padding, max_x to right padding
        canvas_x = (x - self.bounds[0]) * self.scale + self.padding

        # Apply scale, Y inversion, and offset for Y
        # Map min_y to bottom padding (canvas_height - padding), max_y to top padding
        canvas_y = self.canvas_height - ((y - self.bounds[1]) * self.scale + self.padding)

        return canvas_x, canvas_y


    def draw_gcode(self):
        """Draws the parsed G-code path onto the canvas."""
        self.clear_canvas()
        if not self.parsed_data or self.bounds is None or self.scale <= 1e-9:
            self.status_label.config(text="No data or valid scale to draw.")
            return

        # --- Get Line Width ---
        line_width_pixels = 1 # Default pixel width
        try:
            line_width_mm = float(self.line_width_entry.get())
            if line_width_mm > 0:
                # Ensure scale is valid before using it
                if self.scale and self.scale > 1e-9:
                     # Use max(1, ...) to ensure lines are always visible, even if scale is small
                     line_width_pixels = max(1.0, line_width_mm * self.scale)
                else:
                    print("Warning: Invalid scale detected during line width calculation. Using default width.") # Debug print
            else:
                 # Silently use default for non-positive, or provide feedback
                 # print("Warning: Line width must be positive. Using default width.")
                 pass # Keep default width of 1
        except ValueError:
            # Silently use default for invalid input, or provide feedback
            # print("Warning: Invalid line width input. Using default width.")
            pass # Keep default width of 1
            # Optionally show a message to the user via status bar or messagebox
            # self.status_label.config(text="Invalid line width. Using 1px.")

        # --- Drawing Logic ---
        current_x, current_y = 0.0, 0.0 # Logical coordinates tracking current position
        last_canvas_x, last_canvas_y = None, None # Canvas coordinates of the previous point

        # Find the first actual position to start drawing from
        initial_state_set = False
        temp_x, temp_y = 0.0, 0.0 # Temporary holders for first coords
        for item in self.parsed_data:
            command = item.get('command')
            # Find the first move command (G0 or G1) with coordinates
            if command in ['G0', 'G1'] and not initial_state_set:
                temp_x = item.get('x', temp_x)
                temp_y = item.get('y', temp_y)
                # Only set initial state if coordinates are actually present in this first move
                if 'x' in item or 'y' in item:
                    current_x, current_y = temp_x, temp_y
                    last_canvas_x, last_canvas_y = self.transform_coords(current_x, current_y)
                    initial_state_set = True
                    break # Found the starting point, no need to scan further in this loop

        # If no move commands with coordinates were found, nothing to draw
        if not initial_state_set:
             self.status_label.config(text="Drawing complete (No plottable move commands found).")
             return # Exit drawing if no starting point


        # Iterate through commands again to draw, starting from the established state
        # The first item that set initial_state_set is skipped implicitly
        # because its coordinates are already stored in last_canvas_x/y
        for item in self.parsed_data:
            command = item.get('command')
            # Only process G0/G1 moves
            if command in ['G0', 'G1']:
                # Get target logical coordinates, defaulting to current if not specified
                target_x = item.get('x', current_x)
                target_y = item.get('y', current_y)

                # Check if position actually changes
                if target_x != current_x or target_y != current_y:
                    target_canvas_x, target_canvas_y = self.transform_coords(target_x, target_y)

                    if command == 'G1': # Linear move - draw line
                        # Get the color specifically associated with this move operation
                        move_color = item.get('color', 'black') # Default to black if no color specified
                        if last_canvas_x is not None and last_canvas_y is not None: # Ensure we have a start point
                            self.canvas.create_line(
                                last_canvas_x, last_canvas_y,
                                target_canvas_x, target_canvas_y,
                                fill=move_color, # Use the color from THIS item
                                width=line_width_pixels # Use calculated pixel width
                            )

                    # Update current logical position and last canvas position for the next segment
                    current_x, current_y = target_x, target_y
                    last_canvas_x, last_canvas_y = target_canvas_x, target_canvas_y

            # Other commands (like 'color' itself) are ignored in this drawing loop
            # as the color is retrieved directly from the G1 move item.

        # Display final status
        if self.bounds:
            min_x, min_y, max_x, max_y = self.bounds
            status_text = (
                f"Drawing complete. Bounds: ({min_x:.2f},{min_y:.2f}) to ({max_x:.2f},{max_y:.2f}), "
                f"Scale: {self.scale:.3f}, Line Width: {line_width_pixels:.1f}px"
            )
            self.status_label.config(text=status_text)
        else:
             self.status_label.config(text="Drawing complete (No plottable data).")


    def clear_canvas(self):
        """Clears all items from the canvas."""
        self.canvas.delete("all")

if __name__ == "__main__":
    root = tk.Tk()
    app = GCodeVisualizerApp(root)
    root.mainloop()