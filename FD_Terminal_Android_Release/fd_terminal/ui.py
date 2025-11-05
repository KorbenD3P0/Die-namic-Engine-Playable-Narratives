# fd_terminal/ui.py

# --- IMPORTS FIRST ---
from kivy.app import App
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.app import App
from kivy.uix.screenmanager import Screen, ScreenManager, FadeTransition, SlideTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.gridlayout import GridLayout
from kivy.uix.slider import Slider
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp, sp
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivy.uix.popup import Popup
from kivy.uix.dropdown import DropDown
from kivy.properties import StringProperty, BooleanProperty, ObjectProperty
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from functools import partial
import logging
import sys
import os
import glob
import random
from typing import Optional
from kivy.core.text import LabelBase
from kivy.clock import Clock
from kivy.utils import get_color_from_hex
from kivy.core.window import Window
from .utils import color_text, get_save_slot_info
from .game_logic import GameLogic
from .achievements import AchievementsSystem
from .widgets import (
    StatusDisplayWidget, OutputPanelWidget, MapDisplayWidget,
    ActionInputWidget, QTEPopup,
    MainActionsWidget, ContextualActionsWidget, InfoPopup,
    ContextDockWidget  # <-- Added missing import
)


# --- NEW: FONT LOGIC AND GLOBAL DEFINITIONS AT THE TOP ---

# This set will keep track of fonts we've already registered.
REGISTERED_FONT_NAMES = set()

# Proclaim the global names for our fonts so all classes can see them.
DEFAULT_FONT_BOLD_NAME = "RobotoMonoBold"
DEFAULT_FONT_REGULAR_NAME = "RobotoMono"  # Added definition for regular font
THEMATIC_FONT_NAME = "RobotoMonoBold" # Start with a safe default

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(base_path, relative_path)

def register_thematic_fonts():
    """
    Discovers, registers, and selects a random thematic font.
    Returns the selected font name (registered with Kivy).
    """
    global THEMATIC_FONT_NAME
    try:
        font_dir = resource_path("assets/fonts")
        if not os.path.isdir(font_dir):
            logging.warning(f"Font directory not found: {font_dir}. Using fallback.")
            return None

        font_files = glob.glob(os.path.join(font_dir, "*.ttf")) + glob.glob(os.path.join(font_dir, "*.otf"))
        thematic_fonts = [f for f in font_files if "Roboto" not in os.path.basename(f)]

        if not thematic_fonts:
            logging.warning(f"No thematic fonts found in {font_dir}. Using fallback.")
            return None
            
        selected_font_path = random.choice(thematic_fonts)
        font_name = os.path.splitext(os.path.basename(selected_font_path))[0]

        if font_name not in REGISTERED_FONT_NAMES:
            LabelBase.register(name=font_name, fn_regular=selected_font_path)
            REGISTERED_FONT_NAMES.add(font_name)
            logging.info(f"Registered thematic font: '{font_name}'")
        
        THEMATIC_FONT_NAME = font_name
        logging.info(f"Selected thematic font: {THEMATIC_FONT_NAME}")
        return THEMATIC_FONT_NAME
    except Exception as e:
        logging.error(f"Error during thematic font registration: {e}", exc_info=True)
        return None

def get_thematic_font_name():
    """
    Read the selected thematic font from the App if available, else fallback.
    """
    app = App.get_running_app()
    return getattr(app, 'thematic_font_name', THEMATIC_FONT_NAME)

def _wrap_button_text(btn, align='center'):
    """
    Ensure a Kivy Button wraps/ellipsizes correctly when width changes.
    """
    try:
        btn.halign = align
        btn.shorten = True
        btn.text_size = (btn.width - dp(20), None)
        btn.bind(width=lambda i, w: setattr(i, 'text_size', (w - dp(20), None)))
    except Exception:
        pass

# A base screen for common functionality
class BaseScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(0.05, 0.05, 0.05, 1) # Dark background color
            self.rect = Rectangle(size=self.size, pos=self.pos)
        self.bind(size=self._update_rect, pos=self._update_rect)

    def _update_rect(self, instance, value):
        self.rect.pos = instance.pos
        self.rect.size = instance.size

    def go_to_screen(self, screen_name: str, direction: str = 'left'):
        try:
            if direction == 'fade':
                self.manager.transition = FadeTransition()
            elif direction in ('left', 'right', 'up', 'down'):
                self.manager.transition = SlideTransition(direction=direction)
            else:
                self.manager.transition = SlideTransition(direction='left')
            self.manager.current = screen_name
        except Exception as e:
            logging.error(f"go_to_screen: failed to switch to '{screen_name}' (from '{getattr(self.manager,'current', '?')}'): {e}", exc_info=True)

# --- Minimal Screen Definitions ---
# We only need the classes to exist for main.py to import them.

class TitleScreen(BaseScreen):
    # Expose colors to KV early so KV can read them without AttributeError
    color_white = StringProperty('ffffff')
    color_white = [1, 1, 1, 1] 
    color_red = StringProperty('ff0000')

    def __init__(self, **kwargs):
        # Pop custom deps BEFORE super so we can compute properties used by KV
        self.resource_manager = kwargs.pop('resource_manager', None)
        self.achievements_system = kwargs.pop('achievements_system', None)

        # Compute colors now so KV sees the final values during apply()
        if self.resource_manager:
            constants = self.resource_manager.get_data('constants', {})
            colors = constants.get('COLORS', {})
            self.color_white = colors.get('WHITE', self.color_white)
            self.color_red = colors.get('RED', self.color_red)

        super().__init__(**kwargs)

        if self.resource_manager:
            constants = self.resource_manager.get_data('constants', {})
            colors = constants.get('COLORS', {})
            self.color_white = colors.get('WHITE', 'ffffff')
            self.color_red = colors.get('RED', 'ff0000')

    def on_enter(self, *args):
        """
        Always wipe any existing session when arriving at the title screen.
        Guarantees that 'New Game' starts fresh.
        """
        app = App.get_running_app()
        if app and hasattr(app, 'reset_session'):
            app.reset_session()
        return super().on_enter(*args)


    def start_new_game_display(self, character_class="Journalist"):
        self.game_logic.start_new_game(character_class)
        initial_description = self.game_logic.get_game_start_description()
        self.display_message(initial_description)
        self.update_location_display(self.game_logic.player['location'])
        self.update_output(initial_description)

    def start_new_game_flow(self, *args): # Kivy passes the button instance as an arg
        """Initiates the new game flow."""
        app = App.get_running_app()
        app.start_new_session_flag = True 
        self.go_to_screen('character_select', direction='left')

class CharacterSelectScreen(BaseScreen):
    def __init__(self, **kwargs):
        """
        Initializes the static layout of the screen.
        The actual character buttons are added by the on_enter method.
        """
        self.resource_manager = kwargs.pop('resource_manager', None)
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(10))

        layout.add_widget(Label(
            text="[b]Select Your Character[/b]",
            markup=True,
            font_name=DEFAULT_FONT_BOLD_NAME,
            font_size=dp(24),
            size_hint_y=0.15
        ))
        self.logger = logging.getLogger(__name__ + ".CharacterSelectScreen")
        # Create the grid layout and assign it to self.character_grid.
        # It will be populated by the on_enter method.
        self.character_grid = GridLayout(cols=1, spacing=dp(8), size_hint_y=0.7)
        layout.add_widget(self.character_grid)

        # Add spacer to push button to bottom
        layout.add_widget(Widget(size_hint_y=1))

        btn_back = Button(
            text="Back to Title",
            size_hint_y=None,
            height=dp(50),
            font_name=DEFAULT_FONT_BOLD_NAME,
            font_size=dp(18),
            on_release=lambda x: self.go_to_screen('title', 'right')
        )
        layout.add_widget(btn_back)

        self.add_widget(layout)

    def on_enter(self, *args):
        """
        REFACTORED: This method is now more robust, with better logging
        to diagnose data-related issues.
        """
        logging.info("CharacterSelectScreen: on_enter called. Populating character classes.")
        self.character_grid.clear_widgets()

        app = App.get_running_app()
        if not app or not app.resource_manager:
            logging.error("CharacterSelectScreen: Could not get App or ResourceManager.")
            self.character_grid.add_widget(Label(text="Error: Could not load character data."))
            return

        character_data = app.resource_manager.get_data('character_classes', {})
        logging.debug(f"Character data loaded: {character_data}")  # Add this for debugging

        if not character_data:
            logging.warning("CharacterSelectScreen: No character classes found in master data.")
            self.character_grid.add_widget(Label(text="No character classes available."))
            return

        for key, details in character_data.items():
            try:
                name = details.get('name', key)
                description = details.get('description', 'No description.')
                btn_text = f"[b]{name}[/b]\n[size=14dp]{description}[/size]"

                char_button = Button(
                    text=btn_text, markup=True, halign='center', valign='middle',
                    font_name=DEFAULT_FONT_BOLD_NAME,  # Use the registered name directly
                    size_hint_y=None, height=dp(100)
                )
                # Ensure text wraps if the screen size changes
                def set_text_size(instance, value):
                    instance.text_size = (value - dp(20), None)
                char_button.bind(width=set_text_size)
                # Set initial text_size
                char_button.text_size = (char_button.width - dp(20), None)
                char_button.bind(on_press=lambda instance, char_key=key: self.select_character(char_key))
                self.character_grid.add_widget(char_button)
            except Exception as e:
                logging.error(f"CharacterSelectScreen: Failed to create button for '{key}': {e}", exc_info=True)

    def select_character(self, char_class: str):
        """
        Creates a new session only if needed, then transitions to intro.
        """
        app = App.get_running_app()
        self.logger.info(f"Character selected: {char_class}. Checking for existing session.")

        # Check if we already have a valid game session
        existing_session = getattr(app, 'game_logic', None)
        if existing_session and hasattr(existing_session, 'player') and existing_session.player:
            self.logger.info("Valid game session already exists, reusing it.")
            # Optionally update the character class if it's different
            if existing_session.player.get('character_class') != char_class:
                existing_session.player['character_class'] = char_class
                self.logger.info(f"Updated character class to {char_class}")
        else:
            self.logger.info("No valid session found, creating new one.")
            # Create new session only if none exists
            app.create_new_game_session(char_class)

        # Set the flag for the GameScreen
        app.start_new_session_flag = True

        # Transition to the intro
        self.go_to_screen('intro', direction='left')

class IntroScreen(BaseScreen):
    """Displays the introductory story text for the game."""
    def __init__(self, **kwargs):
        self.resource_manager = kwargs.pop('resource_manager', None)
        super().__init__(**kwargs)
        logging.info("IntroScreen initializing")
        self.logger = logging.getLogger(__name__ + ".IntroScreen")
        
        layout = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))

        # Safely get constants with fallbacks
        if self.resource_manager:
            constants = self.resource_manager.get_data('constants', {})
            colors = constants.get('COLORS', {})
            color_white_hex = colors.get('WHITE', 'ffffff')
            color_red_hex = colors.get('RED', 'ff0000')
        else:
            color_white_hex = 'ffffff'
            color_red_hex = 'ff0000'

        intro_titles = [
            "The Setup",
            "A Chilling Premonition",
            "Death Beckons",
            "Fate's Cruel Game",
            "The Last Survivor",
            "Escaping the Inevitable",
            "Death is at it again, that Fuck"
        ]
        intro_title = Label(
            text=random.choice(intro_titles),
            font_name=THEMATIC_FONT_NAME, # Use thematic font
            font_size=dp(30),
            size_hint_y=None
        )
        layout.add_widget(intro_title)

        self.intro_text_label = Label(
            text="Loading premonition...",
            markup=True,
            valign='top',
            halign='center',  # Changed to center for better readability of paragraphs
            font_name=DEFAULT_FONT_REGULAR_NAME,  # Use readable default font
            font_size=dp(16),  # Adjusted size
            padding=(dp(10), dp(10)),
            size_hint_y=None  # Height will be driven by texture_size
        )
        self.intro_text_label.bind(
            texture_size=self._update_intro_label_height,
            width=self._update_intro_label_text_size # For text wrapping
        )

        scroll_view = ScrollView(size_hint=(1, 1)) # Takes remaining space
        scroll_view.add_widget(self.intro_text_label)
        layout.add_widget(scroll_view)

        # Button layout at the bottom
        button_layout_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(60), padding=(0, dp(5)))
        # Add spacers to center the button
        button_layout_box.add_widget(Widget(size_hint_x=0.25)) 
        self.continue_button = Button(
            text="Continue to Emergency Room",
            font_name=DEFAULT_FONT_BOLD_NAME,
            font_size=dp(18),
            size_hint_x=0.9, # Button takes 75% of horizontal space
            size_hint_y=None,
            height=dp(50)
        )
        self.continue_button.bind(on_press=self.proceed_to_game)
        button_layout_box.add_widget(self.continue_button)
        button_layout_box.add_widget(Widget(size_hint_x=0.25))
        layout.add_widget(button_layout_box)

        self.add_widget(layout)

    def _update_intro_label_height(self, instance, texture_size_value):
        instance.height = texture_size_value[1] # Set height to fit content

    def _update_intro_label_text_size(self, instance, width_value):
        # Update text_size for wrapping, considering padding
        instance.text_size = (width_value - dp(20), None) 


    def on_enter(self, *args):
        """
        When the screen is entered, this method generates and displays the full,
        randomized intro text directly from the app's GameLogic instance.
        """
        self.logger.info("IntroScreen on_enter: Generating and displaying intro text.")
        app = App.get_running_app()
        
        # The single source of truth for the game state
        game_logic = app.game_logic
        
        if not game_logic or 'intro_disaster' not in game_logic.player:
            self.intro_text_label.text = "A chilling premonition grips you..." # Failsafe
            return

        details = game_logic.player['intro_disaster']
        rm = self.resource_manager # Convenience alias
        
        # --- The Static Part of the Narrative ---
        intro_base = (f"Welcome to McKinley, population: {color_text('dropping like flies.', 'error', rm)}\\n\\n"
                      "Local tales speak of 'Death's List'. It was nonsense to you. Past tense.\\n\\n"
                      "You arrive at Hope River Hospital, accompanying the body of the most recent ex-survivor of a disaster that almost took your lives. By this point, you were sticking together, safety in numbers and such.. but now..")
        
        # --- The Dynamic Part of the Narrative ---
        disaster_desc_template = details.get("full_description_template", "A terrible disaster occurred.")
        
        try:
            # Use the .format() method to weave all the random threads into the template
            formatted_disaster_description = disaster_desc_template.format(
                visionary=color_text(details.get("visionary", "a figure"), 'special', rm),
                warning=color_text(details.get("warning", "Watch out!"), 'warning', rm),
                killed_count=color_text(str(details.get("killed_count", 0)), 'warning', rm),
                survivor_fates=color_text(details.get("survivor_fates", "met grim ends."), 'item', rm)
            )
        except KeyError as e:
            self.logger.warning(f"IntroScreen: Missing placeholder in disaster template: {e}")
            formatted_disaster_description = disaster_desc_template

        # --- The Final Assembly ---
        # Use only raw newlines in f-strings, not escaped \n
        full_intro = (
            f"{intro_base}\n\n"
            f"You both recently walked away from a mass casualty disaster that claimed a lot of lives: {color_text(details.get('event_description', 'a disaster'), 'special', rm)}.\n"
            f"{formatted_disaster_description}\n\n"
            f"{color_text('Your journey has just begun and you are already the last one left;', 'error', rm)} there's nothing and nobody standing between you and Death.\n\n"
            f"Your goal: find evidence that might help you learn about how to cheat Death before your time runs out. Dangers are {color_text('EVERYWHERE.', 'error', rm)}\n"
            f"Type '{color_text('list', 'command', rm)}' or use buttons for actions.\n\n"
            f"{color_text('Good luck...', 'special', rm)}"
        )
        # Display the final text and scroll to the top
        self.intro_text_label.text = full_intro.replace("\\n", "\n")
        def scroll_to_top(dt):
            self.intro_text_label.parent.parent.scroll_y = 1
        Clock.schedule_once(scroll_to_top, 0.1)

    def proceed_to_game(self, instance):
        """Switches to the 'game' screen."""
        logging.info("IntroScreen: Proceeding to GameScreen.")
        self.go_to_screen('game', direction='left')

class TutorialScreen(BaseScreen):
    def __init__(self, **kwargs):
        self.resource_manager = kwargs.pop('resource_manager', None)
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(10))
        
        layout.add_widget(Label(
            text="[b]How to Play[/b]", 
            markup=True, 
            font_name=DEFAULT_FONT_BOLD_NAME, 
            font_size=dp(24), 
            size_hint_y=0.1
        ))
        
        # Use canonical color names defined in your constants/colors system
        rm = self.resource_manager
        _welcome = color_text("Welcome to Final Destination Terminal!", "special", rm)
        _evidence = color_text("Evidence", "item", rm)
        _survive = color_text("survive the current level", "success", rm)
        _hp = color_text("Health (HP)", "success", rm)
        _turns = color_text("Turns Left", "warning", rm)
        _text_input = color_text("Text Input:", "info", rm)
        _action_buttons = color_text("Action Buttons:", "info", rm)
        _context_buttons = color_text("Contextual Buttons:", "info", rm)
        _list_cmd = color_text("list", "light_grey", rm)
        _help_cmd = color_text("help", "light_grey", rm)
        _examine_cmd = color_text("examine [object/item/room]", "light_grey", rm)
        _search_cmd = color_text("search [furniture]", "light_grey", rm)
        _take_cmd = color_text("take [item]", "light_grey", rm)
        _use_cmd = color_text("use [item] on [target]", "light_grey", rm)
        _inv_cmd = color_text("inventory", "light_grey", rm)
        _inv_short = color_text("i", "light_grey", rm)
        _map_cmd = color_text("map", "light_grey", rm)
        _journal_cmd = color_text("journal", "light_grey", rm)
        _dangerous = color_text("dangerous", "error", rm)
        _sparks = color_text("Sparks", "special", rm)
        _gas_smells = color_text("gas smells", "item", rm)
        _unstable = color_text("unstable objects", "special", rm)
        _qtes = color_text("QTEs", "error", rm)
        _break = color_text("Break", "light_grey", rm)

        tutorial_text_content = (
            f"{_welcome}\n\n"
            "You've narrowly escaped a catastrophe, but Death doesn't like to be cheated. "
            "You find yourself at the abandoned Bludworth residence, seeking clues about Death's design "
            "and how others might have survived... or failed.\n\n"
            "[b]Objective:[/b]\n"
            f"- Explore each location (e.g., The House, The Hospital) to find {_evidence} related to past events and victims.\n"
            f"- Some evidence is crucial to understanding how to proceed or {_survive}.\n"
            f"- Manage your {_hp} and {_turns}. Running out of either means Death catches up.\n\n"
            "[b]Interacting with the World:[/b]\n"
            f"- {_text_input} Type commands like '"
            f"{color_text('move north', 'light_grey', rm)}', "
            f"'{color_text('examine table', 'light_grey', rm)}', or "
            f"'{color_text('take key', 'light_grey', rm)}'.\n"
            f"- {_action_buttons} Use the main action buttons (Move, Examine, etc.) at the bottom left. Selecting an action will show available targets.\n"
            f"- {_context_buttons} After selecting a main action, specific targets (objects, items, directions) will appear as buttons.\n\n"
            "[b]Key Commands (examples):[/b]\n"
            f"- '{_list_cmd}' or '{_help_cmd}': Shows available actions in your current situation.\n"
            f"- '{_examine_cmd}': Get more details. Examining items in your inventory can reveal new information.\n"
            f"- '{_search_cmd}': Look inside containers like desks or cabinets to find hidden items.\n"
            f"- '{_take_cmd}': Pick up an item you can see or have found.\n"
            f"- '{_use_cmd}': Use an item from your inventory on something in the room.\n"
            f"- '{_inv_cmd}' or '{_inv_short}': Check what you're carrying.\n"
            f"- '{_map_cmd}': View a map of your surroundings.\n"
            f"- '{_journal_cmd}': Review collected evidence and clues.\n\n"
            "[b]Hazards & QTEs:[/b]\n"
            f"- The environment is {_dangerous}. Hazards can change, interact, or be triggered by your actions.\n"
            f"- Pay attention to descriptions! {_sparks}, {_gas_smells}, or {_unstable} are bad signs.\n"
            f"- Quick Time Events ({_qtes}) may occur. You'll have a few seconds to type the correct command (e.g., 'DODGE') to survive.\n\n"
            f"- '{_break}': Some objects can be broken to reveal secrets or create hazards.\n\n"
            "[b]Good luck. You'll need it.[/b]"
        )
        
        scroll_view = ScrollView(size_hint_y=0.8)
        scroll_label = Label(
            text=tutorial_text_content, 
            font_name=DEFAULT_FONT_REGULAR_NAME, 
            font_size=dp(15), # Slightly smaller for more text
            markup=True, 
            size_hint_y=None, # Height determined by content
            halign='left', 
            valign='top',
            padding=(dp(5), dp(5))
        )
        scroll_label.bind(width=lambda instance, value: setattr(instance, 'text_size', (value - dp(10), None))) # Word wrapping
        scroll_label.bind(texture_size=lambda instance, value: setattr(instance, 'height', value[1])) # Fit height to text
        
        scroll_view.add_widget(scroll_label)
        layout.add_widget(scroll_view)
        
        btn_back = Button(
            text="Back to Title", 
            size_hint_y=None, # Explicit height
            height=dp(50), 
            font_name=DEFAULT_FONT_BOLD_NAME, 
            font_size=dp(18),
            on_release=lambda x: self.go_to_screen('title', 'right')
        )
        layout.add_widget(btn_back)
        self.add_widget(layout)

# --- Achievements Screen (from new ui.py, looks good) ---
class AchievementsScreen(BaseScreen):
    def __init__(self, achievements_system=None, **kwargs):
        self.resource_manager = kwargs.pop('resource_manager', None)
        super().__init__(**kwargs)
        self.achievements_system = achievements_system
        layout = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        layout.add_widget(Label(text="[b]Achievements[/b]", markup=True, font_name=DEFAULT_FONT_BOLD_NAME, size_hint_y=0.1, font_size=dp(24)))
        self.scroll_view = ScrollView(size_hint_y=0.8); self.grid_layout = GridLayout(cols=1, spacing=dp(5), size_hint_y=None)
        self.grid_layout.bind(minimum_height=self.grid_layout.setter('height')); self.scroll_view.add_widget(self.grid_layout); layout.add_widget(self.scroll_view)
        btn_back = Button(text="< Back", font_name=DEFAULT_FONT_BOLD_NAME, size_hint_y=0.1, height=dp(50), on_release=lambda x: self.go_to_screen('title', 'right'))
        layout.add_widget(btn_back); self.add_widget(layout)

    def on_enter(self, *args):
        self.grid_layout.clear_widgets()
        if self.achievements_system:
            # Sort: Unlocked first, then by name
            sorted_achievements = sorted(
                self.achievements_system.get_all_achievements(),
                key=lambda ach: (not ach['unlocked'], ach['name'])
            )
            for ach_data in sorted_achievements: # ach_data is now a dict
                status_color_name = 'success' if ach_data['unlocked'] else 'error'
                icon = ach_data.get('icon', '▪') # Default icon
                text = f"{icon} [b]{ach_data['name']}[/b] ({color_text('Unlocked' if ach_data['unlocked'] else 'Locked', status_color_name, self.resource_manager)})\n   {ach_data['description']}"

                
                ach_label = Label(text=text, font_name=DEFAULT_FONT_REGULAR_NAME, markup=True, 
                                  size_hint_y=None, height=dp(70), # Fixed height for consistency
                                  halign='left', valign='top', padding=(dp(5),dp(5)))
                # Bind text_size to width for wrapping
                ach_label.bind(width=lambda instance, value: setattr(instance, 'text_size', (value - dp(10), None)))
                self.grid_layout.add_widget(ach_label)
        else:
            self.grid_layout.add_widget(Label(text="Achievements system not available.", font_name=DEFAULT_FONT_REGULAR_NAME))

class JournalScreen(BaseScreen):
    def __init__(self, achievements_system=None, **kwargs):
        self.resource_manager = kwargs.pop('resource_manager', None)
        super().__init__(**kwargs)
        self.achievements_system = achievements_system
        
        # Main Layout
        main_layout = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        main_layout.add_widget(Label(
            text="[b]Journal[/b]", markup=True, font_name=DEFAULT_FONT_BOLD_NAME, 
            size_hint_y=0.08, font_size=dp(24)
        ))
        
        # Tab Buttons
        tab_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(50), spacing=dp(10))
        
        self.btn_evidence_tab = ToggleButton(
            text="Evidence", font_name=DEFAULT_FONT_BOLD_NAME, font_size=dp(16),
            group='journal_tabs', state='down'
        )
        self.btn_evidence_tab.bind(on_press=lambda x: self.switch_view('evidence'))
        
        self.btn_stories_tab = ToggleButton(
            text="Stories", font_name=DEFAULT_FONT_BOLD_NAME, font_size=dp(16),
            group='journal_tabs'
        )
        self.btn_stories_tab.bind(on_press=lambda x: self.switch_view('stories'))
        
        tab_layout.add_widget(self.btn_evidence_tab)
        tab_layout.add_widget(self.btn_stories_tab)
        main_layout.add_widget(tab_layout)
        
        # Content Manager (Screen Manager for Evidence/Stories views)
        from kivy.uix.screenmanager import ScreenManager, Screen
        self.content_manager = ScreenManager(size_hint_y=0.8)
        
        # Evidence Screen
        evidence_screen = Screen(name='evidence')
        evidence_content = self._create_details_view_layout()
        self.evidence_list_layout = evidence_content['list_layout']
        self.evidence_details_title = evidence_content['details_title']
        self.evidence_details_description = evidence_content['details_description']
        self.evidence_details_scroll = evidence_content['details_scroll']
        evidence_screen.add_widget(evidence_content['root'])
        self.content_manager.add_widget(evidence_screen)
        
        # Stories Screen
        stories_screen = Screen(name='stories')
        stories_content = self._create_details_view_layout()
        self.stories_list_layout = stories_content['list_layout']
        self.story_details_title = stories_content['details_title']
        self.story_details_description = stories_content['details_description']
        self.story_details_scroll = stories_content['details_scroll']
        stories_screen.add_widget(stories_content['root'])
        self.content_manager.add_widget(stories_screen)
        
        main_layout.add_widget(self.content_manager)
        
        # Back Button
        btn_back = Button(
            text="< Back", font_name=DEFAULT_FONT_BOLD_NAME, 
            size_hint_y=None, height=dp(50),
            on_release=lambda x: self.go_to_screen('title', 'right')
        )
        main_layout.add_widget(btn_back)
        self.add_widget(main_layout)

    def _create_details_view_layout(self):
        """Creates and returns the widgets for a reusable two-panel list/details view."""
        # Main horizontal layout
        main_horizontal = BoxLayout(orientation='horizontal', spacing=dp(10))
        
        # Left panel - List of items
        left_panel = BoxLayout(orientation='vertical', size_hint_x=0.4)
        left_panel.add_widget(Label(
            text="[b]Items[/b]", markup=True, font_name=DEFAULT_FONT_BOLD_NAME,
            size_hint_y=None, height=dp(30), font_size=dp(16)
        ))
        
        # Scrollable list
        list_scroll = ScrollView()
        list_layout = BoxLayout(orientation='vertical', spacing=dp(5), size_hint_y=None)
        list_layout.bind(minimum_height=list_layout.setter('height'))
        list_scroll.add_widget(list_layout)
        left_panel.add_widget(list_scroll)
        
        # Right panel - Details
        right_panel = BoxLayout(orientation='vertical', size_hint_x=0.6)
        details_title = Label(
            text="[b]Select an Item[/b]", markup=True, font_name=DEFAULT_FONT_BOLD_NAME,
            size_hint_y=None, height=dp(40), font_size=dp(18), halign='center'
        )
        right_panel.add_widget(details_title)
        
        # Scrollable details description
        details_scroll = ScrollView()
        details_description = Label(
            text="Click on an item from the list to see its details here.",
            font_name=DEFAULT_FONT_REGULAR_NAME, font_size=dp(14),
            markup=True, halign='left', valign='top',
            size_hint_y=None, padding=(dp(10), dp(10))
        )
        details_description.bind(width=lambda instance, value: setattr(instance, 'text_size', (value - dp(20), None)))
        details_description.bind(texture_size=details_description.setter('size'))
        details_scroll.add_widget(details_description)
        right_panel.add_widget(details_scroll)
        
        # Assemble the layout
        main_horizontal.add_widget(left_panel)
        main_horizontal.add_widget(right_panel)
        
        return {
            'root': main_horizontal,
            'list_layout': list_layout,
            'details_title': details_title,
            'details_description': details_description,
            'details_scroll': details_scroll
        }

    def switch_view(self, view_name):
        """Switch between evidence and stories views."""
        if view_name in ['evidence', 'stories']:
            self.content_manager.current = view_name
            # Reset details panels when switching views
            if view_name == 'evidence':
                self.evidence_details_title.text = "Select Evidence to View Details"
                self.evidence_details_description.text = "Click on an evidence item from the list to see its details here."
            elif view_name == 'stories':
                self.story_details_title.text = "Select a Story to Read"
                self.story_details_description.text = "Click on an unlocked story from the list to read its complete backstory."

    def on_enter(self, *args):
        """Called when the journal screen is entered."""
        # Get the current achievements system from the app if not set
        if not self.achievements_system:
            app = App.get_running_app()
            if app and hasattr(app, 'achievements_system'):
                self.achievements_system = app.achievements_system
        
        self.populate_evidence_list()
        self.populate_unlocked_stories_list()
        # Default to evidence view
        self.content_manager.current = 'evidence'
        self.btn_evidence_tab.state = 'down'
        self.btn_stories_tab.state = 'normal'


    def populate_evidence_list(self):
        """Populate the evidence list with collected evidence items."""
        self.evidence_list_layout.clear_widgets()
        
        if not self.achievements_system or not self.achievements_system.evidence_collection:
            self.evidence_list_layout.add_widget(Label(
                text="No evidence collected yet.\nExplore and search to find clues!", 
                font_name=DEFAULT_FONT_REGULAR_NAME, 
                size_hint_y=None, height=dp(60),
                halign='center', valign='middle'
            ))
            # Reset details panel
            self.evidence_details_title.text = "No Evidence Yet"
            self.evidence_details_description.text = "Start exploring to find your first piece of evidence!"
            return
        
        # Sort evidence by found_date (most recent first)
        try:
            sorted_evidence = sorted(
                self.achievements_system.evidence_collection.items(), 
                key=lambda item: item[1].get('found_date', '1970-01-01 00:00'),
                reverse=True  # Most recent first
            )
        except Exception as e:
            logging.error(f"JournalScreen: Error sorting evidence: {e}")
            sorted_evidence = list(self.achievements_system.evidence_collection.items())

        for ev_id, ev_data in sorted_evidence:
            btn_text = ev_data.get('name', ev_id).title()
            btn = Button(
                text=btn_text, 
                font_name=DEFAULT_FONT_REGULAR_NAME, 
                font_size=dp(14),
                size_hint_y=None, 
                height=dp(45),
                halign='left', 
                padding_x=dp(10)
            )
            btn.text_size = (None, None)  # Allow text to wrap
            btn.bind(on_release=lambda x, eid=ev_id: self.show_evidence_details(eid))
            self.evidence_list_layout.add_widget(btn)
        
        # Reset details panel
        self.evidence_details_title.text = "Select Evidence to View Details"
        self.evidence_details_description.text = "Click on an evidence item from the list to see its details here."

    def _check_for_story_completion(self, new_evidence_id):
        """Checks if a newly collected piece of evidence completes a story set."""
        if not self.resource_manager:
            logging.warning("ResourceManager not available. Story completion checking disabled.")
            return
            
        evidence_by_source = self.resource_manager.get_data('evidence_by_source', {})
        if not evidence_by_source:
            logging.warning("EVIDENCE_BY_SOURCE not found in data. Story completion checking disabled.")
            return

        collected_ids = set(self.evidence_collection.keys())
        
        # Log for debugging
        logging.info(f"Checking story completion for evidence: {new_evidence_id}")
        logging.info(f"Current evidence collection: {', '.join(collected_ids)}")

        for source_name, source_data in evidence_by_source.items():
            # Check if this is the source the new evidence belongs to
            if new_evidence_id in source_data['evidence_list']:
                logging.info(f"Evidence {new_evidence_id} belongs to story: {source_name}")
                
                required_ids = set(source_data['evidence_list'])
                # Log for clarity
                logging.info(f"Required evidence for {source_name}: {', '.join(required_ids)}")
                logging.info(f"Missing evidence: {', '.join(required_ids - collected_ids)}")
                
                # Check if all required IDs for this source are in our collection
                if required_ids.issubset(collected_ids):
                    if source_name not in self.unlocked_stories:
                        self.unlocked_stories.add(source_name)
                        logging.info(f"Story Unlocked: {source_name}")
                        
                        # Trigger notification for story unlock
                        if self.notify_callback:
                            self.notify_callback(
                                "Story Unlocked!",
                                f"You've collected all evidence for '{source_name}'. Read the full story in your journal."
                            )
                        
                        self.unlock("lore_master")  # Will only unlock on first story
                        
                        if len(self.unlocked_stories) >= 5:
                            self.unlock("historian")
                        
                        self._check_story_type_achievements()
                        
                        # Always save after unlocking a story
                        self.save_achievements()

    def populate_unlocked_stories_list(self):
        """Populate the stories list with unlocked complete story sets."""
        self.stories_list_layout.clear_widgets()
        
        if not self.achievements_system or not self.achievements_system.unlocked_stories:
            # Check if we have any evidence at all
            evidence_count = len(self.achievements_system.evidence_collection) if self.achievements_system else 0
            
            if evidence_count == 0:
                message = "No stories unlocked yet.\nStart collecting evidence to unlock complete backstories!"
            else:
                message = f"No complete stories yet.\nYou have {evidence_count} evidence pieces.\nKeep collecting to unlock full backstories!"
            
            self.stories_list_layout.add_widget(Label(
                text=message,
                font_name=DEFAULT_FONT_REGULAR_NAME, 
                size_hint_y=None, height=dp(80),
                halign='center', valign='middle'
            ))
            # Reset details panel
            self.story_details_title.text = "No Stories Unlocked"
            self.story_details_description.text = "Collect all evidence from a story set to unlock its complete backstory."
            return

        # Sort stories alphabetically
        sorted_stories = sorted(list(self.achievements_system.unlocked_stories))

        for story_name in sorted_stories:
            # Add visual indicator for story type
            story_icon = "🎬"  # Default movie icon
            if "Book:" in story_name:
                story_icon = "📖"
            elif "Comic:" in story_name:
                story_icon = "📚"
            elif "Archives" in story_name:
                story_icon = "🗃️"
            
            btn_text = f"{story_icon} {story_name}"
            btn = Button(
                text=btn_text,
                font_name=DEFAULT_FONT_REGULAR_NAME,
                font_size=dp(14),
                size_hint_y=None, 
                height=dp(45),
                halign='left', 
                padding_x=dp(10)
            )
            btn.bind(on_release=lambda x, s_name=story_name: self.show_story_details(s_name))
            self.stories_list_layout.add_widget(btn)

        # Reset details panel
        self.story_details_title.text = "Select a Story to Read"
        self.story_details_description.text = "Click on an unlocked story from the list to read its complete backstory."


    def show_evidence_details(self, evidence_id):
        """
        Display detailed information about a specific piece of evidence.
        Canonical: Always shows character association, description, and story set(s).
        """
        if not self.achievements_system or evidence_id not in self.achievements_system.evidence_collection:
            self.evidence_details_title.text = "Evidence Not Found"
            self.evidence_details_description.text = "This evidence could not be found in your collection."
            return

        evidence_data = self.achievements_system.evidence_collection[evidence_id]

        # Title: Evidence name (colored)
        title_text = evidence_data.get('name', evidence_id).title()
        # Use canonical color: 'special' (from color_text system)
        self.evidence_details_title.text = color_text(title_text, 'special')

        # Description: Prefer 'description', fallback to 'examine_details'
        desc = evidence_data.get('description')
        if not desc or desc.strip() == "":
            # Try to get from items.json
            app = App.get_running_app()
            items_data = app.resource_manager.get_data('items', {}) if app and app.resource_manager else {}
            item_master = items_data.get(evidence_id.lower()) or items_data.get(evidence_id)
            desc = (item_master.get('description') if item_master else "") or evidence_data.get('examine_details', "No description available.")

        found_date_str = evidence_data.get('found_date', 'Unknown time')

        # --- Canonical: Always show story set info, even if incomplete ---
        app = App.get_running_app()
        evidence_by_source = app.resource_manager.get_data('evidence_by_source', {}) if app and app.resource_manager else {}
        story_sets = []
        for story_name, story_data in evidence_by_source.items():
            if 'evidence_list' in story_data and evidence_id in story_data['evidence_list']:
                story_sets.append(story_name)
        if story_sets:
            story_text = "\n\n[b]Story Set(s):[/b] " + ", ".join(color_text(s, 'special') for s in story_sets)
        else:
            story_text = "\n\n[i][color=aaaaaa]This evidence is not part of any known story set.[/color][/i]"

        # --- Canonical: Always show character association if present ---
        # Try evidence_data, then items.json
        character_assoc = evidence_data.get('character_connection')
        if not character_assoc:
            app = App.get_running_app()
            items_data = app.resource_manager.get_data('items', {}) if app and app.resource_manager else {}
            item_master = items_data.get(evidence_id.lower()) or items_data.get(evidence_id)
            character_assoc = item_master.get('character_connection') if item_master else None

        if character_assoc:
            # Use canonical color name 'special' for character association
            char_info_text = f"\n[b]Victim/Character:[/b] {color_text(character_assoc, 'special')}"
        else:
            char_info_text = ""

        # Use canonical color name 'light_grey' via color_text for found date
        self.evidence_details_description.text = (
            f"[b]Description:[/b]\n{desc}\n\n"
            f"[size={int(dp(13))}sp]{color_text(f'Found: {found_date_str}', 'light_grey')}[/size]"
            f"{story_text}"
            f"{char_info_text}"
        )
        self.evidence_details_scroll.scroll_y = 1  # Scroll to top

    def show_story_details(self, story_name):
        """Display the complete backstory for an unlocked story set."""
        # Use canonical color name 'special' for story title
        self.story_details_title.text = color_text(story_name, 'special', self.resource_manager)

        
        # Get story data from resource manager
        app = App.get_running_app()
        if not app or not app.resource_manager:
            self.story_details_description.text = "Error: Could not load story data."
            return
            
        evidence_by_source = app.resource_manager.get_data('evidence_by_source', {})
        story_data = evidence_by_source.get(story_name, {})
        backstory = story_data.get("backstory", "This story's details are shrouded in mystery.")
        
        # Add story completion info
        evidence_list = story_data.get('evidence_list', [])
        completion_text = ""
        if evidence_list:
            # Use canonical color name 'success' for completion message
            completion_text = f"\n\n{color_text('[b]Story Complete![/b]', 'success', self.resource_manager)}\n[size={int(dp(12))}sp]You collected all {len(evidence_list)} evidence pieces from this story.[/size]"

        
        self.story_details_description.text = f"{backstory}{completion_text}"
        self.story_details_scroll.scroll_y = 1  # Scroll to top

    def _get_evidence_story_info(self, evidence_id):
        """Get information about which story set this evidence belongs to."""
        app = App.get_running_app()
        if not app or not app.resource_manager:
            return None
            
        evidence_by_source = app.resource_manager.get_data('evidence_by_source', {})
        if not evidence_by_source:
            return None
        
        for story_name, story_data in evidence_by_source.items():
            if evidence_id in story_data.get('evidence_list', []):
                # Count how many pieces from this story we have
                story_evidence_ids = set(story_data['evidence_list'])
                collected_ids = set(self.achievements_system.evidence_collection.keys()) if self.achievements_system else set()
                collected_from_story = story_evidence_ids.intersection(collected_ids)
                
                return {
                    'story_name': story_name,
                    'collected_count': len(collected_from_story),
                    'total_count': len(story_evidence_ids),
                    'is_complete': story_name in (self.achievements_system.unlocked_stories if self.achievements_system else set())
                }
        
        return None
    
class SettingsScreen(BaseScreen):
    def __init__(self, **kwargs):
        self.resource_manager = kwargs.pop('resource_manager', None)
        super().__init__(**kwargs)
        app = App.get_running_app()
        config = app.config

        layout = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(10))

        # --- Text Size Setting ---
        layout.add_widget(Label(text="Text Size", font_size=dp(18), size_hint_y=None, height=dp(30)))
        text_size_slider = Slider(min=12, max=48, value=float(config.get('Display', 'text_size')), step=1, size_hint_y=None, height=dp(40))
        text_size_label = Label(text=str(int(text_size_slider.value)), size_hint_y=None, height=dp(30))
        def on_text_size_slider(instance, value):
            text_size_label.text = str(int(value))
            config.set('Display', 'text_size', str(int(value)))
            app.update_text_size(value)
        text_size_slider.bind(value=on_text_size_slider)
        layout.add_widget(text_size_slider)
        layout.add_widget(text_size_label)

        # --- Theme Setting ---
        layout.add_widget(Label(text="Color Theme", font_size=dp(18), size_hint_y=None, height=dp(30)))
        theme_dropdown = DropDown()
        for theme in ["Light", "Dark"]:
            btn = Button(text=theme, size_hint_y=None, height=dp(40))
            btn.bind(on_release=lambda btn: theme_dropdown.select(btn.text))
            theme_dropdown.add_widget(btn)
        mainbutton = Button(text=config.get('Display', 'theme'), size_hint_y=None, height=dp(40))
        def on_theme_select(instance, value):
            mainbutton.text = value
            config.set('Display', 'theme', value)
            app.apply_theme(value)
        mainbutton.bind(on_release=theme_dropdown.open)
        theme_dropdown.bind(on_select=on_theme_select)
        layout.add_widget(mainbutton)

        # --- Music Volume Setting ---
        layout.add_widget(Label(text="Music Volume", font_size=dp(18), size_hint_y=None, height=dp(30)))
        music_volume_slider = Slider(min=0, max=100, value=float(config.get('Audio', 'music_volume')), step=1, size_hint_y=None, height=dp(40))
        music_volume_label = Label(text=str(int(music_volume_slider.value)), size_hint_y=None, height=dp(30))
        def on_music_volume_slider(instance, value):
            music_volume_label.text = str(int(value))
            config.set('Audio', 'music_volume', str(int(value)))
            app.set_music_volume(value)
        music_volume_slider.bind(value=on_music_volume_slider)
        layout.add_widget(music_volume_slider)
        layout.add_widget(music_volume_label)

        # --- Back Button ---
        btn_back = Button(
            text="Back to Title",
            size_hint_y=None,
            height=50,
            on_release=lambda x: self.go_to_screen('title', 'right')
        )
        layout.add_widget(btn_back)
        self.add_widget(layout)

class SaveGameScreen(BaseScreen):
    def __init__(self, **kwargs):
        self.resource_manager = kwargs.pop('resource_manager', None)
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(10))
        layout.add_widget(Label(text="[b]Save Game[/b]", markup=True, font_name=DEFAULT_FONT_BOLD_NAME, size_hint_y=0.1, font_size=dp(24)))
        
        # ScrollView for save slots
        scroll_view = ScrollView(size_hint_y=0.7) # Added ScrollView
        self.slots_layout = BoxLayout(orientation='vertical', spacing=dp(5), size_hint_y=None)
        self.slots_layout.bind(minimum_height=self.slots_layout.setter('height')) # For ScrollView
        scroll_view.add_widget(self.slots_layout)
        layout.add_widget(scroll_view)

        self.status_label = Label(text="", markup=True, font_name=DEFAULT_FONT_REGULAR_NAME, size_hint_y=0.1, font_size=dp(16))
        layout.add_widget(self.status_label)
        
        buttons_bottom_layout = BoxLayout(size_hint_y=0.1, height=dp(50), spacing=dp(10)) # Layout for back button
        btn_back = Button(text="< Back to Game", font_name=DEFAULT_FONT_BOLD_NAME, 
                          on_release=lambda x: self.go_to_screen('game', 'right'))
        buttons_bottom_layout.add_widget(btn_back)
        layout.add_widget(buttons_bottom_layout)
        
        self.add_widget(layout)

    def on_enter(self, *args):
        self.populate_save_slots()
        self.status_label.text = "Select a slot to save or delete."

    def populate_save_slots(self):
        """
        Populates the save slots UI with up-to-date info from save files.
        Unified: Uses the standalone get_save_slot_info utility, injects logging, and ensures robust slot display.
        Maximum debugging logic injected.
        """
        import logging
        self.slots_layout.clear_widgets()
        # Use MAX_SAVE_SLOTS from GameLogic if available, else default to 5
        max_slots = getattr(GameLogic, "MAX_SAVE_SLOTS", 5)
        slots_to_show = ["quicksave"] + [f"slot_{i}" for i in range(1, max_slots + 1)]

        for slot_id in slots_to_show:
            try:
                slot_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(60), spacing=dp(10))
                preview_info = get_save_slot_info(slot_id)  # Standalone utility, not a method
                display_text = f"{slot_id.replace('_', ' ').capitalize()}"

                if preview_info:
                    loc = preview_info.get('location', '?')
                    ts = preview_info.get('timestamp', 'No date')
                    char_class = preview_info.get('character_class', '')
                    turns = preview_info.get('turns_left', '')
                    display_text += f" - {char_class}, {loc} (Turns: {turns})\n   {ts}"
                    if preview_info.get("corrupted"):
                        display_text += color_text(" (Corrupted)", 'error')
                    logging.debug(f"Save slot '{slot_id}': {preview_info}")
                else:
                    display_text += color_text(" (Empty Slot)", 'light_grey')
                    logging.debug(f"Save slot '{slot_id}': Empty")

                save_btn = Button(
                    text=display_text, markup=True, font_name=DEFAULT_FONT_REGULAR_NAME,
                    size_hint_x=0.7, halign='left', padding_x=dp(10)
                )
                save_btn.bind(width=lambda instance, value: setattr(instance, 'text_size', (value - dp(20), None)))
                save_btn.bind(on_release=lambda x, s_id=slot_id: self.confirm_save(s_id))
                slot_box.add_widget(save_btn)

                delete_btn = Button(text="Del", size_hint_x=0.3, font_name=DEFAULT_FONT_BOLD_NAME)
                if not preview_info:
                    delete_btn.disabled = True
                delete_btn.bind(on_release=lambda x, s_id=slot_id: self.confirm_delete_popup(s_id))
                slot_box.add_widget(delete_btn)

                self.slots_layout.add_widget(slot_box)
            except Exception as e:
                logging.error(f"Error populating save slot '{slot_id}': {e}", exc_info=True)
                # Add a fallback label for this slot
                fallback_label = Label(
                    text=f"{slot_id.replace('_', ' ').capitalize()} {color_text('(Error)', 'error')}",
                    markup=True, font_name=DEFAULT_FONT_REGULAR_NAME,
                    size_hint_y=None, height=dp(60)
                )
                self.slots_layout.add_widget(fallback_label)

    def confirm_save(self, slot_identifier): #
        gs = self.manager.get_screen('game') #
        if gs and gs.game_logic: #
            save_response = gs.game_logic._command_save(slot_identifier) #
            self.status_label.text = save_response.get("message", "Save status unknown.") #
            if save_response.get("success"): #
                self.populate_save_slots() #
        else: #
            self.status_label.text = color_text("Cannot save: No active game logic.", 'error')

    def confirm_delete_popup(self, slot_identifier):
        content = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(10))
        content.add_widget(Label(text=f"Really delete save slot '{slot_identifier.replace('_',' ').capitalize()}'?\nThis cannot be undone.",
                                 font_name=DEFAULT_FONT_REGULAR_NAME, halign='center'))
        
        buttons_layout = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10))
        
        yes_btn = Button(text="Yes, Delete", font_name=DEFAULT_FONT_BOLD_NAME)
        yes_btn.bind(on_release=lambda x: self.do_delete_save(slot_identifier))
        
        no_btn = Button(text="No, Cancel", font_name=DEFAULT_FONT_BOLD_NAME)
        
        buttons_layout.add_widget(yes_btn)
        buttons_layout.add_widget(no_btn)
        content.add_widget(buttons_layout)

        self.popup = Popup(title="Confirm Deletion", content=content,
                           size_hint=(0.7, 0.4), auto_dismiss=False)
        no_btn.bind(on_release=self.popup.dismiss)
        self.popup.open()

    def do_delete_save(self, slot_identifier):
        if hasattr(self, 'popup') and self.popup:
            self.popup.dismiss()
            self.popup = None

        gs = self.manager.get_screen('game')
        if gs and gs.game_logic:
            delete_response = gs.game_logic.delete_save_game(slot_identifier)
            self.status_label.text = delete_response.get("message", "Delete status unknown.")
            if delete_response.get("success"):
                self.populate_save_slots() # Refresh the list
        else:
            self.status_label.text = color_text("Cannot delete: No active game logic.", 'error')

class LoadGameScreen(BaseScreen):
    def __init__(self, **kwargs):
        self.resource_manager = kwargs.pop('resource_manager', None)
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(10))
        layout.add_widget(Label(text="[b]Load Game[/b]", markup=True, font_name=DEFAULT_FONT_BOLD_NAME, size_hint_y=0.1, font_size=dp(24)))
        
        # ScrollView for load slots (Ensure this structure is used if not already)
        scroll_view = ScrollView(size_hint_y=0.7)
        self.slots_layout = BoxLayout(orientation='vertical', spacing=dp(5), size_hint_y=None)
        self.slots_layout.bind(minimum_height=self.slots_layout.setter('height'))
        scroll_view.add_widget(self.slots_layout)
        layout.add_widget(scroll_view)

        self.status_label = Label(text="", markup=True, font_name=DEFAULT_FONT_REGULAR_NAME, size_hint_y=0.1, font_size=dp(16))
        layout.add_widget(self.status_label)
        
        # This button's text and action will be set in on_enter
        self.btn_back_dynamic = Button(
            font_name=DEFAULT_FONT_BOLD_NAME,
            size_hint_y=0.1, # Consistent with other screens
            height=dp(50)    # Consistent height
        )
        layout.add_widget(self.btn_back_dynamic)
        
        self.add_widget(layout)

    def on_enter(self, *args): 
        self.populate_load_slots()
        self.status_label.text = "Select a slot to load."

        game_screen = self.manager.get_screen('game')
        # Check if a game session is active and GameLogic is initialized in GameScreen
        if game_screen and getattr(game_screen, 'game_started', False) and getattr(game_screen, 'game_logic', None) is not None:
            self.btn_back_dynamic.text = "< Back to Game"
            self.btn_back_dynamic.unbind(on_release=None)  # Clear previous bindings
            self.btn_back_dynamic.bind(on_release=self._go_to_game_screen_action)
        else:
            self.btn_back_dynamic.text = "< Back to Title"
            self.btn_back_dynamic.unbind(on_release=None)  # Clear previous bindings
            self.btn_back_dynamic.bind(on_release=self._go_to_title_screen_action)

    def _go_to_game_screen_action(self, instance):
        """Helper method to navigate to the game screen."""
        self.go_to_screen('game', 'right')

    def _go_to_title_screen_action(self, instance):
        """Helper method to navigate to the title screen."""
        self.go_to_screen('title', 'right')


    def populate_load_slots(self):
        self.slots_layout.clear_widgets()
        slots_to_show = ["quicksave"] + [f"slot_{i}" for i in range(1, 5 + 1)]
        found_any_saves = False

        # --- THE REFACTORED LOGIC ---
        # No longer creates a temporary GameLogic instance.
        # It now calls the standalone utility function we moved to utils.py.
        for slot_id in slots_to_show:
            preview_info = get_save_slot_info(slot_id)
        # --- END OF REFACTOR ---
            
            display_text = f"{slot_id.replace('_', ' ').capitalize()}"
            if preview_info:
                found_any_saves = True
                if preview_info.get("corrupted"):
                    display_text += color_text(" (Corrupted - Cannot Load)", 'error')
                    btn = Label(
                        text=display_text, markup=True, font_name=DEFAULT_FONT_REGULAR_NAME,
                        size_hint_y=None, height=dp(60),
                        halign='left', padding_x=dp(10), color=get_color_from_hex('aaaaaa')  # Use canonical 'light_grey'
                    )
                    btn.text_size = (self.width * 0.8, None)
                else:
                    loc = preview_info.get('location', '?')
                    ts = preview_info.get('timestamp', 'No date')
                    char_class = preview_info.get('character_class', '')
                    turns = preview_info.get('turns_left', '')
                    display_text += f" - {char_class}, {loc} (Turns: {turns})\n   {ts}"
                    btn = Button(text=display_text, markup=True, font_name=DEFAULT_FONT_REGULAR_NAME, 
                                 size_hint_y=None, height=dp(60),
                                 halign='left', padding_x=dp(10))
                    btn.text_size = (self.width * 0.8, None) 
                    btn.bind(on_release=lambda x, s_id=slot_id: self.load_game_action(s_id))
                self.slots_layout.add_widget(btn)
            else: 
                 empty_slot_label = Label(
                     text=f"{display_text} {color_text('(Empty Slot)', 'light_grey')}",
                     markup=True, font_name=DEFAULT_FONT_REGULAR_NAME, 
                     size_hint_y=None, height=dp(60), color=(0.7,0.7,0.7,1))
                 empty_slot_label.text_size = (self.width * 0.8, None)
                 self.slots_layout.add_widget(empty_slot_label)

        if not found_any_saves: 
            self.slots_layout.add_widget(Label(
                text="No save games found.", font_name=DEFAULT_FONT_REGULAR_NAME, 
                size_hint_y=None, height=dp(50)
            ))

    def load_game_action(self, slot_identifier):
        game_screen = self.manager.get_screen('game') #
        if game_screen:
            game_screen.pending_load = True #
            game_screen.load_slot_identifier = slot_identifier  #
            
            self.status_label.text = f"Preparing to load game from '{slot_identifier}'..." #
            
            Clock.schedule_once(lambda dt: self.go_to_screen('game', 'left'), 0.2) #
        else: 
            self.status_label.text = color_text("Critical Error: Game screen not found.", 'error')

class EvadedHazardEntry(RecycleDataViewBehavior, Label):
    """ Displays a single evaded hazard. """
    index = None
    selected = BooleanProperty(False)
    selectable = BooleanProperty(True)

    def refresh_view_attrs(self, rv, index, data):
        ''' Catch and handle the view changes '''
        self.index = index
        self.text = data.get('text', '')
        self.markup = True
        self.font_name = DEFAULT_FONT_REGULAR_NAME
        self.font_size = dp(14)
        self.halign = 'left'
        self.valign = 'top'
        self.text_size = (rv.width * 0.9, None) # Ensure wrapping
        self.size_hint_y = None
        self.height = self.texture_size[1] + dp(10) # Add padding
        return super(EvadedHazardEntry, self).refresh_view_attrs(rv, index, data)

    def on_touch_down(self, touch):
        ''' Add selection on touch down '''
        if super(EvadedHazardEntry, self).on_touch_down(touch):
            return True
        if self.collide_point(*touch.pos) and self.selectable:
            return self.parent.select_with_touch(self.index, touch)

    def apply_selection(self, rv, index, is_selected):
        ''' Respond to a selection change. '''
        self.selected = is_selected
        # You can change background color or something on selection if desired
   
    def proceed_to_next_level(self, instance):
        """
        Handles transition to the next level, win screen, or title screen.
        Ensures GameLogic and UI state are updated appropriately.
        """
        app = App.get_running_app()
        app.start_new_session_flag = False  # Always continuing, not starting fresh

        # If there is a next level, go to the game screen (GameLogic state should already be set)
        if getattr(self, 'next_level_id', None):
            self.go_to_screen('game', direction='left')
            return

        # If there is no next level, check if the game was won
        game_logic = getattr(app, 'game_logic', None)
        if game_logic and getattr(game_logic, 'game_won', False):
            self.go_to_screen('win', direction='fade')
        else:
            # No next level and not explicitly won (e.g., end of content)
            self.go_to_screen('title', direction='right')


class InterLevelScreen(BaseScreen):
    def __init__(self, **kwargs):
        self.resource_manager = kwargs.pop('resource_manager', None)
        super().__init__(**kwargs)
        self.next_level_id = None
        self.next_level_start_room = None
        self.logger = logging.getLogger(__name__ + ".InterLevelScreen")

        layout = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(15))
        
        # Use canonical color from constants/colors system
        app = App.get_running_app()
        color_green_hex = '00ff00' # Default
        if app and getattr(app, 'resource_manager', None):
            constants = app.resource_manager.get_data('constants', {}) or {}
            color_green_hex = constants.get('COLORS', {}).get('GREEN', '00ff00')
        
        self.title_label = Label(
            text="[b]Level Complete![/b]", markup=True,
            font_name=THEMATIC_FONT_NAME, font_size=dp(32),
            size_hint_y=None, height=dp(45), color=get_color_from_hex(color_green_hex)
        )
        layout.add_widget(self.title_label)

        self.narrative_label = Label(
            text="Loading transition...", markup=True, font_name=DEFAULT_FONT_REGULAR_NAME,
            font_size=dp(16), size_hint_y=0.2, halign='center', valign='top',
            padding=(dp(5), dp(5))
        )
        self.narrative_label.bind(width=lambda i, w: setattr(i, 'text_size', (w * 0.9, None)))
        layout.add_widget(self.narrative_label)
        
        stats_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(30), spacing=dp(10))
        self.score_label = Label(text="Score: --", markup=True, font_name=DEFAULT_FONT_BOLD_NAME, font_size=dp(15))
        self.turns_taken_label = Label(text="Turns This Level: --", markup=True, font_name=DEFAULT_FONT_BOLD_NAME, font_size=dp(15))
        self.evidence_count_label = Label(text="Evidence Found: --", markup=True, font_name=DEFAULT_FONT_BOLD_NAME, font_size=dp(15))
        stats_layout.add_widget(self.score_label)
        stats_layout.add_widget(self.turns_taken_label)
        stats_layout.add_widget(self.evidence_count_label)
        layout.add_widget(stats_layout)

        layout.add_widget(Label(
            text="[u]Hazards Evaded This Level:[/u]", markup=True,
            font_name=DEFAULT_FONT_BOLD_NAME, font_size=dp(17),
            size_hint_y=None, height=dp(25), padding=(0, dp(5))
        ))

        self.rv = RecycleView(size_hint=(1, 0.45), scroll_type=['bars', 'content'])
        self.rv.viewclass = EvadedHazardEntry
        self.rv_layout = RecycleBoxLayout(orientation='vertical', size_hint_y=None,
                                          default_size=(None, dp(45)), default_size_hint=(1, None),
                                          padding=dp(10), spacing=dp(5))
        self.rv_layout.bind(minimum_height=self.rv_layout.setter('height'))
        self.rv.add_widget(self.rv_layout)
        layout.add_widget(self.rv)

        self.continue_button = Button(
            text="Continue to Next Area", font_name=DEFAULT_FONT_BOLD_NAME,
            size_hint_y=None, height=dp(50), font_size=dp(18)
        )
        self.continue_button.bind(on_release=self.proceed_to_next_level)
        layout.add_widget(Widget(size_hint_y=0.05)) # Spacer
        layout.add_widget(self.continue_button)
        self.add_widget(layout)

    def on_enter(self, *args):
        app = App.get_running_app()
        rm = getattr(app, 'resource_manager', None) or self.resource_manager

        # Prefer canonical live data from GameLogic
        gl = getattr(app, 'game_logic', None)
        try:
            # 1) Narrative, stats, next level info
            level_data = {}
            if hasattr(app, 'interlevel_narrative_text') and getattr(app, 'interlevel_narrative_text', None):
                # Use the values prepared by GameScreen if present
                self.title_label.text = "[b]Level Complete![/b]"
                self.narrative_label.text = color_text(getattr(app, 'interlevel_narrative_text', "You survived. Take a breath..."), 'special', rm)
                self.score_label.text = f"Score: {getattr(app, 'interlevel_score_for_level', 0)}"
                self.turns_taken_label.text = f"Turns This Level: {getattr(app, 'interlevel_turns_taken_for_level', 0)}"
                self.evidence_count_label.text = f"Evidence Found: {getattr(app, 'interlevel_evidence_found_for_level_count', 0)}"
                self.next_level_id = getattr(app, 'interlevel_next_level_id', None)
                self.next_level_start_room = getattr(app, 'interlevel_next_start_room', None)
            else:
                # Recompute from live state (canonical)
                if gl and hasattr(gl, 'get_level_completion_data'):
                    level_data = gl.get_level_completion_data() or {}
                narrative = level_data.get('narrative', 'You survived this area.')
                self.title_label.text = "[b]Level Complete![/b]"
                try:
                    self.narrative_label.text = color_text(narrative, 'special', rm)
                except Exception:
                    self.narrative_label.text = narrative

                # Live stats from player
                player = getattr(gl, 'player', {}) if gl else {}
                score = int(player.get('score', 0))
                turns_taken = int(player.get('actions_taken', 0))
                inv = player.get('inventory', []) or []
                evaded = player.get('evaded_hazards', []) or []

                self.score_label.text = f"Score: {score}"
                self.turns_taken_label.text = f"Turns This Level: {turns_taken}"
                self.evidence_count_label.text = f"Evidence Found: {len(inv) if isinstance(inv, (list, dict)) else 0}"
                self.next_level_id = level_data.get('next_level_id')
                self.next_level_start_room = level_data.get('next_start_room')

                # Mirror values to App for consistency if needed later
                try:
                    app.interlevel_evaded_hazards = evaded
                except Exception:
                    pass

            # 2) Populate hazards from live player state
            self.populate_evaded_hazards()
        except Exception as e:
            self.logger.error(f"InterLevelScreen.on_enter error: {e}", exc_info=True)

    def populate_evaded_hazards(self):
        """Populate the RecycleView with evaded hazards data."""
        try:
            app = App.get_running_app()
            gl = getattr(app, 'game_logic', None)
            # Prefer live canonical player state
            evaded_hazards = []
            if gl and isinstance(getattr(gl, 'player', None), dict):
                evaded_hazards = gl.player.get('evaded_hazards', []) or []
            # Fallback to App stash if live not available
            if not evaded_hazards:
                evaded_hazards = getattr(app, 'interlevel_evaded_hazards', []) or []

            if not evaded_hazards:
                self.rv.data = [{'text': '[i]No hazards were encountered this level.[/i]'}]
                return

            hazard_data = []
            for hazard in evaded_hazards:
                if isinstance(hazard, dict):
                    hazard_name = hazard.get('name', 'Unknown Hazard')
                    hazard_desc = hazard.get('description', 'Successfully evaded.')
                    display_text = f"[b]{hazard_name}[/b]\n{hazard_desc}"
                else:
                    display_text = str(hazard)
                hazard_data.append({'text': display_text})

            self.rv.data = hazard_data
        except Exception as e:
            self.logger.error(f"populate_evaded_hazards error: {e}", exc_info=True)
            self.rv.data = [{'text': '[i]No hazards available.[/i]'}]

    def on_continue_pressed(self, *_):
        app = App.get_running_app()
        if getattr(self, 'game_logic', None) and self.next_level_id:
            self.game_logic.start_next_level(self.next_level_id, self.next_level_start_room)
        self.go_to_screen('game', 'right')

    def proceed_to_next_level(self, instance):
        app = App.get_running_app()
        game_screen = self.manager.get_screen('game')

        if self.next_level_id and game_screen and game_screen.game_logic:
            self.logger.info(f"InterLevelScreen: Proceeding to level {self.next_level_id}.")
            start_room = self.next_level_start_room or None
            try:
                # Use the API that exists today
                game_screen.game_logic.start_next_level(self.next_level_id, start_room)
            except Exception as e:
                self.logger.error(f"InterLevelScreen: Failed to start next level: {e}", exc_info=True)
            self.go_to_screen('game', direction='left')
        else:
            self.logger.info("InterLevelScreen: No next level ID found. Proceeding to WinScreen.")
            if game_screen and game_screen.game_logic:
                app.last_game_score = getattr(game_screen.game_logic, 'player', {}).get('score', 0)
            self.go_to_screen('win', direction='fade')
            
# --- Win Screen ---
class WinScreen(BaseScreen):
    def __init__(self, **kwargs):
        self.resource_manager = kwargs.pop('resource_manager', None)
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(20),
                           # Add background for this specific screen if desired
                           # canvas_before=[Color(0.1, 0.3, 0.1, 1), Rectangle(size=self.size, pos=self.pos)]
                           )
        # self.bind(size=self._update_bg_rect, pos=self._update_bg_rect) # If adding custom bg

        layout.add_widget(Label(
            text=f"[b][color=00ff00]Demo cleared![/color][/b]", 
            markup=True, font_name=THEMATIC_FONT_NAME, font_size=dp(34) # Larger thematic font
        ))
        self.score_display = Label(text="Final Score: 0", font_name=DEFAULT_FONT_BOLD_NAME, font_size=dp(22))
        layout.add_widget(self.score_display)
        
        # Add a congratulatory message or flavor text
        flavor_text = Label(
            text="Your friendly neighborhood developer, KorbenD3P0, is hard at work bringing you the complete game! Stay tuned for upcoming features, including:\nPlayable intro disasters! More hazards! An ending!\nPlus, a collectable item for every FD character you know\n-and some for a few you may NOT!\n\nThank you for playing this demo version of 'FDT - Final Destination: Terminal'! Your support and feedback are invaluable as I continue to develop the full experience.",
            font_name=DEFAULT_FONT_REGULAR_NAME, font_size=dp(16), markup=True,
            halign='center', text_size=(Window.width*0.7, None) # Enable wrapping
        )
        flavor_text.bind(width=lambda i, w: setattr(i, 'text_size', (w*0.8, None))) # Adjust text_size on width change
        layout.add_widget(flavor_text)

        btn_main_menu = Button(
            text="Return to Main Menu", font_name=DEFAULT_FONT_BOLD_NAME, 
            size_hint_y=None, height=dp(50), font_size=dp(18),
            on_release=lambda x: self.go_to_screen('title','right')
        )
        layout.add_widget(Widget(size_hint_y=0.1)) # Spacer
        layout.add_widget(btn_main_menu)
        self.add_widget(layout)

    def on_enter(self, *args):
        app = App.get_running_app()
        try:
            # Prefer live score from GameLogic
            gl = getattr(app, 'game_logic', None)
            if gl and isinstance(getattr(gl, 'player', None), dict):
                score = int(gl.player.get('score', getattr(app, 'last_game_score', 0)))
            else:
                score = getattr(app, 'last_game_score', 0)
            self.score_display.text = f"Final Score: {score}"
        except Exception as e:
            logging.getLogger(__name__).error(f"WinScreen.on_enter error: {e}", exc_info=True)
            self.score_display.text = f"Final Score: {getattr(app, 'last_game_score', 0)}"

# --- Lose Screen ---

class LoseScreen(BaseScreen):
    def __init__(self, **kwargs):
        self.resource_manager = kwargs.pop('resource_manager', None)
        super().__init__(**kwargs)
        
        root_scrollview = ScrollView(size_hint=(1, 1))
        layout = GridLayout(cols=1, padding=dp(30), spacing=dp(20), size_hint_y=None)
        layout.bind(minimum_height=layout.setter('height'))

        # --- WIDGET DEFINITIONS ---
        # 1. Main Title Label (choose randomly from a pool)
        GAME_OVER_TITLE_LABELS = [
            "[b][color={COLOR_RED}]DEATH HAS CLAIMED YOU[/color][/b]",
            "[b][color={COLOR_RED}]YOUR FINAL DESTINATION[/color][/b]",
            "[b][color={COLOR_RED}]THE DESIGN WAS FLAWLESS[/color][/b]",
            "[b][color={COLOR_RED}]YOU WERE ON THE LIST[/color][/b]",
            "[b][color={COLOR_RED}]THE BLUEPRINT WAS COMPLETED[/color][/b]",
            "[b][color={COLOR_RED}]THE SHADOWS HAVE WON[/color][/b]",
            "[b][color={COLOR_RED}]THE END HAS COME[/color][/b]",
            "[b][color={COLOR_RED}]DEATH ALWAYS COLLECTS[/color][/b]",
            "[b][color={COLOR_RED}]THE UNIVERSE CLAIMED ITS DUE[/color][/b]",
            "[b][color={COLOR_RED}]THE FINAL CALCULATION[/color][/b]",
        ]
        # Use canonical color from constants/colors system
        app = App.get_running_app()
        color_red_hex = getattr(app, 'resource_manager', None)
        if color_red_hex:
            color_red_hex = app.resource_manager.get_data('constants', {}).get('COLORS', {}).get('RED', 'ff0000')
        else:
            color_red_hex = 'ff0000'
        title_label_text = random.choice(GAME_OVER_TITLE_LABELS).format(
            COLOR_RED=color_red_hex
        )
        title_label = Label(
            text=title_label_text,
            markup=True, 
            font_name=THEMATIC_FONT_NAME, 
            font_size=dp(30),
            size_hint_y=None
        )
        title_label.bind(texture_size=title_label.setter('size'))
        layout.add_widget(title_label)
        
        # 2. Cause of Death Label
        self.death_reason_label = Label(
            font_name=DEFAULT_FONT_REGULAR_NAME, 
            font_size=dp(18), 
            markup=True,
            halign='center',
            size_hint_y=None
        )
        self.death_reason_label.bind(width=lambda instance, value: setattr(instance, 'text_size', (value, None)))
        self.death_reason_label.bind(texture_size=self.death_reason_label.setter('size'))
        layout.add_widget(self.death_reason_label)

        # 3. Final Narrative Label
        self.final_narrative_label = Label(
            markup=True,
            font_name=DEFAULT_FONT_REGULAR_NAME,
            font_size=dp(18),
            halign='center',
            valign='center',
            size_hint_y=None
        )
        self.final_narrative_label.bind(width=lambda i, w: setattr(i, 'text_size', (w, None)))
        self.final_narrative_label.bind(texture_size=self.final_narrative_label.setter('size'))
        layout.add_widget(self.final_narrative_label)

        # 5. Return Button
        btn_main_menu = Button(
            text="Return to Main Menu", 
            font_name=DEFAULT_FONT_BOLD_NAME, 
            size_hint_y=None, 
            height=dp(50),
            font_size=dp(18),
            on_release=lambda x: self.go_to_screen('title','right')
        )
        layout.add_widget(btn_main_menu)
        
        root_scrollview.add_widget(layout)
        self.add_widget(root_scrollview)

    def on_enter(self, *args):
        app = App.get_running_app()
        try:
            gl = getattr(app, 'game_logic', None)
            # Prefer canonical live death reason + narrative from GameLogic
            reason = None
            final_narrative = None
            if gl and isinstance(getattr(gl, 'player', None), dict):
                reason = gl.player.get('death_reason') or getattr(app, 'last_death_reason', None)
                # Use the canonical composer, fallback to stashed app text
                try:
                    if hasattr(gl, 'get_death_narrative'):
                        final_narrative = gl.get_death_narrative()
                except Exception:
                    final_narrative = None
            # Fallbacks
            if not reason:
                reason = getattr(app, 'last_death_reason', "The design caught up with you.")
            if not final_narrative:
                final_narrative = getattr(app, 'last_game_output_narrative', "")

            self.death_reason_label.text = f"Cause of Death:\n{reason}"
            self.final_narrative_label.text = final_narrative
        except Exception as e:
            logging.getLogger(__name__).error(f"LoseScreen.on_enter error: {e}", exc_info=True)
            # Minimal fallback
            self.death_reason_label.text = f"Cause of Death:\n{getattr(app, 'last_death_reason', 'Unknown')}"
            self.final_narrative_label.text = getattr(app, 'last_game_output_narrative', '')

class GameScreen(BaseScreen):
    status_display = ObjectProperty(None)
    output_panel = ObjectProperty(None)
    action_input = ObjectProperty(None)
    main_actions = ObjectProperty(None)
    contextual_actions = ObjectProperty(None)

    def __init__(self, **kwargs):
        self.resource_manager = kwargs.pop('resource_manager', None)
        kwargs.pop('achievements_system', None)
        kwargs.pop('hazard_engine', None)
        kwargs.pop('death_ai', None)
        super().__init__(**kwargs)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.game_logic = None
        self.active_qte_popup = None
        self.active_info_popup = None
        # NEW: track current overlay instructions and last popup signature to suppress duplicates
        self._low_health_color = None
        self._low_health_rect = None
        self._low_health_pulse_ev = None
        self._last_popup_sig = None
        # NEW: lock VFX while a popup is open that intentionally shows them
        self._popup_vfx_lock = {"fear": False, "damage": False}
        # Thresholds (could read from game_config if you prefer)
        self._fear_hold_threshold = 0.6
        Clock.schedule_interval(self._update, 1/60.0)

    def _get_widget(self, name: str):
        return (getattr(self, name, None)
                or self.ids.get(name)
                or self.ids.get(f"{name}_id"))

    def _update(self, dt):
        """The main UI update loop, driven by the Clock."""
        if self.game_logic:
            # Check for any signals from the engine
            events = self.game_logic.get_ui_events()
            if events:
                self._handle_ui_events(events)

    def on_pre_enter(self, *args):
        """Attach engine references before any UI events or input occur."""
        app = App.get_running_app()

        # --- FORCE REBIND: always use the latest session's engines ---
        try:
            # Always rebind GameLogic from App (prevents stale/stuck sessions)
            self.game_logic = getattr(app, 'game_logic', None)

            # Also refresh engine cross-links every time
            if self.game_logic:
                # Ensure GL <-> engines are consistent
                hz = getattr(app, 'hazard_engine', None)
                da = getattr(app, 'death_ai', None)
                qte = getattr(app, 'qte_engine', None)

                self.game_started = True
                self.game_logic.hazard_engine = hz
                self.game_logic.death_ai = da
                self.game_logic.qte_engine = qte

                if hz and getattr(hz, 'game_logic', None) is not self.game_logic:
                    hz.game_logic = self.game_logic

                # Clear any lingering QTE flags from old overlays
                try:
                    if isinstance(self.game_logic.player, dict):
                        self.game_logic.player['qte_active'] = False
                        self.game_logic.player['qte_context'] = {}
                except Exception:
                    pass
            else:
                self.game_started = False
        except Exception as e:
            self.logger.error(f"GameScreen.on_pre_enter: rebind failed: {e}", exc_info=True)

        self.logger.info("GameScreen: Engine references attached.")

    def on_enter(self, *args):
        try:
            if not self.game_logic:
                out = self._get_widget('output_panel')
                if out and hasattr(out, 'append_text'):
                    out.append_text("[color=ff4444]Engine not initialized. Return to main menu.[/color]")
                return

            # Ensure start_response is set before switching to GameScreen
            if not getattr(self.game_logic, 'start_response', None):
                try:
                    # Use rich room description for initial output
                    location = self.game_logic.player.get('location', '')
                    initial_desc = self.game_logic._get_rich_room_description(location)
                    # PATCH: Check for first_entry_text and add popup event
                    room_data = self.game_logic.get_room_data(location) or {}
                    ui_events = []
                    first_text = room_data.get('first_entry_text')
                    if first_text:
                        ui_events.append(self.game_logic._make_first_entry_popup_event(location, first_text))
                    
                    start_resp = {
                        'game_state': self.game_logic.get_current_game_state() if hasattr(self.game_logic, 'get_current_game_state') else {},
                        'messages': [initial_desc] if initial_desc else [],
                        'ui_events': ui_events
                    }
                    self.game_logic.start_response = start_resp
                except Exception as e:
                    self.logger.error(f"Failed to generate fallback start_response: {e}", exc_info=True)
                    self.game_logic.start_response = {'game_state': {}, 'messages': ["Welcome to the game."], 'ui_events': []}

            # Initial room description from stored start response (if present)
            start_resp = getattr(self.game_logic, 'start_response', None)
            room_desc = ""
            if start_resp:
                # Always use rich room description for output
                location = self.game_logic.player.get('location', '')
                room_desc = self.game_logic._get_rich_room_description(location)
                
                # PATCH: Process UI events from start_response (including first_entry_text popup)
                ui_events = start_resp.get('ui_events', [])
                if ui_events:
                    for event in ui_events:
                        self._handle_ui_events(ui_events)
            
            panel = self._get_widget('output_panel')
            if panel and hasattr(panel, 'append_text') and room_desc:
                panel.append_text(room_desc, clear_previous=True)

            ai = self._get_widget('action_input')
            if ai:
                if hasattr(ai, 'submit_button'):
                    ai.submit_button.unbind(on_release=self.on_submit_command)
                    ai.submit_button.bind(on_release=self.on_submit_command)
                if hasattr(ai, 'text_input'):
                    ai.text_input.unbind(on_text_validate=self.on_submit_command)
                    ai.text_input.bind(on_text_validate=self.on_submit_command)
                    ai.text_input.focus = True

            # Update map display
            map_widget = self._get_widget('map_display')
            if map_widget and hasattr(map_widget, 'update'):
                try:
                    map_string = self.game_logic.get_gui_map_string()
                    map_widget.update(map_string)
                except Exception as e:
                    self.logger.error(f"Failed to update map: {e}", exc_info=True)
                    map_widget.update("Map unavailable")

            self._populate_main_action_buttons()
            self.update_all_ui_elements(self.game_logic.get_current_game_state())
        except Exception as e:
            self.logger.error(f"_update_widgets error: {e}", exc_info=True)
            
    def update_all_ui_elements(self, game_state: dict):
        status = self._get_widget('status_display')
        if status and hasattr(status, 'update'):
            status.update(game_state.get('player', {}))
        else:
            self.logger.warning("GameScreen: status_display not wired.")
        # Keep the low-health VFX in sync with current HP/max_hp
        try:
            player = (game_state or {}).get('player', {}) or {}
            hp = int(player.get('hp', 0))
            max_hp = int(player.get('max_hp', 30))
            threshold = max(5, int(max_hp * 0.15))
            if 0 < hp <= threshold:
                self.show_low_health_effect()
            else:
                # Do not clear if a popup is forcing damage VFX
                if not self._popup_vfx_lock.get("damage"):
                    self.clear_low_health_effect()
        except Exception:
            pass
        # Fear VFX sync
        try:
            player = (game_state or {}).get('player', {}) or {}
            fear_val = float(player.get('fear', 0.0))
            # While popup lock is on, keep it forced; otherwise normal rules
            self.show_fear_effect(fear_val, force_override=self._popup_vfx_lock.get("fear", False))
            if not self._popup_vfx_lock.get("fear", False) and fear_val < 0.15:
                self.clear_fear_effect()
        except Exception:
            pass

    def _refresh_map(self):
        try:
            if not self.game_logic: return
            map_widget = self._get_widget('map_display')
            if map_widget and hasattr(map_widget, 'update'):
                map_widget.update(self.game_logic.get_gui_map_string())
        except Exception as e:
            self.logger.error(f"_refresh_map failed: {e}", exc_info=True)

    # --- NEW: The UI Event Handler ---
    def on_qte_input_submit(self, user_input):
        """Handle QTE input submission from QTEPopup - supports all QTE types and events, with robust logging."""
        self.logger.debug(f"on_qte_input_submit called with input: {user_input!r}")
        if not self.game_logic or not getattr(self.game_logic, 'qte_engine', None):
            self.logger.error("GameLogic or QTE engine not available in on_qte_input_submit")
            return

        # Route structured QTE events through GameLogic (the Conductor) and stop
        if isinstance(user_input, dict):
            try:
                result = self.game_logic.process_player_input(user_input)
            except Exception as e:
                self.logger.error(f"on_qte_input_submit: error routing dict to GameLogic: {e}", exc_info=True)
                return

            # Apply result immediately
            if isinstance(result, dict):
                out = self._get_widget('output_panel')
                for m in result.get('messages', []):
                    if out and hasattr(out, 'append_text'):
                        out.append_text(m)
                self.update_all_ui_elements(result.get('game_state', {}))
                self._handle_ui_events(result.get('ui_events', []))
            return

        # Fallback: string QTE input (rare; most QTEs send dict events)
        if isinstance(user_input, str):
            try:
                result = self.game_logic.process_player_input(user_input)
            except Exception as e:
                self.logger.error(f"on_qte_input_submit: error routing string to GameLogic: {e}", exc_info=True)
                return
            if isinstance(result, dict):
                out = self._get_widget('output_panel')
                for m in result.get('messages', []):
                    if out and hasattr(out, 'append_text'):
                        out.append_text(m)
                self.update_all_ui_elements(result.get('game_state', {}))
                self._handle_ui_events(result.get('ui_events', []))
            return

    def _normalize_ui_events(self, events):
        """Accept list/dict and unwrap common containers to a flat list of UI events."""
        if not events:
            return []
        # If a dict container with 'consequences' was accidentally pushed to UI, unwrap it
        if isinstance(events, dict) and 'consequences' in events and not events.get('event_type') and not events.get('type'):
            cons = events.get('consequences') or []
            return cons if isinstance(cons, list) else [cons]
        # If already a list, return as-is
        if isinstance(events, list):
            return events
        # Anything else, wrap to list
        return [events]

    def _synthesize_deferred_qte_if_missing(self, event: dict) -> Optional[dict]:
        """If a popup has no defer fields but references a state that triggers a QTE, synthesize on_close_start_qte."""
        try:
            meta = event.get("meta") or {}
            hid = meta.get("hazard_id")
            state = meta.get("state")
            if not (hid and state and self.game_logic and self.game_logic.hazard_engine):
                return None
            h = self.game_logic.hazard_engine.active_hazards.get(hid)
            sdef = ((h or {}).get("master_data") or {}).get("states", {}).get(state, {})
            qte_entry = sdef.get("triggers_qte_on_entry")
            if not qte_entry:
                return None
            qte_ctx = dict(qte_entry.get("qte_context") or {})
            qte_ctx["qte_source_hazard_id"] = hid
            return {"qte_type": qte_entry.get("qte_type"), "qte_context": qte_ctx}
        except Exception as e:
            self.logger.error(f"_synthesize_deferred_qte_if_missing error: {e}", exc_info=True)
            return None

    def _bind_popup_defers(self, popup, event: dict):
        """Bind deferred actions to popup dismissal with robust fallback."""
        deferred_qte = event.get("on_close_start_qte")
        defer_state = event.get("on_close_set_hazard_state")
        emit_events = event.get("on_close_emit_ui_events")
        vfx_hint = event.get("vfx_hint")

        def on_dismiss(*_):
            # Before defers: clear popup-scoped VFX if thresholds do not demand persistence
            try:
                player = (self.game_logic.get_current_game_state().get('player', {})
                            if self.game_logic else {})
            except Exception:
                player = (self.game_logic.player if self.game_logic else {}) or {}

            if vfx_hint == "damage":
                # Keep if HP remains below threshold, else clear
                hp = int(player.get('hp', 0))
                max_hp = int(player.get('max_hp', 30))
                low_thr = max(5, int(max_hp * 0.15))
                if not (0 < hp <= low_thr):
                    self.clear_low_health_effect()
                self._popup_vfx_lock["damage"] = False

            if vfx_hint == "fear":
                fear_val = float(player.get('fear', 0.0))
                # Keep if fear high enough, else clear
                if fear_val < self._fear_hold_threshold:
                    self.clear_fear_effect()
                self._popup_vfx_lock["fear"] = False

            # --- existing deferred QTE/state/UI flow ---
            if deferred_qte and self.game_logic and self.game_logic.qte_engine:
                qte_type = deferred_qte.get('qte_type')
                qte_ctx = deferred_qte.get('qte_context', {})
                try:
                    self.logger.info(f"Starting deferred QTE '{qte_type}' after popup")
                    self.game_logic.qte_engine.start_qte(qte_type, qte_ctx)
                    return
                except Exception as e:
                    self.logger.error(f"Failed to start deferred QTE '{qte_type}': {e}", exc_info=True)

            if defer_state and self.game_logic and self.game_logic.hazard_engine:
                hid = defer_state.get("hazard_id")
                t_state = defer_state.get("target_state")
                try:
                    self.logger.info(f"Applying deferred state change: {hid} -> {t_state}")
                    result = self.game_logic.hazard_engine.set_hazard_state(hid, t_state)
                    cons = (result or {}).get("consequences", [])
                    if cons:
                        self._handle_consequences_sequentially(cons)
                        return
                except Exception as e:
                    self.logger.error(f"Error applying deferred hazard state: {e}", exc_info=True)

            if emit_events and self.game_logic:
                for ev in emit_events:
                    self.game_logic.add_ui_event(ev)

            self.active_info_popup = None

        popup.bind(on_dismiss=on_dismiss)

    def _handle_ui_events(self, events):
        """
        Orchestrator for UI event processing with normalization, prioritization, and delegation.
        Delegates to small helpers with robust logging and error handling.
        """
        if not events:
            return

        try:
            # 1. Normalize and validate events
            events = self._normalize_ui_events(events)
            valid_events = [e for e in events if isinstance(e, dict)]
            sorted_events = sorted(valid_events, key=lambda e: e.get('priority', 0), reverse=True)
            self.logger.debug(f"_handle_ui_events: Processing {len(sorted_events)} valid events")

            # 2. Track inventory-affecting events for final UI refresh
            inventory_changed = self._process_all_events(sorted_events)

            # 3. Final UI refresh if needed
            if inventory_changed and self.game_logic:
                self.update_all_ui_elements(self.game_logic.get_current_game_state())
        except Exception as e:
            self.logger.error(f"_handle_ui_events: Orchestrator error: {e}", exc_info=True)

    def _process_all_events(self, sorted_events: list) -> bool:
        """
        Process all events in priority order and return True if inventory may have changed.
        Delegates to handler map or fallback processors.
        """
        inventory_affecting_types = {
            "take", "use", "drop", "give", "talk", "talk_to", "talkto", "respond 1", "respond 2", "respond 3",
            "equip", "unequip", "consume", "pickup", "pick_up", "steal", "loot"
        }
        inventory_changed = False

        for event in sorted_events:
            try:
                event_type = event.get('event_type') or event.get('type')
                if not event_type:
                    self.logger.warning(f"_process_all_events: Skipping malformed event (no type): {event!r}")
                    continue

                self.logger.debug(f"_process_all_events: Handling event_type '{event_type}'")

                # Try handler map first
                if self._dispatch_to_handler_map(event_type, event):
                    pass  # Successfully handled
                elif self._try_consequences_fallback(event):
                    pass  # Handled as consequence bundle
                else:
                    self.logger.warning(f"_process_all_events: Unhandled event type '{event_type}'")

                # Mark if inventory-affecting
                if event_type and event_type.lower() in inventory_affecting_types:
                    inventory_changed = True

            except Exception as e:
                self.logger.error(f"_process_all_events: Error processing event {event}: {e}", exc_info=True)

        return inventory_changed

    def _dispatch_to_handler_map(self, event_type: str, event: dict) -> bool:
        """
        Dispatch event to the appropriate handler from the handler map.
        Returns True if handler was found and executed, False otherwise.
        """
        handler_map = {
            "show_popup": lambda e: self._handle_show_popup_with_defers(e),
            "show_qte": self._handle_show_qte,
            "hide_qte": self._handle_hide_qte,
            "qte_finished": self._handle_hide_qte,
            "destroy_qte_popup": self._handle_destroy_qte_popup,
            "game_over": self._handle_game_over,
            "game_won": self._handle_game_won,
            "level_complete": self._handle_level_complete,
            "append_text": self._handle_show_message,
            "show_message": self._handle_show_message,
            "game_loaded": self._handle_game_loaded,
            "refresh_map": lambda e: self._refresh_map(),
            "refresh_ui": lambda e: self._refresh_map(),
            "refresh_context_actions": lambda e: self._handle_refresh_context_actions(),
            "player_damage_effect": lambda e: self.show_damage_effect(),
            "player_low_health_effect": lambda e: self.show_low_health_effect(),
            "player_clear_low_health_effect": lambda e: self.clear_low_health_effect(),
            "player_fear_effect_update": lambda e: self.show_fear_effect(e.get('fear')),
            "go_to_main_menu": lambda e: self._go_to_main_menu_from_game(),
        }

        handler = handler_map.get(event_type)
        if handler:
            try:
                handler(event)
                return True
            except Exception as e:
                self.logger.error(f"_dispatch_to_handler_map: Error handling '{event_type}': {e}", exc_info=True)
                return False
        return False

    def _try_consequences_fallback(self, event: dict) -> bool:
        """
        Fallback: if event has 'consequences' list, pass to sequential processor.
        Returns True if consequences were found and processed.
        """
        if 'consequences' in event and isinstance(event.get('consequences'), list):
            try:
                self._handle_consequences_sequentially(event['consequences'])
                return True
            except Exception as e:
                self.logger.error(f"_try_consequences_fallback: Error handling consequences: {e}", exc_info=True)
        return False

    def _handle_refresh_context_actions(self):
        """
        Refresh contextual actions after game state changes (e.g., container revealed, door unlocked).
        Uses context_dock if present, else falls back to legacy contextual_actions widget.
        """
        try:
            # Prefer context_dock (modern approach)
            if hasattr(self, 'context_dock') and self.context_dock:
                self.context_dock.update(self.game_logic)
                self.logger.info("Refreshed context_dock after game state change")
                return

            # Fallback to legacy contextual_actions widget
            ctx = self._get_widget('contextual_actions')
            if ctx and hasattr(ctx, 'update'):
                ctx.update(self.game_logic)
                self.logger.info("Refreshed contextual_actions widget after game state change")
                return

            self.logger.warning("_handle_refresh_context_actions: No context widget found to refresh")
        except Exception as e:
            self.logger.error(f"_handle_refresh_context_actions: Failed to refresh: {e}", exc_info=True)

    def _go_to_main_menu_from_game(self):
        """
        Reset session and navigate to title from in-game context
        (e.g., after _command_main_menu or any fatal error fallback).
        """
        app = App.get_running_app()
        try:
            if app and hasattr(app, 'reset_session'):
                app.reset_session()
        except Exception:
            pass
        self.go_to_screen('title', direction='right')

    def _collect_unlock_force_targets(self, verb: str) -> list[tuple[str, str]]:
        """
        Build canonical (button_text, command) pairs for unlock/force verbs.
        - unlock: only key-locked exits/furniture.
        - force: key-locked or MRI-locked exits, and locked/forceable/breakable furniture.
        """
        pairs: list[tuple[str, str]] = []
        try:
            gl = self.game_logic
            if not gl:
                return pairs
            room_id = gl.player.get('location')
            room = gl.get_room_data(room_id) or {}

            # Exits
            for direction, dest in (room.get('exits') or {}).items():
                if not isinstance(dest, str):
                    continue  # skip blocked/complex dict exits
                dest_live = gl.current_level_rooms_world_state.get(dest, {}) or {}
                dest_master = gl.get_room_data(dest) or {}
                locking = dest_master.get('locking', {}) if isinstance(dest_master.get('locking'), dict) else {}
                key_locked = bool(locking.get('locked', False))
                mri_locked = bool(dest_live.get('locked_by_mri') or dest_master.get('locked_by_mri'))
                show_unlock = (verb == 'unlock' and key_locked)
                show_force = (verb == 'force' and (key_locked or mri_locked or dest_master.get('forceable')))
                if show_unlock or show_force:
                    btn_text = f"{direction.title()} Door ({dest.replace('_',' ').title()})"
                    pairs.append((btn_text, f"{verb} {direction}"))

            # Furniture
            for f in (room.get('furniture') or []):
                if not isinstance(f, dict):
                    continue
                fname = f.get('name', 'Unknown')
                locking = f.get('locking', {}) if isinstance(f.get('locking'), dict) else {}
                locked = bool(f.get('locked') or locking.get('locked'))
                forceable = bool(f.get('forceable') or f.get('is_breakable'))
                show_unlock = (verb == 'unlock' and locked)
                show_force = (verb == 'force' and (locked or forceable))
                if show_unlock or show_force:
                    pairs.append((fname, f"{verb} {fname}"))
        except Exception as e:
            self.logger.error(f"_collect_unlock_force_targets error: {e}", exc_info=True)
        return pairs

    # --- Simple visual effects for player status ---
    def _update_fx_rect(self, *_):
        """Keep FX overlays sized to the screen."""
        try:
            if hasattr(self, "_damage_rect") and self._damage_rect is not None:
                self._damage_rect.pos = self.pos
                self._damage_rect.size = self.size
            if hasattr(self, "_low_health_rect") and self._low_health_rect is not None:
                self._low_health_rect.pos = self.pos
                self._low_health_rect.size = self.size
            # NEW: keep fear overlay in sync
            if hasattr(self, "_fear_rect") and self._fear_rect is not None:
                self._fear_rect.pos = self.pos
                self._fear_rect.size = self.size
        except Exception:
            pass

    # --- NEW: helper to apply popup-scoped VFX ---
    def _apply_popup_vfx_hint(self, event: dict):
        try:
            hint = (event or {}).get("vfx_hint")
            if not hint:
                return
            if hint == "fear":
                # Force show even if fear below threshold while popup is open
                self._popup_vfx_lock["fear"] = True
                # Use current fear to scale intensity; force overlay visible
                try:
                    fear_val = float(self.game_logic.player.get('fear', 0.0)) if self.game_logic else 0.0
                except Exception:
                    fear_val = 0.0
                self.show_fear_effect(fear_val, force_override=True)
            elif hint == "damage":
                # Force a persistent red pulse while popup is open
                self._popup_vfx_lock["damage"] = True
                self.show_low_health_effect()
        except Exception as e:
            self.logger.error(f"_apply_popup_vfx_hint error: {e}", exc_info=True)

    # --- NEW: Fear pulse overlay (blue), scales with player fear in [0..1] ---
    # --- NEW: adjust fear effect to support forced visibility ---
    def show_fear_effect(self, fear_value: float = None, force_override: bool = False):
        """
        Show or update a blue pulsing overlay whose intensity increases with fear.
        fear_value: 0..1. Clears overlay if below threshold unless force_override=True.
        """
        try:
            if fear_value is None and self.game_logic:
                fear_value = float(self.game_logic.player.get('fear', 0.0))
            fear = max(0.0, min(1.0, float(fear_value or 0.0)))

            # Threshold below which we don't show the effect, unless forced by popup
            if not force_override and fear < 0.15:
                # Respect lock: do not clear if a popup has forced it on
                if not self._popup_vfx_lock.get("fear"):
                    self.clear_fear_effect()
                return

            # ...existing creation/pulse code...
            if not getattr(self, "_fear_color", None) or not getattr(self, "_fear_rect", None):
                with self.canvas.after:
                    self._fear_color = Color(0.15, 0.45, 1.0, 0.0)
                    self._fear_rect = Rectangle(pos=self.pos, size=self.size)
                self.bind(size=self._update_fx_rect, pos=self._update_fx_rect)

            min_alpha = 0.05 + 0.10 * fear
            max_alpha = min(0.45, 0.12 + 0.30 * fear)
            speed = 1.0 + 2.0 * fear

            if getattr(self, "_fear_pulse_ev", None):
                try:
                    self._fear_pulse_ev.cancel()
                except Exception:
                    pass
                self._fear_pulse_ev = None

            phase = 0.0
            def pulse(dt):
                if not self._fear_color:
                    return False
                nonlocal phase
                phase += dt * speed * 2 * 3.1415926
                s = (1 + __import__("math").sin(phase)) * 0.5
                self._fear_color.a = min_alpha + (max_alpha - min_alpha) * s
                return True

            self._fear_pulse_ev = Clock.schedule_interval(pulse, 1/60.0)
        except Exception as e:
            self.logger.error(f"show_fear_effect error: {e}", exc_info=True)

    def clear_fear_effect(self):
        """Remove fear overlay and pulse."""
        try:
            if getattr(self, "_fear_pulse_ev", None):
                try:
                    self._fear_pulse_ev.cancel()
                except Exception:
                    pass
                self._fear_pulse_ev = None
            if getattr(self, "_fear_color", None):
                try:
                    self.canvas.after.remove(self._fear_color)
                    self.canvas.after.remove(self._fear_rect)
                except Exception:
                    pass
                self._fear_color = None
                self._fear_rect = None
        except Exception as e:
            self.logger.error(f"clear_fear_effect error: {e}", exc_info=True)

    def show_damage_effect(self):
        """Quick red flash overlay to indicate damage."""
        try:
            # Clean previous flash if running
            if getattr(self, "_damage_cleanup_ev", None):
                self._damage_cleanup_ev.cancel()
                self._damage_cleanup_ev = None
            if getattr(self, "_damage_color", None):
                # Remove previous instructions
                try:
                    self.canvas.after.remove(self._damage_color)
                    self.canvas.after.remove(self._damage_rect)
                except Exception:
                    pass
                self._damage_color = None
                self._damage_rect = None

            with self.canvas.after:
                self._damage_color = Color(1, 0, 0, 0.0)  # start transparent
                self._damage_rect = Rectangle(pos=self.pos, size=self.size)
            # Ensure it tracks size/pos
            self.bind(size=self._update_fx_rect, pos=self._update_fx_rect)

            # Flash timeline: ramp up quickly then fade out
            duration_up = 0.08
            duration_down = 0.28
            peak_alpha = 0.55
            total = duration_up + duration_down
            elapsed = 0.0

            def step(dt):
                nonlocal elapsed
                if not self._damage_color:
                    return False
                elapsed += dt
                if elapsed <= duration_up:
                    # ramp in
                    t = max(0.0, min(1.0, elapsed / duration_up))
                    self._damage_color.a = peak_alpha * t
                elif elapsed <= total:
                    # fade out
                    t = (elapsed - duration_up) / duration_down
                    self._damage_color.a = peak_alpha * (1.0 - max(0.0, min(1.0, t)))
                else:
                    # cleanup
                    try:
                        if self._damage_color:
                            self.canvas.after.remove(self._damage_color)
                        if self._damage_rect:
                            self.canvas.after.remove(self._damage_rect)
                    except Exception:
                        pass
                    self._damage_color = None
                    self._damage_rect = None
                    self._damage_cleanup_ev = None
                    return False
                return True

            self._damage_cleanup_ev = Clock.schedule_interval(step, 1/60.0)
        except Exception as e:
            self.logger.error(f"show_damage_effect error: {e}", exc_info=True)

    def show_low_health_effect(self):
        """Persistent subtle pulsing red tint when health is low."""
        try:
            # If already active, do nothing
            if getattr(self, "_low_health_color", None) and getattr(self, "_low_health_pulse_ev", None):
                return
            with self.canvas.after:
                self._low_health_color = Color(1, 0, 0, 0.14)
                self._low_health_rect = Rectangle(pos=self.pos, size=self.size)
            self.bind(size=self._update_fx_rect, pos=self._update_fx_rect)

            # Pulse between two alpha values
            min_alpha, max_alpha, speed = 0.10, 0.22, 2.0
            phase = 0.0
            def pulse(dt):
                if not self._low_health_color:
                    return False
                nonlocal phase
                phase += dt * speed * 2 * 3.1415926
                s = (1 + __import__("math").sin(phase)) * 0.5
                self._low_health_color.a = min_alpha + (max_alpha - min_alpha) * s
                return True
            self._low_health_pulse_ev = Clock.schedule_interval(pulse, 1/60.0)
        except Exception as e:
            self.logger.error(f"show_low_health_effect error: {e}", exc_info=True)

    def clear_low_health_effect(self):
        """Remove low-health overlay and pulse."""
        try:
            if getattr(self, "_low_health_pulse_ev", None):
                try:
                    self._low_health_pulse_ev.cancel()
                except Exception:
                    pass
                self._low_health_pulse_ev = None
            if getattr(self, "_low_health_color", None):
                try:
                    self.canvas.after.remove(self._low_health_color)
                    self.canvas.after.remove(self._low_health_rect)
                except Exception:
                    pass
                self._low_health_color = None
                self._low_health_rect = None
        except Exception as e:
            self.logger.error(f"clear_low_health_effect error: {e}", exc_info=True)


    def _handle_show_popup_with_defers(self, event):
        """Enhanced popup handler with deferred action binding."""
        # Start popup-scoped VFX if requested
        self._apply_popup_vfx_hint(event)
        # Close any existing info popup
        if hasattr(self, 'active_info_popup') and self.active_info_popup:
            try:
                self.active_info_popup.dismiss()
            except Exception:
                pass
            self.active_info_popup = None
        # Show the popup and bind deferred actions
        popup = InfoPopup(title=event.get('title', 'Notice'), message=event.get('message', ''))
        self.active_info_popup = popup
        self._bind_popup_defers(popup, event)
        popup.open()

    def _handle_destroy_qte_popup(self, event):
        self.logger.info("_handle_destroy_qte_popup: Attempting to destroy QTE popup.")
        if self.active_qte_popup:
            try:
                self.active_qte_popup.dismiss()
            except Exception as e:
                self.logger.error(f"Error dismissing QTE popup: {e}", exc_info=True)
            self.active_qte_popup = None
            self.logger.info("QTE popup destroyed successfully")

    def _handle_show_qte(self, event):
        self.logger.info("_handle_show_qte: Attempting to show QTE popup.")
        if not self.active_qte_popup:
            try:
                popup = QTEPopup(
                    prompt=event.get("prompt", "React!"),
                    duration=event.get('duration', 5.0),
                    input_type=event.get('input_type', 'word'),
                    submit_callback=self.on_qte_input_submit,
                    qte_context=event.get('qte_context', {})
                )
                popup.open()
                self.active_qte_popup = popup
                self.logger.info("QTE popup shown successfully.")
            except Exception as e:
                self.logger.error(f"Failed to create QTEPopup: {e}", exc_info=True)

    def _handle_show_popup(self, event):
        """Show an info popup, with optional deferred actions on dismiss."""
        title = event.get("title", "Notice")
        message = event.get("message", "")
        deferred_qte = event.get("on_close_start_qte")
        defer_state = event.get("on_close_set_hazard_state")
        emit_events = event.get("on_close_emit_ui_events")

        def on_dismiss(*_):
            self.logger.info("_handle_show_popup: Info popup dismissed.")
            # Start QTE first if requested
            if deferred_qte and self.game_logic and self.game_logic.qte_engine:
                try:
                    self.logger.info(f"Starting deferred QTE '{deferred_qte.get('qte_type')}' after popup")
                    self.game_logic.qte_engine.start_qte(
                        deferred_qte.get('qte_type'),
                        deferred_qte.get('qte_context', {})
                    )
                    return  # QTE will drive the rest
                except Exception as e:
                    self.logger.error(f"Error starting deferred QTE: {e}", exc_info=True)

            # Apply deferred state change
            if defer_state and self.game_logic and self.game_logic.hazard_engine:
                try:
                    hid = defer_state.get("hazard_id")
                    tstate = defer_state.get("target_state")
                    if hid and tstate:
                        self.logger.info(f"Applying deferred state change: {hid} -> {tstate}")
                        result = self.game_logic.hazard_engine.set_hazard_state(hid, tstate)
                        # FIXED: Process consequences from the state change
                        if result and isinstance(result, dict):
                            consequences = result.get('consequences', [])
                            if consequences:
                                self.logger.info(f"Processing {len(consequences)} consequences from deferred state change")
                                self._handle_consequences_sequentially(consequences)
                except Exception as e:
                    self.logger.error(f"Error applying deferred state change: {e}", exc_info=True)

            # Emit any UI events (e.g., game_over/level_complete) after popup dismissal
            if emit_events and self.game_logic:
                for ev in emit_events:
                    self.game_logic.add_ui_event(ev)

            if hasattr(self, 'active_info_popup'):
                self.active_info_popup = None

        try:
            popup = InfoPopup(title=title, message=message)
            popup.bind(on_dismiss=on_dismiss)
            popup.open()
            if hasattr(self, 'active_info_popup'):
                self.active_info_popup = popup
            self.logger.info(f"_handle_show_popup: Showing info popup with title '{title}'.")
        except Exception as e:
            self.logger.error(f"Error showing popup: {e}", exc_info=True)


    def _handle_level_complete(self, event):
        """
        Handles the transition to the InterLevelScreen after a level is completed.
        Sets all relevant attributes on the App instance, with robust logging and error handling.
        """
        # PATCH: Prevent duplicate level_complete processing
        if getattr(self, '_level_complete_in_progress', False):
            self.logger.warning("_handle_level_complete: Already processing level complete, ignoring duplicate event.")
            return
        self._level_complete_in_progress = True

        self.logger.info("_handle_level_complete: Transitioning to InterLevelScreen.")
        try:
            # Dismiss any active QTE popup
            if hasattr(self, 'active_qte_popup') and self.active_qte_popup:
                try:
                    self.active_qte_popup.dismiss()
                except Exception as e:
                    self.logger.warning(f"Failed to dismiss active QTE popup: {e}", exc_info=True)
                self.active_qte_popup = None

            app = App.get_running_app()
            if not app:
                self.logger.error("_handle_level_complete: Could not get running App instance.")
                self._level_complete_in_progress = False
                return

            # Set all required attributes with robust error handling
            try:
                app.last_level_complete = event
                app.interlevel_completed_level_name = event.get('level_name', 'Unknown Area')
                app.interlevel_narrative_text = event.get('narrative', 'You survived this area.')
                app.interlevel_score_for_level = event.get('score', 0)
                app.interlevel_turns_taken_for_level = event.get('turns_taken', 0)
                app.interlevel_evidence_found_for_level_count = event.get('evidence_count', 0)
                app.interlevel_evaded_hazards = event.get('evaded_hazards', [])
                app.interlevel_next_level_id = event.get('next_level_id')
                app.interlevel_next_start_room = event.get('next_start_room')
                self.logger.info(
                    f"Level complete: {app.interlevel_completed_level_name}, "
                    f"Score: {app.interlevel_score_for_level}, "
                    f"Turns: {app.interlevel_turns_taken_for_level}, "
                    f"Evidence: {app.interlevel_evidence_found_for_level_count}, "
                    f"Next Level: {app.interlevel_next_level_id}"
                )
            except Exception as e:
                self.logger.error(f"_handle_level_complete: Error setting App attributes: {e}", exc_info=True)

            # Schedule screen transition with cleanup
            try:
                self.logger.info("Scheduled transition to 'inter_level' screen.")
                def _transition_after_frame(*args):
                    try:
                        # PATCH: Use self.manager (the ScreenManager) instead of app.screen_manager
                        if self.manager:
                            self.manager.current = 'inter_level'
                        else:
                            self.logger.error("_handle_level_complete: self.manager is None, cannot transition.")
                        self._level_complete_in_progress = False
                    except Exception as e:
                        self.logger.error(f"_handle_level_complete: Screen transition failed: {e}", exc_info=True)
                        self._level_complete_in_progress = False
                Clock.schedule_once(_transition_after_frame, 0)
            except Exception as e:
                self.logger.error(f"_handle_level_complete: Failed to schedule transition: {e}", exc_info=True)
                self._level_complete_in_progress = False

        except Exception as e:
            self.logger.error(f"_handle_level_complete: Unexpected error: {e}", exc_info=True)
            self._level_complete_in_progress = False

    def _handle_game_over(self, event):
        self.logger.info("_handle_game_over: Transitioning to LoseScreen.")
        app = App.get_running_app()
        app.last_death_reason = event.get('death_reason', 'Unknown cause')
        app.last_game_output_narrative = event.get('final_narrative', '')
        Clock.schedule_once(lambda dt: self.go_to_screen('lose', 'fade'), 1.0)

    def _handle_game_won(self, event):
        self.logger.info("_handle_game_won: Transitioning to WinScreen.")
        app = App.get_running_app()
        app.last_game_score = event.get('final_score', 0)
        Clock.schedule_once(lambda dt: self.go_to_screen('win', 'fade'), 1.0)

    def _handle_show_message(self, event):
        message = event.get("message")
        self.logger.info(f"_handle_show_message: Displaying message: {message}")
        if message and self.output_panel and hasattr(self.output_panel, 'append_text'):
            self.output_panel.append_text(message)

    def _handle_hide_qte(self, event):
        self.logger.info("_handle_hide_qte: Hiding QTE popup and resetting QTE state.")
        if self.active_qte_popup:
            self.active_qte_popup = None
        if self.game_logic and hasattr(self.game_logic, 'player') and isinstance(self.game_logic.player, dict):
            self.game_logic.player['qte_active'] = False

    def _handle_consequences_sequentially(self, consequences: list):
        """Process consequences one at a time with robust logging and error handling."""
        try:
            if not consequences:
                self.logger.debug("_handle_consequences_sequentially: No consequences to process.")
                return

            first, rest = consequences[0], consequences[1:]
            ctype = first.get("type") or first.get("event_type")
            self.logger.debug(f"_handle_consequences_sequentially: Processing consequence type '{ctype}' with data: {first!r}")

            if ctype == "show_popup":
                title = first.get("title", "Notice")
                message = first.get("message", "")
                self.logger.info(f"Sequential consequence: Showing popup '{title}' with message '{message[:80]}...'")
                try:
                    popup = InfoPopup(title=title, message=message)
                    self._bind_popup_defers(popup, first)

                    def _continue(*_):
                        try:
                            if rest:
                                self.logger.debug("Continuing with remaining consequences after popup.")
                                self._handle_consequences_sequentially(rest)
                        except Exception as e:
                            self.logger.error(f"Error in popup continuation: {e}", exc_info=True)

                    popup.bind(on_dismiss=_continue)
                    popup.open()
                except Exception as e:
                    self.logger.error(f"Error showing popup: {e}", exc_info=True)
                    if rest:
                        self._handle_consequences_sequentially(rest)
                return

            if ctype == "start_qte":
                self.logger.info(f"Sequential consequence: Starting QTE '{first.get('qte_type')}' with context {first.get('qte_context', {})}")
                if self.game_logic and self.game_logic.qte_engine:
                    try:
                        self.game_logic.qte_engine.start_qte(first.get("qte_type"), first.get("qte_context", {}))
                        self.logger.debug("QTE started successfully. Remaining consequences will be handled by QTE resolution.")
                        return
                    except Exception as e:
                        self.logger.error(f"Seq: failed to start QTE: {e}", exc_info=True)
                else:
                    self.logger.warning("QTE engine not available, cannot start QTE.")
                if rest:
                    self.logger.debug("Continuing with remaining consequences after failed QTE start.")
                    self._handle_consequences_sequentially(rest)
                return

            if ctype == "hazard_state_change":
                self.logger.info(f"Sequential consequence: Changing hazard state for hazard_id '{first.get('hazard_id')}' to '{first.get('target_state')}'")
                if self.game_logic and self.game_logic.hazard_engine:
                    try:
                        res = self.game_logic.hazard_engine.set_hazard_state(first.get("hazard_id"), first.get("target_state"))
                        nxt = (res or {}).get("consequences", [])
                        self.logger.debug(f"Hazard state changed. Next consequences: {nxt!r}")
                        self._handle_consequences_sequentially((nxt or []) + rest)
                        return
                    except Exception as e:
                        self.logger.error(f"Seq: hazard_state_change error: {e}", exc_info=True)
                else:
                    self.logger.warning("Hazard engine not available, cannot change hazard state.")
                if rest:
                    self.logger.debug("Continuing with remaining consequences after failed hazard state change.")
                    self._handle_consequences_sequentially(rest)
                return

            # Fallback: let GameLogic handle other consequence types immediately then continue
            if hasattr(self.game_logic, 'handle_hazard_consequence'):
                try:
                    self.logger.info(f"Sequential consequence: Passing to game_logic.handle_hazard_consequence: {first!r}")
                    self.game_logic.handle_hazard_consequence(first)
                except Exception as e:
                    self.logger.error(f"Seq: handle_hazard_consequence error: {e}", exc_info=True)
            else:
                self.logger.warning("game_logic.handle_hazard_consequence not available.")
            if rest:
                self.logger.debug("Continuing with remaining consequences after fallback handler.")
                self._handle_consequences_sequentially(rest)
        except Exception as e:
            self.logger.error(f"Unexpected error in _handle_consequences_sequentially: {e}", exc_info=True)

    def _populate_main_action_buttons(self):
        """Use context-sensitive dock instead of flat button grid."""
        container = self._get_widget('main_actions')
        if not container:
            return
        
        container.clear_widgets()
        
        # Replace with context dock
        dock = ContextDockWidget()
        dock.on_command = self.on_main_action_press  # Wire to existing handler
        dock.update(self.game_logic)  # Initial population
        
        container.add_widget(dock)
        
        # Store reference for updates
        self.context_dock = dock

    def on_main_action_press(self, verb: str):
        self.logger.debug(f"GameScreen: on_main_action_press called with verb '{verb}'")
        if not self.game_logic:
            self.logger.error("GameScreen: game_logic missing on main action press.")
            return

        # Add support for special verbs: 'main menu', 'save', 'load'
        if verb == 'main menu':
            self.logger.info("GameScreen: Navigating to main menu (title screen).")
            self.go_to_screen('title', direction='right')
            return
        elif verb == 'save':
            self.logger.info("GameScreen: Navigating to save game screen.")
            self.go_to_screen('save_game', direction='right')
            return
        elif verb == 'load':
            self.logger.info("GameScreen: Navigating to load game screen.")
            self.go_to_screen('load_game', direction='left')
            return

        # Verbs that do NOT require a target
        no_target_verbs = {'inventory', 'inv', 'wait', 'rest', 'help', 'list', 'map', 'main menu', 'save', 'load'}
        if verb in no_target_verbs:
            command = verb
            self.logger.debug(f"GameScreen: Executing '{verb}' with no target.")
            self.on_submit_command(command_override=command)
            return

        ctx = self._get_widget('contextual_actions')
        if not ctx or not hasattr(ctx, 'populate'):
            self.logger.error("GameScreen: contextual_actions missing.")
            return

        # Special handling for 'use'
        if verb == "use":
            def on_target_selected(target):
                command = f"use {target}"
                self.process_and_clear(command)
            ctx.populate_use_targets(self.game_logic, on_target_selected)
            return

        # NEW: special handling for 'unlock' and 'force'
        if verb in ('unlock', 'force'):
            pairs = self._collect_unlock_force_targets(verb)
            buttons = []
            for btn_text, command in pairs:
                try:
                    b = Button(text=btn_text, size_hint_y=None, height=dp(40))
                    _wrap_button_text(b, align='center')
                    b.bind(on_release=lambda _i, c=command: self.process_and_clear(c))
                    buttons.append(b)
                except Exception as e:
                    self.logger.error(f"GameScreen: Error adding {verb} button '{btn_text}': {e}", exc_info=True)
            back = Button(text="< Back", size_hint_y=None, height=dp(40))
            _wrap_button_text(back, align='center')
            back.bind(on_release=lambda *_: ctx.populate([]))
            buttons.append(back)
            ctx.populate(buttons)
            self.logger.debug(f"GameScreen: Contextual actions populated for verb '{verb}'")
            return

        # Default path
        try:
            targets = self.game_logic.get_available_targets(verb) or []
            self.logger.debug(f"GameScreen: Available targets for verb '{verb}': {targets}")
        except Exception as e:
            self.logger.error(f"GameScreen: Error getting targets for verb '{verb}': {e}", exc_info=True)
            targets = []

        buttons = []
        for target in targets:
            command = f"{verb} {target}"
            try:
                b = Button(text=target.replace('_', ' ').title(), size_hint_y=None, height=dp(40))
                _wrap_button_text(b, align='center')
                b.bind(on_release=lambda _i, c=command: self.process_and_clear(c))
                buttons.append(b)
            except Exception as e:
                self.logger.error(f"GameScreen: Error adding contextual button for target '{target}': {e}", exc_info=True)
        back = Button(text="< Back", size_hint_y=None, height=dp(40))
        _wrap_button_text(back, align='center')
        back.bind(on_release=lambda *_: ctx.populate([]))
        buttons.append(back)
        ctx.populate(buttons)
        self.logger.debug(f"GameScreen: Contextual actions populated for verb '{verb}'")

    def process_and_clear(self, command: str):
        self.logger.debug(f"GameScreen: process_and_clear called with command '{command}'")
        self.on_submit_command(command_override=command)
        self.clear_contextual_actions()

    def on_submit_command(self, instance=None, command_override: str = None):
        self.logger.debug(f"GameScreen: on_submit_command called. instance={instance}, command_override={command_override}")
        if not self.game_logic:
            self.logger.error("GameScreen: game_logic is None on submit.")
            return

        ai = self._get_widget('action_input')
        out = self._get_widget('output_panel')
        text = command_override or (ai.text_input.text.strip() if ai and hasattr(ai, 'text_input') else '')
        self.logger.debug(f"GameScreen: Command text resolved to '{text}'")
        if not text:
            self.logger.warning("GameScreen: No command text to process.")
            return

        # If a QTE is active, route input to QTE engine instead of normal commands
        if self.game_logic.player.get('qte_active') and getattr(self.game_logic, 'qte_engine', None) and self.game_logic.qte_engine.active_qte:
            self.logger.info("GameScreen: QTE active, routing input to QTE engine.")
            if out and hasattr(out, 'append_text'):
                out.append_text(f"> {text}")
            # Clear box for next input
            if ai and hasattr(ai, 'text_input'):
                ai.text_input.text = ""

            try:
                result = self.game_logic.qte_engine.handle_qte_input(text)
                self.logger.debug(f"GameScreen: QTE engine result: {result}")
            except Exception as e:
                self.logger.error(f"GameScreen: Error handling QTE input: {e}", exc_info=True)
                result = None
            # If QTE resolved, refresh UI and clear QTE mode
            if isinstance(result, dict):
                for m in result.get('messages', []):
                    if out and hasattr(out, 'append_text'):
                        out.append_text(m)
                self.update_all_ui_elements(result.get('game_state', {}))
                self.in_qte_mode = False
                if ai and hasattr(ai, 'text_input'):
                    ai.text_input.hint_text = ""
            return

        # Normal command flow
        command = text
        if ai and hasattr(ai, 'text_input'):
            ai.text_input.text = ""
        if out and hasattr(out, 'append_text'):
            out.append_text(f"> {command}")

        try:
            response = self.game_logic.process_player_input(command)
            self.logger.debug(f"GameScreen: process_player_input response: {response}")
        except Exception as e:
            self.logger.error(f"Engine error: {e}", exc_info=True)
            response = {"messages": [f"[color=ff4444]Engine error: {e}[/color]"], "game_state": self.game_logic.get_current_game_state(), "ui_events": []}

        self.update_all_ui_elements(response.get('game_state', {}))
        for m in response.get('messages', []):
            if out and hasattr(out, 'append_text'):
                out.append_text(m)
        self._handle_ui_events(response.get('ui_events', []))

        # Drain any late-queued events (ensures immediate popup without needing another action)
        pending = getattr(self.game_logic, "get_ui_events", lambda: [])()
        if pending:
            self._handle_ui_events(pending)

        if hasattr(self, 'context_dock'):
            self.context_dock.update(self.game_logic)

        self.logger.info(f"GameScreen: Finished processing command '{command}'")

    def clear_contextual_actions(self, *args):
        self.logger.debug("clear_contextual_actions called")
        ctx = self._get_widget('contextual_actions')
        if ctx and hasattr(ctx, 'populate'):
            self.logger.debug("Contextual actions widget found, clearing actions")
            ctx.populate([])
        else:
            self.logger.warning("Contextual actions widget not found or missing 'populate' method")

    def on_leave(self, *args):
        """Called when leaving GameScreen. Clean up QTE popups and reset transition state."""
        self.logger.info("GameScreen.on_leave: Cleaning up QTE popups and resetting transition state.")
        try:
            # Reset level complete flag
            self._level_complete_in_progress = False
            
            # Dismiss QTE if active
            if hasattr(self, 'active_qte_popup') and self.active_qte_popup:
                try:
                    self._handle_hide_qte()
                except Exception as e:
                    self.logger.error(f"on_leave: Error hiding QTE: {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"GameScreen.on_leave: Error during cleanup: {e}", exc_info=True)

    def _handle_game_loaded(self, event):
        """Handle game loaded event by refreshing the entire UI."""
        self.logger.info("_handle_game_loaded: Refreshing UI after loading game")
        
        # Clear and update output panel with room description
        room_desc = event.get('room_description', '')
        if room_desc and self.output_panel and hasattr(self.output_panel, 'append_text'):
            self.output_panel.append_text(room_desc, clear_previous=True)
        
        # Force full UI refresh
        if self.game_logic:
            self.update_all_ui_elements(self.game_logic.get_current_game_state())