# fd_terminal/qte_engine.py

import logging, copy, time
import random
import math
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.widget import Widget
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.properties import ListProperty
from fd_terminal.widgets import QTEButtonWidget


class QTE_Engine(Widget):
    def __init__(self, resource_manager=None, game_logic_ref=None, **kwargs):
        super().__init__(**kwargs)
        self.logger = logging.getLogger("QTE_Engine")
        self.resource_manager = resource_manager
        self.game_logic = game_logic_ref

        # Only load qte_definitions if resource_manager is available
        if self.resource_manager:
            self.qte_definitions = self.resource_manager.get_data('qte_definitions', {})
        else:
            self.qte_definitions = {}

        self.active_qte = None
        self.timeout_event = None
        self.sequence_widget = None

        # Mouse tracking for spiral detection
        self.mouse_positions = []
        self.spiral_center = None
        self.spiral_radius_history = []
        self.spiral_angle_total = 0
        self.debug_success_rate = None  # When set, overrides normal success calculation
        Window.bind(on_mouse_down=self._on_mouse_down)

        self.logger.info("QTE Engine forged and definitions loaded.")

    def start_qte(self, qte_type: str, context: dict):
        if getattr(self.game_logic, 'is_transitioning', False):
            self.logger.warning(f"Blocked start of QTE '{qte_type}' because a level transition is in progress.")
            return

        if self.active_qte:
            self.logger.warning(f"Cannot start QTE '{qte_type}'; a QTE is already active.")
            return

        blueprint = self.qte_definitions.get(qte_type)
        if not blueprint:
            self.logger.error(f"Could not find QTE definition for type: '{qte_type}'")
            return

        # Merge the blueprint with the specific context from the hazard.
        final_qte_data = copy.deepcopy(blueprint)
        final_qte_data.update(context)

        # Resolve per-character overrides now; expose effective values to UI
        effective = self._resolve_character_overrides(final_qte_data)
        if 'effective_target_mash_count' not in effective:
            effective['effective_target_mash_count'] = self._effective_mash_target(final_qte_data)
        final_qte_data.update(effective)

        # Initialize runtime state for this QTE instance
        final_qte_data['runtime_state'] = {
            'mash_count': 0,
            'tap_count': 0,
            'alternations_done': 0,
            'last_alt_key': None,
            'hold_start': None,
            'start_time': time.time(),
            'effective_target_mash_count': final_qte_data.get('effective_target_mash_count'),
        }

        self.active_qte = final_qte_data
        # Ensure runtime state container
        self.active_qte.setdefault('runtime_state', {})

        # Mark QTE active on the player so UI routes input
        if self.game_logic:
            self.game_logic.player['qte_active'] = True

        # Reset mouse tracking for spiral QTEs
        if final_qte_data.get('input_type') == 'spiral':
            self.mouse_positions = []
            self.spiral_center = None
            self.spiral_radius_history = []
            self.spiral_angle_total = 0

        final = self.active_qte
        prompt = final.get('ui_prompt_message') or final.get('description') or "React quickly!"
        duration = float(final.get('duration') or 3.0)
        input_type = final.get('input_type', 'word')

        # Remove any existing sequence/widget
        if self.sequence_widget and self.sequence_widget.parent:
            self.remove_widget(self.sequence_widget)
            self.sequence_widget = None

        # Always use QTEButtonWidget for button-based QTEs
        if input_type in (
            'mash', 'hold', 'hold_release', 'hold_and_release',
            'tap', 'tap_count', 'precision_tap_count',
            'alternate', 'alternating_keys', 'balance'
        ):
            self.sequence_widget = QTEButtonWidget(input_type, self)
            self.add_widget(self.sequence_widget)

        # If this is a sequence/pattern/directional QTE, add the widget
        if input_type in ('sequence', 'pattern', 'directional'):
            options = final.get('alphabet_default') or final.get('directions_default') or ["up", "down", "left", "right"]
            required_length = final.get('sequence_length_default') or final.get('pattern_length_default') or len(final.get('required_sequence', [])) or 3
            self.sequence_widget = QTESequenceWidget(
                options=options,
                required_length=required_length,
            )
            self.sequence_widget.qte_engine = self
            self.add_widget(self.sequence_widget)

        pass_through = (
            "choices", "choices_default", "correct_choice",
            "input_to_next_state", "valid_responses", "expected_input_word",
            "required_sequence", "required_pattern", "required_code",
            "target_mash_count", "required_tap_count", "required_key",
            "effective_target_mash_count"
        )
        qctx = {k: v for k, v in final.items() if k in pass_through}
        qctx["qte_source_hazard_id"] = final.get("qte_source_hazard_id")
        qctx["input_type"] = input_type

        self.logger.info(f"QTE '{qte_type}' started. Duration: {duration:.1f}s. Input type: {input_type}. Prompt: {prompt}")

        # Announce to UI
        if self.game_logic:
            self.game_logic.add_ui_event({
                "event_type": "show_qte",
                "qte_type": qte_type,
                "input_type": input_type,
                "prompt": prompt,
                "duration": duration,
                "qte_context": qctx
            })

        self.timeout_event = Clock.schedule_once(self._on_qte_timeout, duration)

    def get_time(self):
        # Use this for timing, so you can mock/replace if needed
        return time.time()

    def handle_qte_input(self, player_input):
        # Guard: do not process input if QTE has already been resolved
        if not self.active_qte:
            self.logger.warning("handle_qte_input called but no active QTE.")
            return

        # Prevent further tap/mash/touch input if QTE is already being resolved
        if getattr(self, 'is_dismissed', False):
            self.logger.info("handle_qte_input ignored: QTE already dismissed/resolved.")
            return

        q = self.active_qte
        qtype = (q.get('input_type') or '').lower()

        # Route dictionary-based UI events
        if isinstance(player_input, dict):
            event = (player_input.get('event') or '').strip().lower()
            self.logger.debug(f"QTE input event: {event}")

            # Event dispatch map
            handlers = {
                'submit_text': self._evt_submit_text,
                'mash_press': self._evt_mash_press,
                'tap': self._evt_tap,
                'sequence_input': self._evt_sequence_input,
                'correct_key': lambda p: self._evt_single_key(True, p),
                'wrong_key':   lambda p: self._evt_single_key(False, p),
                'hold_release': self._evt_hold_release,
                'choice_selected': self._evt_choice_selected, 
                'alternation_success': lambda p: self.resolve_qte(success=True),
            }
            handler = handlers.get(event)
            if handler:
                result = handler(player_input)
                if result is not None:
                    return result
        if isinstance(player_input, dict):
            event = (player_input.get('event') or '').strip().lower()
            if event == 'rhythm_tap':
                return self._evt_rhythm_tap(player_input)

            self.logger.debug("QTE dict event not applicable for this type; ignoring.")
            return None

        # Route string inputs
        text = str(player_input).strip().lower()
        self.logger.debug(f"Normalized input: {text!r}")
        return self._type_dispatch(qtype, text)

    # ---- Event handlers (dict payload) ----

    def _evt_rhythm_tap(self, payload):
        q = self.active_qte
        rs = q.get('runtime_state', {})
        rs.setdefault('tap_results', [])
        on_time = payload.get('on_time', False)
        rs['tap_results'].append(on_time)
        target = int(q.get('target_beats', 5))
        required_accuracy = float(q.get('required_accuracy', q.get('required_accuracy_default', 0.8)))
        self.logger.info(f"Rhythm QTE tap: on_time={on_time}, tap_results={rs['tap_results']}")
        if len(rs['tap_results']) >= target:
            hits = sum(1 for t in rs['tap_results'] if t)
            accuracy = hits / float(target)
            self.logger.info(f"Rhythm QTE complete: hits={hits}, accuracy={accuracy:.2f}, required={required_accuracy}")
            return self.resolve_qte(success=(accuracy >= required_accuracy))
        return None

    def _evt_choice_selected(self, payload: dict):
        """Handle choice selection from UI buttons"""
        q = self.active_qte
        qtype = (q.get('input_type') or '').lower()
        if qtype not in ('choice', 'cancel', 'timed_choice'):
            return None
        
        choice = str(payload.get('choice', '')).lower()
        mapping = q.get('input_to_next_state') or {}
        choices = q.get('choices') or q.get('choices_default') or []
        correct = (q.get('correct_choice') or q.get('correct_choice_default'))
        
        self.logger.info(f"Choice event: selected='{choice}', choices={choices}, mapping={mapping}")
        
        # Handle input_to_next_state mapping
        if choice and mapping and choice in mapping:
            q['next_state_after_qte_success'] = mapping[choice]
            self.logger.info("Choice QTE succeeded via input_to_next_state mapping.")
            return self.resolve_qte(success=True)
        
        # Handle correct choice mode
        if correct:
            result = choice == str(correct).lower()
            self.logger.info(f"Choice QTE {'succeeded' if result else 'failed'} (correct-choice mode).")
            return self.resolve_qte(success=result)
        
        # Handle any valid choice mode
        result = choice in [str(c).lower() for c in choices]
        self.logger.info(f"Choice QTE {'succeeded' if result else 'failed'} (any valid choice mode).")
        return self.resolve_qte(success=result)

    def _evt_submit_text(self, payload: dict):
        """Handle text submission for word/input QTEs."""
        q = self.active_qte
        qtype = (q.get('input_type') or '').lower()
        if qtype != 'word':
            return None
        typed = (payload.get('text') or '').strip().lower()
        expected = (q.get('expected_input_word') or '').strip().lower()
        alt = (q.get('alternative_input') or '').strip().lower()
        valids = [v.strip().lower() for v in (q.get('valid_responses') or [])]
        allowed = {v for v in [expected, alt] if v}
        allowed.update(valids)
        self.logger.info(f"Word QTE submit: typed='{typed}', allowed={sorted(allowed) or ['<none>']}")
        if not allowed:
            return self.resolve_qte(success=(len(typed) > 0))
        return self.resolve_qte(success=(typed in allowed))

    def _evt_mash_press(self, payload: dict):
        q = self.active_qte
        rs = q.get('runtime_state', {})
        prev = rs.get('mash_count', 0)
        rs['mash_count'] = int(payload.get('count', prev + 1))
        target = (rs.get('effective_target_mash_count')
                  or q.get('effective_target_mash_count')
                  or q.get('target_mash_count')
                  or q.get('target_mash_count_default')
                  or q.get('target_score_default')
                  or 15)
        self.logger.info(f"Mash event: count={rs['mash_count']}, target={target}")
        if rs['mash_count'] >= int(target):
            self.logger.info("Mash QTE succeeded.")
            return self.resolve_qte(success=True)
        return None

    def _evt_tap(self, payload: dict):
        q = self.active_qte
        rs = q.get('runtime_state', {})
        rs['tap_count'] = int(payload.get('count', rs.get('tap_count', 0)))
        need = int(q.get('required_tap_count', q.get('required_tap_count_default', 10)))
        self.logger.info(f"Tap event: count={rs['tap_count']}, need={need}")
        if rs['tap_count'] >= need:
            self.logger.info("Tap QTE succeeded.")
            return self.resolve_qte(success=True)
        return None

    def _evt_sequence_input(self, payload: dict):
        q = self.active_qte
        qtype = (q.get('input_type') or '').lower()
        if qtype not in ('sequence', 'pattern', 'directional'):
            return None
        rs = q.get('runtime_state', {})
        rs['key_sequence'] = list(payload.get('sequence', []))
        required = [s.strip().lower() for s in (q.get('required_sequence') or q.get('required_pattern') or [])]
        self.logger.info(f"Sequence event: entered={rs['key_sequence']}, required={required}")
        if required and [s.lower() for s in rs['key_sequence']] == required:
            self.logger.info("Sequence QTE succeeded.")
            return self.resolve_qte(success=True)
        return None

    def _evt_single_key(self, success: bool, payload: dict):
        self.logger.info(f"Single Key QTE {'succeeded' if success else 'failed'}.")
        return self.resolve_qte(success=success)

    def _evt_hold_release(self, payload: dict):
        q = self.active_qte
        qtype = (q.get('input_type') or '').lower()
        if qtype not in ('hold', 'hold_release', 'hold_threshold', 'hold_to_threshold', 'hold_and_release'):
            return None
        dur = float(payload.get('duration', 0.0))
        # For hold_and_release, check the release window
        if qtype in ('hold_release', 'hold_and_release'):
            window = (q.get('release_window') or q.get('release_window_default') or [0.6, 0.8])
            lo, hi = float(window[0]), float(window[1])
            self.logger.info(f"Hold & Release QTE: held={dur:.2f}s, window=({lo:.2f}, {hi:.2f})")
            return self.resolve_qte(success=(lo <= dur <= hi))
        # For plain hold, check minimum duration
        need = float(q.get('required_hold_time', q.get('required_hold_time_default', 2.0)))
        self.logger.info(f"Hold QTE release: held={dur:.2f}s, need={need:.2f}s")
        return self.resolve_qte(success=(dur >= need))

    # ---- Type handlers (string payload) ----

    def _type_dispatch(self, qtype: str, text: str):
        if qtype == 'word':
            return self._type_word(text)
        if qtype == 'spiral':
            # allow CLI fallback
            if text == 'spiral':
                self.logger.info("Spiral QTE passed via text input.")
                return self.resolve_qte(success=True)
            return None
        if qtype in ('sequence', 'pattern', 'directional'):
            return self._type_sequence_like(text)
        if qtype == 'code':
            return self._type_code(text)
        if qtype in ('hold', 'hold_threshold', 'hold_to_threshold'):
            return self._type_hold(text)
        if qtype in ('hold_release', 'timed_release', 'hold_and_release'):
            return self._type_hold_release(text)
        if qtype in ('single_key', 'reaction'):
            return self._type_single_key(text)
        if qtype in ('choice', 'cancel', 'timed_choice'):
            return self._type_choice(text)
        if qtype in ('tap', 'tap_count', 'precision_tap_count'):
            return self._type_tap(text)
        if qtype in ('alternate', 'alternating_keys', 'balance'):
            return self._type_alternate(text)
        if qtype == 'rhythm':
            return self._type_rhythm(text)
        if qtype in ('analog', 'aim', 'aim_click', 'drag'):
            return self._type_analog_like(text)

        # Fallback: accept any non-empty input
        if text:
            self.logger.info("Fallback QTE succeeded (any input).")
            return self.resolve_qte(success=True)
        return None

    def _type_word(self, text: str):
        q = self.active_qte
        expected = (q.get('expected_input_word') or '').strip().lower()
        alt = (q.get('alternative_input') or '').strip().lower()
        valids = [v.strip().lower() for v in (q.get('valid_responses') or [])]
        allowed = {v for v in [expected, alt] if v}
        allowed.update(valids)
        if not allowed:
            return self.resolve_qte(success=(len(text) > 0))
        return self.resolve_qte(success=(text in allowed))

    def _type_sequence_like(self, text: str):
        q = self.active_qte
        required = (q.get('required_sequence') or q.get('required_pattern'))
        self.logger.debug(f"Sequence QTE required: {required}")
        if isinstance(required, list) and text == " ".join(str(x).lower() for x in required):
            self.logger.info("Sequence QTE succeeded.")
            return self.resolve_qte(success=True)
        self.logger.info("Sequence QTE failed: wrong input.")
        return self.resolve_qte(success=False, reason="wrong_input")

    def _type_code(self, text: str):
        q = self.active_qte
        required = q.get('required_code')
        self.logger.debug(f"Code QTE required: {required}")
        if isinstance(required, list):
            if text == " ".join(required):
                self.logger.info("Code QTE succeeded.")
                return self.resolve_qte(success=True)
            self.logger.info("Code QTE failed: wrong input.")
            return self.resolve_qte(success=False, reason="wrong_input")
        expected = (q.get('expected_input_word') or '').lower()
        self.logger.debug(f"Code QTE fallback expected: {expected}")
        return self.resolve_qte(success=(text == expected))

    def _type_hold(self, text: str):
        q = self.active_qte
        rs = q.get('runtime_state', {})
        if text == 'hold':
            rs['hold_start'] = time.time()
            self.logger.debug("Hold QTE: hold started.")
            return None
        if text == 'release':
            if rs.get('hold_start'):
                held = time.time() - rs['hold_start']
                need = float(q.get('required_hold_time', q.get('required_hold_time_default', 2.0)))
                self.logger.debug(f"Hold QTE: held={held:.2f}s, need={need:.2f}s")
                return self.resolve_qte(success=(held >= need))
            self.logger.info("Hold QTE failed: release without hold.")
            return self.resolve_qte(success=False, reason="wrong_input")
        self.logger.debug("Hold QTE input not recognized.")
        return None

    def _type_hold_release(self, text: str):
        q = self.active_qte
        rs = q.get('runtime_state', {})
        if text == 'hold':
            rs['hold_start'] = time.time()
            self.logger.debug("Hold & Release QTE: hold started.")
            return None
        if text == 'release':
            if rs.get('hold_start'):
                held = time.time() - rs['hold_start']
                window = (q.get('release_window') or q.get('release_window_default') or [0.6, 0.8])
                lo, hi = float(window[0]), float(window[1])
                self.logger.debug(f"Hold & Release QTE: held={held:.2f}s, window=({lo:.2f}, {hi:.2f})")
                return self.resolve_qte(success=(lo <= held <= hi))
            self.logger.info("Hold & Release QTE failed: release without hold.")
            return self.resolve_qte(success=False, reason="wrong_input")
        self.logger.debug("Hold & Release QTE input not recognized.")
        return None

    def _type_single_key(self, text: str):
        q = self.active_qte
        req = (q.get('required_key') or '').lower()
        self.logger.debug(f"Single Key QTE required: {req}")
        if req:
            result = text == req
            self.logger.info(f"Single Key QTE {'succeeded' if result else 'failed'}.")
            return self.resolve_qte(success=result)
        result = len(text) == 1
        self.logger.info(f"Single Key QTE {'succeeded' if result else 'failed'} (any key).")
        return self.resolve_qte(success=result)

    def _type_choice(self, text: str):
        q = self.active_qte
        mapping = q.get('input_to_next_state') or {}
        choices = q.get('choices') or q.get('choices_default') or []
        correct = (q.get('correct_choice') or q.get('correct_choice_default'))
        self.logger.debug(f"Choice QTE: input={text}, choices={choices}, mapping={mapping}, correct={correct}")
        if text and mapping and text in mapping:
            q['next_state_after_qte_success'] = mapping[text]
            self.logger.info("Choice QTE succeeded via input_to_next_state mapping.")
            return self.resolve_qte(success=True)
        if correct:
            result = text == str(correct).lower()
            self.logger.info(f"Choice QTE {'succeeded' if result else 'failed'} (correct-choice mode).")
            return self.resolve_qte(success=result)
        result = text in [str(c).lower() for c in choices]
        self.logger.info(f"Choice QTE {'succeeded' if result else 'failed'} (any valid choice mode).")
        return self.resolve_qte(success=result)

    def _type_tap(self, text: str):
        q = self.active_qte
        rs = q.get('runtime_state', {})
        prev = rs.get('tap_count', 0)
        rs['tap_count'] = prev + 1
        need = int(q.get('required_tap_count', q.get('required_tap_count_default', 10)))
        self.logger.debug(f"Tap QTE: count={rs['tap_count']}, need={need}")
        if rs['tap_count'] >= need:
            self.logger.info("Tap QTE succeeded.")
            return self.resolve_qte(success=True)
        return None

    def _type_alternate(self, text: str):
        q = self.active_qte
        keys = q.get('keys_default', q.get('keys', ['a', 'd']))
        if not keys or len(keys) < 2:
            keys = ['a', 'd']
        rs = q.get('runtime_state', {})
        rs['alternations_done'] = rs.get('alternations_done', 0)
        target = int(q.get('target_alternations_default', q.get('target_alternations', 12)))
        expected = str(keys[rs['alternations_done'] % 2]).lower()
        self.logger.debug(f"Alternate QTE: input={text}, expected={expected}, done={rs['alternations_done']}, target={target}")
        if text == expected:
            rs['alternations_done'] += 1
            if rs['alternations_done'] >= target:
                self.logger.info("Alternate QTE succeeded.")
                return self.resolve_qte(success=True)
            return None
        self.logger.info("Alternate QTE failed: wrong input.")
        return self.resolve_qte(success=False, reason="wrong_input")

    def _type_rhythm(self, text: str):
        q = self.active_qte
        rs = q.get('runtime_state', {})
        prev = rs.get('tap_count', 0)
        rs['tap_count'] = prev + 1
        need = int(q.get('target_beats', 5))
        self.logger.debug(f"Rhythm QTE: count={rs['tap_count']}, need={need}")
        if rs['tap_count'] >= need:
            self.logger.info("Rhythm QTE succeeded.")
            return self.resolve_qte(success=True)
        return None

    def _type_analog_like(self, text: str):
        self.logger.debug(f"Analog/Aim QTE input: {text!r}")
        if text:
            self.logger.info("Analog/Aim QTE succeeded.")
            return self.resolve_qte(success=True)
        return None

    def _on_qte_timeout(self, dt):
        """Handle QTE timeout - process failure then cleanup."""
        if self.active_qte:
            self.logger.info(f"QTE timed out for '{self.active_qte.get('name')}'.")
            # Process timeout as failure WITHOUT clearing active_qte first
            result = self.resolve_qte(success=False, reason="timeout")
            if self.game_logic:
                self.game_logic._handle_qte_resolution(result)

    def _force_qte_cleanup(self):
        """Force immediate UI cleanup without clearing QTE data."""
        # Clear UI state but keep active_qte for resolve_qte to process
        if self.game_logic:
            self.game_logic.player['qte_active'] = False
            self.game_logic.add_ui_event({"event_type": "hide_qte"})
        
        # Cancel timeout if it exists
        if self.timeout_event:
            try:
                self.timeout_event.cancel()
            except:
                pass
            self.timeout_event = None

    def dismiss(self, *largs, **kwargs):
        """Override dismiss to ensure proper cleanup."""
        self.logger.info("Dismissing QTEPopup and cleaning up event bindings")
        
        # Unbind all events to prevent further input processing
        try:
            Window.unbind(on_key_down=self._on_key_down)
            Window.unbind(on_mouse_down=self._on_mouse_down)
        except Exception as e:
            self.logger.warning(f"Error unbinding events: {e}")
        
        # Mark as dismissed to prevent further callbacks
        self.is_dismissed = True
        
        # Remove sequence widget if present
        if self.sequence_widget and self.sequence_widget.parent:
            self.remove_widget(self.sequence_widget)
            self.sequence_widget = None
        
        super().dismiss(*largs, **kwargs)

    def _on_mouse_down(self, window, x, y, button, modifiers):
        if getattr(self, 'is_dismissed', False):
            return False
        if not self.active_qte:
            return False
        qtype = (self.active_qte.get('input_type') or '').lower()
        if qtype in ('mash',):
            rs = self.active_qte.get('runtime_state', {})
            prev = rs.get('mash_count', 0)
            payload = {'event': 'mash_press', 'count': prev + 1}
            self.handle_qte_input(payload)
            return True
        elif qtype in ('tap', 'tap_count', 'precision_tap_count'):
            rs = self.active_qte.get('runtime_state', {})
            prev = rs.get('tap_count', 0)
            payload = {'event': 'tap', 'count': prev + 1}
            self.handle_qte_input(payload)
            return True
        elif qtype in ('alternate', 'alternating_keys', 'balance'):
            keys = self.active_qte.get('keys_default', self.active_qte.get('keys', ['a', 'd']))
            if not keys or len(keys) < 2:
                keys = ['a', 'd']
            if button == 'left':
                self.handle_qte_input(keys[0])
            elif button == 'right':
                self.handle_qte_input(keys[1])
            return True
        return False

    def on_touch_down(self, touch):
        if not self.active_qte:
            return super().on_touch_down(touch)
        qtype = (self.active_qte.get('input_type') or '').lower()
        # If a QTEPopup with a hold button is present, ignore global touch
        if qtype in ('hold_release', 'timed_release', 'hold_and_release', 'hold', 'hold_threshold', 'hold_to_threshold'):
            # Only the popup/button should handle this
            return False
        elif qtype in ('mash',):
            rs = self.active_qte.get('runtime_state', {})
            prev = rs.get('mash_count', 0)
            payload = {'event': 'mash_press', 'count': prev + 1}
            self.handle_qte_input(payload)
            return True
        elif qtype in ('tap', 'tap_count', 'precision_tap_count'):
            rs = self.active_qte.get('runtime_state', {})
            prev = rs.get('tap_count', 0)
            payload = {'event': 'tap', 'count': prev + 1}
            self.handle_qte_input(payload)
            return True
        elif qtype == 'rhythm':
            rs = self.active_qte.get('runtime_state', {})
            prev = rs.get('tap_count', 0)
            payload = {'event': 'tap', 'count': prev + 1}
            self.handle_qte_input(payload)
            return True
        elif qtype in ('alternate', 'alternating_keys', 'balance'):
            # Split screen: left = first key, right = second key
            width = self.width if self.width else Window.width
            keys = self.active_qte.get('keys_default', self.active_qte.get('keys', ['a', 'd']))
            if not keys or len(keys) < 2:
                keys = ['a', 'd']
            if touch.x < width / 2:
                self.handle_qte_input(keys[0])
            else:
                self.handle_qte_input(keys[1])
            return True
        elif qtype in ('single_key', 'reaction'):
            # Treat any tap as the required key for mobile
            req = (self.active_qte.get('required_key') or '').lower()
            if req:
                self.handle_qte_input(req)
            else:
                self.handle_qte_input('tap')
            return True
        elif qtype in ('aim', 'aim_click'):
            # If your UI provides a target area, check if touch is inside it
            # For now, treat any tap as a valid aim
            self.handle_qte_input('aim')
            return True
        elif qtype == 'drag':
            # Start drag tracking
            self.drag_start = (touch.x, touch.y)
            return True
        elif qtype == 'spiral':
            # Start spiral tracking
            self.mouse_positions = [(touch.x, touch.y)]
            self.spiral_center = None
            self.spiral_radius_history = []
            self.spiral_angle_total = 0
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if not self.active_qte:
            return super().on_touch_move(touch)
        qtype = (self.active_qte.get('input_type') or '').lower()
        if qtype == 'drag':
            # Optionally, track drag path here
            pass
        elif qtype == 'spiral':
            self._handle_mouse_spiral(touch.x, touch.y)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if not self.active_qte:
            return super().on_touch_up(touch)
        qtype = (self.active_qte.get('input_type') or '').lower()
        # For timed release variants, let the dedicated popup/button handle release
        if qtype in ('hold_release', 'timed_release', 'hold_and_release'):
            return False
        if qtype in ('hold', 'hold_threshold', 'hold_to_threshold'):
            # End hold (release) for non-timed hold variants
            self.handle_qte_input('release')
            return True
        elif qtype == 'drag':
            # On drag end, treat as drag complete
            self.handle_qte_input('drag')
            return True
        return super().on_touch_up(touch)

    def _on_key_down(self, window, key, scancode, codepoint, modifiers):
        """Handle key press events, but only if not dismissed."""
        if getattr(self, 'is_dismissed', False):
            return False
        
    def _on_mouse_down(self, window, x, y, button, modifiers):
        """Handle mouse events, but only if not dismissed.""" 
        if getattr(self, 'is_dismissed', False):
            return False
        if not self.active_qte:
            return False
        qtype = (self.active_qte.get('input_type') or '').lower()
        if qtype in ('mash',):
            rs = self.active_qte.get('runtime_state', {})
            prev = rs.get('mash_count', 0)
            payload = {'event': 'mash_press', 'count': prev + 1}
            self.handle_qte_input(payload)
            return True
        elif qtype in ('tap', 'tap_count', 'precision_tap_count'):
            rs = self.active_qte.get('runtime_state', {})
            prev = rs.get('tap_count', 0)
            payload = {'event': 'tap', 'count': prev + 1}
            self.handle_qte_input(payload)
            return True
        elif qtype in ('alternate', 'alternating_keys', 'balance'):
            keys = self.active_qte.get('keys_default', self.active_qte.get('keys', ['a', 'd']))
            if not keys or len(keys) < 2:
                keys = ['a', 'd']
            if button == 'left':
                self.handle_qte_input(keys[0])
            elif button == 'right':
                self.handle_qte_input(keys[1])
            return True
        elif qtype == 'rhythm':
            rs = self.active_qte.get('runtime_state', {})
            prev = rs.get('tap_count', 0)
            payload = {'event': 'tap', 'count': prev + 1}
            self.handle_qte_input(payload)
            return True
        return False

    def _build_resolution_message(self, qte_data: dict, success: bool, reason: str = "") -> str:
        """Build the resolution message for a completed QTE, preferring hazard-supplied messages over QTE defaults."""
        if not qte_data:
            return "QTE resolved."

        # Prefer hazard-supplied messages over QTE definition defaults
        if success:
            message = (
                qte_data.get('success_message') or
                qte_data.get('success_message_default') or
                "Success!"
            )
        else:
            if reason == "timeout" and qte_data.get('timeout_message'):
                message = qte_data['timeout_message']
            else:
                message = (
                    qte_data.get('failure_message') or
                    qte_data.get('failure_message_wrong_input') or
                    qte_data.get('failure_message_default') or
                    "Failed!"
                )

        # Apply HP damage on failure
        if not success:
            hp_damage = (
                qte_data.get('hp_damage_on_failure') or
                qte_data.get('hp_damage_on_failure_default') or
                0
            )
            if hp_damage > 0:
                current_hp = self.game_logic.player.get('hp', 100)
                new_hp = max(0, current_hp - hp_damage)
                self.game_logic.player['hp'] = new_hp
                message += f" You lose {hp_damage} HP."

                is_fatal = (
                    qte_data.get('is_fatal_on_failure') or
                    qte_data.get('is_fatal_on_failure_default') or
                    False
                )
                if is_fatal or new_hp <= 0:
                    self.game_logic.is_game_over = True

                    # Pull death_reason from the hazard's failure state
                    death_reason = self._get_hazard_death_message(qte_data)
                    self.game_logic.player.setdefault('death_reason', death_reason)
                    message += " You have died!"

        self.logger.info(f"QTE '{qte_data.get('name', 'Unknown')}' resolved. Success: {success}. Message: {message}")
        return message

    def _get_hazard_death_message(self, qte_data: dict) -> str:
        """
        Extract the canonical death message from the hazard state that triggered this QTE.
        Falls back to a constructed message if not found.
        """
        hazard_id = qte_data.get('qte_source_hazard_id')
        failure_state = qte_data.get('next_state_after_qte_failure')
        
        # Try to get death message from the failure state in hazard definition
        if hazard_id and failure_state and self.game_logic and self.game_logic.hazard_engine:
            try:
                hazard = self.game_logic.hazard_engine.active_hazards.get(hazard_id)
                if hazard:
                    master_data = hazard.get('master_data', {})
                    states = master_data.get('states', {})
                    failure_state_def = states.get(failure_state, {})
                    
                    # Prefer explicit death_message from state
                    death_msg = failure_state_def.get('death_message')
                    if death_msg:
                        return death_msg
                    
                    # Fall back to state description if marked as terminal
                    if failure_state_def.get('is_terminal_state') or failure_state_def.get('instant_death_in_room'):
                        desc = failure_state_def.get('description')
                        if desc:
                            return desc
                    
                    # Use hazard name as last resort
                    hazard_name = master_data.get('name', 'an unknown hazard')
                    return f"Killed by {hazard_name}."
            except Exception as e:
                self.logger.error(f"_get_hazard_death_message: failed to extract death message: {e}", exc_info=True)
        
        # Final fallback
        qte_name = qte_data.get('name', 'a deadly hazard')
        return f"You failed to overcome {qte_name}."

    def _get_current_character(self) -> str:
        try:
            return (self.game_logic.player.get('character_class') or self.game_logic.player.get('class') or '').upper()
        except Exception:
            return ''

    def resolve_qte(self, success: bool, reason: str = "") -> dict:
        """Improved QTE resolution: returns result data, tracks evaded hazards, and commands UI resolution."""
        if not self.active_qte:
            self.logger.warning("resolve_qte called but no active QTE found")
            return {"success": False, "reason": "no_active_qte"}

        qte_data = self.active_qte
        self.active_qte = None

        # Cancel timeout
        if self.timeout_event:
            try:
                self.timeout_event.cancel()
            except Exception:
                pass
            self.timeout_event = None

        # Remove sequence widget if present
        if self.sequence_widget and self.sequence_widget.parent:
            self.remove_widget(self.sequence_widget)
            self.sequence_widget = None

        # Build resolution message
        message = self._build_resolution_message(qte_data, success, reason)

        # Determine next state
        if success:
            # Prefer new 'on_success' mapping if present, fallback to legacy
            next_state = (
                qte_data.get('on_success', {}).get('target_state')
                or qte_data.get('next_state_after_qte_success')
                or 'inactive'
            )
            # Track successfully evaded hazards
            if self.game_logic and next_state in ['inactive', 'resolved', 'evaded', 'neutralized']:
                hazard_id = qte_data.get('qte_source_hazard_id')
                if hazard_id:
                    hazard_type = hazard_id.split('#')[0] if '#' in hazard_id else hazard_id
                    hazards_master = self.game_logic.resource_manager.get_data('hazards', {})
                    hazard_def = hazards_master.get(hazard_type, {})
                    evaded_hazard = {
                        'name': hazard_def.get('name', hazard_type.replace('_', ' ').title()),
                        'description': f"Successfully evaded via QTE: {qte_data.get('description', 'Quick reflexes saved you!')}"
                    }
                    self.game_logic.player.setdefault('evaded_hazards', []).append(evaded_hazard)
                    self.logger.info(f"Added evaded hazard: {evaded_hazard['name']}")
        else:
            next_state = (
                qte_data.get('on_failure', {}).get('target_state')
                or qte_data.get('next_state_after_qte_failure')
                or 'critical'
            )

        hazard_id = qte_data.get('qte_source_hazard_id')
        if not hazard_id:
            self.logger.warning("resolve_qte: No hazard_id found in QTE data")
            return {
                "success": success,
                "reason": reason or "no_hazard_id",
                "message": message
            }

        # Destroy any QTE popup before showing result
        if self.game_logic:
            self.game_logic.add_ui_event({"event_type": "destroy_qte_popup", "priority": 1000})

        # Complete resolution: show popup and trigger hazard state change after dismiss
        self._complete_qte_resolution(message, hazard_id, next_state)
        return {
            "success": success,
            "reason": reason,
            "message": message,
            "qte_source_hazard_id": hazard_id,
            "next_state_success": qte_data.get('next_state_after_qte_success'),
            "next_state_failure": qte_data.get('next_state_after_qte_failure'),
            "hp_damage": qte_data.get('hp_damage_on_failure', 0) if not success else 0,
            "is_fatal": qte_data.get('is_fatal_on_failure', False) if not success else False
        }
        
    def _complete_qte_resolution(self, message: str, hazard_id: str, next_state: str):
        """Show result popup first; apply next state only after dismiss."""
        if not self.game_logic:
            return
        self.game_logic.add_ui_event({
            "event_type": "show_popup",
            "priority": 99,
            "title": "QTE Result",
            "message": message,
            "on_close_set_hazard_state": {
                "hazard_id": hazard_id,
                "target_state": next_state
            }
        })

    def _resolve_character_overrides(self, qte_data: dict) -> dict:
        """
        Resolve known per-character tunables in-place. Returns a dict of effective values to expose to UI.
        """
        effective = {}
        char = self._get_current_character()

        def _pick(value):
            if isinstance(value, dict):
                if char and char in value:
                    return value[char]
                if 'default' in value:
                    return value['default']
                # fallback to any scalar inside
                for v in value.values():
                    if isinstance(v, (int, float, str)):
                        return v
                return None
            return value

        # Known tunables that may be authored as maps
        keys = [
            'target_mash_count',
            'required_tap_count',
            'required_hold_time',
            'target_alternations_default',
            'pattern_length_default',
            'sequence_length_default',
        ]
        for k in keys:
            if k in qte_data:
                resolved = _pick(qte_data.get(k))
                if resolved is not None:
                    qte_data[k] = resolved
                    effective[f"effective_{k}"] = resolved

        # Add EMT perk if applicable and no explicit override was provided for mash
        if 'effective_target_mash_count' not in effective and 'target_mash_count' in qte_data:
            try:
                t = int(qte_data.get('target_mash_count'))
            except Exception:
                t = None
            if t is not None:
                if self._get_current_character() == 'EMT':
                    t = max(1, t - 10)
                effective['effective_target_mash_count'] = t

        return effective

    def _resolve_for_character(self, value, default_key: str = 'default'):
        """
        Resolve a value that may be a per-character mapping, e.g. {"default": 25, "EMT": 15}.
        Returns a scalar (int/float/str) suitable for use by the QTE logic.
        """
        if not isinstance(value, dict):
            return value
        try:
            char = (self.game_logic.player.get('character_class') or self.game_logic.player.get('class') or '').upper()
        except Exception:
            char = ''
        if char and char in value:
            return value[char]
        if default_key in value:
            return value[default_key]
        # Fallback to any scalar value found
        for v in value.values():
            if isinstance(v, (int, float, str)):
                return v
        return None

    def _effective_mash_target(self, qte_data: dict) -> int:
        """
        Compute the effective mash target with character rules:
        - Use per-character overrides if provided.
        - Otherwise apply EMT perk: -10 presses (min 1).
        """
        raw = qte_data.get('target_mash_count')
        came_from_char_map = isinstance(raw, dict)
        target = self._resolve_for_character(raw)
        if target is None:
            target = (qte_data.get('target_mash_count_default')
                      or qte_data.get('target_score_default')
                      or 999)
        try:
            target = int(target)
        except Exception:
            target = 999

        # Apply EMT perk only if not explicitly overridden in the map
        char = ''
        try:
            char = (self.game_logic.player.get('character_class') or '').upper()
        except Exception:
            pass
        if char == 'EMT' and not came_from_char_map:
            target = max(1, target - 10)
        return target
    
    def _handle_mouse_spiral(self, x, y):
        """Process mouse movement for spiral detection"""
        current_pos = (x, y)
        self.mouse_positions.append(current_pos)
        
        # Need at least 3 positions to start analyzing
        if len(self.mouse_positions) < 3:
            return None
            
        # Establish spiral center from early positions
        if self.spiral_center is None and len(self.mouse_positions) >= 5:
            # Use centroid of first few positions as approximate center
            center_x = sum(pos[0] for pos in self.mouse_positions[:5]) / 5
            center_y = sum(pos[1] for pos in self.mouse_positions[:5]) / 5
            self.spiral_center = (center_x, center_y)
            
        if self.spiral_center is None:
            return None
            
        # Calculate current radius and angle from center
        dx = x - self.spiral_center[0]
        dy = y - self.spiral_center[1]
        current_radius = math.sqrt(dx*dx + dy*dy)
        current_angle = math.atan2(dy, dx)
        
        self.spiral_radius_history.append(current_radius)
        
        # Track angle progression for spiral detection
        if len(self.mouse_positions) >= 2:
            prev_pos = self.mouse_positions[-2]
            prev_dx = prev_pos[0] - self.spiral_center[0]
            prev_dy = prev_pos[1] - self.spiral_center[1]
            prev_angle = math.atan2(prev_dy, prev_dx)
            
            # Calculate angle difference (accounting for wraparound)
            angle_diff = current_angle - prev_angle
            if angle_diff > math.pi:
                angle_diff -= 2 * math.pi
            elif angle_diff < -math.pi:
                angle_diff += 2 * math.pi
                
            self.spiral_angle_total += abs(angle_diff)
        
        # Check spiral completion criteria
        required_accuracy = self.active_qte.get('required_spiral_accuracy_default', 0.8)
        
        # Spiral is successful if:
        # 1. Total angle traversed is at least 2π (one full rotation)
        # 2. Radius shows spiral pattern (increasing or decreasing trend)
        if (self.spiral_angle_total >= 2 * math.pi and 
            len(self.spiral_radius_history) >= 10):
            
            # Check if radius shows spiral pattern (not just circular)
            radius_trend = self._analyze_radius_trend()
            if radius_trend >= required_accuracy:
                return self.resolve_qte(success=True)
        
        return None  # Continue spiral

    def _analyze_radius_trend(self):
        """Analyze if radius history shows spiral pattern"""
        if len(self.spiral_radius_history) < 10:
            return 0.0
            
        # Check for consistent increase or decrease in radius (spiral pattern)
        increases = 0
        decreases = 0
        
        for i in range(1, len(self.spiral_radius_history)):
            if self.spiral_radius_history[i] > self.spiral_radius_history[i-1]:
                increases += 1
            elif self.spiral_radius_history[i] < self.spiral_radius_history[i-1]:
                decreases += 1
        
        total_changes = increases + decreases
        if total_changes == 0:
            return 0.0
            
        # Return the proportion of changes that follow the dominant trend
        dominant_trend = max(increases, decreases)
        return dominant_trend / total_changes

    def set_resource_manager(self, resource_manager):
        self.resource_manager = resource_manager
        self.qte_definitions = self.resource_manager.get_data('qte_definitions', {})

class QTESequenceWidget(BoxLayout):
    # directions or pattern alphabet, e.g. ["up", "down", "left", "right"]
    options = ListProperty(["up", "down", "left", "right"])
    required_length = 3  # or set dynamically
    qte_engine = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.current_sequence = []

        # Add direction/pattern buttons
        btn_row = BoxLayout(orientation="horizontal", size_hint_y=0.3)
        for opt in self.options:
            btn = Button(text=opt.capitalize())
            btn.bind(on_release=lambda btn, o=opt: self.on_option_press(o))
            btn_row.add_widget(btn)
        self.add_widget(btn_row)

        # Add a TextInput for manual entry (optional)
        self.input = TextInput(hint_text="Type sequence (space-separated)", multiline=False, size_hint_y=0.2)
        self.input.bind(on_text_validate=self.on_text_submit)
        self.add_widget(self.input)

        # Add a submit button
        submit_btn = Button(text="Submit", size_hint_y=0.2)
        submit_btn.bind(on_release=self.on_submit)
        self.add_widget(submit_btn)

    def on_option_press(self, option):
        self.current_sequence.append(option)
        # Optionally, show the sequence so far
        self.input.text = " ".join(self.current_sequence)
        if len(self.current_sequence) >= self.required_length:
            self.submit_sequence()

    def on_text_submit(self, instance):
        self.submit_sequence()

    def on_code_submit(self, instance):
        code = instance.text.strip()
        self.qte_engine.handle_qte_input(code)

    def on_submit(self, instance):
        self.submit_sequence()

    def submit_sequence(self):
        sequence = self.input.text.strip().lower().split()
        if not sequence and self.current_sequence:
            sequence = self.current_sequence
        if self.qte_engine:
            self.qte_engine.handle_qte_input({'event': 'sequence_input', 'sequence': sequence})
        # Optionally, reset for next QTE
        self.current_sequence = []
        self.input.text = ""

