import tkinter as tk
from tkinter import ttk # Import ttk for Notebook
from tkinter import filedialog, messagebox
import math

# Attempt to import the parser and modifier
try:
    from gcode_parser import parse_gcode
    from gcode_modifier import modify_gcode # Import the main modification function
except ImportError as e:
    # More specific error message
    missing_module = str(e).split("'")[-2] # Attempt to get module name
    messagebox.showerror("Import Error", f"Could not find {missing_module}.py. Make sure it's in the same directory.")
    exit()
except Exception as e:
    messagebox.showerror("Import Error", f"An error occurred during import: {e}")
    exit()

class GCodeVisualizerApp:
    DEFAULT_ANIMATION_S = 5.0
    DEFAULT_LINE_WIDTH_MM = 10.0

    def __init__(self, master):
        self.master = master
        master.title("G-Code 2D Visualizer & Modifier") # Updated title
        master.geometry("800x650") # Keep geometry

        # --- Create Notebook (Tabs) ---
        self.notebook = ttk.Notebook(master)
        self.notebook.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

        # --- Tab 1: Visualization ---
        self.vis_tab = tk.Frame(self.notebook)
        self.notebook.add(self.vis_tab, text='Visualization')

        # --- Tab 2: G-code Modification ---
        self.mod_tab = tk.Frame(self.notebook)
        self.notebook.add(self.mod_tab, text='G-code Modification')

        # --- GUI Elements for Visualization Tab ---
        self.top_frame = tk.Frame(self.vis_tab) # Place in vis_tab
        self.top_frame.pack(pady=5, fill=tk.X)

        self.load_button = tk.Button(self.top_frame, text="Load G-Code File", command=self.load_file)
        self.load_button.pack(side=tk.LEFT, padx=5)

        # Line Width Input
        self.line_width_label = tk.Label(self.top_frame, text="Line Width (mm):")
        self.line_width_label.pack(side=tk.LEFT, padx=(10, 2))
        self.line_width_entry = tk.Entry(self.top_frame, width=5)
        self.line_width_entry.pack(side=tk.LEFT, padx=(0, 5))
        self.line_width_entry.insert(0, str(self.DEFAULT_LINE_WIDTH_MM))

        # Animation Length Input
        self.anim_label = tk.Label(self.top_frame, text="Animation (s):")
        self.anim_label.pack(side=tk.LEFT, padx=(10, 2))
        self.anim_entry = tk.Entry(self.top_frame, width=5)
        self.anim_entry.pack(side=tk.LEFT, padx=(0, 5))
        self.anim_entry.insert(0, str(self.DEFAULT_ANIMATION_S))

        self.status_label = tk.Label(self.top_frame, text="Select a G-code file to visualize.")
        self.status_label.pack(side=tk.RIGHT, padx=5)

        # Canvas (place in vis_tab)
        self.canvas_width = 780 # Keep original calculation basis if needed elsewhere
        self.canvas_height = 550
        self.padding = 20
        self.canvas = tk.Canvas(self.vis_tab, bg="white", relief=tk.SUNKEN, borderwidth=1) # No fixed size, let it expand
        self.canvas.pack(pady=10, padx=10, fill=tk.BOTH, expand=True) # Fill available space in tab

        # --- GUI Elements for Modification Tab ---
        self.mod_content_frame = tk.Frame(self.mod_tab, padx=10, pady=10)
        self.mod_content_frame.pack(fill=tk.BOTH, expand=True) # Allow frame to expand

        # --- Top section for controls ---
        self.mod_controls_frame = tk.Frame(self.mod_content_frame)
        self.mod_controls_frame.pack(anchor=tk.NW) # Keep controls at the top-left

        self.strategy_label = tk.Label(self.mod_controls_frame, text="Select Path Optimization Strategy:")
        self.strategy_label.pack(anchor=tk.W, pady=(0, 5))

        self.strategy_var = tk.StringVar(master)
        self.strategy_var.set("Shortest Path")

        self.radio_shortest = tk.Radiobutton(self.mod_controls_frame, text="Shortest Path", variable=self.strategy_var, value="Shortest Path")
        self.radio_shortest.pack(anchor=tk.W)

        self.radio_vertical = tk.Radiobutton(self.mod_controls_frame, text="Vertical Lines (Left-to-Right)", variable=self.strategy_var, value="Vertical")
        self.radio_vertical.pack(anchor=tk.W)

        self.radio_horizontal = tk.Radiobutton(self.mod_controls_frame, text="Horizontal Lines (Top-to-Bottom)", variable=self.strategy_var, value="Horizontal")
        self.radio_horizontal.pack(anchor=tk.W)

        # Connect the button command
        self.modify_button = tk.Button(self.mod_controls_frame, text="Modify G-code", command=self.modify_gcode_path)
        self.modify_button.pack(anchor=tk.W, pady=(15, 10)) # Add some bottom padding

        # --- Output Text Area ---
        self.mod_output_label = tk.Label(self.mod_content_frame, text="Modified G-code:")
        self.mod_output_label.pack(anchor=tk.W, pady=(10, 2))

        self.mod_output_text = tk.Text(self.mod_content_frame, height=15, wrap=tk.WORD, relief=tk.SUNKEN, borderwidth=1)
        self.mod_output_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5) # Fill remaining space

        # Add scrollbar for the text area
        self.mod_scrollbar = tk.Scrollbar(self.mod_output_text, command=self.mod_output_text.yview)
        self.mod_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.mod_output_text.config(yscrollcommand=self.mod_scrollbar.set)


        # --- Visualization State ---
        self.parsed_data = None
        self.original_filepath = None # Store the original filepath
        self.bounds = None # (min_x, min_y, max_x, max_y)
        self.scale = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0

        # --- Animation State ---
        self.animation_job_id = None
        self.current_anim_x = 0.0
        self.current_anim_y = 0.0
        self.last_anim_canvas_x = None
        self.last_anim_canvas_y = None
        self.current_anim_z = None
        self.is_pen_down = False
    
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

        self.original_filepath = filepath # Store the path
        self.status_label.config(text=f"Loading: {filepath.split('/')[-1]}...")
        self.master.update_idletasks()

        try:
            # Clear previous modified output when loading a new file
            self.mod_output_text.delete('1.0', tk.END)
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

    # ... (rest of the methods: load_file, calculate_bounds_and_scale, etc.) ...

    # --- Need to update transform_coords and potentially others to use canvas dimensions dynamically ---
    # Example adjustment (might need more depending on usage):
    def transform_coords(self, x, y):
        """Applies scaling and offset to G-code coordinates for canvas drawing."""
        # Get current canvas dimensions
        current_canvas_width = self.canvas.winfo_width()
        current_canvas_height = self.canvas.winfo_height()

        if current_canvas_width <= 1 or current_canvas_height <= 1: # Canvas not yet drawn or too small
             current_canvas_width = self.canvas_width # Fallback to initial estimates
             current_canvas_height = self.canvas_height

        if self.bounds is None or self.scale <= 1e-9:
            # Center if no bounds/scale
            return current_canvas_width / 2, current_canvas_height / 2

        # Recalculate available space based on current dimensions
        available_width = current_canvas_width - 2 * self.padding
        available_height = current_canvas_height - 2 * self.padding

        # --- Recalculate scale based on current canvas size ---
        # This should ideally happen when the canvas size changes or data loads,
        # but for simplicity, we might recalculate it here if needed,
        # or ensure calculate_bounds_and_scale uses dynamic dimensions.
        # For now, assume self.scale was calculated correctly based on initial load.
        # If resizing is needed, a more robust approach involving binding to <Configure> is required.

        canvas_x = (x - self.bounds[0]) * self.scale + self.padding
        # Invert Y axis for canvas coordinates
        canvas_y = available_height - (y - self.bounds[1]) * self.scale + self.padding # Use available_height

        # Clamp coordinates to be within the visible canvas area? Optional.
        # canvas_x = max(self.padding, min(canvas_x, current_canvas_width - self.padding))
        # canvas_y = max(self.padding, min(canvas_y, current_canvas_height - self.padding))

        return canvas_x, canvas_y

    # --- Adjust calculate_bounds_and_scale to use dynamic canvas size ---
    def calculate_bounds_and_scale(self):
        """Calculates the bounding box of the G-code path and the scaling factor."""
        if not self.parsed_data:
            self.bounds = None
            self.scale = 1.0
            # Offset calculation is implicit in transform_coords
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
             return

        self.bounds = (min_x, min_y, max_x, max_y)

        # --- Use current canvas dimensions for scaling ---
        # Ensure canvas is updated to get actual size
        self.master.update_idletasks()
        current_canvas_width = self.canvas.winfo_width()
        current_canvas_height = self.canvas.winfo_height()

        if current_canvas_width <= 1 or current_canvas_height <= 1: # Fallback if not drawn
             current_canvas_width = self.canvas_width
             current_canvas_height = self.canvas_height
        # ------------------------------------------------

        data_width = max_x - min_x
        data_height = max_y - min_y
        available_width = current_canvas_width - 2 * self.padding
        available_height = current_canvas_height - 2 * self.padding

        # Handle zero dimensions safely
        if data_width <= 1e-6 and data_height <= 1e-6:
             self.scale = 1.0 # Or some default scale?
        elif data_width <= 1e-6:
             self.scale = available_height / data_height if data_height > 1e-6 else 1.0
        elif data_height <= 1e-6:
             self.scale = available_width / data_width if data_width > 1e-6 else 1.0
        else:
             scale_x = available_width / data_width
             scale_y = available_height / data_height
             self.scale = min(scale_x, scale_y)

        self.scale = max(1e-6, self.scale) # Prevent zero or negative scale

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

    # --- Add the new method ---
    def modify_gcode_path(self):
        """Handles the G-code modification process based on selected strategy."""
        selected_strategy = self.strategy_var.get()
        self.mod_output_text.delete('1.0', tk.END) # Clear previous output

        if not self.parsed_data:
            messagebox.showerror("Error", "No G-code data loaded. Please load a file first.")
            self.mod_output_text.insert(tk.END, "Error: Load G-code file first.")
            return

        # No need to check original_filepath here, modify_gcode doesn't need it directly
        # if not self.original_filepath:
        #      messagebox.showerror("Error", "Original file path not found. Please reload the file.")
        #      self.mod_output_text.insert(tk.END, "Error: Original file path missing.")
        #      return

        self.mod_output_text.insert(tk.END, f"Starting modification with strategy: {selected_strategy}\n")
        # self.mod_output_text.insert(tk.END, f"Original file: {self.original_filepath}\n") # Optional info
        self.mod_output_text.insert(tk.END, f"Processing {len(self.parsed_data)} original commands...\n")
        self.master.update_idletasks() # Show status update

        try:
            # --- Call the actual modification logic ---
            modified_gcode_result = modify_gcode(self.parsed_data, selected_strategy)
            # --- End modification logic call ---

            self.mod_output_text.insert(tk.END, "\n--- Generated G-code ---\n")
            self.mod_output_text.insert(tk.END, modified_gcode_result) # Display the result

            # Show info message, indicating placeholder status if applicable
            if "placeholder" in modified_gcode_result.lower() or "error" in modified_gcode_result.lower():
                 messagebox.showwarning("Modification Result", f"Modification process finished for strategy: {selected_strategy}.\nCheck output area for details (may contain placeholders or errors).")
            else:
                 messagebox.showinfo("Modification Complete", f"Modification process complete for strategy: {selected_strategy}.\nGenerated G-code is shown in the text area.")


        except Exception as e:
            # This catches errors within modify_gcode_path itself,
            # modify_gcode has its own internal try/except
            messagebox.showerror("Modification Error", f"An unexpected error occurred in the GUI application during modification:\n{e}")
            self.mod_output_text.insert(tk.END, f"\nGUI Error during modification: {e}")


    # ... (rest of the methods: transform_coords, calculate_bounds_and_scale, etc.) ...

    def clear_canvas(self):
        """Clears the visualization canvas."""
        self.canvas.delete("gcode_path") # Use the tag to delete only G-code lines
        # Optionally clear other elements if needed
        # self.canvas.delete("all") # To clear everything

# ... (main execution block) ...
if __name__ == "__main__":
    root = tk.Tk()
    app = GCodeVisualizerApp(root)
    root.mainloop()