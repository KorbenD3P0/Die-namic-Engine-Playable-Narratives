# fd_terminal/main.py
"""
The Alpha.

This is the main entry point for the Final Destination: Terminal application.
It defines the root App class, which is responsible for initializing and holding
the core systems (ResourceManager, HazardEngine, etc.) and managing the UI screens.
"""
import sys
import os
import json
import logging
from datetime import datetime
from kivy.core.text import LabelBase
from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, SlideTransition
from kivy.uix.label import Label
from kivy.lang import Builder
from fd_terminal.qte_engine import QTE_Engine
from kivy.core.window import Window
from kivy.metrics import sp, Metrics


# Import all screen classes from the UI module
from .ui import (
    register_thematic_fonts,
    TitleScreen, IntroScreen, CharacterSelectScreen, TutorialScreen,
    GameScreen, WinScreen, LoseScreen, LoadGameScreen, SaveGameScreen,
    AchievementsScreen, JournalScreen, InterLevelScreen, SettingsScreen
)

# Import the core engine systems
from .resource_manager import ResourceManager
from .hazard_engine import HazardEngine
from .achievements import AchievementsSystem
from .death_ai import DeathAI
from kivy.config import ConfigParser
from kivy.uix.settings import SettingsWithSidebar

Window.softinput_mode = 'pan'

class FinalDestinationApp(App):
    use_kivy_settings = False  # Hide default Kivy settings panel
    settings_cls = SettingsWithSidebar

    def __init__(self, **kwargs):
        """
        The moment of conception for the App.
        Core, non-visual systems are forged here to ensure they exist for the entire app lifecycle.
        """
        super().__init__(**kwargs)

        # Configure logging FIRST
        self._configure_app_logging()

        # --- 1. Forge the Grand Library (ResourceManager) ---
        self.resource_manager = ResourceManager()
        self.resource_manager.load_master_data()

        # --- 2. Appoint the Chronicler (AchievementsSystem) ---
        self.achievements_system = AchievementsSystem(
            notify_callback=None,
            resource_manager=self.resource_manager
        )

        # --- 3. Ignite the Engine of Calamity (HazardEngine) ---
        self.hazard_engine = HazardEngine(resource_manager=self.resource_manager)
        self.game_logic = None  # will be created on character select
        self.death_ai = None    # ensure attribute exists early
        self.qte_engine = None  # will be created with game_logic

        # --- FONT REGISTRATION RITE ---
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        font_path_regular = os.path.join(project_root, 'assets', 'fonts', 'RobotoMono-Regular.ttf')
        font_path_bold = os.path.join(project_root, 'assets', 'fonts', 'RobotoMono-Bold.ttf')
        LabelBase.register(name="RobotoMono", fn_regular=font_path_regular)
        LabelBase.register(name="RobotoMonoBold", fn_regular=font_path_bold)
        self.thematic_font_name = register_thematic_fonts() or "RobotoMonoBold"

        # --- Load KV BEFORE screen instances so <GameScreen> rule binds ids ---
        try:
            Builder.load_file(os.path.join(os.path.dirname(__file__), "finaldestination.kv"))
        except Exception as e:
            logging.getLogger(__name__).critical("Failed to load KV file", exc_info=True)

        self.logger = logging.getLogger(__name__)
        self.font_scale = 1.0  # global responsive scale
        # Recompute scale when the window changes size (rotation, soft keys, etc.)
        Window.bind(on_resize=lambda *_: self.update_text_size())

    def create_new_game_session(self, character_class: str):
        """
        Centralized factory so all screens consistently build a session.
        """
        from .game_logic import GameLogic
        from .death_ai import DeathAI
        from .qte_engine import QTE_Engine

        self.game_logic = GameLogic(resource_manager=self.resource_manager)
        self.qte_engine = QTE_Engine(resource_manager=self.resource_manager, game_logic_ref=self.game_logic)
        self.game_logic.qte_engine = self.qte_engine
        self.game_logic.hazard_engine = self.hazard_engine
        self.hazard_engine.game_logic = self.game_logic
        self.game_logic.achievements_system = self.achievements_system
        self.death_ai = DeathAI(self.game_logic)
        self.game_logic.death_ai = self.death_ai

        start_response = self.game_logic.start_new_game(character_class=character_class)
        self.game_logic.start_response = start_response

        # Add QTE_Engine to the widget tree and set it to cover the screen
        if self.root and self.qte_engine:
            # Find the GameScreen (or the screen where QTEs should appear)
            game_screen = self.root.get_screen('game')
            # Add QTE_Engine to that screen
            game_screen.add_widget(self.qte_engine)

        self.logger.info(f"Game session created. HazardEngine.game_logic set: {self.hazard_engine.game_logic is not None}")
        return self.game_logic

    def build(self):
        """
        This is the genesis of the VISUALS. Called by Kivy after __init__.
        Its purpose is to construct the application's UI.
        """
        try:
            self.title = "Die-namic Engine Presents: Final Destination Goes to.. the Mall!"

            # --- Construct the Oracle's Window (ScreenManager) ---
            sm = ScreenManager(transition=SlideTransition(direction='left', duration=0.25))

            # All screens are now given the core systems
            sm.add_widget(TitleScreen(
                name='title',
                achievements_system=self.achievements_system,
                resource_manager=self.resource_manager
            ))
            sm.add_widget(CharacterSelectScreen(
                name='character_select',
                resource_manager=self.resource_manager
            ))
            sm.add_widget(SettingsScreen(
                name='settings',
                resource_manager=self.resource_manager
            ))
            sm.add_widget(IntroScreen(name='intro', resource_manager=self.resource_manager))
            sm.add_widget(TutorialScreen(name='tutorial', resource_manager=self.resource_manager))
            sm.add_widget(GameScreen(name='game', resource_manager=self.resource_manager))
            sm.add_widget(WinScreen(name='win', resource_manager=self.resource_manager))
            sm.add_widget(LoseScreen(name='lose', resource_manager=self.resource_manager))
            sm.add_widget(LoadGameScreen(name='load_game', resource_manager=self.resource_manager))
            sm.add_widget(SaveGameScreen(name='_command_save', resource_manager=self.resource_manager))
            sm.add_widget(AchievementsScreen(
                name='achievements',
                achievements_system=self.achievements_system,  # <-- pass the instance!
                resource_manager=self.resource_manager
            ))
            sm.add_widget(JournalScreen(name='journal', achievements_system=self.achievements_system, resource_manager=self.resource_manager))
            sm.add_widget(InterLevelScreen(name='inter_level', resource_manager=self.resource_manager))

            # --- 6. Set the Initial View ---
            sm.current = 'title'

            # First pass to ensure fonts are scaled for the current window
            self.update_text_size()
            self.logger.info("FinalDestinationApp build() completed successfully.")
            return sm

        except Exception as e:
            logging.critical(f"FATAL BUILD ERROR: {e}", exc_info=True)
            return Label(text=f"A fatal error occurred during application build:\n{e}\n\nCheck the console log for details.")

    def on_start(self):
        """Called once the Kivy application loop is running, after __init__."""
        self.logger.info("Application starting.")
        self._cleanup_corrupted_saves()
        self.achievements_system.load_achievements()

    def on_stop(self):
        """Called when the application is closing."""
        self.logger.info("Application stopping.")
        self.achievements_system.save_achievements()

    def build_config(self, config):
        config.setdefaults('Display', {
            'text_size': 18,
            'theme': 'Light'
        })
        config.setdefaults('Audio', {
            'music_volume': 80
        })

    def build_settings(self, settings):
        pass

    def on_config_change(self, config, section, key, value):
        if section == "Display" and key == "text_size":
            self.update_text_size(float(value))
        elif section == "Display" and key == "theme":
            self.apply_theme(value)
        elif section == "Audio" and key == "music_volume":
            self.set_music_volume(int(value))

    def update_text_size(self, size: float | None = None):
        """
        Update global font scale based on current window size (or a user override).
        Called on startup, rotation, and when the Settings slider changes.
        """
        # If user provided explicit scale, honor it
        if size is not None:
            self.font_scale = float(size)
        else:
            # Compute width in dp and choose a scale that preserves readability
            dpi = max(160.0, float(getattr(Metrics, 'dpi', 160.0)))
            width_px = float(Window.width or 1080)
            width_dp = width_px * 160.0 / dpi
            # Simple responsive steps; tweak as desired
            if width_dp < 360:
                self.font_scale = 0.9
            elif width_dp < 411:
                self.font_scale = 1.0
            elif width_dp < 480:
                self.font_scale = 1.15
            elif width_dp < 600:
                self.font_scale = 1.25
            else:
                self.font_scale = 1.35

        # Push scale to all screens that implement update_font_scale
        if hasattr(self, 'root') and self.root:
            for scr in getattr(self.root, 'screens', []):
                if hasattr(scr, 'update_font_scale'):
                    try:
                        scr.update_font_scale(self.font_scale)
                    except Exception:
                        pass

    def apply_theme(self, theme):
        # Example: propagate to all screens/widgets
        for screen in self.root.screens:
            if hasattr(screen, "set_theme"):
                screen.set_theme(theme)

    def set_music_volume(self, volume):
        # Example: set volume in your audio engine
        if hasattr(self, "audio_engine"):
            self.audio_engine.set_volume(volume)

    def _cleanup_corrupted_saves(self):
        """Finds and renames any save files that are not valid JSON."""
        try:
            self.logger.info("Checking for corrupted save files...")
            # Ensure the user data directory exists
            os.makedirs(self.user_data_dir, exist_ok=True)
            
            save_dir = os.path.join(self.user_data_dir, 'saves')
            if not os.path.exists(save_dir):
                os.makedirs(save_dir, exist_ok=True)
                self.logger.info(f"Created saves directory: {save_dir}")
                return

            for filename in os.listdir(save_dir):
                if not filename.endswith('.json'):
                    continue

                filepath = os.path.join(save_dir, filename)
                try:
                    with open(filepath, encoding='utf-8') as f:
                        if not f.read().strip():
                            continue
                        f.seek(0)
                        json.load(f)
                except json.JSONDecodeError:
                    backup_path = filepath + ".corrupted"
                    try:
                        os.rename(filepath, backup_path)
                        self.logger.warning(f"Found and renamed corrupted save file: {filename} -> {filename}.corrupted")
                    except OSError as e:
                        self.logger.error(f"Could not rename corrupted save file {filename}: {e}")
        except Exception as e:
            self.logger.error(f"Error during save cleanup: {e}")

    def _configure_app_logging(self):
        """
        Configures logging to create a unique, timestamped log for each session
        inside a 'logs' directory in the PROJECT ROOT.
        """
        self.logger = logging.getLogger("FinalDestinationApp")

        try:
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
            log_dir = os.path.join(project_root, "logs")
            os.makedirs(log_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            session_log_file = os.path.join(log_dir, f"session_{timestamp}.txt")
            consolidated_log_file = os.path.join(log_dir, "fd_terminal_consolidated.txt")
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

            session_handler = logging.FileHandler(session_log_file, mode='w', encoding='utf-8')
            session_handler.setFormatter(formatter)
            consolidated_handler = logging.FileHandler(consolidated_log_file, mode='a', encoding='utf-8')
            consolidated_handler.setFormatter(formatter)

            root_logger = logging.getLogger()
            root_logger.handlers.clear()
            root_logger.addHandler(session_handler)
            root_logger.addHandler(consolidated_handler)
            root_logger.setLevel(logging.INFO)

            self.logger.info(f"Logging configured. Session log: {session_log_file}")

        except Exception as e:
            logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', force=True)
            self.logger = logging.getLogger("FinalDestinationApp")
            self.logger.error(f"Error configuring file logging: {e}. Using basic console config.", exc_info=True)

# --- The True Entry Point ---
if __name__ == '__main__':
    import sys
    import os

    if getattr(sys, 'frozen', False):
        # Running in a bundle
        BASEDIR = sys._MEIPASS
    else:
        BASEDIR = os.path.dirname(os.path.abspath(__file__))

    FinalDestinationApp().run()

