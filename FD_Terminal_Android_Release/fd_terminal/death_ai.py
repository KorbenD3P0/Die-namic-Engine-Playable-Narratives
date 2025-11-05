import collections
from typing import Optional
import random
import logging

from .resource_manager import ResourceManager
from .utils import color_text  # Add this import for color_text


class DeathAI:
    """
    An intelligent antagonist system that learns player behavior and 
    creates targeted threats in locations the player feels safest.
    """
    
    def __init__(self, game_logic_ref):
        self.game_logic = game_logic_ref
        # self.resource_manager = resource_manager
        self.resource_manager = game_logic_ref.resource_manager
        self.logger = logging.getLogger("DeathAI")
        self.hazard_engine = None  # Will be set after game_logic.hazard_engine is assigned

        # Enhanced threat scoring system - using defaultdict for cleaner code
        self.location_threat_scores = collections.defaultdict(float)
        self.object_threat_scores = collections.defaultdict(float)
        self.room_safety_perception = collections.defaultdict(float)  # How "safe" player thinks each room is
        
        # Enhanced behavioral pattern tracking
        self.player_behavior_patterns = {
            'preferred_escape_routes': collections.deque(maxlen=10),  # Limited memory for recent patterns
            'hiding_spots_used': collections.defaultdict(int),
            'item_usage_patterns': collections.defaultdict(list),
            'qte_success_rate': 0.0,
            'qte_successes': 0,
            'qte_attempts': 0,
            'room_visit_frequency': collections.defaultdict(int),
            'search_patterns': collections.defaultdict(int),
            'time_spent_per_room': collections.defaultdict(int),
            'preferred_hiding_spots': set(),
            'examination_patterns': {},
            'last_actions': [],
            'panic_indicators': 0,
            'confidence_indicators': 0
        }
        
        # Enhanced threat escalation system
        self.escalation_threshold = 5.0  # Threat score that triggers active countermeasures
        self.max_threat_score = 20.0     # Cap to prevent infinite escalation
        self.max_safety_tolerance = 0.8  # Legacy compatibility
        self.counter_strategy_cooldown = 3  # turns between major interventions
        self.last_intervention_turn = 0
        
        # Enhanced counter-strategy queue with priorities
        self.pending_counter_strategies = []
        self.active_strategies = []  # Legacy compatibility
        self.strategy_effectiveness = {}
        
        # Enhanced aggression factors
        self.base_aggression = 0.1
        self.current_aggression_multiplier = 1.0

        self.fear_increase_events = {
            'near_miss': 0.15,
            'witness_death': 0.25,
            'gruesome_event': 0.20,
            'high_threat_location': 0.10,
            'qte_failure': 0.08,
            'ambient_noise': 0.05,
            'examine_omen': 0.20, 
        }
        self.fear_decay_per_turn = 0.03  # Fear decays slowly each turn
    
    @property
    def hazard_engine(self):
        """Dynamic property that always gets hazard_engine from game_logic"""
        return self.game_logic.hazard_engine if self.game_logic else None
    
    @hazard_engine.setter
    def hazard_engine(self, value):
        """Allow setting hazard_engine directly (for backwards compatibility)"""
        # This setter is needed because we try to set it in __init__
        pass
    
    def update_fear(self, event_type=None, custom_amount=None, hp_loss=None):
        """Increase or decrease player fear based on event type, custom amount, or HP loss. Includes robust debugging."""
        player = self.game_logic.player
        if 'fear' not in player:
            player['fear'] = 0.0

        initial_fear = player['fear']
        debug_details = []

        # Canonical: HP loss increases fear proportionally (e.g., 0.01 per HP lost)
        if hp_loss is not None and hp_loss > 0:
            increment = hp_loss * 0.01
            player['fear'] += increment
            debug_details.append(f"HP loss: {hp_loss} -> fear +{increment:.3f}")

        if event_type and event_type in self.fear_increase_events:
            increment = self.fear_increase_events[event_type]
            player['fear'] += increment
            debug_details.append(f"Event '{event_type}' -> fear +{increment:.3f}")

        elif custom_amount is not None:
            player['fear'] += custom_amount
            debug_details.append(f"Custom amount -> fear +{custom_amount:.3f}")

        # Clamp fear between 0 and 1
        clamped_fear = max(0.0, min(1.0, player['fear']))
        if clamped_fear != player['fear']:
            debug_details.append(f"Fear clamped from {player['fear']:.3f} to {clamped_fear:.3f}")
        player['fear'] = clamped_fear

        # NEW: record cumulative and peak fear in live stats
        try:
            gain = max(0.0, player['fear'] - initial_fear)
            player['fear_gained_total'] = float(player.get('fear_gained_total', 0.0)) + float(gain)
            player['max_fear'] = max(float(player.get('max_fear', 0.0)), float(player['fear']))
        except Exception:
            pass

        # NEW: push UI update so blue pulse reflects current fear immediately
        try:
            self.game_logic.add_ui_event({"event_type": "player_fear_effect_update", "fear": player['fear']})
        except Exception:
            pass

        # Log debug info
        self.logger.debug(
            f"update_fear called: initial={initial_fear:.3f}, final={player['fear']:.3f}, details={debug_details}"
        )

    def decay_fear(self):
        """Decay fear each turn."""
        player = self.game_logic.player
        if 'fear' not in player:
            player['fear'] = 0.0
        player['fear'] = max(0.0, player['fear'] - self.fear_decay_per_turn)

    def analyze_player_action(self, action_type, target=None, location=None, success=None, context=None):
        """
        Analyzes player actions to build a comprehensive threat profile.
        This is the single point of entry for AI analysis per player turn.
        """
        context = context or {}
        # The 'location' argument is now preferred. Fallback to GameLogic for the current room if not provided.
        current_room = location or self.game_logic.player.get('location')
        if not current_room:
            self.logger.warning("DeathAI could not determine current room for action analysis.")
            return

        self.logger.info(f"Analyzing player action: '{action_type}' in '{current_room}'")

        # 1. Calculate the threat generated by this specific action.
        threat_increase = self._calculate_base_threat_increase(action_type, success)
        
        # 2. Update the threat scores for the location and target.
        self._update_location_threat_score(current_room, action_type, threat_increase)
        if target:
            self._update_object_threat_score(f"{current_room}:{target}", action_type, threat_increase)
        
        # 3. Update the AI's perception of how "safe" the player feels.
        self._update_safety_perception_enhanced(current_room, action_type, success)
        
        # 4. Log the player's behavior for pattern analysis.
        self._analyze_behavioral_patterns_enhanced(action_type, current_room, target, success, context)
        
        # 5. Check if this action triggers a need for the AI to escalate its strategy.
        self._evaluate_escalation_triggers(current_room, action_type, success)
        
        # 6. Fear system integration
        if action_type == 'qte_failure':
            self.update_fear('qte_failure')
        elif action_type == 'move' and self.location_threat_scores.get(location, 0) > 4.0:
            self.update_fear('high_threat_location')
        
    def get_fear_hallucination(self) -> Optional[str]:
        """
        If fear is high enough, has a chance to return a hallucination message.
        Enhanced: Level-aware contextual hallucinations.
        """
        player_fear = self.game_logic.player.get('fear', 0.0)
        current_level = self.game_logic.player.get('current_level', 1)
        current_room = self.game_logic.player.get('location', '')
        
        self.logger.debug(f"get_fear_hallucination called: player_fear={player_fear:.3f}, level={current_level}, room='{current_room}'")

        hallucination_triggered = False
        hallucination_message = None

        if random.random() < player_fear:
            # Get level-specific hallucinations
            hallucinations = self._get_level_hallucinations(current_level, current_room)
            hallucination_message = random.choice(hallucinations)
            hallucination_triggered = True

        self.logger.debug(
            f"Hallucination triggered: {hallucination_triggered}, message: {hallucination_message!r}"
        )
        return hallucination_message
    
    def _get_level_hallucinations(self, level: int, room: str) -> list:
        """Get contextually appropriate hallucinations for the current level and room."""
        
        # Base hallucinations that work anywhere
        base_hallucinations = [
            "For a split second, you see a shadowy figure at the edge of your vision, but it's gone when you turn.",
            "You hear a faint, distorted whisper that sounds like your own name.",
            "A sudden, inexplicable chill washes over you, raising goosebumps on your arms."
        ]
        
        # Level 1: Hospital - Medical/clinical horror
        if level == 1:
            hospital_hallucinations = [
                "The lights flicker violently for a moment, plunging the room into a disorienting strobe effect before returning to normal.",
                "You hear the distant sound of a heart monitor flatlining, but there's no one else here.",
                "The antiseptic smell suddenly becomes overwhelming, making your eyes water.",
                "You hear the squeak of gurney wheels rolling down an empty hallway.",
                "A ventilator's mechanical breathing echoes from somewhere nearby, though you see no machines.",
                "The fluorescent lights buzz ominously, casting harsh shadows that seem to move.",
                "You catch a glimpse of something pale moving past a doorway, but nothing's there when you look.",
                "The smell of formaldehyde suddenly fills your nostrils, sharp and chemical."
            ]
            
            # Room-specific hospital hallucinations
            if 'morgue' in room.lower():
                hospital_hallucinations.extend([
                    "You hear the soft hiss of a refrigeration unit opening, but all doors remain closed.",
                    "The sound of running water echoes from the steel tables, though the room is dry."
                ])
            elif 'mri' in room.lower():
                hospital_hallucinations.extend([
                    "You feel a strange tingling, as if invisible magnetic forces are pulling at your bones.",
                    "The MRI machine emits a low hum that seems to resonate in your skull."
                ])
            elif 'patient' in room.lower() or 'icu' in room.lower():
                hospital_hallucinations.extend([
                    "You hear the soft beep of a heart monitor that isn't there.",
                    "The IV stand creaks softly, as if someone brushed against it."
                ])
            
            return base_hallucinations + hospital_hallucinations
        
        # Level 2: Home/Domestic - Familiar spaces turned sinister
        elif level == 2:
            home_hallucinations = [
                "A floorboard creaks in the room above you. You're supposed to be alone.",
                "You hear the soft sound of footsteps padding across carpet in another room.",
                "A door you're certain you left open is now closed.",
                "The house settles with a groan that sounds almost like a sigh.",
                "You smell something cooking, but the kitchen is empty and cold.",
                "A child's laughter echoes faintly from upstairs, but there are no children here.",
                "The television in another room turns on by itself, voices murmuring indistinctly.",
                "You hear running water from the bathroom, but the taps are all dry."
            ]
            return base_hallucinations + home_hallucinations
        
        # Level 3: Fairground - Carnival horror
        elif level == 3:
            fairground_hallucinations = [
                "Carnival music plays faintly in the distance, distorted and off-key.",
                "You hear the creaking of a ferris wheel that isn't turning.",
                "Children's laughter echoes from empty rides, but you see no one.",
                "The smell of cotton candy and popcorn suddenly fills the air, sickeningly sweet.",
                "Calliope music warbles through the air, as if played on a broken music box.",
                "You hear the distant barking of a carnival barker, but can't make out the words.",
                "The wind carries the scent of hay and animals, mixed with something less pleasant.",
                "Bells and chimes tinkle softly, as if ghostly patrons are playing the games."
            ]
            return base_hallucinations + fairground_hallucinations
        
        # Fallback for unknown levels
        else:
            self.logger.warning(f"Unknown level {level} for hallucinations, using base set")
            return base_hallucinations

    def _apply_level_specific_fear_effects(self, description: str, room_name: str, level: int) -> str:
        """Apply level-specific atmospheric effects to room descriptions."""
        
        if level == 1:  # Hospital
            if 'morgue' in room_name.lower():
                return description + " The cold air carries the faint chemical tang of preservatives."
            elif 'mri' in room_name.lower():
                return description + " You feel a subtle magnetic pull, making your fillings ache."
            elif 'emergency' in room_name.lower():
                return description + " The silence is broken only by the hum of medical equipment."
            else:
                return description + " The antiseptic smell is stronger here, almost overwhelming."
        
        elif level == 2:  # Home
            fear_additions = {
                "Living Room": " The shadows in the corners seem deeper than they should be.",
                "Kitchen": " You can almost hear the echo of family meals that will never happen again.",
                "Bedroom": " The bed looks as if someone just got up from it, though you know you're alone.",
                "Basement": " Every creak of the house above sounds like footsteps."
            }
            addition = fear_additions.get(room_name, " This place feels like it's holding its breath.")
            return description + addition
        
        elif level == 3:  # Fairground
            if 'tent' in room_name.lower():
                return description + " The canvas walls flutter with no wind, as if breathing."
            elif 'ride' in room_name.lower() or 'carousel' in room_name.lower():
                return description + " You can almost hear the ghost of carnival music in the air."
            elif 'game' in room_name.lower():
                return description + " The prizes seem to watch you with glassy, unblinking eyes."
            else:
                return description + " The air smells of cotton candy and rust."
        
        return description

    def _calculate_base_threat_increase(self, action: str, success: bool) -> float:
        """Calculate how much threat score should increase based on action type. Adds robust logging."""
        base_scores = {
            'search': 0.8,
            'examine': 0.3,
            'move': 0.2,
            'use': 0.5,
            'take': 0.6,
            'qte_success': 2.0,
            'qte_failure': -0.3,
            'unlock': 1.2,
            'solve_puzzle': 1.5
        }

        base_threat = base_scores.get(action, 0.1)
        initial_base_threat = base_threat

        # Success multiplier
        if success:
            base_threat *= 1.2
        else:
            base_threat *= 0.7

        self.logger.debug(
            f"_calculate_base_threat_increase: action={action}, success={success}, "
            f"initial_base_threat={initial_base_threat:.2f}, final_base_threat={base_threat:.2f}"
        )
        return base_threat

    def _update_location_threat_score(self, location: str, action: str, base_threat: float):
        """
        Update threat score for a specific location.
        Enhanced: Adds robust logging for all threat score changes.
        """
        threat_increase = base_threat * self.current_aggression_multiplier
        debug_details = [f"base_threat={base_threat:.2f}", f"aggression_multiplier={self.current_aggression_multiplier:.2f}"]

        # Certain actions in certain locations are more threatening to Death
        if action == 'search' and any(safe_word in location.lower()
                                      for safe_word in ['office', 'closet', 'storage']):
            threat_increase *= 1.5
            debug_details.append("search in safe location: threat_increase x1.5")

        if action == 'qte_success':
            threat_increase *= 2.0
            debug_details.append("qte_success: threat_increase x2.0")

        old_score = self.location_threat_scores[location]
        new_score = min(old_score + threat_increase, self.max_threat_score)
        self.location_threat_scores[location] = new_score

        self.logger.debug(
            f"_update_location_threat_score: location={location}, action={action}, "
            f"old_score={old_score:.2f}, threat_increase={threat_increase:.2f}, new_score={new_score:.2f}, details={debug_details}"
        )

        if threat_increase > 1.0:
            logging.info(f"[DeathAI] Threat score for {location} increased by {threat_increase:.2f} "
                         f"(now {self.location_threat_scores[location]:.2f})")

    def _update_object_threat_score(self, object_key: str, action: str, base_threat: float):
        """
        Track threat scores for specific objects (furniture, items, etc.).
        Enhanced: Adds robust logging for object threat score changes.
        """
        threat_increase = base_threat * 0.5
        old_score = self.object_threat_scores[object_key]
        new_score = min(old_score + threat_increase, self.max_threat_score)
        self.object_threat_scores[object_key] = new_score

        self.logger.debug(
            f"_update_object_threat_score: object_key={object_key}, action={action}, "
            f"base_threat={base_threat:.2f}, threat_increase={threat_increase:.2f}, "
            f"old_score={old_score:.2f}, new_score={new_score:.2f}"
        )

    def _update_safety_perception_enhanced(self, location: str, action: str, success: bool):
        """
        Enhanced safety perception tracking.
        Track how 'safe' the player likely perceives each location.
        Higher safety perception = bigger target for Death.
        Adds robust logging for debugging.
        """
        safety_increase = 0

        if action == 'search' and success:
            safety_increase += 0.5  # Successfully searching makes player feel room is "cleared"
        elif action == 'examine' and success:
            safety_increase += 0.2  # Examining without consequence feels safe
        elif action == 'move' and success:
            safety_increase += 0.1  # Easy movement feels safe
        elif action == 'qte_success':
            safety_increase += 1.0  # Surviving a QTE makes player feel temporarily safe

        old_safety = self.room_safety_perception[location]
        self.room_safety_perception[location] += safety_increase
        new_safety = self.room_safety_perception[location]

        self.logger.debug(
            f"_update_safety_perception_enhanced: location={location}, action={action}, success={success}, "
            f"safety_increase={safety_increase:.2f}, old_safety={old_safety:.2f}, new_safety={new_safety:.2f}"
        )

    def _analyze_behavioral_patterns_enhanced(self, action: str, location: str, target: str,
                                                success: bool, context: dict):
        """Enhanced pattern recognition with robust logging."""
        patterns = self.player_behavior_patterns
        debug_details = []

        # Track movement patterns
        if action == 'move' and success:
            patterns['preferred_escape_routes'].append(location)
            patterns['room_visit_frequency'][location] += 1
            debug_details.append(f"Moved to {location}, visit count: {patterns['room_visit_frequency'][location]}")

        # Track search patterns
        if action == 'search':
            key = f"{location}:{target}"
            patterns['search_patterns'][key] += 1
            debug_details.append(f"Searched {key}, count: {patterns['search_patterns'][key]}")

        # Track hiding behavior
        if action == 'search' and target and any(hiding_word in target.lower()
                                                    for hiding_word in ['closet', 'cabinet', 'under', 'behind']):
            key = f"{location}:{target}"
            patterns['hiding_spots_used'][key] += 1
            debug_details.append(f"Hiding spot used: {key}, count: {patterns['hiding_spots_used'][key]}")

        # Track QTE performance
        if action.startswith('qte_'):
            patterns['qte_attempts'] += 1
            if success:
                patterns['qte_successes'] += 1
            patterns['qte_success_rate'] = patterns['qte_successes'] / max(1, patterns['qte_attempts'])
            debug_details.append(
                f"QTE action: {action}, attempts: {patterns['qte_attempts']}, successes: {patterns['qte_successes']}, "
                f"success_rate: {patterns['qte_success_rate']:.2f}"
            )

        # Track item usage effectiveness
        if action == 'use' and target:
            usage_entry = {
                'location': location,
                'success': success,
                'turn': context.get('turn', 0)
            }
            patterns['item_usage_patterns'][target].append(usage_entry)
            debug_details.append(f"Used item: {target} at {location}, success: {success}, turn: {usage_entry['turn']}")

        self.logger.debug(
            f"_analyze_behavioral_patterns_enhanced: action={action}, location={location}, target={target}, "
            f"success={success}, context={context}, details={debug_details}"
        )

    def _evaluate_escalation_triggers(self, location: str, action: str, success: bool):
        """Determine if Death should escalate its efforts. Adds robust logging."""
        current_threat = self.location_threat_scores[location]
        escalation_reasons = []

        if current_threat >= self.escalation_threshold:
            escalation_reasons.append(f"location_threat_high_{location}")

        if action == 'qte_success' and self.player_behavior_patterns['qte_success_rate'] > 0.7:
            escalation_reasons.append("player_too_successful_at_qtes")

        if self.room_safety_perception[location] > 3.0:
            escalation_reasons.append(f"player_feels_too_safe_{location}")

        # Check for overuse of hiding spots
        for hiding_spot, usage_count in self.player_behavior_patterns['hiding_spots_used'].items():
            if usage_count >= 3:
                escalation_reasons.append(f"overused_hiding_spot_{hiding_spot}")

        self.logger.debug(
            f"_evaluate_escalation_triggers: location={location}, action={action}, success={success}, "
            f"current_threat={current_threat:.2f}, safety_perception={self.room_safety_perception[location]:.2f}, "
            f"escalation_reasons={escalation_reasons}"
        )

        # Execute escalation if triggered
        for reason in escalation_reasons:
            self._queue_escalation_response(reason, location)

    def _queue_escalation_response(self, reason: str, location: str):
        """Queue specific counter-strategies based on escalation triggers. Adds robust logging."""
        strategy = {
            'reason': reason,
            'target_location': location,
            'priority': self._calculate_strategy_priority(reason),
            'strategy_type': self._determine_strategy_type(reason, location)
        }

        self.pending_counter_strategies.append(strategy)
        # Sort by priority (highest first)
        self.pending_counter_strategies.sort(key=lambda x: x['priority'], reverse=True)

        self.logger.info(
            f"_queue_escalation_response: Queued strategy: reason={reason}, location={location}, "
            f"priority={strategy['priority']:.2f}, type={strategy['strategy_type']}. "
            f"Pending strategies: {len(self.pending_counter_strategies)}"
        )

    def _calculate_strategy_priority(self, reason: str) -> float:
        """Calculate priority for counter-strategies. Adds robust logging."""
        priority_map = {
            'player_too_successful_at_qtes': 10.0,  # Highest priority
            'player_feels_too_safe': 8.0,
            'location_threat_high': 6.0,
            'overused_hiding_spot': 7.0
        }

        for key, priority in priority_map.items():
            if key in reason:
                self.logger.debug(f"_calculate_strategy_priority: reason={reason}, matched={key}, priority={priority}")
                return priority

        self.logger.debug(f"_calculate_strategy_priority: reason={reason}, default priority=5.0")
        return 5.0  # Default priority

    def _determine_strategy_type(self, reason: str, location: str) -> str:
        """Determine what type of counter-strategy to employ. Adds robust logging."""
        if 'hiding_spot' in reason:
            strategy_type = 'contaminate_hiding_spot'
        elif 'too_safe' in reason:
            strategy_type = 'spawn_in_safe_zone'
        elif 'qte_success' in reason:
            strategy_type = 'increase_qte_difficulty'
        elif 'location_threat_high' in reason:
            strategy_type = 'targeted_hazard_spawn'
        else:
            strategy_type = 'general_escalation'

        self.logger.debug(
            f"_determine_strategy_type: reason={reason}, location={location}, strategy_type={strategy_type}"
        )
        return strategy_type
    
    def execute_counter_strategies(self):
        """
        Executes the highest-priority counter-strategy from the pending queue.
        Called once per game turn by the HazardEngine.
        Enhanced: Adds robust logging and debugging.
        """
        if not self.pending_counter_strategies:
            self.logger.debug("[DeathAI] No pending counter-strategies to execute.")
            return []  # No strategies to execute

        strategy_to_execute = self.pending_counter_strategies.pop(0)  # Get the highest priority one

        self.logger.info(
            f"[DeathAI] Executing counter-strategy: reason={strategy_to_execute.get('reason')}, "
            f"type={strategy_to_execute.get('strategy_type')}, location={strategy_to_execute.get('target_location')}"
        )

        # Placeholder for actual execution logic
        success = True

        if success:
            self.logger.debug(
                f"[DeathAI] Counter-strategy '{strategy_to_execute.get('reason')}' executed successfully."
            )
            # --- CONSOLIDATION PATCH ---
            # Use the imported utility function for consistent styling.
            return [color_text("[i]The air grows colder. You feel a malevolent focus shift towards you...[/i]", "error", self.resource_manager)]
            # --- END OF PATCH ---
        else:
            self.logger.warning(
                f"[DeathAI] Counter-strategy '{strategy_to_execute.get('reason')}' failed to execute."
            )

        # Add a chance to manifest Death's presence when fear is high
        if self.game_logic.player.get('fear', 0) > 0.6 and random.random() < 0.2:
            current_room = self.game_logic.player.get('location')
            if current_room:
                self.manifest_deaths_presence(current_room)

        return []

    def manifest_deaths_presence(self, location: str, intensity: float = None):
        """
        Creates or escalates the Death's Breath hazard based on player fear level.
        Higher fear = more intense manifestation.
        """
        if not self.hazard_engine:
            return False

        self.logger.info(f"DeathAI manifesting presence in {location} (player fear: {self.game_logic.player.get('fear', 0):.2f})")

        # Check if Death's Breath already exists in this location
        active_ids = self.hazard_engine.get_active_hazards_for_room(location)
        deaths_breath_id = None
        for hid in active_ids:
            # Our hazard ids are like "<type>#abcd1234"
            if "deaths_breath" in (hid or ""):
                deaths_breath_id = hid
                break

        # If intensity not specified, derive from fear
        if intensity is None:
            intensity = min(1.0, self.game_logic.player.get('fear', 0) * 1.5)

        # Helper: pick a state from intensity
        def _state_for_intensity(val: float) -> str:
            if val < 0.15:
                return "subtle_chill"
            if val < 0.35:
                return "cold_breeze"
            if val < 0.65:
                return "icy_presence"
            return "malevolent_gust"

        # If already exists, possibly escalate based on intensity
        if deaths_breath_id:
            inst = self.hazard_engine.active_hazards.get(deaths_breath_id, {})
            curr_state = (inst or {}).get("state", "subtle_chill")
            states = ["subtle_chill", "cold_breeze", "icy_presence", "malevolent_gust"]
            try:
                curr_idx = states.index(curr_state)
            except ValueError:
                curr_idx = 0

            # Higher intensity = higher chance to escalate
            escalate_chance = max(0.0, intensity * 0.7)
            if random.random() < escalate_chance and curr_idx < len(states) - 1:
                target_state = states[curr_idx + 1]
                self.logger.info(f"DeathAI escalating Death's Breath from {curr_state} to {target_state}")
                self.hazard_engine.set_hazard_state(deaths_breath_id, target_state)
                return True

            return False

        # Otherwise, spawn new instance with appropriate initial state
        if intensity > 0.18:
            initial_state = _state_for_intensity(intensity)
            self.logger.info(f"DeathAI spawning new Death's Breath in {location} at '{initial_state}'")
            self.hazard_engine._add_active_hazard(
                hazard_type="deaths_breath",
                location=location,
                initial_state_override=initial_state,
                source_trigger_id="death_ai_manifestation"
            )
            return True

        return False

    def increase_aggression(self, amount: float, reason: str):
        """
        Public method to increase the AI's aggression multiplier from external events.
        This makes Death more active and dangerous in response to player failures.
        Enhanced: Adds robust logging and debugging.
        """
        if amount <= 0:
            self.logger.debug(f"DeathAI: increase_aggression called with non-positive amount ({amount}). No change.")
            return

        old_multiplier = self.current_aggression_multiplier
        self.current_aggression_multiplier = min(self.current_aggression_multiplier + amount, 5.0)

        self.logger.info(
            f"DeathAI aggression increased by {amount:.2f} due to '{reason}'. "
            f"New multiplier: {self.current_aggression_multiplier:.2f} (was {old_multiplier:.2f})"
        )

    def _escalate_immediate_threat(self, hazard_engine, params):
        """
        Create immediate danger in the player's current location.
        REVISED: If no high-impact hazards are available, escalate using synergistic hazard chains or random spawn, and return a narrative message.
        Enhanced: Adds robust logging and debugging.
        """
        messages = []
        location = params.get('location')
        self.logger.debug(f"_escalate_immediate_threat called with location={location}")

        if location:
            immediate_threats = ['sudden_collapse', 'electrical_surge', 'gas_explosion']
            hazards_data = self.game_logic.resource_manager.get_data('hazards', {})

            threat_spawned = False
            for hazard_type in immediate_threats:
                if hazard_type in hazards_data:
                    hazard_engine._add_active_hazard(
                        hazard_type=hazard_type,
                        location=location,
                        initial_state_override='imminent',
                        source_trigger_id="death_ai_escalation"
                    )
                    self.player_behavior_patterns['confidence_indicators'] = 0
                    self.player_behavior_patterns['panic_indicators'] += 3
                    self.logger.info(
                        f"[DeathAI] Immediate threat '{hazard_type}' spawned in '{location}'."
                    )
                    # --- CONSOLIDATION PATCH ---
                    messages.append(color_text("[b]Death will not be cheated![/b]", "error", self.resource_manager))
                    # --- END OF PATCH ---
                    threat_spawned = True
                    break
            if not threat_spawned:
                self.logger.info(
                    f"[DeathAI] No immediate threats available for '{location}'. Attempting synergistic escalation."
                )
                synergy_message = self._escalate_threat(location)
                if synergy_message:
                    messages.append(synergy_message)
                else:
                    self.logger.warning(
                        f"[DeathAI] Synergistic escalation failed or returned no message for '{location}'."
                    )
        else:
            self.logger.warning("[DeathAI] _escalate_immediate_threat called with no location specified.")

        self.logger.debug(f"_escalate_immediate_threat returning messages: {messages}")
        return messages

    
    def _contaminate_hiding_spot_enhanced(self, location: str, strategy: dict) -> bool:
        """Enhanced hiding spot contamination"""
        reason = strategy['reason']
        if 'overused_hiding_spot_' in reason:
            hiding_spot_key = reason.split('overused_hiding_spot_')[1]
            # --- START FIX ---
            # Add a defensive check to ensure the key can be split.
            if ':' not in hiding_spot_key:
                self.logger.warning(f"[DeathAI] Could not parse hiding spot key '{hiding_spot_key}' for contamination. Key must be in 'location:target' format.")
                return False
            # --- END FIX ---
            try:
                location, target = hiding_spot_key.split(':', 1)
                
                # Spawn hazard that targets this specific hiding spot
                hazard_types = ['gas_leak', 'electrical_fault', 'structural_weakness']
                hazard_type = random.choice(hazard_types)
                
                self.game_logic.hazard_engine._add_active_hazard(
                    hazard_type, 
                    location,
                    initial_state_override="dormant",
                    target_object_override=target
                )
                
                self.logger.info(f"[DeathAI] Contaminated hiding spot: {location}:{target} with {hazard_type}")
                return True
            except ValueError:
                # --- PATCH START ---
                # Log the error instead of failing silently.
                self.logger.warning(f"[DeathAI] Could not parse hiding spot key '{hiding_spot_key}' after splitting. Ensure it is in 'location:target' format.")
                # --- PATCH END ---
                
        return False

    
    def _spawn_hazard_in_safe_zone(self, location: str, strategy: dict) -> bool:
        """Spawn hazards in locations where player feels safe"""
        # Choose hazard type based on room type and existing hazards
        existing_hazards = self.game_logic.hazard_engine.get_room_hazards_descriptions(location)

        # Avoid duplicate hazard types in same room
        existing_types = [h.get('type', '') for h in existing_hazards.values()]
        
        suitable_hazards = ['gas_leak', 'electrical_fault', 'structural_collapse', 
                          'ceiling_fan_malfunction', 'ventilation_blockage']
        available_hazards = [h for h in suitable_hazards if h not in existing_types]
        
        if available_hazards:
            chosen_hazard = random.choice(available_hazards)
            self.game_logic.hazard_engine._add_active_hazard(
                chosen_hazard,
                location,
                initial_state_override="building_tension"
            )
            
            logging.info(f"[DeathAI] Spawned {chosen_hazard} in perceived safe zone: {location}")
            return True
            
        return False

    def _increase_qte_difficulty(self, strategy: dict) -> bool:
        """
        Increase global QTE difficulty due to player success.
        Enhanced: Adds robust logging and debugging.
        """
        old_multiplier = self.current_aggression_multiplier
        new_multiplier = min(old_multiplier * 1.2, 3.0)  # Cap at 3x difficulty

        self.logger.info(
            f"[DeathAI] _increase_qte_difficulty called. Reason: {strategy.get('reason', 'N/A')}, "
            f"Old multiplier: {old_multiplier:.2f}, New multiplier: {new_multiplier:.2f}"
        )

        self.current_aggression_multiplier = new_multiplier

        # Debug: Log strategy details
        self.logger.debug(
            f"[DeathAI] QTE difficulty increased. Strategy details: {strategy}"
        )

        if new_multiplier > old_multiplier:
            self.logger.info(
                f"[DeathAI] Aggression multiplier successfully increased to {new_multiplier:.2f}."
            )
        else:
            self.logger.warning(
                f"[DeathAI] Aggression multiplier already at cap ({new_multiplier:.2f}). No further increase."
            )

        return True
    
    def _spawn_targeted_hazard(self, location: str, strategy: dict) -> bool:
        """Spawn hazard specifically targeting high-threat locations. Adds robust logging and debugging."""
        threat_score = self.location_threat_scores[location]
        self.logger.debug(
            f"_spawn_targeted_hazard called: location={location}, threat_score={threat_score:.2f}, strategy={strategy}"
        )

        # Higher threat = more dangerous hazard
        if threat_score >= 15.0:
            hazard_type = "catastrophic_failure"
        elif threat_score >= 10.0:
            hazard_type = "cascading_malfunction"
        else:
            hazard_type = "escalating_danger"

        self.logger.info(
            f"[DeathAI] Spawning targeted hazard '{hazard_type}' in high-threat location '{location}' (score={threat_score:.2f})"
        )

        try:
            self.game_logic.hazard_engine._add_active_hazard(
                hazard_type,
                location,
                initial_state_override="rapid_escalation"
            )
            self.logger.debug(
                f"[DeathAI] Hazard '{hazard_type}' successfully spawned in '{location}'."
            )
            return True
        except Exception as e:
            self.logger.error(
                f"[DeathAI] Failed to spawn hazard '{hazard_type}' in '{location}': {e}"
            )
            return False

    def _general_escalation(self, location: str, strategy: dict) -> bool:
        """General escalation of danger level. Adds robust logging and debugging."""
        self.logger.debug(
            f"_general_escalation called: location={location}, strategy={strategy}"
        )
        room_hazards = self.game_logic.hazard_engine.get_room_hazards_descriptions(location)
        escalated_count = 0

        for hazard_id, hazard_instance in room_hazards.items():
            # Accelerate hazard progression
            if 'progression_rate' in hazard_instance:
                old_rate = hazard_instance['progression_rate']
                hazard_instance['progression_rate'] *= 1.5
                escalated_count += 1
                self.logger.info(
                    f"[DeathAI] Escalated hazard '{hazard_id}' in '{location}': progression_rate {old_rate} -> {hazard_instance['progression_rate']}"
                )

        if escalated_count > 0:
            self.logger.info(f"[DeathAI] Escalated {escalated_count} hazards in {location}")
            return True

        self.logger.warning(f"[DeathAI] No hazards escalated in {location}.")
        return False

    def load_state(self, state_dict):
        """
        Loads the DeathAI state from a dictionary.
        Extend this to restore any relevant AI state.
        Adds robust logging and debugging.
        """
        if not state_dict:
            self.logger.warning("DeathAI.load_state called with empty state_dict.")
            return
        for key, value in state_dict.items():
            setattr(self, key, value)
            self.logger.debug(f"DeathAI.load_state: Restored '{key}' = {value!r}")

    def _contaminate_safe_space(self, hazard_engine, params):
        """Add hazards to rooms the player considers safe. Adds robust logging and debugging."""
        messages = []
        safe_rooms = params.get('rooms', [])
        self.logger.debug(f"_contaminate_safe_space called: safe_rooms={safe_rooms}, params={params}")

        for room in safe_rooms[:2]:  # Limit to 2 rooms per intervention
            room_data = self.game_logic.get_room_data(room)
            if not room_data:
                self.logger.warning(f"[DeathAI] No room data found for '{room}'. Skipping contamination.")
                continue

            hazard_type = self._select_contextual_hazard(room, room_data)
            if hazard_type:
                try:
                    hazard_engine._add_active_hazard(
                        hazard_type=hazard_type,
                        location=room,
                        source_trigger_id="death_ai_contamination"
                    )
                    self.logger.info(
                        f"[DeathAI] Contaminated safe room '{room}' with hazard '{hazard_type}'."
                    )
                    self.room_safety_perception[room] *= 0.6  # Significantly reduce safety feeling
                    messages.append(f"[i]Something feels different about the {room}...[/i]")
                except Exception as e:
                    self.logger.error(
                        f"[DeathAI] Failed to contaminate safe room '{room}' with hazard '{hazard_type}': {e}"
                    )
            else:
                self.logger.warning(f"[DeathAI] No suitable hazard found for safe room '{room}'.")
        self.logger.debug(f"_contaminate_safe_space returning messages: {messages}")
        return messages

    def _target_hiding_spots(self, hazard_engine, params):
        """Create hazards specifically in the player's preferred locations. Adds robust logging and debugging."""
        messages = []
        hiding_spots = params.get('rooms', [])
        self.logger.debug(f"_target_hiding_spots called: hiding_spots={hiding_spots}, params={params}")

        for room in hiding_spots[:1]:  # One hiding spot per intervention
            aggressive_hazards = ['gas_leak', 'electrical_hazard', 'structural_instability']
            hazards_data = self.game_logic.resource_manager.get_data('hazards', {})

            for hazard_type in aggressive_hazards:
                if hazard_type in hazards_data:
                    try:
                        hazard_engine._add_active_hazard(
                            hazard_type=hazard_type,
                            location=room,
                            source_trigger_id="death_ai_hiding_spot_target"
                        )
                        self.logger.info(
                            f"[DeathAI] Targeted hiding spot '{room}' with hazard '{hazard_type}'."
                        )
                        self.player_behavior_patterns['preferred_hiding_spots'].discard(room)
                        messages.append(color_text("Your sanctuary has been violated.", "error", self.resource_manager))
                        break
                    except Exception as e:
                        self.logger.error(
                            f"[DeathAI] Failed to target hiding spot '{room}' with hazard '{hazard_type}': {e}"
                        )
        self.logger.debug(f"_target_hiding_spots returning messages: {messages}")
        return messages

    def _corrupt_examined_objects(self, hazard_engine, params):
        """
        Make previously examined objects become dangerous.
        Enhanced: Logging, color_text usage, and robust fallback logic.
        """
        messages = []
        objects = params.get('objects', [])
        self.logger.info(f"DeathAI: Attempting to corrupt examined objects: {objects}")

        location = None
        if hasattr(self.game_logic, 'player') and self.game_logic.player:
            location = self.game_logic.player.get('location')
        else:
            self.logger.warning("DeathAI: Cannot get player location for object corruption")
            return messages

        if not location:
            self.logger.warning("DeathAI: Player location is None, cannot corrupt objects.")
            return messages

        for obj_name in objects[:1]:  # One object per intervention
            hazards_data = self.game_logic.resource_manager.get_data('hazards', {})
            if 'corrupted_object' not in hazards_data:
                self.logger.warning("DeathAI: 'corrupted_object' hazard type not defined in hazards data")
                hazard_type = 'environmental_hazard'  # Fallback to a generic hazard type
            else:
                hazard_type = 'corrupted_object'

            try:
                hazard_id = hazard_engine._add_active_hazard(
                    hazard_type=hazard_type,
                    location=location,
                    target_object_override=obj_name,
                    source_trigger_id="death_ai_object_corruption"
                )
                if hazard_id:
                    messages.append(color_text(f"The {obj_name} seems... different now.", "warning"))
                    self.logger.info(f"DeathAI: Corrupted object '{obj_name}' in '{location}' (hazard_id={hazard_id})")
                else:
                    self.logger.warning(f"DeathAI: Failed to create hazard for object '{obj_name}' in '{location}'")
            except Exception as e:
                self.logger.error(
                    f"DeathAI: Exception while corrupting object '{obj_name}' in '{location}': {e}"
                )
        self.logger.debug(f"_corrupt_examined_objects returning messages: {messages}")
        return messages

    def _escalate_threat(self, room_id):
        """
        Spawns a new hazard in the room, prioritizing synergistic chains.
        REVISED: Now attempts to create a chain reaction before falling back to random spawning.
        Adds robust logging and debugging.
        """
        if not self.game_logic or not self.game_logic.hazard_engine:
            self.logger.warning(f"DeathAI._escalate_threat: Missing game_logic or hazard_engine for room '{room_id}'")
            return None

        self.logger.info(f"DeathAI evaluating threat escalation for room: '{room_id}'")
        synergies = self.game_logic.resource_manager.get_data("hazard_synergies", {})
        all_hazards_master = self.game_logic.resource_manager.get_data("hazards", {})
        spawnable_hazards = [h for h, d in all_hazards_master.items() if d.get("can_be_spawned")]

        existing_hazards_in_room = self.game_logic.hazard_engine.get_hazards_in_location(room_id)
        self.logger.debug(f"Existing hazards in room '{room_id}': {existing_hazards_in_room}")

        for existing_hazard in existing_hazards_in_room:
            existing_hazard_type = all_hazards_master.get(existing_hazard.get("type"), {}).get("hazard_class")
            if existing_hazard_type in synergies:
                possible_synergy_types = synergies[existing_hazard_type]
                for hazard_key in spawnable_hazards:
                    if all_hazards_master.get(hazard_key, {}).get("hazard_class") in possible_synergy_types:
                        self.logger.info(f"Synergy found! Existing hazard '{existing_hazard_type}' pairs with '{hazard_key}'.")
                        return self._spawn_specific_hazard(hazard_key, room_id)

        self.logger.info("No synergistic opportunity found. Spawning random hazard.")
        if spawnable_hazards:
            hazard_to_spawn = random.choice(spawnable_hazards)
            self.logger.info(f"Random hazard selected: '{hazard_to_spawn}' for room '{room_id}'")
            return self._spawn_specific_hazard(hazard_to_spawn, room_id)

        self.logger.warning("No spawnable hazards available.")
        return None

    def _spawn_specific_hazard(self, hazard_key, room_id):
        """Helper function to spawn a hazard and return a message. Adds robust logging and debugging."""
        try:
            new_hazard_id = self.game_logic.hazard_engine._add_active_hazard(
                hazard_type=hazard_key,
                location=room_id,
                source="DeathAI"
            )
            if new_hazard_id:
                self.logger.info(f"DeathAI escalated threat in '{room_id}' by spawning '{hazard_key}' (ID: {new_hazard_id}).")
                self.location_threat_scores[room_id] = 0  # Reset threat
                omen_messages = self.game_logic.resource_manager.get_data("omen_messages", [])
                msg = random.choice(omen_messages) if omen_messages else "You feel a sudden chill..."
                self.logger.debug(f"_spawn_specific_hazard returning message: {msg}")
                return msg
            else:
                self.logger.warning(f"DeathAI failed to spawn hazard '{hazard_key}' in '{room_id}'.")
        except Exception as e:
            self.logger.error(f"DeathAI exception while spawning hazard '{hazard_key}' in '{room_id}': {e}")
        return None

    def get_threat_weighted_location(self, candidate_locations: list) -> str:
        """
        Select a location for new hazard spawn based on threat weighting.
        Higher threat score = higher chance of selection.
        Adds robust logging and debugging.
        """
        self.logger.debug(f"get_threat_weighted_location called: candidate_locations={candidate_locations}")
        if not candidate_locations:
            self.logger.warning("get_threat_weighted_location called with empty candidate_locations.")
            return None

        weights = []
        for location in candidate_locations:
            threat_score = self.location_threat_scores[location]
            safety_perception = self.room_safety_perception[location]
            combined_weight = threat_score + (safety_perception * 2.0)
            weights.append(max(combined_weight, 0.1))  # Minimum weight of 0.1
            self.logger.debug(
                f"Location '{location}': threat_score={threat_score:.2f}, safety_perception={safety_perception:.2f}, combined_weight={combined_weight:.2f}"
            )

        total_weight = sum(weights)
        self.logger.debug(f"Total weight for selection: {total_weight:.2f}, weights={weights}")

        if total_weight == 0:
            selected = random.choice(candidate_locations)
            self.logger.info(f"All weights zero, randomly selected '{selected}'")
            return selected

        rand_value = random.uniform(0, total_weight)
        cumulative_weight = 0

        for i, weight in enumerate(weights):
            cumulative_weight += weight
            if rand_value <= cumulative_weight:
                selected_location = candidate_locations[i]
                self.logger.info(
                    f"[DeathAI] Selected {selected_location} for hazard spawn "
                    f"(threat: {self.location_threat_scores[selected_location]:.2f}, "
                    f"safety: {self.room_safety_perception[selected_location]:.2f})"
                )
                return selected_location

        self.logger.warning("Weighted selection fell through; returning last candidate.")
        return candidate_locations[-1]  # Fallback
    
    def get_status_report(self) -> dict:
        """Return current AI status for debugging with robust logging."""
        self.logger.debug("get_status_report called.")
        top_threat_locations = dict(sorted(
            self.location_threat_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5])
        top_safe_perception_locations = dict(sorted(
            self.room_safety_perception.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5])
        report = {
            'top_threat_locations': top_threat_locations,
            'top_safe_perception_locations': top_safe_perception_locations,
            'pending_strategies': len(self.pending_counter_strategies),
            'active_strategies': len(self.active_strategies),  # Legacy compatibility
            'aggression_multiplier': self.current_aggression_multiplier,
            'qte_success_rate': self.player_behavior_patterns['qte_success_rate']
        }
        self.logger.debug(f"get_status_report: {report}")
        return report

    def get_threat_analysis(self):
        """Return current threat analysis for debugging/display (legacy compatibility) with robust logging."""
        self.logger.debug("get_threat_analysis called.")
        analysis = {
            'location_threats': dict(self.location_threat_scores),
            'object_threats': dict(self.object_threat_scores),
            'safety_perception': dict(self.room_safety_perception),
            'behavior_pattern': self.player_behavior_patterns,
            'active_strategies': len(self.active_strategies),
            'last_intervention': self.last_intervention_turn
        }
        self.logger.debug(f"get_threat_analysis: {analysis}")
        return analysis

    def get_forced_hazard_activations(self, level_id, current_level_rooms):
        """
        Decide which hazards to force-activate at the start of a level.
        Returns a list of dicts with hazard activation parameters.
        This can use any AI logic or heuristics you want.
        Enhanced: Adds robust logging and debugging.
        """
        self.logger.debug(f"get_forced_hazard_activations called: level_id={level_id}, rooms={list(current_level_rooms.keys())}")
        activations = []

        # Example logic: Always spawn at least one electrical hazard in a utility room
        for room_name, room_data in current_level_rooms.items():
            self.logger.debug(f"Checking room '{room_name}' for gas lines and faulty wiring hazard.")
            if room_data.get("has_gas_lines") and "faulty_wiring" in self.game_logic.resource_manager.get_data("hazards", {}):
                activation = {
                    "hazard_type": "faulty_wiring",
                    "location": room_name,
                    "initial_state_override": None,
                    "target_object_override": None,
                    "support_object_override": None,
                    "source_trigger_id": "death_ai_forced_activation"
                }
                activations.append(activation)
                self.logger.info(f"Forced activation: {activation}")
                break  # Only one for demo; remove break for more

        # Example: If player has been too successful, spawn a hazard in a "safe" room
        safe_rooms = [room for room, score in self.room_safety_perception.items() if score > 2.0]
        self.logger.debug(f"Safe rooms with high safety perception: {safe_rooms}")
        if safe_rooms:
            chosen_room = random.choice(safe_rooms)
            activation = {
                "hazard_type": "gas_leak",
                "location": chosen_room,
                "initial_state_override": "building_tension",
                "target_object_override": None,
                "support_object_override": None,
                "source_trigger_id": "death_ai_forced_activation"
            }
            activations.append(activation)
            self.logger.info(f"Forced activation in safe room: {activation}")

        self.logger.debug(f"get_forced_hazard_activations returning: {activations}")
        # You can add more sophisticated logic here based on threat analysis, etc.
        return activations


    def _apply_high_fear_effects(self, description, room_name):
        """
        Applies high fear level modifications to room descriptions.
        """
        fear_modifications = {
            "Living Room": " The shadows in the corners seem to move when you're not looking directly at them.",
            "Kitchen": " Every creak of the house makes you jump. The silence feels oppressive.",
            "Main Basement Area": " Your breathing echoes unnaturally. Something feels fundamentally wrong here.",
            "MRI Scan Room": " The metallic surfaces seem to pulse with an otherworldly energy.",
            "Hospital Morgue": " The cold air carries whispers that might just be your imagination."
        }
        fear_addition = fear_modifications.get(room_name, " Your heart pounds as anxiety grips you.")
        return description + fear_addition

    def _apply_medium_fear_effects(self, description, room_name):
        """
        Applies medium fear level modifications to room descriptions.
        """
        fear_modifications = {
            "Living Room": " The room feels unnaturally quiet.",
            "Kitchen": " You can't shake the feeling that you're being watched.",
            "Main Basement Area": " The air feels heavy and oppressive.",
            "MRI Scan Room": " The machinery seems more ominous than before.",
            "Hospital Morgue": " The cold seems to seep into your bones."
        }
        fear_addition = fear_modifications.get(room_name, " You feel on edge.")
        return description + fear_addition

    def _apply_environmental_effects(self, description, room_name):
        """
        Applies environmental effects like temperature, lighting, etc.
        """
        rooms_data = self.game_logic.resource_manager.get_data('rooms', {})
        cold_rooms = []
        dark_rooms = []
        for level_rooms in rooms_data.values():
            for room_id, room_data in level_rooms.items():
                if (room_data.get('temperature') == 'cold' or 
                    'morgue' in room_data.get('name', '').lower() or
                    'basement' in room_data.get('name', '').lower()):
                    cold_rooms.append(room_id)
                if (room_data.get('lighting') == 'dark' or
                    'basement' in room_data.get('name', '').lower()):
                    dark_rooms.append(room_id)
        # Apply cold environment effects
        if room_name in cold_rooms and self.game_logic.player.get('temperature_status') != 'warm':
            description += " The cold air makes you shiver."
        # Apply dark environment effects
        if (room_name in dark_rooms and 
            not self._player_has_active_light_source() and
            self.game_logic.player.get('lighting_status') != 'illuminated'):
            description += " The darkness presses in around you."
        return description


    def _handle_mri_control_interaction(self, item_data, rule, messages):
        """
        Handles the special MRI control desk interaction.
        """
        if not self.hazard_engine:
            messages.append(color_text("Error: Hazard system offline for MRI interaction.", "error"))
            return {"death": False, "turn_taken": False}
        
        # Get hazards data from resource manager
        hazards_data = self.game_logic.resource_manager.get_data('hazards', {})
        
        # Find MRI hazard type
        mri_hazard_type = None
        for hazard_type, hazard_data in hazards_data.items():
            if 'MRI' in hazard_type or 'mri' in hazard_type.lower():
                mri_hazard_type = hazard_type
                break
        
        if not mri_hazard_type:
            messages.append(color_text("Error: MRI hazard type not found in hazards data.", "error"))
            return {"death": False, "turn_taken": False}
        
        # Find MRI hazard instance
        mri_hazard_id = None
        for hid, h_inst in self.hazard_engine.active_hazards.items():
            if h_inst.get('type') == mri_hazard_type:
                mri_hazard_id = hid
                break
        
        if not mri_hazard_id:
            messages.append(color_text("Error: MRI machine hazard not found.", "error"))
            return {"death": False, "turn_taken": False}
        
        mri_hazard = self.hazard_engine.active_hazards[mri_hazard_id]
        current_state = mri_hazard.get("state")
        allowed_deactivation_states = rule.get("mri_states_can_deactivate", [])
        
        if current_state in allowed_deactivation_states:
            # Deactivate MRI
            self.hazard_engine.set_hazard_state(mri_hazard_id, "safely_powered_down", messages)
            success_msg = rule.get("message_success", "You swipe the key card. The MRI machine powers down with a final whine.")
            messages.append(color_text(success_msg.format(item_name=item_data.get("name", "key card")), "success"))
            return {"death": False, "turn_taken": True}
        else:
            # Already off or can't be deactivated
            fail_msg = rule.get("message_fail_mri_state", "The MRI machine is not in a state that can be remotely deactivated.")
            messages.append(color_text(fail_msg, "warning"))
            return {"death": False, "turn_taken": False}
        
    def escalate_environment(self, aggression_level):
        """
        Dynamically alter the environment based on Death's aggression.
        aggression_level: float from 0.0 (calm) to 1.0 (maximum aggression)
        Enhanced: Adds robust logging and debugging.
        """
        self.logger.debug(f"escalate_environment called: aggression_level={aggression_level:.2f}")
        for room_name, room in self.game_logic.current_level_rooms.items():
            effects = {}
            if aggression_level > 0.3:
                effects['temperature'] = 'cold'
            if aggression_level > 0.6:
                effects['lighting'] = 'flickering'
            if aggression_level > 0.85:
                effects['lighting'] = 'dark'
            if effects:
                self.logger.info(
                    f"Applying environmental effects to '{room_name}': {effects}"
                )
                self.game_logic.apply_environmental_effect(room_name, effects)

        # Subtle object changes: randomly crack mirrors, tilt pictures, etc.
        for room_name, room in self.game_logic.current_level_rooms.items():
            for furn in room.get('furniture', []):
                # Example: crack mirrors
                if furn.get('type') == 'mirror' and aggression_level > 0.5:
                    chance = aggression_level - 0.5
                    rand_val = random.random()
                    self.logger.debug(
                        f"Checking mirror '{furn.get('name')}' in '{room_name}': chance={chance:.2f}, rand_val={rand_val:.2f}"
                    )
                    if rand_val < chance:
                        self.logger.info(
                            f"Cracking mirror '{furn['name']}' in '{room_name}' due to aggression."
                        )
                        self.game_logic.set_object_examine_overlay(
                            room_name, furn['name'],
                            "[color=ccccff]The mirror is now cracked, a jagged line splitting your reflection.[/color]"
                        )
                # Example: tilt picture frames
                if furn.get('type') == 'picture_frame' and aggression_level > 0.4:
                    chance = aggression_level - 0.4
                    rand_val = random.random()
                    self.logger.debug(
                        f"Checking picture frame '{furn.get('name')}' in '{room_name}': chance={chance:.2f}, rand_val={rand_val:.2f}"
                    )
                    if rand_val < chance:
                        self.logger.info(
                            f"Tilting picture frame '{furn['name']}' in '{room_name}' due to aggression."
                        )
                        self.game_logic.set_object_examine_overlay(
                            room_name, furn['name'],
                            "[color=ffffcc]The picture frame is now hanging crooked, as if disturbed by unseen hands.[/color]"
                        )

    def on_turn(self):
        """Call this each turn to escalate environment based on aggression. Enhanced: Adds robust logging and debugging."""
        aggression = getattr(self, 'aggression', 0.0)
        self.logger.debug(f"on_turn called: aggression={aggression:.2f}")
        self.escalate_environment(aggression)
        self.logger.debug("on_turn completed environment escalation.")
        # ...existing turn logic...

    def analyze_room_for_threat_potential(self, room_name: str) -> float:
        """
        Analyze a room for its threat potential based on hazards, safety perception, and behavioral patterns.
        Returns a float score representing threat potential.
        Enhanced: Adds robust logging and debugging.
        """
        self.logger.debug(f"analyze_room_for_threat_potential called: room_name={room_name}")
        hazards = self.game_logic.get_room_hazards_descriptions(room_name)
        hazard_score = sum(h.get('threat_level', 1.0) for h in hazards.values()) if hazards else 0.0
        safety_score = self.room_safety_perception.get(room_name, 0.0)
        visit_freq = self.player_behavior_patterns['room_visit_frequency'].get(room_name, 0)
        threat_score = self.location_threat_scores.get(room_name, 0.0)
        total_score = hazard_score + (threat_score * 1.5) - (safety_score * 0.5) + (visit_freq * 0.2)
        self.logger.debug(
            f"Room '{room_name}': hazard_score={hazard_score:.2f}, threat_score={threat_score:.2f}, "
            f"safety_score={safety_score:.2f}, visit_freq={visit_freq}, total_score={total_score:.2f}"
        )
        return total_score

    def get_omen_message(self) -> str:
        """
        Generate an omen message based on pending counter-strategies.
        Returns None if no omen should be generated.
        Enhanced: Adds robust logging and debugging.
        """
        self.logger.debug("get_omen_message called.")
        if not self.pending_counter_strategies:
            self.logger.debug("No pending counter-strategies; no omen message generated.")
            return None
        strategy = self.pending_counter_strategies[0]
        reason = strategy.get('reason', '')
        location = strategy.get('location', '')
        self.logger.debug(f"Pending strategy for omen: reason={reason}, location={location}")
        if reason.startswith('player_feels_too_safe_'):
            loc = reason.split('player_feels_too_safe_')[1]
            msg = f"You sense you are no longer safe in the {loc}."
            self.logger.info(f"Omen message generated: {msg}")
            return msg
        elif reason.startswith('location_threat_high_'):
            loc = reason.split('location_threat_high_')[1]
            msg = f"Something dark is drawn towards the {loc}."
            self.logger.info(f"Omen message generated: {msg}")
            return msg
        elif reason == 'player_too_successful_at_qtes':
            msg = "You feel a growing malice watching your every move."
            self.logger.info(f"Omen message generated: {msg}")
            return msg
        # Default fallback
        msg = "A chill runs down your spine, as if something is about to happen..."
        self.logger.info(f"Omen message generated (default): {msg}")
        return msg
    
    def get_save_state(self) -> dict:
        """Get the current state for saving."""
        return {
            "aggression_level": self.aggression_level,
            "last_intervention_time": self.last_intervention_time,
            "recent_hiding_spots": list(self.recent_hiding_spots) if hasattr(self, 'recent_hiding_spots') else [],
            "intervention_count": getattr(self, 'intervention_count', 0),
            "fear_threshold": getattr(self, 'fear_threshold', 0.5)
        }
    
    def load_state(self, state_data: dict):
        """Restore state from save data."""
        try:
            self.aggression_level = state_data.get("aggression_level", 0.0)
            self.last_intervention_time = state_data.get("last_intervention_time", 0)
            
            if hasattr(self, 'recent_hiding_spots'):
                self.recent_hiding_spots = set(state_data.get("recent_hiding_spots", []))
            if hasattr(self, 'intervention_count'):
                self.intervention_count = state_data.get("intervention_count", 0)
            if hasattr(self, 'fear_threshold'):
                self.fear_threshold = state_data.get("fear_threshold", 0.5)
            
            self.logger.info("Death AI state restored from save")
        except Exception as e:
            self.logger.error(f"Failed to restore Death AI state: {e}", exc_info=True)