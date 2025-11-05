# fd_terminal/hazard_engine.py
"""
The Engine of Calamity.

This system manages the state and progression of all environmental hazards.
It operates autonomously each turn and responds to player interactions.
"""
import logging
from typing import Tuple
from typing import Set, Tuple
from typing import Union, Set, Tuple
from typing import List, Set, Tuple
import random
import uuid
from kivy.clock import Clock

from typing import Optional, Tuple
from .resource_manager import ResourceManager
from .utils import color_text

class HazardEngine:
    def __init__(self, resource_manager: ResourceManager):
        self.resource_manager = resource_manager
        self.logger = logging.getLogger("HazardEngine")
        
        # This reference will be injected by GameLogic after initialization
        # to prevent a circular import dependency.
        self.game_logic = None 
        
        self.active_hazards = {}
        self.hazards_master_data = self.resource_manager.get_data('hazards', {})
        
        self.logger.info("Engine of Calamity initialized.")

    def initialize_for_level(self, level_id: int):
        """Resets and sets up hazards for the start of a new level, then spawns their entities."""
        self.logger.debug(f"Initializing hazards for level {level_id}. Clearing active hazards.")
        self.active_hazards.clear()
        self.logger.info(f"Hazard Engine (re)initialized for Level {level_id}.")
        # Seed hazards and spawn their related entities from rooms config
        if not getattr(self, 'game_logic', None):
            self.logger.warning("HazardEngine.initialize_for_level: game_logic not set; cannot seed hazards/entities.")
            return
        rooms = self.game_logic.current_level_rooms_world_state or {}
        for room_name, room in rooms.items():
            hazard_entries = room.get('hazards_present') or room.get('hazards') or []
            for h in hazard_entries:
                if isinstance(h, str):
                    hazard_type = h
                    chance = 1.0
                elif isinstance(h, dict):
                    hazard_type = h.get('type') or h.get('hazard_type')
                    chance = h.get('chance', 1.0)
                else:
                    continue
                if not hazard_type or hazard_type not in self.hazards_master_data:
                    continue
                if random.random() > float(chance):
                    continue
                # Add hazard instance
                hid = self._add_active_hazard(
                    hazard_type=hazard_type,
                    location=room_name,
                    source_trigger_id="level_seed"
                )
                # Spawn related objects for this hazard
                if hid:
                    self._spawn_entities_for_hazard(hid)

    def _add_active_hazard(
        self,
        hazard_type: str,
        location: str,
        initial_state_override: Optional[str] = None,
        target_object_override: Optional[str] = None,
        support_object_override: Optional[str] = None,
        source_trigger_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Create and register a new active hazard instance from master data.
        Returns the new hazard_id or None on failure.
        """
        h_def = self.hazards_master_data.get(hazard_type)
        if not h_def:
            self.logger.warning(f"_add_active_hazard: Unknown hazard type '{hazard_type}'.")
            return None

        hazard_id = f"{hazard_type}#{uuid.uuid4().hex[:8]}"
        initial_state = initial_state_override or h_def.get("initial_state") or "dormant"

        self.active_hazards[hazard_id] = {
            "id": hazard_id,
            "type": hazard_type,
            "location": location,
            "state": initial_state,
            "master_data": h_def,
            "spawned_entities": {},
            "target_object_override": target_object_override,
            "support_object_override": support_object_override,
            "source_trigger_id": source_trigger_id,
            "started_by_player": False,  # respect requires_player_interaction_to_start
        }
        self.logger.info(f"Spawned hazard '{hazard_type}' in '{location}' (id={hazard_id}) at state '{initial_state}'.")

        # Spawn any related room entities
        try:
            self._spawn_entities_for_hazard(hazard_id)
        except Exception as e:
            self.logger.error(f"_add_active_hazard: Failed spawning entities for '{hazard_id}': {e}", exc_info=True)

        # Set initial state WITHOUT entry effects; we only want state recorded
        try:
            self.set_hazard_state(hazard_id, initial_state, suppress_entry_effects=True)
        except Exception as e:
            self.logger.error(f"_add_active_hazard: Failed to finalize state entry for '{hazard_id}': {e}", exc_info=True)

        return hazard_id

    # Convenience used by DeathAI/escalation code
    def get_hazards_in_location(self, room_name: str) -> list:
        """Return all active hazard instances in a room."""
        return [h for h in self.active_hazards.values() if h.get("location") == room_name]

    def get_room_hazards_descriptions(self, room_name: str) -> dict:
        """Return a mapping of hazard_id -> hazard instance for a room (used by DeathAI)."""
        return {hid: h for hid, h in self.active_hazards.items() if h.get("location") == room_name}

    def _spawn_entities_for_hazard(self, hazard_id: str):
        """Place hazard-related objects into the room, picking display names randomly per entity."""
        hazard_inst = self.active_hazards.get(hazard_id)
        if not hazard_inst:
            return
        hazard_type = hazard_inst.get('type')
        room_name = hazard_inst.get('location')
        hazard_def = self.hazards_master_data.get(hazard_type, {})
        entity_keys = list(hazard_def.get('spawn_entities', []))

        rooms = self.game_logic.current_level_rooms_world_state
        room = rooms.get(room_name)
        if not room:
            return

        # Ensure objects list exists
        objs = room.get('objects')
        if objs is None:
            room['objects'] = objs = []

        # Normalizer for display names
        try:
            norm = self.game_logic._norm
        except Exception:
            norm = lambda s: str(s or "").strip().lower().replace('_', ' ')

        # EXISTING: dedupe by display name and key
        existing_names = set()
        existing_keys = set()
        for o in objs:
            if isinstance(o, dict):
                if o.get('name'):
                    existing_names.add(norm(o.get('name')))
                if o.get('key'):
                    existing_keys.add(str(o.get('key')).strip().lower())
            else:
                existing_names.add(norm(o))

        def _add_entity(display_name: str, desc_text: str | None = None, key_hint: str | None = None):
            dn = str(display_name)
            kh = (key_hint or "").strip().lower() if key_hint else None
            if norm(dn) in existing_names or (kh and kh in existing_keys):
                return
            entity = {
                "name": dn,
                "type": "hazard_entity",
                "hazard_key": hazard_type
            }
            if kh:
                entity["key"] = kh
            if desc_text:
                entity["description"] = desc_text
            objs.append(entity)
            existing_names.add(norm(dn))
            if kh:
                existing_keys.add(kh)

        # If explicit spawn_entities are defined, create those
        if entity_keys:
            items_master = self.game_logic.resource_manager.get_data('items', {}) if self.game_logic and self.game_logic.resource_manager else {}
            for ekey in entity_keys:
                # choose display name like before
                display = self._choose_display_name_for_entity(ekey, hazard_def, items_master)
                curr_state = hazard_inst.get('state') or hazard_def.get('initial_state')
                sdef = (hazard_def.get('states') or {}).get(curr_state or "", {})
                desc = sdef.get('description')
                if desc:
                    desc = desc.replace("{object_name}", display)
                # NEW: pass the key hint so we dedupe against room objects that already declare "key": ekey
                _add_entity(display, desc_text=desc, key_hint=str(ekey).lower())
            return

        # ...existing fallback entity creation (unchanged)...

    def _choose_display_name_for_entity(self, entity_key, hazard_def: dict, items_master: dict) -> str:
        """
        Pick a random user-facing name for an entity from item name/aliases and hazard object_name_options.
        Handles entity_key as dict or string. Robust logging included.
        """
        candidates = []
        # Normalize entity_key to string if it's a dict
        if isinstance(entity_key, dict):
            # Try to extract a useful identifier
            key_str = entity_key.get('id') or entity_key.get('name') or str(entity_key)
            logging.warning(f"_choose_display_name_for_entity: entity_key was dict, using '{key_str}' as key.")
        else:
            key_str = str(entity_key)

        # From items.json
        item = items_master.get(key_str) or items_master.get(key_str.replace(' ', '_')) or {}
        if item:
            base = item.get('name') or key_str
            aliases = item.get('aliases') or []
            candidates.extend([base] + list(aliases))
        else:
            candidates.append(key_str)

        # From hazard-level object_name_options (simple keyword relevance)
        extras = hazard_def.get('object_name_options') or []
        ek_norm = key_str.replace('_', ' ').lower()
        for opt in extras:
            o_norm = str(opt).lower()
            if any(tok and tok in o_norm for tok in ek_norm.split()):
                candidates.append(opt)

        # Dedup and choose
        seen = set()
        filtered = []
        for c in candidates:
            if c and c not in seen:
                filtered.append(c)
                seen.add(c)

        if not filtered:
            logging.warning(f"_choose_display_name_for_entity: No candidates found for entity_key '{key_str}'. Returning as-is.")
        return random.choice(filtered) if filtered else key_str

    def process_turn(self) -> dict:
        """The main tick of the hazard engine. Called once per game turn."""
        self.logger.debug("Processing hazard engine turn.")
        messages = []

        # --- Execute AI Strategies ---
        if self.game_logic and self.game_logic.death_ai:
            self.logger.debug("Calling DeathAI counter strategies.")
            ai_messages = self.game_logic.death_ai.execute_counter_strategies()
            messages.extend(ai_messages)

        # --- Hazard Progression & Movement Logic ---
        for hazard_id, hazard in list(self.active_hazards.items()):
            self.logger.debug(f"Processing hazard {hazard_id}: {hazard}")
            current_state_key = hazard.get('state')
            hazard_def = hazard.get('master_data', {})
            state_data = (hazard_def.get('states') or {}).get(current_state_key, {})

            # Existing autonomous actions
            action = state_data.get('autonomous_action')
            if action == '_check_progression_by_flags':
                self._maybe_progress_on_flags(hazard_id)
            elif action == '_check_icu_examination_flags':
                self._check_icu_examination_flags(hazard)

            # NEW: Process hazard movement if can_move_between_rooms and has movement_logic
            if hazard_def.get('can_move_between_rooms') and hazard_def.get('movement_logic'):
                self._process_hazard_movement(hazard_id)

            # Death's Breath aura influence
            if hazard.get('type') == 'deaths_breath':
                self._influence_hazards_in_room(hazard_id)

        self.logger.debug(f"Turn complete. Messages: {messages}")
        return {
            "messages": messages,
            "death_triggered": False,
            "qte_triggered": None
        }
    
    def _process_hazard_movement(self, hazard_id: str):
        """
        Move hazards between rooms based on their movement_logic.
        Currently supports: 'seek_target_type_then_player'
        """
        hazard = self.active_hazards.get(hazard_id)
        if not hazard:
            return

        hazard_def = hazard.get('master_data', {})
        movement_logic = hazard_def.get('movement_logic')
        current_location = hazard.get('location')

        if movement_logic == 'seek_target_type_then_player':
            self._movement_seek_target_then_player(hazard_id, hazard, hazard_def, current_location)

    def _movement_seek_target_then_player(self, hazard_id: str, hazard: dict, hazard_def: dict, current_location: str):
        """
        Movement AI: seek primary target types (like gas_leak), else move toward player.
        """
        import random

        seekable_types = hazard_def.get('seekable_target_types', [])
        player_seek_chance = hazard_def.get('player_seek_chance_if_no_primary_target', 0.2)

        # 1) Search all rooms for primary targets
        target_room = None
        for room_id, room_data in (self.game_logic.current_level_rooms_world_state or {}).items():
            if room_id == current_location:
                continue
            # Check for hazards of seekable types in this room
            for other_id, other_hazard in self.active_hazards.items():
                if other_hazard.get('location') == room_id and other_hazard.get('type') in seekable_types:
                    target_room = room_id
                    self.logger.info(f"[{hazard_id}] Found target hazard '{other_hazard.get('type')}' in '{room_id}'")
                    break
            if target_room:
                break

        # 2) If no primary target, maybe seek player
        if not target_room and random.random() < player_seek_chance:
            target_room = self.game_logic.player.get('location')
            self.logger.info(f"[{hazard_id}] No primary target found; seeking player in '{target_room}'")

        # 3) Move one step toward target_room
        if target_room and target_room != current_location:
            next_step = self._find_next_step_toward(current_location, target_room)
            if next_step:
                self.logger.info(f"[{hazard_id}] Moving from '{current_location}' to '{next_step}' (toward '{target_room}')")
                hazard['location'] = next_step
                # Respawn entities in new room
                self._spawn_entities_for_hazard(hazard_id)
                # Check for collisions in new room
                self._check_hazard_collisions(hazard_id)

    def _find_next_step_toward(self, start: str, target: str) -> str | None:
        """
        BFS pathfinding: return the first room to move to from 'start' toward 'target'.
        """
        if start == target:
            return None

        from collections import deque
        visited = {start}
        queue = deque([(start, [start])])

        while queue:
            current, path = queue.popleft()
            room_data = (self.game_logic.current_level_rooms_world_state or {}).get(current, {})
            exits = room_data.get('exits', {})

            for direction, dest in exits.items():
                if isinstance(dest, dict):
                    continue  # skip complex/locked exits
                if dest == target:
                    # Found target; return first step in path (after start)
                    return path[1] if len(path) > 1 else dest
                if dest not in visited:
                    visited.add(dest)
                    queue.append((dest, path + [dest]))

        return None  # no path found

    def _check_hazard_collisions(self, hazard_id: str):
        """
        Check if a hazard collides with other hazards or the player in its current room.
        Trigger collision_effects defined in the hazard's master data.
        """
        hazard = self.active_hazards.get(hazard_id)
        if not hazard:
            return

        hazard_def = hazard.get('master_data', {})
        collision_effects = hazard_def.get('collision_effects', {})
        location = hazard.get('location')

        # Check collision with player
        if location == self.game_logic.player.get('location'):
            player_effect = collision_effects.get('player')
            if player_effect:
                import random
                if random.random() < player_effect.get('chance', 1.0):
                    msg = (player_effect.get('message') or "").replace("{object_name}", hazard_def.get('name', 'hazard'))
                    self.logger.info(f"[{hazard_id}] Collision with player: {msg}")
                    self.game_logic.add_ui_event({"event_type": "show_message", "message": msg})
                    # Apply status effect if defined
                    status = player_effect.get('status_effect')
                    if status:
                        # PATCH: normalize status_effects to a list before appending
                        se = self.game_logic.player.get('status_effects')
                        if isinstance(se, dict):
                            # convert dict to list of values (fallback); or start fresh if empty
                            self.game_logic.player['status_effects'] = list(se.values()) if se else []
                        elif not isinstance(se, list):
                            self.game_logic.player['status_effects'] = []
                        self.game_logic.player['status_effects'].append(status)

        # Check collision with other hazards in same room
        for other_id, other_hazard in self.active_hazards.items():
            if other_id == hazard_id or other_hazard.get('location') != location:
                continue
            other_type = other_hazard.get('type')
            effect = collision_effects.get(other_type)
            if effect:
                import random
                if random.random() < effect.get('chance', 1.0):
                    msg = (effect.get('message') or "").replace("{object_name}", hazard_def.get('name', 'hazard'))
                    self.logger.info(f"[{hazard_id}] Collision with '{other_type}': {msg}")
                    self.game_logic.add_ui_event({"event_type": "show_message", "message": msg})
                    # Trigger state change on the target hazard
                    target_state = effect.get('target_state')
                    if target_state:
                        result = self.set_hazard_state(other_id, target_state)
                        if result and self.game_logic:
                            for cons in result.get('consequences', []):
                                self.game_logic.handle_hazard_consequence(cons)

    # --- Helpers for set_hazard_state ---

    def _resolve_state_def(self, hazard: dict, new_state: str) -> dict:
        """Resolve state definition for a hazard and inject the __state_name__ for lookups."""
        self.logger.debug(f"[_resolve_state_def] Resolving state definition for hazard: {hazard.get('id', 'unknown')}, new_state: {new_state}")
        hdef = hazard.get('master_data', {}) or {}
        states = hdef.get('states', {}) or {}
        sdef = states.get(new_state, {}) or {}
        sdef['__state_name__'] = new_state
        self.logger.debug(f"[_resolve_state_def] Resolved state definition: {sdef}")
        return sdef

    def _apply_entry_actions(self, sdef: dict, hazard_id: str):
        """Run special action and entry rewards for a state (safe to call even if they do nothing)."""
        self.logger.debug(f"[_apply_entry_actions] Applying entry actions for hazard_id: {hazard_id}, state: {sdef.get('__state_name__', 'unknown')}")
        # Order preserved with original code
        self._maybe_run_special_action(sdef, hazard_id)
        self._process_state_entry_rewards(sdef)
        self.logger.debug(f"[_apply_entry_actions] Entry actions applied for hazard_id: {hazard_id}")

    def _extract_entry_metadata(self, sdef: dict) -> Tuple[Optional[str], str, Optional[dict], bool, Optional[str]]:
        """Pull out common fields from a state definition needed to build consequences."""
        self.logger.debug(f"[_extract_entry_metadata] Extracting entry metadata from state definition: {sdef}")
        popup_event = sdef.get('ui_popup_event') or {}
        popup_msg = sdef.get('description') or popup_event.get('message')
        popup_title = popup_event.get('title', 'Notice')
        qte_entry = sdef.get('triggers_qte_on_entry') or None
        pause = bool(sdef.get('pause_for_player_acknowledgement'))
        next_state = sdef.get('next_state')
        self.logger.debug(f"[_extract_entry_metadata] Extracted: popup_msg='{popup_msg}', popup_title='{popup_title}', qte_entry='{qte_entry}', pause='{pause}', next_state='{next_state}'")
        return popup_msg, popup_title, qte_entry, pause, next_state

    def _build_popup_consequence(self, hazard_id: str, new_state: str, popup_title: str, popup_message: str,
                                 qte_entry: Optional[dict], pause: bool, next_state: Optional[str]) -> dict:
        """
        Build a popup consequence, formatting placeholders like {object_name} using hazard context.
        """
        popup_evt = {
            "type": "show_popup",
            "title": popup_title or "Notice",
            "message": popup_message or "",
            "meta": {"hazard_id": hazard_id, "state": new_state}
        }

        hazard = self.active_hazards.get(hazard_id)
        # --- GUARD: Prevent repeated transitions in QTE chains ---
        if hazard is not None:
            if "_visited_states" not in hazard:
                hazard["_visited_states"] = set()
            if new_state in hazard["_visited_states"]:
                self.logger.warning(f"[_build_popup_consequence] State '{new_state}' for hazard '{hazard_id}' already visited in this QTE chain. Preventing loop.")
                return popup_evt
            hazard["_visited_states"].add(new_state)
        # --- END GUARD ---

        # If there is a QTE on entry, defer it to popup dismiss (this is for the state we just entered)
        if qte_entry:
            qte_ctx = dict(qte_entry.get('qte_context', {}))
            qte_ctx['qte_source_hazard_id'] = hazard_id
            popup_evt["on_close_start_qte"] = {
                "qte_type": (qte_entry.get('qte_type') or qte_entry.get('qte_to_trigger')),
                "qte_context": qte_ctx
            }

        # IMPORTANT: For pause states, advance to next_state after user acknowledges the popup.
        # Previously this incorrectly set target_state to new_state, causing the chain to stall.
        if pause and next_state:
            popup_evt["on_close_set_hazard_state"] = {
                "hazard_id": hazard_id,
                "target_state": next_state  # <-- advance the chain on dismiss
            }
        elif next_state:
            # Non-paused states can auto-advance (no popup wait)
            try:
                auto = self._build_auto_advance_consequence(hazard_id, next_state)
                if auto:
                    popup_evt.setdefault("followups", []).append(auto)
            except Exception as e:
                self.logger.error(f"[_build_popup_consequence] Failed to attach auto-advance for '{hazard_id}' -> '{next_state}': {e}")

        return popup_evt

    def _build_immediate_qte_consequence(self, hazard_id: str, qte_entry: dict) -> dict:
        """Construct an immediate start_qte consequence when no popup is present."""
        self.logger.debug(f"[_build_immediate_qte_consequence] Building immediate QTE consequence for hazard_id: {hazard_id}, qte_entry: {qte_entry}")
        hazard = self.active_hazards.get(hazard_id)
        new_state = hazard.get('state') if hazard else None

        # --- GUARD: Prevent repeated transitions in QTE chains ---
        if hazard is not None:
            if "_visited_states" not in hazard:
                hazard["_visited_states"] = set()
            if new_state in hazard["_visited_states"]:
                self.logger.warning(f"[_build_immediate_qte_consequence] State '{new_state}' for hazard '{hazard_id}' already visited in this QTE chain. Preventing loop.")
                return {}
            hazard["_visited_states"].add(new_state)
        # --- END GUARD ---

        qte_ctx = dict(qte_entry.get('qte_context', {}))
        qte_ctx['qte_source_hazard_id'] = hazard_id
        consequence = {
            "type": "start_qte",
            "qte_type": qte_entry.get("qte_type"),
            "qte_context": qte_ctx
        }
        self.logger.debug(f"[_build_immediate_qte_consequence] Built consequence: {consequence}")
        return consequence

    def _build_auto_advance_consequence(self, hazard_id: str, next_state: str) -> dict:
        """Construct a follow-up state change consequence for non-paused states."""
        self.logger.debug(f"[_build_auto_advance_consequence] Building auto-advance consequence for hazard_id: {hazard_id}, next_state: {next_state}")
        hazard = self.active_hazards.get(hazard_id)
        # --- GUARD: Prevent repeated transitions in QTE chains ---
        if hazard is not None:
            if "_visited_states" not in hazard:
                hazard["_visited_states"] = set()
            if next_state in hazard["_visited_states"]:
                self.logger.warning(f"[_build_auto_advance_consequence] State '{next_state}' for hazard '{hazard_id}' already visited in this QTE chain. Preventing loop.")
                return {}
            hazard["_visited_states"].add(next_state)
        # --- END GUARD ---
        consequence = {
            "type": "hazard_state_change",
            "hazard_id": hazard_id,
            "target_state": next_state
        }
        self.logger.debug(f"[_build_auto_advance_consequence] Built consequence: {consequence}")
        return consequence

    def set_hazard_state(self, hazard_id: str, new_state: str, suppress_entry_effects: bool = False, messages=None) -> dict:
        """
        Sets hazard state and returns structured consequences for GameLogic to handle.
        Main orchestrator that delegates to helper methods for each stage of state transition.
        """
        self.logger.debug(f"[set_hazard_state] Called for hazard_id='{hazard_id}', new_state='{new_state}'")
        
        # Stage 1: Validation and early returns
        validation_result = self._validate_state_transition(hazard_id, new_state, messages)
        if validation_result.get('early_return'):
            return validation_result
        
        hazard = validation_result['hazard']
        msgs = validation_result['messages']
        consequences = []
        
        # Stage 2: Update hazard state
        self._update_hazard_state(hazard, new_state)
        
        # Stage 3: Check for game over (guard against further processing)
        if self._is_game_over():
            self.logger.info(f"[set_hazard_state] Game over detected; halting QTE chain for hazard '{hazard_id}' state '{new_state}'")
            return {"messages": msgs, "consequences": []}
        
        # Stage 4: Process state change triggers (spawn/affect other hazards)
        trigger_consequences = self._process_state_change_triggers(hazard, new_state, msgs)
        consequences.extend(trigger_consequences)
        
        # Stage 5: Track evaded hazards
        self._track_evaded_hazard_if_safe(hazard, new_state)
        
        # Stage 6: Early return if suppressing entry effects
        if suppress_entry_effects:
            return {"messages": msgs, "consequences": consequences}
        
        # Stage 7: Apply entry actions and extract metadata
        sdef = self._resolve_state_def(hazard, new_state)
        self._apply_entry_actions(sdef, hazard_id)
        popup_msg, popup_title, qte_entry, pause, next_state = self._extract_entry_metadata(sdef)
        
        # Stage 8: Handle terminal states (death or level complete)
        terminal_result = self._handle_terminal_state(sdef, msgs, consequences)
        if terminal_result:
            return terminal_result
        
        # Stage 9: Build and return consequences
        return self._build_state_consequences(
            hazard_id, new_state, popup_msg, popup_title, 
            qte_entry, pause, next_state, msgs, consequences
        )

    # ==================== VALIDATION HELPERS ====================

    def _validate_state_transition(self, hazard_id: str, new_state: str, messages) -> dict:
        """
        Validates hazard exists and state transition is not a duplicate.
        Returns dict with 'early_return' key if validation fails.
        """
        try:
            hazard = self.active_hazards.get(hazard_id)
            if not hazard:
                self.logger.warning(f"[_validate_state_transition] Unknown hazard id '{hazard_id}'")
                return {"early_return": True, "consequences": []}
            
            current_state = hazard.get('state')
            if current_state == new_state:
                self.logger.info(f"[_validate_state_transition] Ignoring repeated transition to state '{new_state}' for hazard '{hazard_id}'")
                return {"early_return": True, "consequences": []}
            
            msgs = messages if isinstance(messages, list) else []
            return {
                "early_return": False,
                "hazard": hazard,
                "messages": msgs
            }
        except Exception as e:
            self.logger.error(f"[_validate_state_transition] Validation failed for '{hazard_id}': {e}", exc_info=True)
            return {"early_return": True, "consequences": []}

    def _is_game_over(self) -> bool:
        """Check if game is over to prevent further consequence processing."""
        try:
            return self.game_logic and getattr(self.game_logic, "is_game_over", False)
        except Exception as e:
            self.logger.error(f"[_is_game_over] Error checking game over state: {e}", exc_info=True)
            return False

    # ==================== STATE UPDATE HELPERS ====================

    def _update_hazard_state(self, hazard: dict, new_state: str):
        """Updates hazard to new state and logs the transition."""
        try:
            prev_state = hazard.get('state')
            hazard['state'] = new_state
            hazard_id = hazard.get('id', 'unknown')
            self.logger.info(f"[_update_hazard_state] Hazard '{hazard_id}' state changed from '{prev_state}' to '{new_state}'.")
        except Exception as e:
            self.logger.error(f"[_update_hazard_state] Failed to update hazard state: {e}", exc_info=True)

    # ==================== TRIGGER PROCESSING ====================

    def _process_state_change_triggers(self, hazard: dict, new_state: str, msgs: list) -> list:
        """
        Process triggers_hazard_on_state_change: spawn or affect other hazards.
        Returns list of consequences generated by triggers.
        """
        consequences = []
        try:
            hazard_type = hazard.get('type')
            location = hazard.get('location')
            hazards_master = self.resource_manager.get_data('hazards', {})
            hazard_def = hazards_master.get(hazard_type, {})
            state_def = hazard_def.get('states', {}).get(new_state, {})
            triggers = state_def.get('triggers_hazard_on_state_change', [])
            
            for trigger in triggers:
                try:
                    trigger_cons = self._process_single_trigger(trigger, location, msgs)
                    if trigger_cons:
                        consequences.append(trigger_cons)
                except Exception as e:
                    self.logger.error(f"[_process_state_change_triggers] Failed to process trigger {trigger}: {e}", exc_info=True)
            
            return consequences
        except Exception as e:
            self.logger.error(f"[_process_state_change_triggers] Error processing triggers: {e}", exc_info=True)
            return []

    def _process_single_trigger(self, trigger: dict, default_location: str, msgs: list) -> Optional[dict]:
        """
        Process a single hazard trigger, spawning or transitioning target hazard.
        Returns consequence dict or None if trigger fails validation.
        """
        try:
            t_hazard_type = trigger.get('hazard_type') or trigger.get('type')
            t_location = trigger.get('location', default_location)
            t_state = trigger.get('target_state') or trigger.get('initial_state')
            t_chance = trigger.get('chance', 1.0)
            
            if not t_hazard_type or not t_state:
                self.logger.warning(f"[_process_single_trigger] Skipping malformed trigger: {trigger}")
                return None
            
            if random.random() > float(t_chance):
                return None
            
            # Find or create target hazard
            existing = self._find_or_create_target_hazard(t_hazard_type, t_location, t_state)
            
            if existing:
                if trigger.get('message'):
                    msgs.append(str(trigger['message']))
                return {
                    "type": "hazard_state_change",
                    "hazard_id": existing,
                    "target_state": t_state
                }
            return None
        except Exception as e:
            self.logger.error(f"[_process_single_trigger] Error: {e}", exc_info=True)
            return None

    def _find_or_create_target_hazard(self, hazard_type: str, location: str, initial_state: str) -> Optional[str]:
        """Find existing hazard of type in location, or create new one."""
        try:
            # Search for existing
            for h_id, h_inst in self.active_hazards.items():
                if h_inst.get('type') == hazard_type and h_inst.get('location') == location:
                    return h_id
            
            # Create new
            return self._add_active_hazard(
                hazard_type=hazard_type,
                location=location,
                initial_state_override=initial_state
            )
        except Exception as e:
            self.logger.error(f"[_find_or_create_target_hazard] Error: {e}", exc_info=True)
            return None

    # ==================== EVADED HAZARD TRACKING ====================

    def _track_evaded_hazard_if_safe(self, hazard: dict, new_state: str):
        """Track hazard as evaded if it reaches a safe terminal state."""
        try:
            safe_states = ['inactive', 'resolved', 'evaded', 'neutralized', 'defused']
            if new_state not in safe_states or not self.game_logic:
                return
            
            hazard_type = hazard.get('type', '')
            hazard_def = hazard.get('master_data', {})
            evaded_hazard = {
                'name': hazard_def.get('name', hazard_type.replace('_', ' ').title()),
                'description': f"Successfully avoided: {hazard_def.get('description', 'Danger averted through quick thinking.')}"
            }
            
            if 'evaded_hazards' not in self.game_logic.player:
                self.game_logic.player['evaded_hazards'] = []
            self.game_logic.player['evaded_hazards'].append(evaded_hazard)
            
            self.logger.info(f"[_track_evaded_hazard_if_safe] Added evaded hazard: {evaded_hazard['name']}")
        except Exception as e:
            self.logger.error(f"[_track_evaded_hazard_if_safe] Error: {e}", exc_info=True)

    # ==================== TERMINAL STATE HANDLING ====================

    def _handle_terminal_state(self, sdef: dict, msgs: list, consequences: list) -> Optional[dict]:
        """
        Handle terminal states (death or level complete).
        Returns complete result dict if terminal, None otherwise.
        """
        try:
            if not (sdef.get('is_terminal_state') or sdef.get('instant_death_in_room')):
                return None
            
            is_death = bool(sdef.get('instant_death_in_room') or sdef.get('death_message'))
            
            if is_death:
                return self._build_death_terminal_result(sdef, msgs, consequences)
            else:
                return self._build_level_complete_terminal_result(sdef, msgs, consequences)
        except Exception as e:
            self.logger.error(f"[_handle_terminal_state] Error: {e}", exc_info=True)
            return None

    def _build_death_terminal_result(self, sdef: dict, msgs: list, consequences: list) -> dict:
        """Build result for death terminal state."""
        try:
            popup_message = sdef.get('death_message') or sdef.get('description') or "You died."
            popup_event = {
                "type": "show_popup",
                "title": "Notice",
                "message": popup_message,
                "output_panel": True,
                "on_close_emit_ui_events": [{
                    "event_type": "game_over",
                    "death_reason": popup_message,
                    "final_narrative": self.game_logic.get_death_narrative() if self.game_logic else ""
                }]
            }
            
            if self.game_logic:
                self.game_logic.is_game_over = True
                self.game_logic.player.setdefault('death_reason', popup_message)
            
            return {"messages": msgs, "consequences": [popup_event] + consequences}
        except Exception as e:
            self.logger.error(f"[_build_death_terminal_result] Error: {e}", exc_info=True)
            return {"messages": msgs, "consequences": consequences}

    def _build_level_complete_terminal_result(self, sdef: dict, msgs: list, consequences: list) -> dict:
        """Build result for level complete terminal state."""
        try:
            popup_message = sdef.get('description') or "You survived!"
            level_complete_event = {"event_type": "level_complete"}
            
            if self.game_logic:
                self.game_logic.is_transitioning = True
                self.game_logic.player['level_complete_flag'] = True
                if hasattr(self.game_logic, 'get_level_completion_data'):
                    lcd = self.game_logic.get_level_completion_data()
                    level_complete_event.update(lcd)
            
            popup_event = {
                "type": "show_popup",
                "title": "Level Complete",
                "message": popup_message,
                "output_panel": True,
                "on_close_emit_ui_events": [level_complete_event]
            }
            
            return {"messages": msgs, "consequences": [popup_event] + consequences}
        except Exception as e:
            self.logger.error(f"[_build_level_complete_terminal_result] Error: {e}", exc_info=True)
            return {"messages": msgs, "consequences": consequences}

    # ==================== CONSEQUENCE BUILDING ====================

    def _build_state_consequences(self, hazard_id: str, new_state: str, popup_msg: str, 
                                popup_title: str, qte_entry: Optional[dict], pause: bool, 
                                next_state: Optional[str], msgs: list, consequences: list) -> dict:
        """
        Build consequences based on state metadata (popup, QTE, auto-advance).
        Returns final consequence dict with guarded builders to prevent loops after death.
        """
        try:
            # Priority 1: Popup with optional deferred actions
            if popup_msg:
                consequence = self._guarded_build_popup_consequence(
                    hazard_id, new_state, popup_title, popup_msg,
                    qte_entry, pause, next_state
                )
                return {"messages": msgs, "consequences": [consequence] + consequences}
            
            # Priority 2: Immediate QTE (no popup)
            if qte_entry:
                consequence = self._guarded_build_immediate_qte_consequence(hazard_id, qte_entry)
                if consequence:
                    return {"messages": msgs, "consequences": [consequence] + consequences}
            
            # Priority 3: Auto-advance to next state (no pause, no QTE)
            if next_state and not pause:
                consequence = self._guarded_build_auto_advance_consequence(hazard_id, next_state)
                if consequence:
                    return {"messages": msgs, "consequences": [consequence] + consequences}
            
            # No additional consequences
            return {"messages": msgs, "consequences": consequences}
        except Exception as e:
            self.logger.error(f"[_build_state_consequences] Error: {e}", exc_info=True)
            return {"messages": msgs, "consequences": consequences}

    # ==================== GUARDED BUILDERS (prevent post-death loops) ====================

    def _guarded_build_popup_consequence(self, hazard_id: str, new_state: str, popup_title: str, 
                                        popup_msg: str, qte_entry: Optional[dict], pause: bool, 
                                        next_state: Optional[str]) -> dict:
        """Build popup consequence with game-over guard."""
        try:
            if self._is_game_over():
                self.logger.info(f"[_guarded_build_popup_consequence] Game over detected; suppressing deferred actions for '{hazard_id}'")
                return {
                    "type": "show_popup",
                    "title": popup_title or "Notice",
                    "message": popup_msg or "",
                    "output_panel": True,
                }
            return self._build_popup_consequence(hazard_id, new_state, popup_title, popup_msg, qte_entry, pause, next_state)
        except Exception as e:
            self.logger.error(f"[_guarded_build_popup_consequence] Error: {e}", exc_info=True)
            return {"type": "show_popup", "title": "Error", "message": "An error occurred."}

    def _guarded_build_immediate_qte_consequence(self, hazard_id: str, qte_entry: dict) -> dict:
        """Build immediate QTE consequence with game-over guard."""
        try:
            if self._is_game_over():
                self.logger.info(f"[_guarded_build_immediate_qte_consequence] Game over detected; suppressing QTE for '{hazard_id}'")
                return {}
            return self._build_immediate_qte_consequence(hazard_id, qte_entry)
        except Exception as e:
            self.logger.error(f"[_guarded_build_immediate_qte_consequence] Error: {e}", exc_info=True)
            return {}

    def _guarded_build_auto_advance_consequence(self, hazard_id: str, next_state: str) -> dict:
        """Build auto-advance consequence with game-over guard."""
        try:
            if self._is_game_over():
                self.logger.info(f"[_guarded_build_auto_advance_consequence] Game over detected; suppressing auto-advance for '{hazard_id}'")
                return {}
            return self._build_auto_advance_consequence(hazard_id, next_state)
        except Exception as e:
            self.logger.error(f"[_guarded_build_auto_advance_consequence] Error: {e}", exc_info=True)
            return {}

    def _handle_timed_transition(self, hazard_id: str, target_state: str):
        """Handle timed state transitions by notifying GameLogic"""
        if self.game_logic:
            result = self.set_hazard_state(hazard_id, target_state)
            # Let GameLogic handle the consequences
            for consequence in result.get("consequences", []):
                self.game_logic.handle_hazard_consequence(consequence)

    def _find_targetable_hazard_in_room(self, room_name: str, self_id: str, interaction_rule: dict) -> Optional[dict]:
        """Finds another hazard in the same room that can be influenced."""
        potential_targets = []
        valid_target_types = {i.get('if_target_is') for i in interaction_rule.get('interactions', [])}

        for hazard_id, hazard in self.active_hazards.items():
            # A hazard cannot influence itself, and must be in the same room.
            if hazard_id == self_id or hazard.get('location') != room_name:
                continue
            
            # Check if the hazard is one of the types we can influence.
            if hazard.get('type') in valid_target_types:
                potential_targets.append(hazard)

        if potential_targets:
            return random.choice(potential_targets)
        
        return None

    def set_hazard_state_by_type(self, room_name: str, hazard_type: str, new_state: str, suppress_entry_effects: bool = False) -> list:
        """Set state for the hazard of a given type at a specific room. Returns UI events."""
        hid = self.get_hazard_instance_id_by_type(room_name, hazard_type)
        if not hid:
            self.logger.warning(f"[set_hazard_state_by_type] No '{hazard_type}' hazard found at '{room_name}'.")
            return []
        
        # Return the UI events from set_hazard_state
        return self.set_hazard_state(hid, new_state, suppress_entry_effects=suppress_entry_effects)

    def get_hazard_instance_id_by_type(self, room_name: str, hazard_type: str) -> Optional[str]:
        """Return the hazard instance id for the given type in the given room, if any."""
        try:
            ht = (hazard_type or "").strip().lower()
            rn = (room_name or "").strip()
        except Exception:
            ht = hazard_type
            rn = room_name
        for hid, inst in (self.active_hazards or {}).items():
            if inst.get('location') == rn and (inst.get('type') or '').lower() == ht:
                return hid
        return None
    
    def _maybe_run_special_action(self, sdef: dict, hazard_id: str) -> list:
        """
        Dispatch on_state_entry_special_action to canonical handlers.
        Returns a list of consequences generated by the special action.
        """
        consequences = []
        if not self.game_logic:
            return consequences
        action = sdef.get('on_state_entry_special_action')
        if not action:
            return consequences

        self.logger.info(f"Executing special action '{action}' for hazard '{hazard_id}'")

        if action == 'trigger_level_transition':
            if self.game_logic.qte_engine:
                self.game_logic.qte_engine._force_qte_cleanup()
            
            self.game_logic.is_transitioning = True
            self.game_logic.player['level_complete_flag'] = True
            
            lcd = self.game_logic.get_level_completion_data()
            
            # Find the specific completion narrative from the level requirements
            level_reqs = self.resource_manager.get_data('level_requirements', {})
            level_cfg = level_reqs.get(str(self.game_logic.player['current_level']), {})
            final_state_key = hazard_id.split('#')[0] + '#' + sdef.get('__state_name__', 'unknown')
            narrative = (level_cfg.get('completion_narratives_by_state', {}).get(sdef.get('__state_name__'))
                            or lcd.get('narrative'))

            self.game_logic.add_ui_event({
                "event_type": "level_complete", "priority": 500,
                "narrative": narrative,
                **lcd
            })
            self.logger.info("[special] trigger_level_transition emitted level_complete UI event.")

        # MRI: lock doors
        if action == 'mri_lock_doors_and_initiate_qtes':
            # Legacy-compatible door lock (sets room_data.locked + locked_by_mri)
            doors_to_lock = sdef.get("doors_to_lock", [])
            locked = 0
            for rule in doors_to_lock:
                target = rule.get("target")
                if not target: continue
                room_data = self.game_logic.current_level_rooms_world_state.get(target)
                if not room_data: 
                    self.logger.warning(f"MRI lock: target room '{target}' not found")
                    continue
                if "locked_by_mri" not in room_data:
                    room_data["original_locked_state"] = bool(room_data.get("locked"))
                room_data["locked"] = True
                room_data["locked_by_mri"] = True
                locked += 1
            if locked:
                # Tell UI to refresh map immediately
                self.game_logic.add_ui_event({"event_type": "refresh_map"})

        # MRI: unlock doors
        if action == 'mri_unlock_doors_and_release_items':
            restored = 0
            for rid, rdata in self.game_logic.current_level_rooms_world_state.items():
                if rdata.get("locked_by_mri"):
                    orig = bool(rdata.get("original_locked_state", False))
                    rdata["locked"] = orig
                    rdata.pop("locked_by_mri", None)
                    rdata.pop("original_locked_state", None)
                    restored += 1
            if restored:
                self.game_logic.add_ui_event({"event_type": "refresh_map"})


        elif hasattr(self, action):
            try:
                getattr(self, action)(sdef)
            except Exception as e:
                self.logger.error(f"[special] Failed to invoke '{action}': {e}", exc_info=True)

        return consequences



    def _action_mri_lock_doors(self, hazard_id: str, state_info: dict, consequences: list):
        """Locks doors defined in the hazard state's door lock configuration."""
        self.logger.info(f"[_action_mri_lock_doors] Executing for hazard '{hazard_id}'")
        
        if not self.game_logic:
            self.logger.error("[_action_mri_lock_doors] game_logic not set")
            return
        
        # Get doors to lock from state definition
        doors_to_lock = state_info.get("doors_to_lock", [
            {"room": "MRI Scan Room", "exit": "west", "target": "MRI Control Room"},
            {"room": "MRI Scan Room", "exit": "south", "target": "Stairwell"}
        ])
        
        locked_count = 0
        for lock_rule in doors_to_lock:
            room_name = lock_rule.get("room")
            target_room = lock_rule.get("target")
            
            if not (room_name and target_room):
                continue
            
            # Get target room data from world state
            target_data = self.game_logic.current_level_rooms_world_state.get(target_room)
            if not target_data:
                self.logger.warning(f"[_action_mri_lock_doors] Target room '{target_room}' not found")
                continue
            
            # Store original lock state before modifying
            if "locked_by_mri" not in target_data:
                target_data["original_locked_state"] = target_data.get("locked", False)
            
            # Lock the room
            target_data["locked"] = True
            target_data["locked_by_mri"] = True
            locked_count += 1
            
            self.logger.info(f"[_action_mri_lock_doors] Locked '{target_room}' (from '{room_name}')")
        
        if locked_count > 0:
            consequences.append({
                "type": "show_popup",
                "title": "Doors Sealed!",
                "message": f"The magnetic field seals {locked_count} door{'s' if locked_count > 1 else ''} shut with a deafening BANG!",
                "output_panel": True
            })

    def _action_mri_unlock_doors(self, hazard_id: str, state_info: dict, consequences: list):
        """Unlocks doors that were locked by the MRI hazard."""
        self.logger.info(f"[_action_mri_unlock_doors] Executing for hazard '{hazard_id}'")
        
        if not self.game_logic:
            self.logger.error("[_action_mri_unlock_doors] game_logic not set")
            return
        
        # Find all rooms locked by MRI and restore their original state
        unlocked_count = 0
        for room_id, room_data in self.game_logic.current_level_rooms_world_state.items():
            if room_data.get("locked_by_mri"):
                # Restore original lock state
                original = room_data.get("original_locked_state", False)
                room_data["locked"] = original
                room_data.pop("locked_by_mri", None)
                room_data.pop("original_locked_state", None)
                unlocked_count += 1
                self.logger.info(f"[_action_mri_unlock_doors] Unlocked '{room_id}'")
        
        if unlocked_count > 0:
            consequences.append({
                "type": "show_popup",
                "title": "Magnetic Field Collapsed",
                "message": "The doors are no longer sealed by the magnetic field!",
                "output_panel": True
            })

    def _process_state_entry_rewards(self, sdef):
        """Award items, achievements, and score bonuses on state entry."""
        try:
            rewards = sdef.get('on_state_entry_rewards', {}) or {}

            # Grant items
            items = rewards.get('items_granted', [])
            for item_id in items:
                if self.game_logic:
                    item_data = (self.game_logic.resource_manager.get_data('items', {}) or {}).get(item_id, {"name": item_id})
                    self.game_logic.player.setdefault('inventory', {})
                    self.game_logic.player['inventory'][item_id] = item_data
                    self.logger.info(f"Awarded item '{item_id}' to player.")

            # Unlock achievements
            achievements = rewards.get('achievements_to_unlock', [])
            for ach_id in achievements:
                if hasattr(self.game_logic, 'achievements_system'):
                    ok = self.game_logic.achievements_system.unlock(ach_id)
                    if ok:
                        self.logger.info(f"Unlocked achievement '{ach_id}'.")
                    else:
                        self.logger.warning(f"Achievement '{ach_id}' not unlocked (missing or already unlocked).")

            # Add score bonus
            score_bonus = rewards.get('score_bonus', 0)
            if score_bonus:
                self.game_logic.player['score'] = self.game_logic.player.get('score', 0) + score_bonus
                self.logger.info(f"Added score bonus: {score_bonus}")
        except Exception as e:
            self.logger.error(f"_process_state_entry_rewards error: {e}", exc_info=True)

    def _maybe_progress_on_flags(self, hazard_id: str) -> list:
        """Check current state progression_condition.requires_all_flags; if met, advance and RETURN consequences."""
        hazard = self.active_hazards.get(hazard_id)
        if not hazard:
            return []
        hdef = hazard.get('master_data', {}) or {}
        states = hdef.get('states', {}) or {}
        cur_state = hazard.get('state')
        sdef = states.get(cur_state, {}) or {}
        prog = sdef.get('progression_condition') or {}
        req_flags = set(prog.get('requires_all_flags', []))
        if not req_flags:
            return []

        if not self.game_logic:
            self.logger.warning("_maybe_progress_on_flags: game_logic missing.")
            return []

        if not req_flags.issubset(self.game_logic.interaction_flags):
            return []

        # Progress
        next_state = sdef.get('next_state')
        if not next_state:
            return []
        self.logger.info("Hazard progressing due to player flags.")
        try:
            result = self.set_hazard_state(hazard_id, next_state)
            return result.get("consequences", [])
        except Exception as e:
            self.logger.error(f"_maybe_progress_on_flags: failed to set state '{next_state}' for '{hazard_id}': {e}", exc_info=True)
            return []

    # --- Helpers for process_player_interaction ---

    def _norm_text(self, s: str) -> str:
        try:
            return self.game_logic._norm(s)
        except Exception:
            return str(s).strip().lower().replace('_', ' ')

    def _synonyms_for(self, name: str, items_master: dict) -> Set[str]:
        """Build alias/synonym set for a typed target using items.json"""
        norm = self._norm_text
        syns = {norm(name)}
        for key, data in items_master.items():
            names = {norm(key), norm(data.get('name', key))}
            aliases = {norm(a) for a in (data.get('aliases') or [])}
            if norm(name) in names or norm(name) in aliases:
                syns |= Union[names, aliases]
        return syns

    def _collect_rules_for_hazard(self, h_master: dict, verb: str) -> List[dict]:
        """Merge player_interaction[verb] with triggered_by_room_action rules for same verb."""
        pi_rules = (h_master.get('player_interaction', {}) or {}).get(verb, [])
        tra_rules = [
            r for r in (h_master.get('triggered_by_room_action', []) or [])
            if isinstance(r, dict) and r.get('action_verb') == verb
        ]
        return list(pi_rules) + tra_rules

    def _rule_matches(self, rule: dict, current_state: str, target_syns: Set[str]) -> bool:
        """Check required state and target names against synonyms."""
        norm = self._norm_text
        valid_targets = rule.get('on_target_name', [])
        if not isinstance(valid_targets, list):
            valid_targets = [valid_targets]
        valid_targets_norm = {norm(v) for v in valid_targets if isinstance(v, str)}
        required_states = rule.get('requires_hazard_state')

        if required_states and current_state not in required_states:
            return False
        if valid_targets_norm and target_syns.isdisjoint(valid_targets_norm):
            return False
        return True

    def _apply_rule_side_effects(self, hazard_id: str, rule: dict) -> Tuple[list, list, bool]:
        """
        Apply flags, popup, state changes, QTEs, and messages for a single rule.
        Returns (consequences, messages, blocks_action_for_rule).
        """
        consequences: list = []
        messages: list = []
        blocks_action = bool(rule.get('blocks_action_success'))
        norm = self._norm_text

        # Flags
        if 'set_player_flag' in rule:
            flag = rule['set_player_flag']
            self.logger.debug(f"[process_player_interaction] set_player_flag: {flag}")
            self.game_logic.set_player_flag(flag, True)

        if 'sets_interaction_flag' in rule:
            flag = rule['sets_interaction_flag']
            self.logger.debug(f"[process_player_interaction] sets_interaction_flag: {flag}")
            self.game_logic.set_interaction_flag(flag)

        # Popup
        popup_event = rule.get('ui_popup_event')
        if popup_event and self.game_logic:
            popup_cmd = {
                "event_type": popup_event.get('type', 'show_popup'),
                "title": popup_event.get('title', 'Alert'),
                "message": popup_event.get('message', ''),
                "takes_turn": popup_event.get('takes_turn', False)
            }
            self.game_logic.add_ui_event(popup_cmd)

        # State change via rule
        effect = rule.get('effect_on_self') or {}
        next_state = effect.get('target_state') or rule.get('target_state')
        if next_state:
            self.logger.debug(f"[process_player_interaction] Setting hazard '{hazard_id}' state -> '{next_state}' from rule")
            try:
                result = self.set_hazard_state(hazard_id, next_state)
                consequences.extend(result.get("consequences", []))
            except Exception as e:
                self.logger.error(f"[process_player_interaction] Failed to set state '{next_state}' for '{hazard_id}': {e}")

        # Optional direct QTE trigger (legacy rules)
        if 'qte_to_trigger' in rule:
            self.logger.info(f"[process_player_interaction] QTE trigger found in rule for hazard '{hazard_id}'.")
            if self.game_logic and hasattr(self.game_logic, 'qte_engine'):
                qte_type = rule['qte_to_trigger']
                qte_context = rule.get('qte_context', {}).copy() if isinstance(rule.get('qte_context', {}), dict) else {}
                qte_context['qte_source_hazard_id'] = hazard_id
                self.logger.debug(f"[process_player_interaction] Calling QTE Engine to start '{qte_type}' with context: {qte_context}")
                try:
                    self.game_logic.qte_engine.start_qte(qte_type, qte_context)
                    self.logger.info(f"[process_player_interaction] QTE '{qte_type}' started successfully.")
                except Exception as e:
                    self.logger.error(f"[process_player_interaction] Exception while starting QTE '{qte_type}': {e}")
            else:
                self.logger.error("[process_player_interaction] HazardEngine cannot trigger QTE: game_logic.qte_engine not found!")

        # Message
        if 'message' in rule:
            try:
                colored_message = color_text(rule['message'], 'info', self.resource_manager)
            except Exception:
                colored_message = rule['message']
            messages.append(colored_message)

        return consequences, messages, blocks_action

    # --- NEW: The Observer Method ---

    def process_player_interaction(self, verb: str, target: str) -> dict:
        """
        Process player interactions and return structured consequences.
        Checks active hazards to see if the player's action triggers any special
        interactions, messages, or flags. Applies all matching rules and forwards
        consequences, including those from flag progression paths.
        PATCH: Skips hazards in terminal/empty states.
        """
        self.logger.debug(f"[process_player_interaction] Called with verb='{verb}', target='{target}'")
        consequences: list = []
        messages: list = []
        matched_rules: list = []
        if not self.game_logic:
            self.logger.warning("[process_player_interaction] Game logic not set. Cannot process player interaction.")
            return {"consequences": consequences, "messages": messages, "blocks_action": False}

        player_location = self.game_logic.player.get('location')
        items_master = self.resource_manager.get_data('items', {})
        target_syns = self._synonyms_for(target, items_master)

        self.logger.debug(f"[process_player_interaction] Player location: {player_location}")
        for hazard_id, hazard_data in self.active_hazards.items():
            if hazard_data.get('location') != player_location:
                continue
            hazard_def = hazard_data.get('master_data', {})
            current_state = hazard_data.get('state')

            # PATCH: Skip interaction if hazard is in a terminal/empty state
            state_def = (hazard_def.get('states') or {}).get(current_state, {})
            if state_def.get('is_terminal_state') or current_state in ['empty', 'destroyed', 'removed']:
                continue

            h_master = hazard_def or {}
            all_rules = self._collect_rules_for_hazard(h_master, verb)
            self.logger.debug(f"[process_player_interaction] Found {len(all_rules)} rules for verb '{verb}'")

            for rule_idx, rule in enumerate(all_rules):
                self.logger.debug(f"[process_player_interaction] Evaluating rule #{rule_idx}: {rule}")
                if not self._rule_matches(rule, current_state, target_syns):
                    continue

                matched_rules.append(rule)
                hazard_data['started_by_player'] = True

                # Apply all side effects for this rule
                rule_cons, rule_msgs, _ = self._apply_rule_side_effects(hazard_id, rule)
                if rule_cons:
                    consequences.extend(rule_cons)
                if rule_msgs:
                    messages.extend(rule_msgs)

                # After each matched rule, we may progress by flags; append consequences
                progressed_cons = self._maybe_progress_on_flags(hazard_id)
                if progressed_cons:
                    consequences.extend(progressed_cons)

        # SAFETY NET: run flag progression once more after rules to catch pure-flag paths
        try:
            player_location = self.game_logic.player.get('location')
            for hid, hz in self.active_hazards.items():
                if hz.get('location') == player_location:
                    extra_cons = self._maybe_progress_on_flags(hid)
                    if extra_cons:
                        consequences.extend(extra_cons)
        except Exception as e:
            self.logger.error(f"[process_player_interaction] post-flag progression failed: {e}", exc_info=True)

        self.logger.debug(f"[process_player_interaction] Player interaction complete. Messages: {messages}")
        return {
            "consequences": consequences,
            "messages": messages,
            "blocks_action": any(rule.get('blocks_action_success') for rule in matched_rules)
        }

    def get_active_hazards_for_room(self, room_name: str) -> list:
        """
        Returns a list of hazard types for all active hazards in a given room.
        Enhanced with robust logging and debugging.
        """
        self.logger.debug(f"[get_active_hazards_for_room] Called for room: '{room_name}'")
        hazards_in_room = [
            h['type'] for h in self.active_hazards.values()
            if h.get('location') == room_name
        ]
        self.logger.info(f"[get_active_hazards_for_room] Found hazards in '{room_name}': {hazards_in_room}")
        return hazards_in_room

    def get_hazard_state(self, hazard_key: str, room_name: str) -> Optional[str]:
        """
        Finds an active hazard of a given type in a room and returns its current state.
        Enhanced with robust logging and debugging.
        """
        self.logger.debug(f"[get_hazard_state] Called for hazard_key='{hazard_key}', room_name='{room_name}'")
        for hazard_id, hazard in self.active_hazards.items():
            self.logger.debug(f"[get_hazard_state] Checking hazard '{hazard_id}' (type='{hazard.get('type')}', location='{hazard.get('location')}')")
            if hazard.get('type') == hazard_key and hazard.get('location') == room_name:
                state = hazard.get('state')
                self.logger.info(f"[get_hazard_state] Found hazard '{hazard_key}' in '{room_name}' with state '{state}'")
                return state
        self.logger.warning(f"[get_hazard_state] No active hazard '{hazard_key}' found in room '{room_name}'")
        return None

    def _check_icu_examination_flags(self, hazard: dict):
        """
        A specific autonomous action for the ventilator hazard. Checks if both
        required flags have been set.
        """
        self.logger.debug("Checking ICU examination flags for hazard progression.")
        if not self.game_logic:
            self.logger.warning("Game logic not set. Cannot check ICU examination flags.")
            return

        required_flags = {'patient_examined_icu_bay', 'ventilator_examined_icu_bay'}
        self.logger.debug(f"Required flags: {required_flags}, current flags: {self.game_logic.interaction_flags}")
        if required_flags.issubset(self.game_logic.interaction_flags):
            self.logger.info("Ventilator hazard progressing due to player examination.")
            hazard['state'] = 'erratic_hiss'  # Or whatever the next state is
            self.logger.debug(f"Hazard state updated to 'erratic_hiss' for hazard: {hazard}")
            # We would also append a message about the change here.

    def _process_autonomous_actions(self, hazard_id, hazard_data):
        """Processes any autonomous actions for a hazard's current state, with robust logging and debugging."""
        self.logger.debug(f"[_process_autonomous_actions] Called for hazard_id='{hazard_id}'")
        state_key = hazard_data.get('state')
        self.logger.debug(f"[_process_autonomous_actions] Current state: '{state_key}'")
        state_info = hazard_data.get('master_data', {}).get('states', {}).get(state_key)

        if not state_info:
            self.logger.warning(f"[_process_autonomous_actions] No state info found for state '{state_key}' in hazard '{hazard_id}'")
            return

        action_name = state_info.get('autonomous_action')
        self.logger.debug(f"[_process_autonomous_actions] Autonomous action: '{action_name}'")

        if action_name:
            # Switchboard for all autonomous actions
            if action_name == '_find_and_launch_projectile_qte':
                self.logger.info(f"[_process_autonomous_actions] Executing '_find_and_launch_projectile_qte' for hazard '{hazard_id}'")
                try:
                    self._action_find_and_launch_projectile(hazard_id, state_info)
                except Exception as e:
                    self.logger.error(f"[_process_autonomous_actions] Exception in '_action_find_and_launch_projectile': {e}", exc_info=True)
            else:
                self.logger.debug(f"[_process_autonomous_actions] Unknown autonomous action '{action_name}' for hazard '{hazard_id}'")
        else:
            self.logger.debug(f"[_process_autonomous_actions] No autonomous action defined for state '{state_key}' in hazard '{hazard_id}'")

    def _action_find_and_launch_projectile(self, hazard_id, state_info):
        """
        Finds a metallic object and launches it at the player via a QTE.
        Enhanced with robust logging and debugging.
        """
        self.logger.debug(f"[_action_find_and_launch_projectile] Called for hazard_id='{hazard_id}'")
        if not self.game_logic:
            self.logger.error("[_action_find_and_launch_projectile] game_logic not set; cannot proceed.")
            return

        in_danger_zone = self.game_logic.get_player_flag('in_mri_danger_zone')
        self.logger.debug(f"[_action_find_and_launch_projectile] Player in danger zone: {in_danger_zone}")
        if not in_danger_zone:
            self.logger.info("[_action_find_and_launch_projectile] Player is not in the danger zone. Projectile will not launch.")
            return

        context = state_info.get('qte_stage_context', {})
        rooms_to_search = context.get('pull_from_rooms', [])
        weight_cats = context.get('pull_weight_categories', [])
        self.logger.info(f"[_action_find_and_launch_projectile] Searching for projectiles in rooms: {rooms_to_search} with weight categories: {weight_cats}")

        potential_projectiles = []
        for room_id in rooms_to_search:
            try:
                items_in_room = self.game_logic.get_items_in_room(room_id)
                self.logger.debug(f"[_action_find_and_launch_projectile] Items in room '{room_id}': {items_in_room}")
            except Exception as e:
                self.logger.error(f"[_action_find_and_launch_projectile] Failed to get items in room '{room_id}': {e}", exc_info=True)
                continue

            for item in items_in_room:
                try:
                    item_master_data = self.game_logic._get_item_master_data(item['id'])
                    is_metallic = item_master_data.get('is_metallic')
                    weight = item_master_data.get('weight')
                    self.logger.debug(f"[_action_find_and_launch_projectile] Checking item '{item['id']}': is_metallic={is_metallic}, weight={weight}")
                    if is_metallic and weight in weight_cats:
                        potential_projectiles.append(item)
                        self.logger.debug(f"[_action_find_and_launch_projectile] Added projectile candidate: {item}")
                except Exception as e:
                    self.logger.error(f"[_action_find_and_launch_projectile] Error processing item '{item}': {e}", exc_info=True)

        if not potential_projectiles:
            self.logger.info("[_action_find_and_launch_projectile] No more projectiles found for this stage.")
            next_state = state_info.get('next_state_if_no_projectiles')
            if next_state:
                self.logger.info(f"[_action_find_and_launch_projectile] Transitioning hazard '{hazard_id}' to next state '{next_state}' due to no projectiles.")
                try:
                    self.set_hazard_state(hazard_id, next_state)
                except Exception as e:
                    self.logger.error(f"[_action_find_and_launch_projectile] Failed to set hazard state '{next_state}' for '{hazard_id}': {e}", exc_info=True)
            return

        # A projectile was found. Pick one and launch it.
        projectile_to_launch = random.choice(potential_projectiles)
        projectile_key = projectile_to_launch['id']
        try:
            projectile_name = self.game_logic._get_item_display_name(projectile_key)
        except Exception as e:
            self.logger.error(f"[_action_find_and_launch_projectile] Failed to get display name for projectile '{projectile_key}': {e}", exc_info=True)
            projectile_name = projectile_key

        self.logger.info(f"[_action_find_and_launch_projectile] Launching projectile: {projectile_name} ({projectile_key})")

        # Trigger the QTE defined in the hazard state
        qte_info = state_info.get('triggers_qte_on_entry', {})
        qte_type = qte_info.get('qte_to_trigger')
        self.logger.debug(f"[_action_find_and_launch_projectile] QTE info: {qte_info}, qte_type: {qte_type}")

        if qte_type and getattr(self.game_logic, 'qte_engine', None):
            try:
                qte_context = dict(qte_info.get('qte_context', {}))
                qte_context['ui_prompt_message'] = f"A {projectile_name} is pulled through the window and flies at your head! DODGE!"
                qte_context['expected_input_word'] = qte_context.get('expected_input_word', 'dodge')
                qte_context['next_state_on_qte_success'] = state_info.get('next_state_on_qte_success')
                qte_context['next_state_on_qte_failure'] = state_info.get('next_state_on_qte_failure')
                qte_context['qte_source_hazard_id'] = hazard_id
                qte_context['projectile_item_id'] = projectile_key

                self.logger.info(f"[_action_find_and_launch_projectile] Starting QTE '{qte_type}' with context: {qte_context}")
                self.game_logic.qte_engine.start_qte(qte_type, qte_context)
            except Exception as e:
                self.logger.error(f"[_action_find_and_launch_projectile] Exception while starting QTE '{qte_type}' for projectile '{projectile_key}': {e}", exc_info=True)
            # Remove the item from the world so it can't be launched again
            try:
                self.logger.info(f"[_action_find_and_launch_projectile] Removing projectile '{projectile_key}' from world.")
                self.game_logic.remove_item_from_world(projectile_key)
            except Exception as e:
                self.logger.error(f"[_action_find_and_launch_projectile] Failed to remove projectile '{projectile_key}' from world: {e}", exc_info=True)
        else:
            self.logger.error(f"[_action_find_and_launch_projectile] Could not trigger QTE for projectile '{projectile_key}'. QTE info missing or engine not found.")

    def get_save_state(self) -> dict:
        """Get the current state for saving."""
        return {
            "active_hazards": self.active_hazards.copy(),
            "escalation_level": getattr(self, 'escalation_level', 0),
            "room_hazard_counters": getattr(self, 'room_hazard_counters', {}),
            "global_flags": getattr(self, 'global_flags', {})
        }
    
    def load_save_state(self, state_data: dict):
        """Restore state from save data."""
        try:
            self.active_hazards = state_data.get("active_hazards", {})
            if hasattr(self, 'escalation_level'):
                self.escalation_level = state_data.get("escalation_level", 0)
            if hasattr(self, 'room_hazard_counters'):
                self.room_hazard_counters = state_data.get("room_hazard_counters", {})
            if hasattr(self, 'global_flags'):
                self.global_flags = state_data.get("global_flags", {})
            
            self.logger.info("Hazard engine state restored from save")
        except Exception as e:
            self.logger.error(f"Failed to restore hazard engine state: {e}", exc_info=True)
        
    def _synonyms_for(self, name: str, items_master: dict) -> Set[str]:
        """Build alias/synonym set for a typed target using items.json"""
        norm = self._norm_text
        syns = {norm(name)}
        for key, data in items_master.items():
            names = {norm(key), norm(data.get('name', key))}
            aliases = {norm(a) for a in (data.get('aliases') or [])}
            if norm(name) in names or norm(name) in aliases:
                # Use update() to avoid accidental replacement with typing.Union
                syns.update(names)
                syns.update(aliases)
        return syns


    def _get_next_state_for(self, hazard_inst: dict) -> str | None:
        """Return configured next_state for a hazard instance, if any."""
        try:
            current_state = hazard_inst.get("state")
            sdef = self._resolve_state_def(hazard_inst, current_state)
            return sdef.get("next_state")
        except Exception:
            return None

    def _influence_hazards_in_room(self, source_hazard_id: str):
        """
        Death's Breath aura: occasionally nudges other hazards in the same room
        to their next_state based on its current intensity/state.
        """
        src = self.active_hazards.get(source_hazard_id)
        if not src or src.get("type") != "deaths_breath":
            return

        room = src.get("location")
        state = src.get("state", "subtle_chill")

        # Intensity mapping: higher state => stronger effect
        intensity = {
            "subtle_chill": 0.05,
            "cold_breeze": 0.10,
            "icy_presence": 0.18,
            "malevolent_gust": 0.30,
        }.get(state, 0.08)

        for hid, inst in list(self.active_hazards.items()):
            if hid == source_hazard_id:
                continue
            if inst.get("location") != room:
                continue

            # Skip terminal/safe states (we won't re-awaken safe_exit_ending etc.)
            next_state = self._get_next_state_for(inst)
            if not next_state:
                continue

            import random as _r
            if _r.random() < intensity:
                self.logger.info(f"[Death's Breath] Nudging '{hid}' in '{room}' -> next_state '{next_state}' (from '{inst.get('state')}')")
                try:
                    result = self.set_hazard_state(hid, next_state)
                    # NEW: immediately forward consequences so QTEs actually start
                    if result and self.game_logic:
                        for cons in result.get('consequences', []):
                            try:
                                self.game_logic.handle_hazard_consequence(cons)
                            except Exception as e:
                                self.logger.error(f"[Death's Breath] Failed to handle consequence {cons}: {e}", exc_info=True)
                        for msg in result.get('messages', []):
                            self.game_logic.add_ui_event({"event_type": "show_message", "message": msg})
                except Exception as e:
                    self.logger.error(f"[Death's Breath] Failed to nudge '{hid}' to '{next_state}': {e}", exc_info=True)
