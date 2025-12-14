import yaml
import os
from pathlib import Path
from PySide6.QtCore import Qt
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
        
        # NOTE: Arrow is NOT parented to video layer - we manually position it
        # based on video layer's displayed size and position
        
        # Auto-transition scene if no arrow positions
        self.auto_transition = spec.get("next_scene") if not self.arrow_positions else None
        
        # Store general transitions
        self.transitions = spec.get("transitions", {})
        
        # Sound effects - use preloaded sounds from scene_manager if available
        self.move_sound = None
        self.select_sound = None
        
        # Inherited background from previous scene (for scenes without videos)
        self.inherited_background = None
        self.inherited_background_pixmap = None  # Store original for resizing
        
        if "move_sound" in spec:
            sound_name = spec.get("move_sound")
            # Check if sound is preloaded globally
            if hasattr(self, 'scene_manager') and sound_name in self.scene_manager.preloaded_sounds:
                self.move_sound = self.scene_manager.preloaded_sounds[sound_name]
                print(f"[Scene] Using preloaded move sound: {sound_name}")
            else:
                # Load it locally
                from media import AudioTrack
                self.move_sound = AudioTrack({"file": sound_name, "loop": False})
                self.move_sound.player.setPosition(0)
        
        if "select_sound" in spec:
            sound_name = spec.get("select_sound")
            # Check if sound is preloaded globally
            if hasattr(self, 'scene_manager') and sound_name in self.scene_manager.preloaded_sounds:
                self.select_sound = self.scene_manager.preloaded_sounds[sound_name]
                print(f"[Scene] Using preloaded select sound: {sound_name}")
            else:
                # Load it locally
                from media import AudioTrack
                self.select_sound = AudioTrack({"file": sound_name, "loop": False})
                self.select_sound.player.setPosition(0)

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
                    self.scene_manager.switch_to_forward(self.auto_transition)
    
    def _handle_loop_completed(self):
        """Handle when a looping video completes one cycle."""
        # If there's a pending transition, execute it
        if self.pending_scene_transition:
            scene_name = self.pending_scene_transition
            self.pending_scene_transition = None
            if hasattr(self, 'scene_manager'):
                self.scene_manager.switch_to_forward(scene_name)
    
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
                self.scene_manager.switch_to_forward(scene_name)
    
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
                    self.scene_manager.switch_to_forward(self.auto_transition)
    
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
            
            # If this audio is already playing (from previous scene) - SAME TRACK
            if filename in self.scene_manager.active_audio_tracks:
                if is_back_navigation:
                    # On back navigation, reposition the existing track (don't recreate)
                    start_pos = aspec.get("start", 0)
                    print(f"[Scene] Back navigation - repositioning audio {filename} to position {start_pos}")
                    try:
                        existing_track = self.scene_manager.active_audio_tracks[filename]
                        existing_track.player.setPosition(start_pos)
                    except Exception as e:
                        print(f"[Scene] Error repositioning audio {filename}: {e}")
                else:
                    # On forward navigation with SAME track, continue from current position (ignore start field)
                    print(f"[Scene] Forward navigation - continuing SAME audio {filename} from current position")
                continue
            
            # NEW/DIFFERENT audio track
            print(f"[Scene] Starting NEW audio: {filename}")
            # Create a modified spec without the start position for forward navigation
            new_aspec = aspec.copy()
            if not is_back_navigation:
                # Forward navigation: play new track from beginning (ignore start field)
                new_aspec.pop("start", None)
                print(f"[Scene] Forward navigation - playing NEW track from beginning")
            else:
                # Back navigation: use start field if present
                if "start" in new_aspec:
                    print(f"[Scene] Back navigation - playing NEW track from position {new_aspec['start']}")
            
            at = AudioTrack(new_aspec)
            at.play()
            self.scene_manager.active_audio_tracks[filename] = at
        
        return current_files

    def start(self, previous_audio_files=None, is_back_navigation=False, inherit_video=False):
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
            self._update_arrow_position()
        
        # Start audio (continuing from previous if same) - pass is_back_navigation
        current_audio = self.start_audio(is_back_navigation)
        
        # Only start videos if we have them (not inheriting)
        if not inherit_video:
            # CRITICAL: Reset all videos to position 0
            for vl in self.video_layers:
                vl.reset_and_reload()
                
            # Start videos
            for vl in self.video_layers:
                vl.play()
        else:
            print(f"[Scene] Inheriting video from previous scene")
        
        return current_audio
    
    def _update_arrow_position(self):
        """Update arrow position based on current index, using scaled coordinates."""
        if not self.active_overlay or not self.arrow_positions:
            return
        
        pos = self.arrow_positions[self.current_arrow_index]
        
        # Check if using scaled coordinates (sx, sy) or absolute (x, y)
        if "sx" in pos and "sy" in pos:
            # Scaled coordinates - calculate based on displayed content (video or static background)
            
            # Use static background if present, otherwise use video layer
            if hasattr(self, 'inherited_background') and self.inherited_background:
                # Menu scene with static background
                bg_item = self.inherited_background
                bg_pos = bg_item.pos()
                
                # Get the background's scaled size
                transform = bg_item.transform()
                scale_x = transform.m11()  # horizontal scale
                scale_y = transform.m22()  # vertical scale
                
                # Original pixmap size
                if hasattr(self, 'inherited_background_pixmap') and self.inherited_background_pixmap:
                    orig_width = self.inherited_background_pixmap.width()
                    orig_height = self.inherited_background_pixmap.height()
                    
                    scaled_width = orig_width * scale_x
                    scaled_height = orig_height * scale_y
                    
                    x = bg_pos.x() + (pos["sx"] * scaled_width)
                    y = bg_pos.y() + (pos["sy"] * scaled_height)
                    
                    # Scale the arrow by the same factor as the background, 
                    # multiplied by the base scale from overlay spec
                    from PySide6.QtGui import QTransform
                    arrow_transform = QTransform()
                    # Use the average of scale_x and scale_y for uniform arrow scaling
                    content_scale = (scale_x + scale_y) / 2
                    # Multiply by the base scale factor from the overlay specification
                    base_scale = self.active_overlay.scale_factor
                    final_arrow_scale = content_scale * base_scale
                    arrow_transform.scale(final_arrow_scale, final_arrow_scale)
                    self.active_overlay.item.setTransform(arrow_transform)
                else:
                    # Fallback
                    x = pos["sx"] * 1920
                    y = pos["sy"] * 1080
            elif self.video_layers:
                # Scene with video layer
                video_item = self.video_layers[0].item
                
                # Force update geometry
                video_item.update()
                
                # Get video item's displayed size (after resize_video_layer sets it)
                video_size = video_item.size()
                
                # Get video item's native size for scale calculation
                native_size = video_item.nativeSize()
                
                # Get video item's position in scene coordinates (centering offset)
                video_pos = video_item.pos()
                
                # Calculate arrow position: video position + (scaled offset within video)
                x = video_pos.x() + (pos["sx"] * video_size.width())
                y = video_pos.y() + (pos["sy"] * video_size.height())
                
                # Scale the arrow by the same factor as the video,
                # multiplied by the base scale from overlay spec
                if native_size.width() > 0 and native_size.height() > 0:
                    from PySide6.QtGui import QTransform
                    arrow_transform = QTransform()
                    # Calculate scale factor from native to displayed size
                    scale_x = video_size.width() / native_size.width()
                    scale_y = video_size.height() / native_size.height()
                    content_scale = (scale_x + scale_y) / 2
                    # Multiply by the base scale factor from the overlay specification
                    base_scale = self.active_overlay.scale_factor
                    final_arrow_scale = content_scale * base_scale
                    arrow_transform.scale(final_arrow_scale, final_arrow_scale)
                    self.active_overlay.item.setTransform(arrow_transform)
            else:
                # Fallback if no video layers
                x = pos["sx"] * 1920  # Assume 1080p
                y = pos["sy"] * 1080
        else:
            # Absolute coordinates (legacy support)
            x = pos.get("x", 0)
            y = pos.get("y", 0)
        
        self.active_overlay.move_to(x, y)

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
        self._update_arrow_position()
        
        # Play move sound - stop, reset, then play
        if self.move_sound:
            self.move_sound.player.stop()
            self.move_sound.player.setPosition(0)
            self.move_sound.player.play()

    def move_arrow_down(self):
        """Move the active arrow overlay to next position."""
        if not self.active_overlay or not self.active_overlay.visible:
            return
        
        if not self.arrow_positions:
            return
        
        # Move to next position (wrap around)
        self.current_arrow_index = (self.current_arrow_index + 1) % len(self.arrow_positions)
        self._update_arrow_position()
        
        # Play move sound - stop, reset, then play
        if self.move_sound:
            self.move_sound.player.stop()
            self.move_sound.player.setPosition(0)
            self.move_sound.player.play()
    
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
        
        # Track original video layers for each scene (before inheritance)
        self.original_video_layers = {}
        
        self.current_scene = None
        self.current_audio_files = set()  # Track currently playing audio filenames
        self.active_audio_tracks = {}  # Map filename -> AudioTrack instance
        
        # Preloaded sound effects - globally available
        self.preloaded_sounds = {}
        self._load_preloaded_assets()
        
        # Load and start the default scene
        self.switch_to_forward("_default")
    
    def _load_preloaded_assets(self):
        """Load globally preloaded assets from preload.yaml"""
        preload_file = self.scenes_folder / "preload.yaml"
        
        if not preload_file.exists():
            print("[SceneManager] No preload.yaml found, skipping global preload")
            return
        
        try:
            import yaml
            with open(preload_file, "r") as f:
                data = yaml.safe_load(f)
            
            # Preload sound effects - index by filename, not name
            if "sounds" in data:
                from media import AudioTrack
                for sound_spec in data["sounds"]:
                    filename = sound_spec.get("file")
                    if filename:
                        print(f"[SceneManager] Preloading sound: {filename}")
                        sound = AudioTrack(sound_spec)
                        # Don't pause or do anything - just create it
                        # It will be ready to play when needed
                        self.preloaded_sounds[filename] = sound
            
            print(f"[SceneManager] Preloaded {len(self.preloaded_sounds)} sounds")
        except Exception as e:
            print(f"[SceneManager] Error loading preload.yaml: {e}")
    
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
        
        # Store original video layers before any inheritance
        self.original_video_layers[scene_name] = scene.video_layers.copy()
        
        # Cache it
        self.loaded_scenes[scene_name] = scene
        
        return scene

    def switch_to_forward(self, scene_name):
        """Switch forward to a scene (normal progression)."""
        print(f"[SceneManager] FORWARD navigation to {scene_name}")
        self._switch_to_internal(scene_name, is_back_navigation=False)
    
    def switch_to_back(self, scene_name):
        """Switch backward to a scene (going back)."""
        print(f"[SceneManager] BACKWARD navigation to {scene_name}")
        self._switch_to_internal(scene_name, is_back_navigation=True)

    def _switch_to_internal(self, scene_name, is_back_navigation=False):
        """Internal method to switch to a different scene by name with seamless transition."""
        # Load the new scene first
        new_scene = self._load_scene(scene_name)
        
        if not new_scene:
            print(f"Failed to switch to scene: {scene_name}")
            return
        
        # If scene is already preloaded, transition immediately
        # Check if any videos need loading
        from PySide6.QtMultimedia import QMediaPlayer
        needs_preload = any(vl.player.mediaStatus() == QMediaPlayer.MediaStatus.NoMedia 
                           for vl in new_scene.video_layers if new_scene.video_layers)
        
        if not needs_preload and new_scene.video_layers:
            print(f"[SceneManager] Scene {scene_name} already preloaded, transitioning immediately")
            self._complete_transition(new_scene, is_back_navigation)
        else:
            print(f"[SceneManager] Preloading scene {scene_name}")
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
        
        # Get new scene's audio files
        new_audio_files = set(spec["file"] for spec in new_scene.audio_specs)
        print(f"[SceneManager] New scene audio files: {new_audio_files}")
        
        # FIXED: Only stop audio tracks that are NOT continuing to the new scene
        # On forward navigation, keep same tracks playing
        # On back navigation, we need to reposition, but don't stop/clear if it's the same track
        if is_back_navigation:
            print(f"[SceneManager] Back navigation - will reposition audio in start_audio()")
            # Don't stop audio here if it's continuing - let start_audio handle repositioning
            tracks_to_stop = []
            for filename, at in list(self.active_audio_tracks.items()):
                if filename not in new_audio_files:
                    tracks_to_stop.append((filename, at))
                    print(f"[SceneManager] Stopping audio track not in new scene: {filename}")
                else:
                    print(f"[SceneManager] Keeping audio track for repositioning: {filename}")
            
            # Stop tracks that won't continue
            for filename, at in tracks_to_stop:
                try:
                    at.stop()
                except Exception as e:
                    print(f"[SceneManager] Error stopping audio {filename}: {e}")
                try:
                    del self.active_audio_tracks[filename]
                except KeyError:
                    pass
        else:
            # Forward navigation - only stop tracks that aren't in the new scene
            tracks_to_stop = []
            for filename, at in list(self.active_audio_tracks.items()):
                if filename not in new_audio_files:
                    tracks_to_stop.append(filename)
                    print(f"[SceneManager] Stopping audio track not in new scene: {filename}")
                    try:
                        at.stop()
                    except Exception as e:
                        print(f"[SceneManager] Error stopping audio {filename}: {e}")
                else:
                    print(f"[SceneManager] Keeping audio track for new scene: {filename}")
            
            # Remove stopped tracks from active_audio_tracks
            for filename in tracks_to_stop:
                try:
                    del self.active_audio_tracks[filename]
                except KeyError:
                    pass
        
        # Check if new scene has its own videos (check original, not modified)
        has_own_videos = bool(self.original_video_layers.get(new_scene.name, []))
        inherit_video = not has_own_videos and self.current_scene and self.current_scene.video_layers
        
        print(f"[SceneManager] New scene has own videos: {has_own_videos}, inherit: {inherit_video}")
        
        if inherit_video:
            print(f"[SceneManager] New scene inheriting video - capturing last frame as static background")
            
            # Determine which scene's video to capture
            source_scene = None
            
            if is_back_navigation:
                # FIXED: Going backwards to a scene without video (e.g., menu)
                # The menu's back_scene points to the scene whose last frame we should show
                # For example: _default_menu.back_scene = "_default", so use _default's last frame
                if new_scene.back_scene:
                    source_scene = self._load_scene(new_scene.back_scene)
                    print(f"[SceneManager] Back navigation - using video from back_scene: {source_scene.name if source_scene else 'None'}")
                    
                    # CRITICAL: Ensure the source video is at the END before capturing
                    if source_scene and source_scene.video_layers:
                        for vl in source_scene.video_layers:
                            duration = vl.player.duration()
                            if duration > 0:
                                # Make sure video is loaded and ready
                                from PySide6.QtMultimedia import QMediaPlayer
                                if vl.player.mediaStatus() == QMediaPlayer.MediaStatus.NoMedia:
                                    print(f"[SceneManager] Video not loaded, loading now...")
                                    vl.player.play()
                                    vl.player.pause()
                                    # Wait for it to load
                                    from PySide6.QtCore import QTimer, QEventLoop
                                    loop = QEventLoop()
                                    timer = QTimer()
                                    timer.setSingleShot(True)
                                    timer.timeout.connect(loop.quit)
                                    timer.start(300)
                                    loop.exec()
                                    timer.stop()
                                    timer.deleteLater()
                                    duration = vl.player.duration()
                                
                                # FIXED: Seek to exact end (duration), not duration - offset
                                print(f"[SceneManager] Seeking back_scene video to exact end: {duration}ms")
                                vl.player.setPosition(duration)
                                
                                # Wait for the seek to complete and frame to render
                                from PySide6.QtCore import QTimer, QEventLoop
                                loop = QEventLoop()
                                timer = QTimer()
                                timer.setSingleShot(True)
                                timer.timeout.connect(loop.quit)
                                timer.start(300)
                                loop.exec()
                                timer.stop()
                                timer.deleteLater()
                                
                                # Double-check position
                                actual_pos = vl.player.position()
                                print(f"[SceneManager] After seek, video at position: {actual_pos}ms / {duration}ms")
                else:
                    # Fallback to current scene
                    source_scene = self.current_scene
                    print(f"[SceneManager] Back navigation - no back_scene, using current")
            else:
                # Going forwards - use current scene, but make sure video is at the END
                source_scene = self.current_scene
                print(f"[SceneManager] Forward navigation - using video from current scene")
                
                # CRITICAL: Ensure the source video is actually at the end before capturing
                if source_scene and source_scene.video_layers:
                    for vl in source_scene.video_layers:
                        duration = vl.player.duration()
                        current_pos = vl.player.position()
                        print(f"[SceneManager] Source video position: {current_pos}ms / {duration}ms")
                        
                        # If video is not at the end, seek to the end
                        if duration > 0 and current_pos < duration - 100:
                            print(f"[SceneManager] Video not at end, seeking to exact end: {duration}ms")
                            vl.player.setPosition(duration)
                            
                            # Wait for the seek to complete with timeout
                            from PySide6.QtCore import QTimer, QEventLoop
                            loop = QEventLoop()
                            timer = QTimer()
                            timer.setSingleShot(True)
                            timer.timeout.connect(loop.quit)
                            timer.start(200)  # 200ms timeout
                            loop.exec()
                            timer.stop()
                            timer.deleteLater()
                            
                            # Verify
                            actual_pos = vl.player.position()
                            print(f"[SceneManager] After seek: {actual_pos}ms / {duration}ms")
            
            # Capture the last frame from the source scene's video
            if source_scene and source_scene.video_layers:
                from PySide6.QtGui import QPixmap
                from PySide6.QtWidgets import QGraphicsPixmapItem
                
                captured = False
                for vl in source_scene.video_layers:
                    # Get the current video frame with safety check
                    try:
                        sink = vl.player.videoSink()
                        if not sink:
                            print(f"[SceneManager] No video sink available")
                            continue
                        
                        frame = sink.videoFrame()
                        if frame and frame.isValid():
                            # Convert to image
                            img = frame.toImage()
                            if not img.isNull():
                                # Store the original pixmap (unscaled)
                                pixmap = QPixmap.fromImage(img)
                                
                                # Create graphics item with original size
                                static_bg = QGraphicsPixmapItem(pixmap)
                                static_bg.setPos(0, 0)
                                static_bg.setZValue(-1)  # Behind other elements
                                static_bg.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
                                
                                self.graphics_scene.addItem(static_bg)
                                
                                # Store both the item and original pixmap for resizing
                                new_scene.inherited_background = static_bg
                                new_scene.inherited_background_pixmap = pixmap
                                
                                # Initial scale to viewport
                                if self.graphics_scene.views():
                                    self._resize_static_background(new_scene)
                                
                                print(f"[SceneManager] Created static background from video frame")
                                captured = True
                                break
                            else:
                                print(f"[SceneManager] Failed to convert frame to image")
                        else:
                            print(f"[SceneManager] No valid video frame available")
                    except Exception as e:
                        print(f"[SceneManager] Error capturing video frame: {e}")
                        continue
                
                if not captured:
                    print(f"[SceneManager] WARNING: Failed to capture video frame for static background")
            
            # Stop and hide all videos from previous scenes
            if self.current_scene:
                for vl in self.current_scene.video_layers:
                    vl.player.stop()
                    vl.player.setPosition(0)
                    vl.item.hide()
            if source_scene and source_scene != self.current_scene:
                for vl in source_scene.video_layers:
                    vl.player.stop()
                    vl.player.setPosition(0)
                    vl.item.hide()
        else:
            print(f"[SceneManager] New scene has own videos - stopping previous scene")
            # Remove any inherited background from previous transitions
            if hasattr(new_scene, 'inherited_background') and new_scene.inherited_background:
                self.graphics_scene.removeItem(new_scene.inherited_background)
                new_scene.inherited_background = None
                new_scene.inherited_background_pixmap = None
            
            # Stop and hide old scene videos
            if self.current_scene and self.current_scene != new_scene:
                # Remove inherited background from old scene if it has one
                if hasattr(self.current_scene, 'inherited_background') and self.current_scene.inherited_background:
                    self.graphics_scene.removeItem(self.current_scene.inherited_background)
                    self.current_scene.inherited_background = None
                    self.current_scene.inherited_background_pixmap = None
                
                for vl in self.current_scene.video_layers:
                    vl.player.stop()
                    vl.player.setPosition(0)
                    vl.item.hide()
        
        # Start new scene (which handles audio)
        self.current_audio_files = new_scene.start(previous_audio, is_back_navigation, inherit_video)
        
        print(f"[SceneManager] New audio files: {self.current_audio_files}")
        print(f"[SceneManager] Active audio tracks after start: {list(self.active_audio_tracks.keys())}")
        
        # FIXED: Resize all video layers in the new scene to match window size
        if new_scene.video_layers:
            for vl in new_scene.video_layers:
                self.resize_callback(vl)
            print(f"[SceneManager] Resized {len(new_scene.video_layers)} video layers to window size")
        
        # Also resize static background if present
        self._resize_static_background(new_scene)
        
        # Stop old scene cleanup
        if self.current_scene and self.current_scene != new_scene and not inherit_video:
            self.current_scene.stop()
        
        # Note: We already stopped all audio tracks at the beginning
        # New scene has started its own audio in start()
        
        # Update current scene reference
        self.current_scene = new_scene
        
        # Preload possible next scenes
        self._preload_next_scenes()
    
    def _resize_static_background(self, scene):
        """Resize the static background to match current viewport size."""
        if not hasattr(scene, 'inherited_background') or not scene.inherited_background:
            return
        if not hasattr(scene, 'inherited_background_pixmap') or not scene.inherited_background_pixmap:
            return
        
        if self.graphics_scene.views():
            view = self.graphics_scene.views()[0]
            viewport_w = view.viewport().width()
            viewport_h = view.viewport().height()
            
            pixmap = scene.inherited_background_pixmap
            img_w = pixmap.width()
            img_h = pixmap.height()
            
            if img_w <= 0 or img_h <= 0:
                return
            
            # Calculate scale factors for both dimensions
            scale_w = viewport_w / img_w
            scale_h = viewport_h / img_h
            
            # Use the MINIMUM scale to fit within bounds (letterbox if needed)
            # This is what video layers do with setSize()
            scale = min(scale_w, scale_h)
            
            # Apply uniform scale (maintains aspect ratio)
            from PySide6.QtGui import QTransform
            transform = QTransform()
            transform.scale(scale, scale)
            scene.inherited_background.setTransform(transform)
            
            # Center the image
            scaled_w = img_w * scale
            scaled_h = img_h * scale
            offset_x = (viewport_w - scaled_w) / 2
            offset_y = (viewport_h - scaled_h) / 2
            scene.inherited_background.setPos(offset_x, offset_y)
    
    def _preload_next_scenes(self):
        """Preload videos for possible next scenes."""
        if not self.current_scene:
            return
        
        scenes_to_preload = set()
        
        # Add auto-transition scene
        if self.current_scene.auto_transition:
            scenes_to_preload.add(self.current_scene.auto_transition)
        
        # Add arrow position scenes
        for pos in self.current_scene.arrow_positions:
            if "scene" in pos:
                scenes_to_preload.add(pos["scene"])
        
        # Add back scene
        if self.current_scene.back_scene:
            scenes_to_preload.add(self.current_scene.back_scene)
        
        print(f"[SceneManager] Preloading next scenes: {scenes_to_preload}")
        
        # Load and preload videos for these scenes
        for scene_name in scenes_to_preload:
            scene = self._load_scene(scene_name)
            if scene:
                for vl in scene.video_layers:
                    vl.preload()
                    # CRITICAL: Hide preloaded videos so they don't appear on screen
                    vl.item.hide()

    def move_arrow_up(self):
        """Delegate arrow movement to current scene."""
        if self.current_scene:
            self.current_scene.move_arrow_up()

    def move_arrow_down(self):
        """Delegate arrow movement to current scene."""
        if self.current_scene:
            self.current_scene.move_arrow_down()
    
    def update_arrow_position(self):
        """Update arrow position after video resize."""
        if self.current_scene:
            self.current_scene._update_arrow_position()
    
    def get_transition(self, key):
        """Get the scene name for a transition key (e.g., 'select', 'back')."""
        if key == "select":
            # Check if there are active arrow selections
            if self.current_scene.has_active_selection():
                selected = self.current_scene.get_selected_scene()
                if selected:
                    # Play select sound - stop, reset, then play
                    if self.current_scene.select_sound:
                        self.current_scene.select_sound.player.stop()
                        self.current_scene.select_sound.player.setPosition(0)
                        self.current_scene.select_sound.player.play()
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
                # Mark this as back navigation using the new method
                self.switch_to_back(self.current_scene.back_scene)
                return None
            return None
        
        # Otherwise use general transitions
        if self.current_scene and key in self.current_scene.transitions:
            return self.current_scene.transitions[key]
        return None