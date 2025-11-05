# widgets.py
"""
The Canvas of Souls.
This scroll defines the placeholder shapes for all the custom UI widgets.
"""
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.metrics import dp, sp
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.progressbar import ProgressBar
from kivy.uix.gridlayout import GridLayout
from .responsive import scale_sp, body_sp, small_sp
import logging
import time

class StatusDisplayWidget(BoxLayout):
    """Displays the player's core stats like HP, Turns, Fear, etc."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = dp(30)
        self.hp_label = Label(markup=True, size_hint_x=0.25)
        self.turns_label = Label(markup=True, size_hint_x=0.25)
        self.fear_label = Label(markup=True, size_hint_x=0.25)
        self.score_label = Label(markup=True, size_hint_x=0.25)
        # Apply responsive font sizes
        self._apply_responsive_fonts()
        Window.bind(size=lambda *_: self._apply_responsive_fonts())
        self.add_widget(self.hp_label)
        self.add_widget(self.turns_label)
        self.add_widget(self.fear_label)
        self.add_widget(self.score_label)

    def _apply_responsive_fonts(self):
        fs = small_sp()
        for lbl in (self.hp_label, self.turns_label, self.fear_label, self.score_label):
            lbl.font_size = fs

    def update(self, player_state: dict):
        """Updates the labels with new player state, including fear."""
        hp = player_state.get('hp', '--')
        loc = player_state.get('location', 'Unknown')
        fear = player_state.get('fear', 0.0)
        score = player_state.get('score', '--')
        turns = player_state.get('turns_left', '--')
        
        # Color-code fear level
        if fear >= 0.8:
            fear_color = 'ff0000'  # Red - terrified
        elif fear >= 0.6:
            fear_color = 'ff6600'  # Orange - very afraid  
        elif fear >= 0.4:
            fear_color = 'ffaa00'  # Yellow - nervous
        elif fear >= 0.2:
            fear_color = 'ffffff'  # White - slightly uneasy
        else:
            fear_color = '00ff00'  # Green - calm

        # Color-code HP level (assuming max HP is 100)
        if isinstance(hp, (int, float)):
            max_hp = player_state.get('max_hp', 100)
            hp_ratio = hp / float(max_hp) if max_hp else 0
            if hp_ratio <= 0.2:
                hp_color = 'ff0000'  # Red - critical
            elif hp_ratio <= 0.4:
                hp_color = 'ff6600'  # Orange - low
            elif hp_ratio <= 0.6:
                hp_color = 'ffaa00'  # Yellow - moderate
            elif hp_ratio <= 0.8:
                hp_color = 'ffffff'  # White - good
            else:
                hp_color = '00ff00'  # Green - healthy
        else:
            hp_color = 'ffffff'  # Default color

        # Color-code turns left (assuming max turns is 180)
        if isinstance(turns, (int, float)):
            turns_ratio = turns / 180.0
            if turns_ratio <= 0.2:
                turns_color = 'ff0000'  # Red - almost out
            elif turns_ratio <= 0.4:
                turns_color = 'ff6600'  # Orange - low
            elif turns_ratio <= 0.6:
                turns_color = 'ffaa00'  # Yellow - moderate
            elif turns_ratio <= 0.8:
                turns_color = 'ffffff'  # White - plenty
            else:
                turns_color = '00ff00'  # Green - safe
        else:
            turns_color = 'ffffff'  # Default color

        # Color-code score (assuming higher is better, thresholds can be adjusted)
        if isinstance(score, (int, float)):
            if score >= 1000:
                score_color = '00ff00'  # Green - excellent
            elif score >= 500:
                score_color = 'ffffff'  # White - good
            elif score >= 250:
                score_color = 'ffaa00'  # Yellow - decent
            elif score >= 100:
                score_color = 'ff6600'  # Orange - low
            else:
                score_color = 'ff0000'  # Red - poor
        else:
            score_color = 'ffffff'  # Default color

        self.hp_label.text = f"[color={hp_color}]HP: {hp}[/color]"
        self.turns_label.text = f"[color={turns_color}]Turns: {turns}[/color]"
        self.fear_label.text = f"[color={fear_color}]Fear: {fear:.1f}[/color]"
        self.score_label.text = f"[color={score_color}]Score: {score}[/color]"

class OutputPanelWidget(BoxLayout):
    """A widget for the main game text output area with robust debugging/logging."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.debug("Initializing OutputPanelWidget")
        self.output_label = Label(
            markup=True,
            font_name='RobotoMono',
            font_size=scale_sp(12, min_sp=10, max_sp=14),  # REDUCED from body_sp()
            size_hint_y=None,
            valign='top',
            halign='left',
            padding=(dp(8), dp(8)),
            text_size=(self.width - dp(12), None)
        )
        self.output_label.bind(
            width=lambda i, w: setattr(i, 'text_size', (w - dp(12), None)),
            texture_size=lambda i, v: setattr(i, 'height', v[1])
        )
        # Update font size on window resize
        Window.bind(size=lambda *_: setattr(self.output_label, 'font_size', scale_sp(12, 10, 14)))
        self.output_scroll_view = ScrollView(size_hint_y=1)
        self.output_scroll_view.add_widget(self.output_label)
        self.add_widget(self.output_scroll_view)
        self.logger.debug("Output label and scroll view initialized and added")

    def append_text(self, text_to_append, clear_previous=False):
        self.logger.info(f"Appending text: {text_to_append[:60]}{'...' if len(text_to_append) > 60 else ''}")
        processed_text = self._ensure_color_tags_closed(text_to_append)
        if clear_previous:
            self.logger.debug("Clearing previous text before appending")
            self.output_label.text = processed_text
        else:
            self.logger.debug("Appending text to existing output")
            self.output_label.text += f"\n\n{processed_text}"
        Clock.schedule_once(lambda dt: setattr(self.output_scroll_view, 'scroll_y', 0), 0.01)
        self.logger.debug("Scheduled scroll to bottom of output")

    def _ensure_color_tags_closed(self, text):
        """Ensure all color tags are properly closed to prevent markup issues."""
        open_tags = text.count('[color=') - text.count('[/color]')
        if open_tags > 0:
            text += '[/color]' * open_tags
        return text

class MapDisplayWidget(BoxLayout):
    """A widget to display the text-based map with robust debugging/logging."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.orientation = 'vertical'
        self.add_widget(Label(
            text="[b]MAP[/b]",
            markup=True,
            size_hint_y=None,
            height=dp(20),
            font_name='RobotoMonoBold',
            font_size=small_sp()
        ))
        map_scroll = ScrollView(
            size_hint_y=1,
            do_scroll_x=False,
            do_scroll_y=True,
            bar_width=dp(8)
        )
        self.map_label = Label(
            text="",
            font_name='RobotoMono',
            font_size=scale_sp(11, min_sp=9, max_sp=14),
            markup=True,
            halign='center',
            valign='top',
            size_hint_y=None,
            padding=(dp(4), dp(4))
        )
        Window.bind(size=lambda *_: setattr(self.map_label, 'font_size', scale_sp(11, 9, 14)))
        self.map_label.bind(texture_size=lambda *args: setattr(self.map_label, 'height', self.map_label.texture_size[1]))
        self.map_label.bind(width=lambda *args: setattr(self.map_label, 'text_size', (self.map_label.width - dp(8), None)))
        map_scroll.add_widget(self.map_label)
        self.add_widget(map_scroll)

    def update(self, map_string: str):
        """Receives a new map string and displays it."""
        self.logger.info(f"Updating map (length={len(map_string)})")
        self.map_label.text = map_string

class ActionInputWidget(BoxLayout):
    """A widget for the player's text input and submit button with robust debugging/logging."""
    def __init__(self, **kwargs):
        super().__init__(orientation='horizontal', spacing=dp(6), size_hint_y=None, height=dp(42), **kwargs)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.debug("Initializing ActionInputWidget")

        self.text_input = TextInput(multiline=False, size_hint_x=0.8)
        self.submit_button = Button(text="Submit", size_hint_x=0.2)

        self.add_widget(self.text_input)
        self.add_widget(self.submit_button)
        self.logger.debug("TextInput and Submit Button added to ActionInputWidget")

        # Bind both button press and 'enter' key to submit
        self.submit_button.bind(on_release=self._on_submit)
        self.text_input.bind(on_text_validate=self._on_submit)
        self.logger.debug("Submit bindings set for button and text input")

    def _on_submit(self, *args):
        self.logger.info(f"Submit triggered with text: '{self.text_input.text}'")
        # Keep focus on text input after submit
        Clock.schedule_once(lambda dt: self._refocus_input(), 0.1)
        self.logger.debug("TextInput will be refocused after submit")

    def _refocus_input(self):
        """Refocus the text input and optionally select all text.
        If a QTE prompt was present, clear it after QTE is done.
        """
        if self.text_input:
            self.text_input.focus = True
            # Remove QTE prompt from input if present
            if hasattr(self, 'qte_prompt_active') and self.qte_prompt_active:
                self.text_input.text = ''
                self.qte_prompt_active = False
                self.logger.debug("QTE prompt cleared from text input")
            # self.text_input.select_all()
            self.logger.debug("TextInput refocused after submit")

class MainActionsWidget(BoxLayout):
    """Holds the primary, static action buttons with robust debugging/logging."""
    def __init__(self, **kwargs):
        super().__init__(orientation='horizontal', spacing=dp(5), **kwargs)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.debug("Initializing MainActionsWidget")
        self.action_buttons = []
        self.logger.debug("MainActionsWidget initialized with empty action_buttons list")

        # --- Add canonical buttons ---
        self.main_menu_button = Button(text="Main Menu")
        self.save_button = Button(text="Save")
        self.load_button = Button(text="Load")
        self.add_action_button(self.main_menu_button)
        self.add_action_button(self.save_button)
        self.add_action_button(self.load_button)

    def add_action_button(self, button):
        """Adds a new action button and logs the event."""
        self.logger.info(f"Adding action button: {getattr(button, 'text', repr(button))}")
        self.action_buttons.append(button)
        self.add_widget(button)
        self.logger.debug(f"Button added. Total buttons: {len(self.action_buttons)}")

    def clear_action_buttons(self):
        """Removes all action buttons and logs the event."""
        self.logger.info("Clearing all action buttons")
        for btn in self.action_buttons:
            self.remove_widget(btn)
        self.action_buttons.clear()
        self.logger.debug("All action buttons cleared")

class ContextualActionsWidget(ScrollView):
    """A scrollable view for dynamic action target buttons with robust debugging/logging."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.debug("Initializing ContextualActionsWidget")
        # Change cols=1 to cols=3 (or 2, 4, etc. as desired)
        self.grid = GridLayout(cols=6, spacing=dp(5), size_hint_y=None)
        self.grid.bind(minimum_height=self.grid.setter('height'))
        self.add_widget(self.grid)
        self.logger.debug("GridLayout added to ScrollView")

    def populate(self, buttons: list):
        self.logger.info(f"Populating ContextualActionsWidget with {len(buttons)} buttons")
        self.grid.clear_widgets()
        self.logger.debug("Cleared existing widgets from grid")
        for idx, button in enumerate(buttons):
            # Reduce button height and font size for compactness
            button.height = dp(30)
            button.font_size = dp(12)
            self.logger.debug(f"Adding button {idx}: {getattr(button, 'text', repr(button))}")
            self.grid.add_widget(button)
        self.logger.info("Finished populating ContextualActionsWidget")

    def add_button(self, button):
        """Adds a single button with logging."""
        self.logger.info(f"Adding single button: {getattr(button, 'text', repr(button))}")
        self.grid.add_widget(button)
        self.logger.debug("Button added to grid")

    def clear_buttons(self):
        """Clears all buttons with logging."""
        self.logger.info("Clearing all buttons from ContextualActionsWidget")
        self.grid.clear_widgets()
        self.logger.debug("All buttons cleared from grid")

    def populate_use_targets(self, game_logic, on_target_selected):
        self.logger.info("Populating use targets for ContextualActionsWidget")
        self.clear_buttons()
        targets = set()

        # 1. Inventory items
        for item_key in game_logic.player.get('inventory', []):
            display_name = game_logic._get_item_display_name(item_key)
            targets.add(display_name)

        # 2. Objects, furniture, hazards with use interaction
        current_room_id = game_logic.player.get('location')
        visible = game_logic._get_all_visible_entities_in_room(current_room_id)
        hazards_master = game_logic.resource_manager.get_data('hazards', {})
        active_hazards = []
        if hasattr(game_logic, 'hazard_engine') and game_logic.hazard_engine:
            active_hazards = game_logic.hazard_engine.get_active_hazards_for_room(current_room_id)

        # For each visible object/furniture
        for entity in visible.get('objects', []) + visible.get('furniture', []):
            name = entity.get('name', '')
            aliases = entity.get('aliases', [])
            all_names = [name] + aliases

            # Check for use_item_interaction (legacy/furniture)
            if entity.get('data', {}).get('use_item_interaction'):
                targets.add(name)

            # Check for hazard_key (hazard-spawned entity)
            hazard_key = entity.get('hazard_key')
            if hazard_key and hazard_key in hazards_master:
                h_def = hazards_master[hazard_key]
                if h_def.get('player_interaction', {}).get('use'):
                    targets.add(name)

            # NEW: Check if any active hazard's player_interaction.use matches this entity's name/alias
            for h_key in active_hazards:
                h_def = hazards_master.get(h_key, {})
                use_rules = h_def.get('player_interaction', {}).get('use', [])
                for rule in use_rules:
                    on_names = rule.get('on_target_name', [])
                    if isinstance(on_names, str):
                        on_names = [on_names]
                    for n in all_names:
                        if n and any(game_logic._norm(n) == game_logic._norm(t) for t in on_names):
                            targets.add(name)

        # 3. Create a button for each target
        for target in sorted(targets):
            btn = Button(
                text=target,
                size_hint_y=None,
                height=dp(32),
                font_name="RobotoMono",
                font_size=dp(12)
            )
            btn.bind(on_release=lambda _, t=target: on_target_selected(t))
            self.add_button(btn)
        self.logger.info(f"ContextualActionsWidget: Populated {len(targets)} use targets")

class InfoPopup(Popup):
    """A generic popup for displaying information to the player with robust debugging/logging."""
    def __init__(self, title, message, **kwargs):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.debug(f"Initializing InfoPopup with title='{title}' and message='{message[:60]}{'...' if len(message) > 60 else ''}'")
        super().__init__(**kwargs)
        self.title = title
        self.size_hint = (None, None)  # Changed from (0.8, 0.5) to allow dynamic sizing
        self.width = Window.width * 0.85  # Start at 85% of window width
        
        layout = BoxLayout(orientation='vertical', padding=dp(15), spacing=dp(15))

        # Scrollable message container (in case text is very long)
        message_scroll = ScrollView(
            size_hint_y=None,
            do_scroll_x=False,
            do_scroll_y=True
        )
        
        message_label = Label(
            text=message,
            markup=True,
            font_name='RobotoMono',
            font_size=dp(14),
            halign='center',
            valign='middle',
            size_hint_y=None,
            padding=(dp(10), dp(10))
        )
        
        # Critical: Set text_size to enable wrapping based on popup width
        def update_text_size(instance, value):
            # Account for padding and scrollbar
            available_width = self.width - dp(60)
            message_label.text_size = (available_width, None)
        
        self.bind(width=update_text_size)
        Clock.schedule_once(lambda dt: update_text_size(None, None), 0)
        
        # Bind texture_size to label height so it grows with content
        message_label.bind(texture_size=lambda instance, value: setattr(instance, 'height', value[1] + dp(20)))
        
        message_scroll.add_widget(message_label)
        layout.add_widget(message_scroll)

        close_button = Button(
            text="Close",
            size_hint_y=None,
            height=dp(50),
            font_name='RobotoMonoBold'
        )
        close_button.bind(on_release=self._on_close)
        layout.add_widget(close_button)

        self.content = layout

        # Dynamically resize popup height based on content
        def adjust_height(*_):
            # Calculate required height: message + button + padding
            content_height = message_label.height + close_button.height + dp(80)
            
            # Clamp between min and max heights
            min_height = Window.height * 0.3
            max_height = Window.height * 0.9
            
            self.height = max(min_height, min(max_height, content_height))
            
            # Also adjust scroll view height to fill available space
            message_scroll.height = self.height - close_button.height - dp(100)
        
        message_label.bind(texture_size=adjust_height)
        self.bind(height=adjust_height)
        Clock.schedule_once(adjust_height, 0.1)

        self.logger.info("InfoPopup initialized and ready to display")

    def _on_close(self, *args):
        self.logger.info("Close button pressed, dismissing InfoPopup")
        self.dismiss()
        
class QTEPopup(Popup):
    """A popup for Quick Time Events (QTEs) with robust logging and debugging."""
    def __init__(self, prompt, duration, input_type, submit_callback, qte_context=None, **kwargs):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.debug(f"Initializing QTEPopup: prompt='{prompt}', duration={duration}, input_type='{input_type}', qte_context={qte_context}")
        super().__init__(**kwargs)
        self.input_type = input_type
        self.submit_callback = submit_callback
        self.qte_context = qte_context or {}

        # Track duration and elapsed time for the visual timer
        self.duration = float(duration or 0.0)
        self.time_elapsed = 0.0

        # Input tracking for different QTE types
        self.mash_count = 0
        self.tap_count = 0
        self.key_sequence = []
        self.hold_start_time = None
        self.last_alt_key = None
        self.alt_count = 0
        self.text_input = None
        self.logger.debug("Setting up QTEPopup layout and prompt label")
        layout = BoxLayout(orientation='vertical', padding='10dp', spacing='10dp')
        self.prompt_label = Label(text=f"[b]{prompt}[/b]", markup=True, halign='center')
        layout.add_widget(self.prompt_label)

        self.logger.debug("Creating QTE interface based on input_type")
        self._create_qte_interface(layout)

        self.timer_bar = ProgressBar(max=self.duration, value=self.duration)
        layout.add_widget(self.timer_bar)
        self.content = layout

        # PATCH: Add hold button for hold_release/timed_release/hold_and_release QTEs
        if input_type in ('hold_release', 'timed_release', 'hold_and_release'):
            self.hold_button = Button(
                text="Hold!",
                font_size='32sp',
                size_hint=(0.8, 0.4),
                pos_hint={'center_x': 0.5, 'center_y': 0.5}
            )
            self.hold_start_time = None
            self.hold_button.bind(on_touch_down=self._on_hold_down, on_touch_up=self._on_hold_up)
            self.content.add_widget(self.hold_button)

        self.logger.debug("Binding key events for QTEPopup")
        Window.bind(on_key_down=self._on_key_down, on_key_up=self._on_key_up)

        self.timer_event = Clock.schedule_interval(self._update_timer, 1/60.0) if self.duration > 0 else None
        self.logger.info("QTEPopup initialized and ready")

    def _on_hold_down(self, instance, touch):
        from kivy.clock import Clock
        if instance.collide_point(*touch.pos):
            self.hold_start_time = Clock.get_time()
            self.logger.info("Hold button pressed down")
            return True
        return False

    def _on_hold_up(self, instance, touch):
        from kivy.clock import Clock
        if instance.collide_point(*touch.pos) and self.hold_start_time is not None:
            held = Clock.get_time() - self.hold_start_time
            self.logger.info(f"Hold button released after {held:.2f}s")
            self.submit_callback({'event': 'hold_release', 'duration': held})
            self.hold_start_time = None
            return True
        return False

    def _create_qte_interface(self, layout):
        """Dispatch to the appropriate QTE UI builder based on input_type."""
        self.logger.debug(f"Creating QTE interface for type: {self.input_type}")
        qtype = self.input_type

        if qtype == 'mash':
            self._qte_ui_mash(layout)
        elif qtype in ('tap', 'tap_count', 'precision_tap_count'):
            self._qte_ui_tap(layout)
        elif qtype in ('hold', 'hold_release', 'hold_and_release', 'timed_release', 'hold_threshold', 'hold_to_threshold'):
            self._qte_ui_hold(layout)
        elif qtype in ('alternate', 'alternating_keys', 'balance'):
            self._qte_ui_alternate(layout)
        elif qtype in ('choice', 'cancel', 'timed_choice'):
            self._qte_ui_choice(layout)
        elif qtype in ('sequence', 'pattern', 'directional', 'code'):
            self._qte_ui_sequence(layout)
        elif qtype == 'single_key':
            self._qte_ui_single_key(layout)
        elif qtype == 'input':
            self._qte_ui_text_input(layout)
        elif qtype == 'spiral':
            self._qte_ui_spiral(layout)
        elif qtype == 'rhythm':
            self._qte_ui_rhythm(layout)
        else:
            self._qte_ui_default(layout)

    def _qte_ui_rhythm(self, layout):
        self.logger.debug("Setting up rhythm QTE UI with beat indicator")
        self.rhythm_bar = ProgressBar(max=1.0, value=0.0, size_hint_y=None, height='30dp')
        layout.add_widget(self.rhythm_bar)
        self.tap_count = 0
        self.beat_index = 0
        self.beat_times = []
        self.beat_interval = float(self.qte_context.get('beat_interval', 0.8))
        self.target_beats = int(self.qte_context.get('target_beats', 5))
        self.rhythm_timer = None
        self.rhythm_active = True

        # Start the beat loop
        self._start_rhythm_beats()

        # Add tap button
        btn = Button(text="Tap!", font_size='32sp', size_hint_y=None, height='60dp')
        btn.bind(on_release=self._on_rhythm_tap)
        layout.add_widget(btn)

    def _start_rhythm_beats(self):
        self.beat_index = 0
        self.beat_times = []
        self.rhythm_bar.value = 0.0
        if self.rhythm_timer:
            self.rhythm_timer.cancel()
        self.rhythm_timer = Clock.schedule_interval(self._on_rhythm_beat, self.beat_interval)

    def _on_rhythm_beat(self, dt):
        if not self.rhythm_active:
            return False
        self.beat_index += 1
        self.beat_times.append(Clock.get_time())
        self.rhythm_bar.value = 0.0
        # Animate bar fill
        Clock.schedule_interval(self._update_rhythm_bar, 1/60.0)
        if self.beat_index >= self.target_beats:
            self.rhythm_active = False
            if self.rhythm_timer:
                self.rhythm_timer.cancel()
            return False
        return True

    def _update_rhythm_bar(self, dt):
        if not self.rhythm_active:
            return False
        self.rhythm_bar.value += dt / self.beat_interval
        if self.rhythm_bar.value >= 1.0:
            self.rhythm_bar.value = 0.0
            return False
        return True

    def _on_rhythm_tap(self, *args):
        if getattr(self, 'is_dismissed', False):
            return
        tap_time = Clock.get_time()
        # Find the closest beat
        if not self.beat_times:
            return
        closest_beat = min(self.beat_times, key=lambda t: abs(tap_time - t))
        delta = abs(tap_time - closest_beat)
        window = float(self.qte_context.get('timing_window', 0.25))
        on_time = delta <= window
        self.logger.info(f"Rhythm tap: tap_time={tap_time:.2f}, closest_beat={closest_beat:.2f}, delta={delta:.2f}, on_time={on_time}")
        self.submit_callback({'event': 'rhythm_tap', 'on_time': on_time, 'delta': delta, 'tap_time': tap_time})
        # After QTE is resolved, set dismissed flag and cancel timers
        self.is_dismissed = True
        if hasattr(self, 'rhythm_timer') and self.rhythm_timer:
            self.rhythm_timer.cancel()
            self.rhythm_timer = None
        # Optionally dismiss the popup if not already handled
        if hasattr(self, 'dismiss') and callable(self.dismiss):
            self.dismiss()

    def _qte_ui_mash(self, layout):
        self.logger.debug("Setting up mash QTE counter")
        target = None
        eff = self.qte_context.get('effective_target_mash_count')
        try:
            if isinstance(eff, (int, float)):
                target = int(eff)
        except Exception:
            target = None

        # Show live counter (and target if known)
        text = f"Presses: {self.mash_count}" + (f" / {target}" if target else "")
        self.mash_counter = Label(
            text=text,
            font_size='24sp',
            size_hint_y=None,
            height='40dp'
        )
        layout.add_widget(self.mash_counter)

        btn = Button(text="Mash!", font_size='32sp', size_hint_y=None, height='60dp')
        # FIX: increment locally, update UI, then notify engine
        btn.bind(on_release=self._on_mash_press)
        layout.add_widget(btn)
        self.text_input = None

        # Optional: keep a separate target label (if you want both)
        if target is not None:
            self.target_label = Label(
                text=f"Target: {target}",
                font_size='18sp',
                size_hint_y=None,
                height='30dp'
            )
            layout.add_widget(self.target_label)


    def _qte_ui_tap(self, layout):
        self.logger.debug("Setting up tap QTE counter")
        required = int(self.qte_context.get('required_tap_count', self.qte_context.get('required_tap_count_default', 10)))
        self.tap_required = required  # cache for display updates
        self.tap_counter = Label(
            text=f"Taps: {self.tap_count}/{required}",
            font_size='20sp',
            size_hint_y=None,
            height='40dp'
        )
        layout.add_widget(self.tap_counter)

        btn = Button(text="Tap!", font_size='32sp', size_hint_y=None, height='60dp')
        # FIX: increment locally, update UI, then notify engine
        btn.bind(on_release=self._on_tap_press)
        layout.add_widget(btn)
        self.text_input = None

    def _qte_ui_hold(self, layout):
        self.logger.debug("Setting up hold QTE display")
        self.hold_label = Label(
            text="Press and hold the button, but RELEASE before time is up!",
            font_size='20sp',
            size_hint_y=None,
            height='40dp'
        )
        layout.add_widget(self.hold_label)
        btn = Button(text="Hold!", font_size='32sp', size_hint_y=None, height='60dp')
        btn.bind(on_touch_down=self._on_hold_down)
        btn.bind(on_touch_up=self._on_hold_up)
        layout.add_widget(btn)
        self.text_input = None

    def _qte_ui_alternate(self, layout):
        self.logger.debug("Setting up alternate/balance QTE display")
        keys = self.qte_context.get('keys_default', ['A', 'D'])
        self.alt_display = Label(
            text=f"Press: [b]{keys[0]}[/b] (Alternations: {self.alt_count})",
            font_size='20sp',
            markup=True,
            size_hint_y=None,
            height='40dp'
        )
        layout.add_widget(self.alt_display)
        row = BoxLayout(orientation='horizontal', spacing='10dp', size_hint_y=None, height='60dp')
        btn_left = Button(text="Left", font_size='32sp')
        btn_right = Button(text="Right", font_size='32sp')
        btn_left.bind(on_release=lambda *_: self.submit_callback({'event': 'alternation', 'side': 'left'}))
        btn_right.bind(on_release=lambda *_: self.submit_callback({'event': 'alternation', 'side': 'right'}))
        row.add_widget(btn_left)
        row.add_widget(btn_right)
        layout.add_widget(row)
        self.text_input = None

    def _qte_ui_choice(self, layout):
        self.logger.debug("Setting up choice QTE buttons")
        choices = self.qte_context.get('choices', self.qte_context.get('choices_default', ['left', 'right', 'forward']))
        choice_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height='50dp', spacing='5dp')
        for choice in choices:
            btn = Button(text=str(choice).title(), font_size='16sp')
            btn.bind(on_release=lambda x, c=choice: self._on_choice_selected(c))
            choice_layout.add_widget(btn)
        layout.add_widget(choice_layout)
        self.text_input = None

    def _qte_ui_sequence(self, layout):
        """
        Build a sequence/pattern/directional/code QTE UI with canonical on-screen buttons
        for each context, plus keyboard fallback. Touch-friendly for mobile, usable on desktop.
        """
        self.logger.debug("Setting up sequence/pattern QTE display with touch + keyboard support")
        required_seq = (
            self.qte_context.get('required_sequence') or
            self.qte_context.get('required_pattern') or
            self.qte_context.get('required_code') or ['up', 'down', 'left']
        )
        input_type = self.input_type

        # Display required sequence
        if isinstance(required_seq, list):
            seq_text = ' '.join(str(x).upper() for x in required_seq)
            vocab_raw = [str(x).lower() for x in required_seq]
        else:
            seq_text = str(required_seq).upper()
            vocab_raw = [str(required_seq).lower()]

        self.key_sequence = []
        self.sequence_display = Label(
            text=f"Required: [b]{seq_text}[/b]\nEntered: ",
            font_size='16sp',
            markup=True,
            size_hint_y=None,
            height='60dp'
        )
        layout.add_widget(self.sequence_display)

        # --- Context-specific button layouts ---
        def update_display():
            entered_text = ' '.join(self.key_sequence).upper()
            self.sequence_display.text = f"Required: [b]{seq_text}[/b]\nEntered: {entered_text}"

        def append_token(tok):
            self.key_sequence.append(tok)
            update_display()
            self.submit_callback({'event': 'sequence_input', 'sequence': self.key_sequence})

        def undo_last(_=None):
            if self.key_sequence:
                self.key_sequence.pop()
                update_display()

        def clear_all(_=None):
            if self.key_sequence:
                self.key_sequence = []
                update_display()

        # Directional context: show arrow buttons
        if input_type == 'directional':
            grid = GridLayout(cols=3, size_hint_y=None, height=dp(140), spacing=dp(6))
            # Row 1: [  ↑  ]
            grid.add_widget(Label())
            btn_up = Button(text="↑", font_size='20sp')
            btn_up.bind(on_release=lambda *_: append_token('up'))
            grid.add_widget(btn_up)
            grid.add_widget(Label())
            # Row 2: [←][   ][→]
            btn_left = Button(text="←", font_size='20sp')
            btn_left.bind(on_release=lambda *_: append_token('left'))
            grid.add_widget(btn_left)
            grid.add_widget(Label())
            btn_right = Button(text="→", font_size='20sp')
            btn_right.bind(on_release=lambda *_: append_token('right'))
            grid.add_widget(btn_right)
            # Row 3: [  ↓  ]
            grid.add_widget(Label())
            btn_down = Button(text="↓", font_size='20sp')
            btn_down.bind(on_release=lambda *_: append_token('down'))
            grid.add_widget(btn_down)
            grid.add_widget(Label())
            layout.add_widget(grid)

        # Code context: show 0-9 keypad
        elif input_type == 'code':
            grid = GridLayout(cols=3, size_hint_y=None, height=dp(180), spacing=dp(6))
            for n in ['1','2','3','4','5','6','7','8','9']:
                btn = Button(text=n, font_size='18sp')
                btn.bind(on_release=lambda _, t=n: append_token(t))
                grid.add_widget(btn)
            btn_clear = Button(text="Clear", font_size='16sp')
            btn_clear.bind(on_release=clear_all)
            grid.add_widget(btn_clear)
            btn_zero = Button(text='0', font_size='18sp')
            btn_zero.bind(on_release=lambda *_: append_token('0'))
            grid.add_widget(btn_zero)
            btn_undo = Button(text="Undo", font_size='16sp')
            btn_undo.bind(on_release=undo_last)
            grid.add_widget(btn_undo)
            layout.add_widget(grid)

        # Pattern/sequence: show unique tokens as buttons
        else:
            # Build vocabulary from required sequence
            vocab = set(vocab_raw)
            # Expand for directionals if present
            directionals = ['up', 'down', 'left', 'right']
            if any(t in directionals for t in vocab):
                vocab.update(directionals)
            tokens = sorted(vocab) if vocab else directionals
            cols = 3 if len(tokens) >= 3 else max(1, len(tokens))
            grid = GridLayout(cols=cols, size_hint_y=None, height=dp(((len(tokens)+cols-1)//cols)*44), spacing=dp(6))
            for tok in tokens:
                label = {'up':'↑', 'down':'↓', 'left':'←', 'right':'→'}.get(tok, tok.upper())
                btn = Button(text=label, font_size='16sp')
                btn.bind(on_release=lambda _, t=tok: append_token(t))
                grid.add_widget(btn)
            layout.add_widget(grid)

        # Controls row (Undo / Clear)
        controls_row = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(40), spacing=dp(6))
        undo_btn = Button(text="Undo", font_size='14sp')
        undo_btn.bind(on_release=undo_last)
        clr_btn = Button(text="Clear", font_size='14sp')
        clr_btn.bind(on_release=clear_all)
        controls_row.add_widget(undo_btn)
        controls_row.add_widget(clr_btn)
        layout.add_widget(controls_row)

        # Keyboard fallback
        self.text_input = TextInput(
            multiline=False,
            halign='center',
            font_size='18sp',
            size_hint_y=None,
            height='40dp'
        )
        layout.add_widget(self.text_input)
        submit_btn = Button(text="Submit", size_hint_y=None, height='36dp')
        submit_btn.bind(on_release=lambda *_: self.submit_callback({'event': 'sequence_input', 'sequence': self.text_input.text}))
        layout.add_widget(submit_btn)

    def _qte_ui_single_key(self, layout):
        self.logger.debug("Setting up single_key QTE display")
        required_key = self.qte_context.get('required_key', 'SPACE').upper()
        self.key_display = Label(
            text=f"Press: [b][color=ff0000]{required_key}[/color][/b]",
            font_size='32sp',
            markup=True,
            size_hint_y=None,
            height='60dp'
        )
        layout.add_widget(self.key_display)
        btn = Button(text=f"Press {required_key}", font_size='32sp', size_hint_y=None, height='60dp')
        btn.bind(on_release=lambda *_: self.submit_callback({'event': 'correct_key', 'key': required_key.lower()}))
        layout.add_widget(btn)
        self.text_input = None

    def _qte_ui_text_input(self, layout):
        self.logger.debug("Setting up input QTE with editable TextInput")
        self.text_input = TextInput(
            multiline=False,
            halign='center',
            font_size='24sp',
            size_hint_y=None,
            height='40dp'
        )
        layout.add_widget(self.text_input)
        submit_btn = Button(text="Submit", size_hint_y=None, height='36dp')
        submit_btn.bind(on_release=lambda *_: self.submit_callback({'event': 'submit_text', 'text': self.text_input.text}))
        layout.add_widget(submit_btn)

    def _qte_ui_spiral(self, layout):
        self.logger.debug("Setting up spiral QTE display")
        self.spiral_display = Label(
            text="Move your finger in a spiral pattern!\n(Or type 'spiral' to complete)",
            font_size='16sp',
            halign='center',
            size_hint_y=None,
            height='60dp'
        )
        layout.add_widget(self.spiral_display)
        self.text_input = None

    def _qte_ui_default(self, layout):
        self.logger.debug("Setting up default text input QTE")
        self.text_input = TextInput(
            multiline=False,
            halign='center',
            font_size='24sp',
            size_hint_y=None,
            height='40dp'
        )
        layout.add_widget(self.text_input)
        submit_btn = Button(text="Submit", size_hint_y=None, height='36dp')
        submit_btn.bind(on_release=lambda *_: self.submit_callback({'event': 'submit_text', 'text': self.text_input.text}))
        layout.add_widget(submit_btn)

    # NEW: unified handlers so the popup updates immediately on touch
    def _on_mash_press(self, *_):
        self.mash_count += 1
        try:
            target = None
            eff = self.qte_context.get('effective_target_mash_count')
            if isinstance(eff, (int, float)):
                target = int(eff)
            if hasattr(self, 'mash_counter'):
                if target is not None:
                    self.mash_counter.text = f"Presses: {self.mash_count} / {target}"
                else:
                    self.mash_counter.text = f"Presses: {self.mash_count}"
        except Exception:
            pass
        # Notify engine with the updated count
        self.submit_callback({'event': 'mash_press', 'count': self.mash_count})

    def _on_tap_press(self, *_):
        self.tap_count += 1
        try:
            required = getattr(self, 'tap_required', self.qte_context.get('required_tap_count', self.qte_context.get('required_tap_count_default', 10)))
            if hasattr(self, 'tap_counter'):
                self.tap_counter.text = f"Taps: {self.tap_count}/{int(required)}"
        except Exception:
            pass
        # Notify engine with the updated count
        self.submit_callback({'event': 'tap', 'count': self.tap_count})

    def _on_key_down(self, window, key, scancode, codepoint, modifiers):
        """Handle key events, but only if not dismissed and still in widget tree."""
        if getattr(self, 'is_dismissed', False):
            self.logger.debug("Key event ignored - popup is dismissed")
            return False
        
        # Additional safety check - ensure popup is still attached to screen
        if not self.parent:
            self.logger.debug("Key event ignored - popup not in widget tree")
            return False

        # CRITICAL FIX: If a TextInput has focus, let it handle all keys (including backspace)
        if self.text_input and self.text_input.focus:
            self.logger.debug("Key event deferred to TextInput (has focus)")
            return False  # Allow TextInput to process the key

        key_char = codepoint if codepoint else (chr(scancode) if scancode < 128 else str(scancode))
        self.logger.debug(f"Key down: key={key}, scancode={scancode}, codepoint='{codepoint}', modifiers={modifiers}, key_char='{key_char}'")


        if self.input_type == 'mash':
            self.mash_count += 1
            self.logger.info(f"Mash QTE: mash_count={self.mash_count}")
            if hasattr(self, 'mash_counter'):
                self.mash_counter.text = f"Presses: {self.mash_count}"
            self.submit_callback({'event': 'mash_press', 'count': self.mash_count})

        elif self.input_type in ('alternate', 'balance'):
            keys = self.qte_context.get('keys_default', ['a', 'd'])
            key_lower = key_char.lower() if key_char else ''
            if key_lower in [k.lower() for k in keys]:
                current_expected = keys[self.alt_count % 2].lower()
                if key_lower == current_expected:
                    self.alt_count += 1
                    next_key = keys[self.alt_count % 2]
                    self.logger.info(f"Alternation correct: alt_count={self.alt_count}, next_key='{next_key}'")
                    if hasattr(self, 'alt_display'):
                        self.alt_display.text = f"Press: [b]{next_key.upper()}[/b] (Alternations: {self.alt_count})"
                    self.submit_callback({'event': 'alternation', 'count': self.alt_count, 'key': key_lower})
                    # --- PATCH: If target reached, disable further input and dismiss ---
                    target = self.qte_context.get('target_alternations_default', 12)
                    if self.alt_count >= target:
                        self.logger.info("Alternation QTE: target reached, disabling input and dismissing popup.")
                        self.is_dismissed = True
                        # Notify engine of success before dismissing
                        self.submit_callback({'event': 'alternation_success', 'count': self.alt_count})
                        self.dismiss()
                    return True
                else:
                    self.logger.warning(f"Alternation wrong: expected='{current_expected}', pressed='{key_lower}'")
                    self.submit_callback({'event': 'wrong_key', 'expected': current_expected, 'pressed': key_lower})

        elif self.input_type == 'tap':
            self.tap_count += 1
            required = self.qte_context.get('required_tap_count_default', 10)
            self.logger.info(f"Tap QTE: tap_count={self.tap_count}/{required}")
            if hasattr(self, 'tap_counter'):
                self.tap_counter.text = f"Taps: {self.tap_count}/{required}"
            self.submit_callback({'event': 'tap', 'count': self.tap_count})

        elif self.input_type == 'single_key':
            required_key = self.qte_context.get('required_key', 'space').lower()
            self.logger.debug(f"Single key QTE: required_key='{required_key}', pressed='{key_char}'")
            if key_char and key_char.lower() == required_key:
                self.logger.info("Single key QTE: correct key pressed")
                self.submit_callback({'event': 'correct_key', 'key': key_char})
            else:
                self.logger.warning("Single key QTE: wrong key pressed")
                self.submit_callback({'event': 'wrong_key', 'expected': required_key, 'pressed': key_char})

        elif self.input_type in ('hold', 'hold_release'):
            if not self.hold_start_time:
                import time
                self.hold_start_time = time.time()
                self.logger.info(f"Hold QTE: hold started at {self.hold_start_time}")
                if hasattr(self, 'hold_display'):
                    self.hold_display.text = "Holding... (release when ready)"
                self.submit_callback({'event': 'hold_start', 'time': self.hold_start_time})

        elif self.input_type in ('sequence', 'pattern', 'input', 'directional'):
            if key_char:
                self.key_sequence.append(key_char.lower())
                self.logger.info(f"Sequence QTE: key_sequence={self.key_sequence}")
                if hasattr(self, 'sequence_display'):
                    entered_text = ' '.join(self.key_sequence).upper()
                    required_seq = (self.qte_context.get('required_sequence') or
                                    self.qte_context.get('required_pattern') or ['up', 'down'])
                    if isinstance(required_seq, list):
                        req_text = ' '.join(str(x).upper() for x in required_seq)
                    else:
                        req_text = str(required_seq).upper()
                    self.sequence_display.text = f"Required: [b]{req_text}[/b]\nEntered: {entered_text}"
                self.submit_callback({'event': 'sequence_input', 'sequence': self.key_sequence})

        elif self.text_input and key == 13:  # Enter key for text input QTEs
            self.logger.info(f"Text input QTE: submit text='{self.text_input.text}'")
            self.submit_callback({'event': 'submit_text', 'text': self.text_input.text})

        return True

    def _on_mouse_down(self, window, x, y, button, modifiers):
        """Handle mouse events, but only if not dismissed."""
        self.logger.debug(f"Mouse down: x={x}, y={y}, button={button}, modifiers={modifiers}")
        if getattr(self, 'is_dismissed', False):
            return False
        if self.input_type == 'mash':
            self.mash_count += 1
            self.logger.info(f"Mash QTE (mouse): mash_count={self.mash_count}")
            if hasattr(self, 'mash_counter'):
                self.mash_counter.text = f"Presses: {self.mash_count}"
            self.submit_callback({'event': 'mash_press', 'count': self.mash_count})
            return True
        return False

    def _on_key_up(self, window, key, scancode):
        """Handle key release events for hold QTEs, with logging."""
        self.logger.debug(f"Key up: key={key}, scancode={scancode}")
        if self.input_type in ('hold', 'hold_release') and self.hold_start_time:
            import time
            hold_duration = time.time() - self.hold_start_time
            self.logger.info(f"Hold QTE: released after {hold_duration:.2f}s")
            if hasattr(self, 'hold_display'):
                self.hold_display.text = f"Released after {hold_duration:.1f}s"
            self.submit_callback({'event': 'hold_release', 'duration': hold_duration})
            self.hold_start_time = None
        return True

    def _on_choice_selected(self, choice):
        """Handle choice button press"""
        self.logger.info(f"Choice QTE: selected '{choice}'")
        self.submit_callback({'event': 'choice_selected', 'choice': choice})

    def on_open(self):
        self.logger.debug("QTEPopup opened")
        if self.text_input:
            Clock.schedule_once(self._focus_text_input, 0.1)

    def _focus_text_input(self, dt):
        self.logger.debug("Focusing text input in QTEPopup")
        if self.text_input:
            self.text_input.focus = True

    def _update_timer(self, dt):
        if not hasattr(self, 'time_elapsed') or not hasattr(self, 'duration'):
            self.logger.warning("Timer update called but attributes missing")
            return False
        self.time_elapsed += dt
        remaining = max(0.0, self.duration - self.time_elapsed)
        if hasattr(self, 'timer_bar') and self.timer_bar:
            self.timer_bar.value = remaining
        self.logger.debug(f"Timer updated: time_elapsed={self.time_elapsed:.2f}, remaining={remaining:.2f}")
        if self.time_elapsed >= self.duration:
            self.logger.info("QTEPopup timer expired")
            if hasattr(self, 'timer_event') and self.timer_event:
                self.timer_event.cancel()
                self.timer_event = None
            return False
        return True

    def dismiss(self, *largs, **kwargs):
        """Override dismiss to ensure complete cleanup."""
        self.logger.info("Dismissing QTEPopup and cleaning up event bindings")
        
        # Set dismissed flag immediately to prevent further callbacks
        self.is_dismissed = True
        
        # Unbind ALL window events
        try:
            Window.unbind(on_key_down=self._on_key_down)
            Window.unbind(on_key_up=self._on_key_up) 
            Window.unbind(on_mouse_down=self._on_mouse_down)
        except Exception as e:
            self.logger.warning(f"Error unbinding window events: {e}")
        
        # Cancel any active timers
        if hasattr(self, 'timer_event') and self.timer_event:
            try:
                self.timer_event.cancel()
            except:
                pass
            
        # Call parent dismiss
        super().dismiss(*largs, **kwargs)


class QTEButtonWidget(BoxLayout):
    """
    Lightweight, touch-friendly QTE control surface that mirrors the keyboard-based QTEPopup.
    It emits the same event payloads expected by the engine so it can be dropped in from
    QTE_Engine.start_qte without removing any of the existing popup code.
    """
    def __init__(self, input_type, qte_engine, **kwargs):
        super().__init__(orientation='vertical', spacing=dp(8), **kwargs)
        self.input_type = input_type
        self.qte_engine = qte_engine

        self.hold_start_time = None
        self.tap_count = 0
        self.mash_count = 0
        self.alternations_done = 0

        self.status = Label(
            text="",
            size_hint=(1, 0.2),
            font_size=dp(18),
            font_name="RobotoMono",
            markup=True
        )
        self.add_widget(self.status)
        self._build_ui()

    def _build_ui(self):
        if self.input_type in ('mash', 'tap', 'tap_count', 'precision_tap_count'):
            # Use a single big button for both mash and tap families
            label = "Mash!" if self.input_type == 'mash' else "Tap!"
            btn = Button(text=label, font_size='32sp', size_hint=(1, 0.8))
            btn.bind(on_release=self._on_tap_or_mash)
            self.add_widget(btn)

        elif self.input_type in ('hold', 'hold_release', 'hold_and_release'):
            btn = Button(text="Hold!", font_size='32sp', size_hint=(1, 0.8))
            btn.bind(on_touch_down=self._on_hold_down)
            btn.bind(on_touch_up=self._on_hold_up)
            self.add_widget(btn)

        elif self.input_type in ('alternate', 'alternating_keys', 'balance'):
            row = BoxLayout(orientation='horizontal', size_hint=(1, 0.8), spacing=dp(10))
            self.alt_btns = []
            for i, label in enumerate(["Left", "Right"]):
                btn = Button(text=label, font_size='32sp', background_color=self._alt_color(i))
                btn.bind(on_release=lambda inst, idx=i: self._on_alternate(idx))
                self.alt_btns.append(btn)
                row.add_widget(btn)
            self.add_widget(row)
            self._update_alternate_visual()

        else:
            # Generic fallback single action
            btn = Button(text="Action!", font_size='32sp', size_hint=(1, 0.8))
            btn.bind(on_release=lambda inst: self.qte_engine.handle_qte_input({'event': 'button_press'}))
            self.add_widget(btn)

    def _engine_time(self):
        # Prefer engine's time source if provided
        if hasattr(self.qte_engine, 'get_time') and callable(self.qte_engine.get_time):
            return self.qte_engine.get_time()
        return time.time()

    def _on_tap_or_mash(self, _instance):
        if self.input_type == 'mash':
            self.mash_count += 1
            self.status.text = f"Mashes: {self.mash_count}"
            # Match QTEPopup event name for mash
            self.qte_engine.handle_qte_input({'event': 'mash_press', 'count': self.mash_count})
        else:
            self.tap_count += 1
            self.status.text = f"Taps: {self.tap_count}"
            self.qte_engine.handle_qte_input({'event': 'tap', 'count': self.tap_count})

    def _on_hold_down(self, instance, touch):
        if instance.collide_point(*touch.pos):
            self.hold_start_time = self._engine_time()
            self.status.text = "Holding..."
            # Emit start event to mirror popup behavior
            self.qte_engine.handle_qte_input({'event': 'hold_start', 'time': self.hold_start_time})
            return True
        return False

    def _on_hold_up(self, instance, touch):
        if instance.collide_point(*touch.pos) and self.hold_start_time is not None:
            held = self._engine_time() - self.hold_start_time
            self.status.text = f"Held: {held:.2f}s"
            self.qte_engine.handle_qte_input({'event': 'hold_release', 'duration': held})
            self.hold_start_time = None
            return True
        return False

    def _on_alternate(self, idx):
        # idx: 0 for left, 1 for right
        expected = self.alternations_done % 2
        if idx == expected:
            self.alternations_done += 1
            self.status.text = f"Alternations: {self.alternations_done}"
            # Send the alternation/key event the engine expects
            keys = []
            if hasattr(self.qte_engine, 'active_qte') and isinstance(self.qte_engine.active_qte, dict):
                keys = self.qte_engine.active_qte.get('keys_default', ['a', 'd'])
            if not keys:
                keys = ['a', 'd']
            key = keys[idx] if idx < len(keys) else 'a'
            self.qte_engine.handle_qte_input({'event': 'alternation', 'count': self.alternations_done, 'key': key})
            self._update_alternate_visual()
        else:
            self.status.text = "[color=ff6600]Wrong button! Alternate![/color]"

    def _alt_color(self, idx):
        # Highlight the expected button
        expected = self.alternations_done % 2
        if idx == expected:
            return [0.2, 0.8, 0.2, 1]  # Green
        else:
            return [0.5, 0.5, 0.5, 1]  # Gray

    def _update_alternate_visual(self):
        if hasattr(self, 'alt_btns'):
            for i, btn in enumerate(self.alt_btns):
                btn.background_color = self._alt_color(i)

    # Integration helper for the engine patch:
    # Allows QTE_Engine.start_qte to delegate simple count increments and return True.
    # This mirrors the "payload/handle_qte_input/return True" lines shown in the patch.
    def engine_tap(self, prev):
        if self.input_type == 'mash':
            payload = {'event': 'mash_press', 'count': prev + 1}
        else:
            payload = {'event': 'tap', 'count': prev + 1}
        self.qte_engine.handle_qte_input(payload)
        return True

class ContextDockWidget(BoxLayout):
    """Shows only commands relevant to current situation."""
    
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', spacing=dp(2), **kwargs)  # Reduced spacing
        self.logger = logging.getLogger(__name__ + ".ContextDockWidget")
        
        # Always-visible core actions section
        self.add_widget(Label(
            text='[b]Core Actions[/b]', 
            markup=True, 
            size_hint_y=None, 
            height=dp(20),  # Reduced from 25
            font_name="RobotoMonoBold",
            font_size=dp(12)  # Smaller font
        ))
        self.core_grid = GridLayout(
            cols=3, 
            spacing=dp(2),  # Reduced spacing
            size_hint_y=None, 
            height=dp(72)  # Reduced from 80, fits 2 rows of buttons
        )
        self.add_widget(self.core_grid)
        
        # Context-sensitive actions section
        self.add_widget(Label(
            text='[b][/b]', 
            markup=True, 
            size_hint_y=None,
            size_hint_x=0.75, 
            height=dp(20),  # Reduced from 25
            font_name="RobotoMonoBold",
            font_size=dp(12)  # Smaller font
        ))
        
        # Context grid in a ScrollView
        context_scroll = ScrollView(
            size_hint_y=None,
            height=dp(80),  # Fixed height prevents expansion
            do_scroll_x=False,
            do_scroll_y=True
        )
        # FIX: match core grid column count for uniform button widths
        self.context_grid = GridLayout(
            cols=3, 
            spacing=dp(2),
            size_hint_y=None
        )
        self.context_grid.bind(minimum_height=self.context_grid.setter('height'))
        context_scroll.add_widget(self.context_grid)
        self.add_widget(context_scroll)
    
    def update(self, game_logic):
        """Rebuild based on current game state."""
        # Core actions (always visible)
        self.core_grid.clear_widgets()
        core_actions = ['move', 'examine', 'inventory', 'take', 'use', 'wait', 'map', 'save', 'main menu']
        for verb in core_actions:
            btn = Button(
                text=verb.capitalize(), 
                size_hint_y=None, 
                height=dp(32),
                font_name="RobotoMonoBold",
                font_size=dp(12)
            )
            btn.bind(on_release=lambda _, v=verb: self.on_command(v))
            self.core_grid.add_widget(btn)

        # Context actions (based on room/inventory)
        self.context_grid.clear_widgets()
        # Keep columns in sync with core grid so single buttons don't stretch
        self.context_grid.cols = self.core_grid.cols
        if not game_logic:
            return

        room_id = game_logic.player.get('location')
        room_data = game_logic.get_room_data(room_id) or {}

        # --- Show unlock buttons for each locked exit IF player has a matching key ---
        items_master = getattr(game_logic, "resource_manager", None)
        if items_master and hasattr(items_master, "get_data"):
            items_master = items_master.get_data('items', {})
        else:
            items_master = {}
        player_keys = set()
        for item_key in game_logic.player.get('inventory', []):
            item_data = items_master.get(item_key, {})
            if item_data.get("type") == "key" or "key" in item_key.lower():
                player_keys.add(item_key)

        for direction, dest in (room_data.get('exits') or {}).items():
            if isinstance(dest, str):
                world_room = game_logic.current_level_rooms_world_state.get(dest, {})
                locked = world_room.get('locked') or world_room.get('locked_by_mri')
                if locked:
                    # Check if player has a key that can unlock this door
                    dest_data = game_logic.get_room_data(dest) or {}
                    locking = dest_data.get('locking', {})
                    required_key = locking.get('unlocks_with')
                    has_key = False
                    for key_id in player_keys:
                        key_data = items_master.get(key_id, {})
                        unlocks = [game_logic._norm(u) for u in key_data.get("unlocks", [])]
                        if (game_logic._norm(required_key) in unlocks or
                            game_logic._norm(dest) in unlocks or
                            game_logic._norm(direction) in unlocks or
                            "*" in key_data.get("unlocks", []) or
                            key_data.get("is_master_key")):
                            has_key = True
                            break
                    if has_key:
                        # Improved: Show which key unlocks if possible
                        key_name = key_data.get('name', key_id) if has_key else ''
                        btn_text = f"Unlock {direction.title()} ({dest.replace('_', ' ').title()})"
                        if key_name:
                            btn_text += f" [{key_name}]"
                        btn = Button(
                            text=btn_text,
                            size_hint_y=None,
                            height=dp(32),
                            font_name="RobotoMonoBold",
                            font_size=dp(12)
                        )
                        btn.bind(on_release=lambda _, d=direction: self.on_command(f"unlock {d}"))
                        self.context_grid.add_widget(btn)

        # --- Show unlock buttons for locked furniture ---
        for f in room_data.get('furniture', []):
            if isinstance(f, dict) and f.get('locked'):
                fname = f.get('name', 'Unknown')
                # Improved: Show which key unlocks if possible
                locking = f.get('locking', {})
                required_key = locking.get('unlocks_with') if isinstance(locking, dict) else None
                key_name = ""
                has_key = False
                for key_id in player_keys:
                    key_data = items_master.get(key_id, {})
                    unlocks = [game_logic._norm(u) for u in key_data.get("unlocks", [])]
                    if (game_logic._norm(required_key) in unlocks or
                        game_logic._norm(fname) in unlocks or
                        "*" in key_data.get("unlocks", []) or
                        key_data.get("is_master_key")):
                        has_key = True
                        key_name = key_data.get('name', key_id)
                        break
                btn_text = f"Unlock {fname}"
                if has_key and key_name:
                    btn_text += f" [{key_name}]"
                btn = Button(
                    text=btn_text,
                    size_hint_y=None,
                    height=dp(32),
                    font_name="RobotoMonoBold",
                    font_size=dp(12)
                )
                btn.bind(on_release=lambda _, n=fname: self.on_command(f"unlock {n}"))
                self.context_grid.add_widget(btn)

        context_actions = []

        # Locked doors/furniture nearby?
        if self._has_locked_things(game_logic, room_data):
            context_actions.append('unlock')
            context_actions.append('force')

        # NPCs present?
        if room_data.get('npcs'):
            context_actions.append('talk')
            if hasattr(game_logic, 'last_dialogue_context') and game_logic.last_dialogue_context.get('options'):
                context_actions.append('respond')

        # Breakable objects?
        if self._has_breakables(game_logic, room_data):
            context_actions.append('break')

        # Searchable containers?
        if self._has_containers(game_logic, room_data):
            context_actions.append('search')
            # Add 'take' if there are items or objects/furniture/hazards that can be taken
            has_take_targets = False
            # Check for items on ground
            if room_data.get('items'):
                has_take_targets = True
            # Check for takeable furniture/objects/hazards
            for f in room_data.get('furniture', []):
                if isinstance(f, dict) and (f.get('can_take') or f.get('is_takeable')):
                    has_take_targets = True
                    break
            for o in room_data.get('objects', []):
                if isinstance(o, dict) and (o.get('can_take') or o.get('is_takeable')):
                    has_take_targets = True
                    break
            # Hazards that can be taken (rare, but possible)
            hazards_master = getattr(game_logic.resource_manager, "get_data", lambda *a, **k: {})("hazards", {})
            for h in room_data.get('hazards', []):
                h_def = hazards_master.get(h, {})
                if h_def.get('can_take') or h_def.get('is_takeable'):
                    has_take_targets = True
                    break
            if has_take_targets:
                context_actions.append('take')

            # Add 'use' if there are inventory items or objects/furniture/hazards that can be used
            has_use_targets = False
            # Inventory items
            if game_logic.player.get('inventory'):
                has_use_targets = True
            # Furniture/objects with use interaction
            for f in room_data.get('furniture', []):
                if isinstance(f, dict) and (f.get('use_item_interaction') or f.get('can_use') or f.get('is_usable')):
                    has_use_targets = True
                    break  # <-- keep break here if you want to short-circuit on first match
            for o in room_data.get('objects', []):
                if isinstance(o, dict) and (o.get('use_item_interaction') or o.get('can_use') or o.get('is_usable')):
                    has_use_targets = True
                    break
            # Hazards with use interaction
            for h in room_data.get('hazards', []):
                h_def = hazards_master.get(h, {})
                if h_def.get('player_interaction', {}).get('use') or h_def.get('can_use') or h_def.get('is_usable'):
                    has_use_targets = True
                    break
            if has_use_targets:
                context_actions.append('use')

        for verb in context_actions:
            btn = Button(
                text=verb.capitalize(),
                size_hint_y=None,
                height=dp(32),
                # FIX: match core button font for uniform look
                font_name="RobotoMonoBold",
                font_size=dp(12)
            )
            btn.bind(on_release=lambda _, v=verb: self.on_command(v))
            self.context_grid.add_widget(btn)
    
    def _has_locked_things(self, gl, room_data) -> bool:
        # Check exits
        for direction, dest in (room_data.get('exits') or {}).items():
            if isinstance(dest, str):
                dest_data = gl.get_room_data(dest) or {}
                # Use live world state for lock status
                world_room = gl.current_level_rooms_world_state.get(dest, {})
                if world_room.get('locked') or world_room.get('locked_by_mri'):
                    return True
                if dest_data.get('locked') or dest_data.get('locked_by_mri'):
                    return True
        # Check furniture
        for f in room_data.get('furniture', []):
            if isinstance(f, dict) and f.get('locked'):
                return True
        return False
    
    def _has_breakables(self, gl, room_data) -> bool:
        for f in room_data.get('furniture', []):
            if isinstance(f, dict) and f.get('is_breakable'):
                return True
        return False
    
    def _has_containers(self, gl, room_data) -> bool:
        for f in room_data.get('furniture', []):
            if isinstance(f, dict) and (f.get('is_container') or f.get('contains_items')):
                return True
        return False
    
    def on_command(self, verb: str):
        """Override in GameScreen to handle command selection."""
        pass