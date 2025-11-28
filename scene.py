import yaml
import os
from pathlib import Path
from media import VideoLayer, AudioTrack, OverlayLayer


class Scene:
    def __init__(self, name: str, spec: dict, graphics_scene, resize_callback):
        self.name = name
        self.graphics_scene = graphics_scene
        self.spec = spec  # Store spec for reference
        
        # Create video layers
        self.video_layers = [
            VideoLayer(vspec, graphics_scene, resize_callback)
            for vspec in spec.get("videos", [])
        ]
        
        # Store audio specs (don't create players yet)
        self.audio_specs = spec.get("audio", [])
        self.audio_tracks = []
        
        # Create overlay layers
        self.overlays = [
            OverlayLayer(graphics_scene, ospec)
            for ospec in spec.get("overlays", [])
        ]
        
        # Connect video end signals
        for video in self.video_layers:
            video.video_ended.connect(self._handle_video_end)
            video.loop_completed.connect(self._handle_loop_completed)
        
        # Track if we're waiting for loop to complete before transition
        self.pending_scene_transition = None
        self.allow_skip = spec.get("allow_skip", False)  # Default to false - prevent accidental skipping
        
        # Back scene defined in YAML
        self.back_scene = spec.get("back_scene", None)
        
        # Track active overlay for arrow navigation
        self.active_overlay = None
        for overlay in self.overlays:
            if overlay.type == "arrow":
                self.active_overlay = overlay
                break
        
        # Store arrow positions and their scene transitions
        self.arrow_positions = spec.get("arrow_positions", [])
        self.current_arrow_index = 0
        
        # Auto-transition scene if no arrow positions
        self.auto_transition = spec.get("next_scene") if not self.arrow_positions else None
        
        # Store general transitions
        self.transitions = spec.get("transitions", {})
        
        # Sound effects
        self.move_sound = None
        self.select_sound = None
        
        if "move_sound" in spec:
            from media import AudioTrack
            self.move_sound = AudioTrack({"file": spec["move_sound"], "loop": False})
        
        if "select_sound" in spec:
            from media import AudioTrack
            self.select_sound = AudioTrack({"file": spec["select_sound"], "loop": False})

    def _handle_video_end(self):
        """Handle when main video ends - activate overlays or auto-transition."""
        # Activate overlays marked as active_on_end
        for overlay in self.overlays:
            if overlay.active_on_end:
                overlay.activate()
        
        # Auto-transition if specified and no arrow positions
        # ONLY if not manually navigated (check if this is actual video end, not revisit)
        if self.auto_transition and not self.arrow_positions:
            if hasattr(self, 'scene_manager'):
                # Check if any video is still playing from beginning
                any_playing = any(vl.player.position() > 100 for vl in self.video_layers)
                if any_playing:  # Only auto-transition if video actually played
                    self.scene_manager.switch_to(self.auto_transition)
    
    def _handle_loop_completed(self):
        """Handle when a looping video completes one cycle."""
        # If there's a pending transition, execute it
        if self.pending_scene_transition:
            scene_name = self.pending_scene_transition
            self.pending_scene_transition = None
            if hasattr(self, 'scene_manager'):
                self.scene_manager.switch_to(scene_name)
    
    def request_scene_transition(self, scene_name):
        """Request transition to another scene (waits for loop to complete)."""
        # Check if any video is looping
        has_looping_video = any(vl.loop for vl in self.video_layers)
        
        if has_looping_video:
            # Wait for loop to complete when going forward
            self.pending_scene_transition = scene_name
            for vl in self.video_layers:
                vl.request_transition()
        else:
            # No loop, transition immediately
            if hasattr(self, 'scene_manager'):
                self.scene_manager.switch_to(scene_name)
    
    def skip_to_next(self):
        """Skip current video to trigger next scene transition."""
        if self.allow_skip:
            # Skip all non-looping videos to their end
            for vl in self.video_layers:
                if not vl.loop:
                    vl.skip_to_end()
            
            # If there's an auto-transition and video hasn't ended yet, trigger it
            if self.auto_transition and not self.arrow_positions:
                if hasattr(self, 'scene_manager'):
                    self.scene_manager.switch_to(self.auto_transition)
    
    def start_audio(self, is_back_navigation=False):
        """Start audio tracks, continuing from previous scene if same file."""
        current_files = set(spec["file"] for spec in self.audio_specs)
        
        # Get the scene manager reference
        if not hasattr(self, 'scene_manager') or not self.scene_manager:
            print("[Scene] Warning: scene_manager not set, audio may not continue properly")
            return current_files
        
        # If this scene has NO audio specified, inherit from previous scene
        if not self.audio_specs:
            print(f"[Scene] No audio specs, inheriting previous audio")
            
            # If going backwards, reset all inherited audio to start position
            if is_back_navigation:
                print(f"[Scene] Back navigation - resetting inherited audio to position 0")
                for filename, at in self.scene_manager.active_audio_tracks.items():
                    at.player.setPosition(0)
            
            # Return the currently active audio files so they don't get stopped
            return set(self.scene_manager.active_audio_tracks.keys())
        
        # Start only new audio tracks
        from media import AudioTrack
        for aspec in self.audio_specs:
            filename = aspec["file"]
            
            # If this audio is already playing (from previous scene)
            if filename in self.scene_manager.active_audio_tracks:
                # If going backwards, reset to start position
                if is_back_navigation:
                    start_pos = aspec.get("start", 0)
                    print(f"[Scene] Back navigation - resetting audio {filename} to position {start_pos}")
                    self.scene_manager.active_audio_tracks[filename].player.setPosition(start_pos)
                else:
                    print(f"[Scene] Continuing audio: {filename}")
                continue
            
            # New audio - create and play it
            print(f"[Scene] Starting new audio: {filename}")
            at = AudioTrack(aspec)
            at.play()
            self.scene_manager.active_audio_tracks[filename] = at
        
        return current_files

    def start(self, previous_audio_files=None, is_back_navigation=False):
        """Start all video and audio for this scene."""
        # Show or hide overlays based on scene type
        for overlay in self.overlays:
            # If there are arrow positions (menu scene), show arrow immediately
            # Otherwise, wait for video end to activate
            if self.arrow_positions and overlay.type == "arrow":
                overlay.activate()
            else:
                overlay.deactivate()
        
        # Reset arrow to first position
        self.current_arrow_index = 0
        if self.active_overlay and self.arrow_positions:
            pos = self.arrow_positions[0]
            self.active_overlay.move_to(pos["x"], pos["y"])
        
        # Start audio (continuing from previous if same) - pass is_back_navigation
        current_audio = self.start_audio(is_back_navigation)
        
        # CRITICAL: Reload video source to guarantee position 0
        for vl in self.video_layers:
            vl.reset_and_reload()
            
        # Start videos
        for vl in self.video_layers:
            vl.play()
        
        return current_audio

    def stop(self):
        """Stop all video and audio for this scene."""
        for vl in self.video_layers:
            vl.stop()
        # Don't stop audio here - SceneManager handles it globally
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
        
        # Play move sound
        if self.move_sound:
            self.move_sound.play()

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
        
        # Play move sound
        if self.move_sound:
            self.move_sound.play()
    
    def get_selected_scene(self):
        """Get the scene name for the currently selected arrow position."""
        if not self.arrow_positions or not self.active_overlay or not self.active_overlay.visible:
            return None
        
        pos = self.arrow_positions[self.current_arrow_index]
        return pos.get("scene")
    
    def has_active_selection(self):
        """Check if there are active arrow positions to select from."""
        return bool(self.arrow_positions and self.active_overlay and self.active_overlay.visible)


class SceneManager:
    def __init__(self, scenes_folder, graphics_scene, resize_callback):
        self.scenes_folder = Path(scenes_folder)
        self.graphics_scene = graphics_scene
        self.resize_callback = resize_callback
        
        # Cache for loaded scenes
        self.loaded_scenes = {}
        
        self.current_scene = None
        self.current_audio_files = set()  # Track currently playing audio filenames
        self.active_audio_tracks = {}  # Map filename -> AudioTrack instance
        
        # Load and start the default scene
        self.switch_to("_default")
    
    def _connect_scene_manager(self, scene):
        """Connect scene back to this manager for transitions."""
        scene.scene_manager = self

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
        
        # Connect scene back to manager
        self._connect_scene_manager(scene)
        
        # Cache it
        self.loaded_scenes[scene_name] = scene
        
        return scene

    def switch_to(self, scene_name, is_back_navigation=False):
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
        QTimer.singleShot(50, lambda: self._complete_transition(new_scene, is_back_navigation))
    
    def _complete_transition(self, new_scene, is_back_navigation=False):
        """Complete the scene transition after preload delay."""
        # Track previous audio before stopping
        previous_audio = self.current_audio_files if self.current_scene else set()
        
        print(f"[SceneManager] Transitioning from {self.current_scene.name if self.current_scene else 'None'} to {new_scene.name}")
        print(f"[SceneManager] Previous audio files: {previous_audio}")
        print(f"[SceneManager] Active audio tracks: {list(self.active_audio_tracks.keys())}")
        print(f"[SceneManager] Is back navigation: {is_back_navigation}")
        
        # CRITICAL: Hide old scene videos BEFORE starting new scene
        if self.current_scene and self.current_scene != new_scene:
            for vl in self.current_scene.video_layers:
                vl.item.hide()
        
        # Start new scene (which handles audio)
        self.current_audio_files = new_scene.start(previous_audio, is_back_navigation)
        
        print(f"[SceneManager] New audio files: {self.current_audio_files}")
        print(f"[SceneManager] Active audio tracks after start: {list(self.active_audio_tracks.keys())}")
        
        # Stop old scene
        if self.current_scene and self.current_scene != new_scene:
            self.current_scene.stop()
            
            # Stop audio tracks that are no longer needed
            audio_to_stop = previous_audio - self.current_audio_files
            print(f"[SceneManager] Audio to stop: {audio_to_stop}")
            for filename in audio_to_stop:
                if filename in self.active_audio_tracks:
                    print(f"[SceneManager] Stopping audio: {filename}")
                    self.active_audio_tracks[filename].stop()
                    del self.active_audio_tracks[filename]
        
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
            # Check if there are active arrow selections
            if self.current_scene.has_active_selection():
                selected = self.current_scene.get_selected_scene()
                if selected:
                    # Play select sound
                    if self.current_scene.select_sound:
                        self.current_scene.select_sound.play()
                    # Request transition (waits for loop if needed)
                    self.current_scene.request_scene_transition(selected)
                    return None  # Don't return scene name - it will transition via callback
            else:
                # No active selections - try to skip to next scene
                self.current_scene.skip_to_next()
                return None
        
        elif key == "back":
            # Use back_scene from YAML if defined
            if self.current_scene.back_scene:
                # Mark this as back navigation
                self.switch_to(self.current_scene.back_scene, is_back_navigation=True)
                return None
            return None
        
        # Otherwise use general transitions
        if self.current_scene and key in self.current_scene.transitions:
            return self.current_scene.transitions[key]
        return None