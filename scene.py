import yaml
import os
from pathlib import Path
from media import VideoLayer, AudioTrack, OverlayLayer


class Scene:
    def __init__(self, name: str, spec: dict, graphics_scene, resize_callback):
        self.name = name
        self.graphics_scene = graphics_scene
        
        # Create video layers
        self.video_layers = [
            VideoLayer(vspec, graphics_scene, resize_callback)
            for vspec in spec.get("videos", [])
        ]
        
        # Create audio tracks
        self.audio_tracks = [
            AudioTrack(aspec)
            for aspec in spec.get("audio", [])
        ]
        
        # Create overlay layers
        self.overlays = [
            OverlayLayer(graphics_scene, ospec)
            for ospec in spec.get("overlays", [])
        ]
        
        # Connect video end signals to activate overlays
        for video in self.video_layers:
            video.video_ended.connect(self._handle_video_end)
        
        # Track active overlay for arrow navigation
        self.active_overlay = None
        for overlay in self.overlays:
            if overlay.type == "arrow":
                self.active_overlay = overlay
                break
        
        # Store arrow positions and their scene transitions
        self.arrow_positions = spec.get("arrow_positions", [])
        self.current_arrow_index = 0
        
        # Store general transitions
        self.transitions = spec.get("transitions", {})

    def _handle_video_end(self):
        """Activate overlays marked as active_on_end when video ends."""
        for overlay in self.overlays:
            if overlay.active_on_end:
                overlay.activate()

    def start(self):
        """Start all video and audio for this scene."""
        # Hide all overlays initially
        for overlay in self.overlays:
            overlay.deactivate()
        
        # Reset arrow to first position
        self.current_arrow_index = 0
        if self.active_overlay and self.arrow_positions:
            pos = self.arrow_positions[0]
            self.active_overlay.move_to(pos["x"], pos["y"])
            
        for vl in self.video_layers:
            vl.play()
        for at in self.audio_tracks:
            at.play()

    def stop(self):
        """Stop all video and audio for this scene."""
        for vl in self.video_layers:
            vl.stop()
        for at in self.audio_tracks:
            at.stop()
        for overlay in self.overlays:
            overlay.deactivate()

    def move_arrow_up(self):
        """Move the active arrow overlay to previous position."""
        if not self.active_overlay or not self.active_overlay.visible:
            return
        
        if not self.arrow_positions:
            return
        
        # Move to previous position (wrap around)
        self.current_arrow_index = (self.current_arrow_index - 1) % len(self.arrow_positions)
        pos = self.arrow_positions[self.current_arrow_index]
        self.active_overlay.move_to(pos["x"], pos["y"])

    def move_arrow_down(self):
        """Move the active arrow overlay to next position."""
        if not self.active_overlay or not self.active_overlay.visible:
            return
        
        if not self.arrow_positions:
            return
        
        # Move to next position (wrap around)
        self.current_arrow_index = (self.current_arrow_index + 1) % len(self.arrow_positions)
        pos = self.arrow_positions[self.current_arrow_index]
        self.active_overlay.move_to(pos["x"], pos["y"])
    
    def get_selected_scene(self):
        """Get the scene name for the currently selected arrow position."""
        if not self.arrow_positions or not self.active_overlay or not self.active_overlay.visible:
            return None
        
        pos = self.arrow_positions[self.current_arrow_index]
        return pos.get("scene")


class SceneManager:
    def __init__(self, scenes_folder, graphics_scene, resize_callback):
        self.scenes_folder = Path(scenes_folder)
        self.graphics_scene = graphics_scene
        self.resize_callback = resize_callback
        
        # Cache for loaded scenes
        self.loaded_scenes = {}
        
        self.current_scene = None
        self.preloaded_scene = None
        
        # Load and start the default scene
        self.switch_to("_default")

    def _load_scene(self, scene_name):
        """Load a scene from its YAML file if not already loaded."""
        if scene_name in self.loaded_scenes:
            return self.loaded_scenes[scene_name]
        
        # Construct the file path
        scene_file = self.scenes_folder / f"{scene_name}.yaml"
        
        if not scene_file.exists():
            print(f"Warning: Scene file '{scene_file}' not found")
            return None
        
        # Load the YAML file
        with open(scene_file, "r") as f:
            spec = yaml.safe_load(f)
        
        # Create the scene object
        scene = Scene(scene_name, spec, self.graphics_scene, self.resize_callback)
        
        # Cache it
        self.loaded_scenes[scene_name] = scene
        
        return scene

    def switch_to(self, scene_name):
        """Switch to a different scene by name with seamless transition."""
        # Load the new scene first
        new_scene = self._load_scene(scene_name)
        
        if not new_scene:
            print(f"Failed to switch to scene: {scene_name}")
            return
        
        # Preload videos to first frame (but don't play yet)
        for vl in new_scene.video_layers:
            vl.preload()
        
        # Small delay to ensure video is ready (Qt needs this)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, lambda: self._complete_transition(new_scene))
    
    def _complete_transition(self, new_scene: Scene):
        """Complete the scene transition after preload delay."""
        # Start new scene
        new_scene.start()
        
        # Stop old scene immediately after
        if self.current_scene and self.current_scene != new_scene:
            self.current_scene.stop()
        
        # Update current scene reference
        self.current_scene = new_scene

    def move_arrow_up(self):
        """Delegate arrow movement to current scene."""
        if self.current_scene:
            self.current_scene.move_arrow_up()

    def move_arrow_down(self):
        """Delegate arrow movement to current scene."""
        if self.current_scene:
            self.current_scene.move_arrow_down()
    
    def get_transition(self, key):
        """Get the scene name for a transition key (e.g., 'select', 'back')."""
        if key == "select":
            # For 'select', check if there's a selected arrow position
            selected = self.current_scene.get_selected_scene()
            if selected:
                return selected
        
        # Otherwise use general transitions
        if self.current_scene and key in self.current_scene.transitions:
            return self.current_scene.transitions[key]
        return None