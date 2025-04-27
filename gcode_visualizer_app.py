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
    DEFAULT_ANIMATION_S = 5.0
    DEFAULT_LINE_WIDTH_MM = 10.0 # Changed default for consistency

    def __init__(self, master):
        self.master = master
        master.title("G-Code 2D Visualizer")
        master.geometry("800x650")

        self.canvas_width = 780
        self.canvas_height = 550
        self.padding = 20

        # --- GUI Elements ---
        self.top_frame = tk.Frame(master)
        self.top_frame.pack(pady=5, fill=tk.X)

        self.load_button = tk.Button(self.top_frame, text="Load G-Code File", command=self.load_file)
        self.load_button.pack(side=tk.LEFT, padx=5)

        # Line Width Input
        self.line_width_label = tk.Label(self.top_frame, text="Line Width (mm):")
        self.line_width_label.pack(side=tk.LEFT, padx=(10, 2))
        self.line_width_entry = tk.Entry(self.top_frame, width=5)
        self.line_width_entry.pack(side=tk.LEFT, padx=(0, 5))
        self.line_width_entry.insert(0, str(self.DEFAULT_LINE_WIDTH_MM)) # Default value

        # Animation Length Input
        self.anim_label = tk.Label(self.top_frame, text="Animation (s):")
        self.anim_label.pack(side=tk.LEFT, padx=(10, 2))
        self.anim_entry = tk.Entry(self.top_frame, width=5)
        self.anim_entry.pack(side=tk.LEFT, padx=(0, 5))
        self.anim_entry.insert(0, str(self.DEFAULT_ANIMATION_S)) # Default value (0 for instant)

        self.status_label = tk.Label(self.top_frame, text="Select a G-code file to visualize.")
        self.status_label.pack(side=tk.RIGHT, padx=5)


        self.canvas = tk.Canvas(master, width=self.canvas_width, height=self.canvas_height, bg="white", relief=tk.SUNKEN, borderwidth=1)
        self.canvas.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

        # --- Visualization State ---
        self.parsed_data = None
        self.bounds = None # (min_x, min_y, max_x, max_y)
        self.scale = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0

        # --- Animation State ---
        self.animation_job_id = None
        self.current_anim_x = 0.0 # Logical X for animation tracking
        self.current_anim_y = 0.0 # Logical Y for animation tracking
        self.last_anim_canvas_x = None # Last drawn canvas X
        self.last_anim_canvas_y = None # Last drawn canvas Y
        self.current_anim_z = None # Logical Z for animation tracking
        self.is_pen_down = False   # Pen state for animation
    
    def load_file(self):
        """Opens a file dialog, attempts parsing, and starts drawing/animation."""
        # --- Cancel any ongoing animation ---
        if self.animation_job_id:
            self.master.after_cancel(self.animation_job_id)
            self.animation_job_id = None
            self.status_label.config(text="Previous animation cancelled.")
        # ------------------------------------

        filepath = filedialog.askopenfilename(
            title="Select G-Code File",
            filetypes=(("G-Code Files", "*.gcode *.nc *.ngc *.tap *.txt"), ("All Files", "*.*"))
        )
        if not filepath:
            self.status_label.config(text="File selection cancelled.")
            return

        self.status_label.config(text=f"Loading: {filepath.split('/')[-1]}...")
        self.master.update_idletasks()

        try:
            self.parsed_data = parse_gcode(filepath)
            if not self.parsed_data:
                self.status_label.config(text=f"File loaded but contains no plottable data: {filepath.split('/')[-1]}")
                self.clear_canvas()
                self.bounds = None
                self.parsed_data = None
                return

            self.status_label.config(text=f"Successfully parsed: {filepath.split('/')[-1]}")
            self.calculate_bounds_and_scale()
            self.draw_gcode() # Start drawing process (animation or instant)
        except FileNotFoundError:
            messagebox.showerror("Error", f"File not found: {filepath}")
            self.status_label.config(text="Error: File not found.")
            self.clear_canvas()
            self.parsed_data = None
        except Exception as e:
            messagebox.showerror("Parsing Error", f"Failed to parse G-code file:\n{e}")
            self.status_label.config(text=f"Error parsing file: {e}")
            self.clear_canvas()
            self.parsed_data = None

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
        current_x, current_y = 0.0, 0.0

        for item in self.parsed_data:
            command = item.get('command')
            if command in ['G0', 'G1']:
                x = item.get('x', current_x)
                y = item.get('y', current_y)
                if 'x' in item or 'y' in item:
                    if not has_coords:
                        min_x, max_x = x, x
                        min_y, max_y = y, y
                        has_coords = True
                    else:
                        min_x = min(min_x, x)
                        max_x = max(max_x, x)
                        min_y = min(min_y, y)
                        max_y = max(max_y, y)
                current_x, current_y = x, y

        if not has_coords:
             self.bounds = (0, 0, 0, 0)
             self.scale = 1.0
             self.offset_x = self.canvas_width / 2
             self.offset_y = self.canvas_height / 2
             return

        self.bounds = (min_x, min_y, max_x, max_y)

        data_width = max_x - min_x
        data_height = max_y - min_y
        available_width = self.canvas_width - 2 * self.padding
        available_height = self.canvas_height - 2 * self.padding

        if data_width <= 1e-6 and data_height <= 1e-6:
             self.scale = 1.0
        elif data_width <= 1e-6:
             self.scale = available_height / data_height if data_height > 1e-6 else 1.0
        elif data_height <= 1e-6:
             self.scale = available_width / data_width if data_width > 1e-6 else 1.0
        else:
             scale_x = available_width / data_width
             scale_y = available_height / data_height
             self.scale = min(scale_x, scale_y)

        self.scale = max(1e-6, self.scale)

        # Offset calculation remains the same, handled by transform_coords
        # self.offset_x = ... (calculated within transform_coords effectively)
        # self.offset_y = ...

    def transform_coords(self, x, y):
        """Applies scaling and offset to G-code coordinates for canvas drawing."""
        if self.bounds is None or self.scale <= 1e-9:
            return self.canvas_width / 2, self.canvas_height / 2

        canvas_x = (x - self.bounds[0]) * self.scale + self.padding
        canvas_y = self.canvas_height - ((y - self.bounds[1]) * self.scale + self.padding)
        return canvas_x, canvas_y

    def get_line_width_pixels(self):
        """Gets and validates line width from entry, returns pixel width."""
        line_width_pixels = 1.0 # Default pixel width
        try:
            line_width_mm = float(self.line_width_entry.get())
            if line_width_mm > 0:
                if self.scale and self.scale > 1e-9:
                     line_width_pixels = max(1.0, line_width_mm * self.scale)
                # else: keep default 1.0 if scale is invalid
            # else: keep default 1.0 for non-positive input
        except ValueError:
            pass # Keep default 1.0 for invalid input
        return line_width_pixels

    def get_animation_duration(self):
        """Gets and validates animation duration from entry."""
        try:
            duration = float(self.anim_entry.get())
            return max(0.0, duration) # Ensure non-negative
        except ValueError:
            return self.DEFAULT_ANIMATION_S # Default on error

    def draw_gcode(self):
        """Clears canvas and decides whether to animate or draw instantly."""
        self.clear_canvas()
        if not self.parsed_data or self.bounds is None or self.scale <= 1e-9:
            self.status_label.config(text="No data or valid scale to draw.")
            return

        animation_duration_s = self.get_animation_duration()
        line_width_pixels = self.get_line_width_pixels()

        # No longer filter for G1 moves here, animation processes all
        # g1_moves = [item for item in self.parsed_data if item.get('command') == 'G1']
        # num_segments = len(g1_moves)
        num_drawable_segments = sum(1 for item in self.parsed_data if item.get('command') == 'G1') # Count G1 for delay calculation

        if num_drawable_segments > 0 and animation_duration_s > 0:
            # --- Start Animation ---
            # Calculate delay based on drawable segments to keep visual speed consistent
            delay_ms = max(1, int((animation_duration_s * 1000) / num_drawable_segments)) if num_drawable_segments > 0 else 1

            # Find the starting position AND Z state *before* the first move
            self.current_anim_x, self.current_anim_y, self.current_anim_z = 0.0, 0.0, None
            initial_state_set = False
            for item in self.parsed_data:
                command = item.get('command')
                if command in ['G0', 'G1']:
                    # Check if this move defines coordinates or Z
                    has_x = 'x' in item
                    has_y = 'y' in item
                    has_z = 'z' in item
                    if has_x or has_y or has_z:
                         # We found the state *before* the first actual move
                         initial_state_set = True
                         break
                    # If no coords/z yet, update potential starting state from defaults
                    # This logic might be slightly flawed if initial state comes from non-G0/G1
                    # Let's refine: only update if it's G0/G1 before the first defining move
                    self.current_anim_x = item.get('x', self.current_anim_x)
                    self.current_anim_y = item.get('y', self.current_anim_y)
                    self.current_anim_z = item.get('z', self.current_anim_z)
                elif 'z' in item: # Also consider standalone Z commands for initial state
                    self.current_anim_z = item.get('z', self.current_anim_z)


            # If the loop finished without finding a move with coords/z (unlikely for valid G-code)
            # the state remains 0,0,None.

            # Set initial pen state based on starting Z
            self.is_pen_down = (self.current_anim_z is not None and self.current_anim_z <= 0)

            self.last_anim_canvas_x, self.last_anim_canvas_y = self.transform_coords(
                self.current_anim_x, self.current_anim_y
            )

            self.status_label.config(text=f"Starting animation ({len(self.parsed_data)} total moves)...")
            # Pass the full parsed data to the animation method
            self.draw_next_segment(0, self.parsed_data, line_width_pixels, delay_ms)
        else:
            # --- Draw Instantly ---
            self.status_label.config(text="Drawing path instantly...")
            self.master.update_idletasks() # Show status before potentially long draw
            self.draw_instant(line_width_pixels)
            min_x, min_y, max_x, max_y = self.bounds
            status_text = (
                f"Drawing complete (Instant). Bounds: ({min_x:.2f},{min_y:.2f}) to ({max_x:.2f},{max_y:.2f}), "
                f"Scale: {self.scale:.3f}, Line Width: {line_width_pixels:.1f}px"
            )
            self.status_label.config(text=status_text)


    def draw_next_segment(self, index, all_moves, line_width_pixels, delay_ms):
        """Draws one segment of the animation and schedules the next, considering pen state."""
        if index >= len(all_moves):
            # Animation finished
            self.status_label.config(text=f"Animation complete ({len(all_moves)} moves processed).")
            self.animation_job_id = None
            # Update final status text
            min_x, min_y, max_x, max_y = self.bounds
            final_z_text = f", Final Z: {self.current_anim_z:.2f}" if self.current_anim_z is not None else ""
            status_text = (
                f"Animation complete. Bounds: ({min_x:.2f},{min_y:.2f}) to ({max_x:.2f},{max_y:.2f}){final_z_text}, "
                f"Scale: {self.scale:.3f}, Line Width: {line_width_pixels:.1f}px"
            )
            self.status_label.config(text=status_text)
            return

        item = all_moves[index]
        command = item.get('command')

        # Update Z state and pen status *before* processing the move
        if 'z' in item:
            self.current_anim_z = item['z']
            self.is_pen_down = (self.current_anim_z is not None and self.current_anim_z <= 0)

        current_delay = 0 # Default delay is 0 for non-drawing moves

        if command in ['G0', 'G1']:
            target_x = item.get('x', self.current_anim_x)
            target_y = item.get('y', self.current_anim_y)

            # Check if position actually changes
            if target_x != self.current_anim_x or target_y != self.current_anim_y:
                target_canvas_x, target_canvas_y = self.transform_coords(target_x, target_y)
                move_color = item.get('color', 'black') # Keep color option

                # --- Conditional Drawing ---
                if command == 'G1' and self.is_pen_down:
                    if self.last_anim_canvas_x is not None and self.last_anim_canvas_y is not None:
                        self.canvas.create_line(
                            self.last_anim_canvas_x, self.last_anim_canvas_y,
                            target_canvas_x, target_canvas_y,
                            fill=move_color,
                            width=line_width_pixels,
                            tags="gcode_path"
                        )
                    current_delay = delay_ms # Apply delay only for drawn segments
                # --- End Conditional Drawing ---

                # --- Always Update Position ---
                self.current_anim_x = target_x
                self.current_anim_y = target_y
                self.last_anim_canvas_x = target_canvas_x
                self.last_anim_canvas_y = target_canvas_y
                # --- End Always Update Position ---
            else:
                 # No XY movement, but Z might have changed (handled above)
                 # If it was a G1 with no XY move, still apply delay? Let's say yes for pacing.
                 if command == 'G1' and self.is_pen_down: # Only delay if pen is down
                     current_delay = delay_ms


        # Update status label less frequently or make it more informative?
        # For now, update every step.
        pen_status = "DOWN" if self.is_pen_down else "UP"
        z_val = f"{self.current_anim_z:.2f}" if self.current_anim_z is not None else "N/A"
        self.status_label.config(text=f"Animating: Move {index + 1}/{len(all_moves)} ({command}), Z:{z_val} (Pen {pen_status})")

        # Schedule the next call
        self.animation_job_id = self.master.after(
            current_delay, # Use calculated delay (0 for G0/Pen Up G1, delay_ms for Pen Down G1)
            self.draw_next_segment,
            index + 1, all_moves, line_width_pixels, delay_ms
        )

    def draw_instant(self, line_width_pixels):
        """Draws the entire G-code path instantly, considering pen state."""
        current_x, current_y, current_z = 0.0, 0.0, None
        last_canvas_x, last_canvas_y = None, None
        is_pen_down = False
        initial_state_set = False

        # Find the first actual position and Z state
        processed_until_index = -1 # Track how far we iterated
        for i, item in enumerate(self.parsed_data):
            command = item.get('command')

            # Update potential initial Z state first
            if 'z' in item:
                current_z = item['z']

            if command in ['G0', 'G1']:
                 # Update potential initial XY state
                 current_x = item.get('x', current_x)
                 current_y = item.get('y', current_y)

                 # Check if this move defines coordinates
                 if 'x' in item or 'y' in item:
                     # This is the first coordinate-defining move.
                     # State (x, y, z) is now set based on this move.
                     is_pen_down = (current_z is not None and current_z <= 0)
                     last_canvas_x, last_canvas_y = self.transform_coords(current_x, current_y)
                     initial_state_set = True
                     processed_until_index = i
                     break # Start main drawing loop from the next item


        if not initial_state_set:
             # If no G0/G1 with coordinates found, try transforming the default 0,0
             # Z might have been set by a command before any move
             is_pen_down = (current_z is not None and current_z <= 0)
             last_canvas_x, last_canvas_y = self.transform_coords(current_x, current_y)
             # We might still have nothing to draw if parsed_data was empty or only comments
             if not self.parsed_data:
                 self.status_label.config(text="No plottable data found.")
                 return # Nothing to draw

        # --- Draw the rest of the path ---
        # Start from the item *after* the one that set the initial state
        start_index = processed_until_index + 1
        for i in range(start_index, len(self.parsed_data)):
            item = self.parsed_data[i]
            command = item.get('command')

            # Update Z state and pen status *before* processing move
            if 'z' in item:
                current_z = item['z']
                is_pen_down = (current_z is not None and current_z <= 0)

            if command in ['G0', 'G1']:
                target_x = item.get('x', current_x)
                target_y = item.get('y', current_y)

                # Check if position actually changes
                if target_x != current_x or target_y != current_y:
                    target_canvas_x, target_canvas_y = self.transform_coords(target_x, target_y)
                    move_color = item.get('color', 'black')

                    # --- Conditional Drawing ---
                    if command == 'G1' and is_pen_down:
                        if last_canvas_x is not None and last_canvas_y is not None:
                            self.canvas.create_line(
                                last_canvas_x, last_canvas_y,
                                target_canvas_x, target_canvas_y,
                                fill=move_color,
                                width=line_width_pixels,
                                tags="gcode_path" # Keep tag
                            )
                    # --- End Conditional Drawing ---

                    # --- Always Update Position ---
                    current_x = target_x
                    current_y = target_y
                    last_canvas_x = target_canvas_x
                    last_canvas_y = target_canvas_y
                    # --- End Always Update Position ---
                # else: No XY movement, Z might have changed (handled above)

    def clear_canvas(self):
        """Clears all items from the canvas."""
        # Also cancel animation if clearing manually or during load
        if self.animation_job_id:
            self.master.after_cancel(self.animation_job_id)
            self.animation_job_id = None
            # Don't change status label here, load_file or draw_gcode will set it
        self.canvas.delete("all")

if __name__ == "__main__":
    root = tk.Tk()
    app = GCodeVisualizerApp(root)
    root.mainloop()