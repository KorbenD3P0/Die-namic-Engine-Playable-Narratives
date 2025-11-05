# fd_terminal/game_logic.py
import logging
from typing import Tuple
from typing import Set, Tuple
from typing import Union, Set, Tuple
from typing import List, Set, Tuple
from typing import Optional
import copy
import random
import re
import os
import math
import string
from .resource_manager import ResourceManager
from .hazard_engine import HazardEngine
from .achievements import AchievementsSystem
from .death_ai import DeathAI
from .qte_engine import QTE_Engine
from .utils import color_text 

HIDDEN_ROOM_LIST_BY_HAZARD = {
    "deaths_breath": {"cold breeze", "sudden draft", "chilling air"}
}

class GameLogic:
    """
    The Loom of Fate. This is the Model.
    It holds the entire state of the game world and enforces its rules.
    """
    def __init__(self, resource_manager: ResourceManager):
        self.resource_manager = resource_manager
        self.logger = logging.getLogger("GameLogic")
        
        # Core systems will be injected after creation to prevent circular dependencies
        self.hazard_engine: HazardEngine = None
        self.achievements_system: AchievementsSystem = None
        self.death_ai: DeathAI = None
        self.qte_engine: 'QTE_Engine' = None 
        self.interaction_flags = set()
        self.player = {}
        self.current_level_rooms_world_state = {}
        self.current_level_items_world_state = {}
        self.is_game_over = False
        self.game_won = False
        self.ui_events = []
        self.last_dialogue_context = {}  # tracks active NPC and options
        self.set_player_flag("has_initialized", True)
        # The Command Map: A clean way to route player commands to the correct methods.
        self.command_map = {
            'move': self._command_move,
            'go': self._command_move,
            'run': self._command_move,
            'walk': self._command_move,
            'north': lambda _: self._command_move('north'),
            'south': lambda _: self._command_move('south'),
            'east': lambda _: self._command_move('east'),
            'west': lambda _: self._command_move('west'),
            'up': lambda _: self._command_move('up'),
            'down': lambda _: self._command_move('down'),
            'n': lambda _: self._command_move('north'),
            's': lambda _: self._command_move('south'),
            'e': lambda _: self._command_move('east'),
            'w': lambda _: self._command_move('west'),
            'u': lambda _: self._command_move('up'),
            'd': lambda _: self._command_move('down'),
            'examine': self._command_examine,
            'look': self._command_examine,
            'inspect': self._command_examine,
            'take': self._command_take,
            'get': self._command_take,
            'grab': self._command_take,
            'talk': self._command_talk,
            'speak': self._command_talk,
            'respond': self._command_respond,
            'use': self._command_use,
            "unlock" : self._command_unlock,
            'search': self._command_search,
            'inventory': self._command_inventory,
            'inv': self._command_inventory,
            'wait': self._command_wait,
            'rest': self._command_wait,
            'help': self._command_help,
            'test_qte': self._command_test_qte,
            'map': self._command_map,
            'force': self._command_force,
            'break': self._command_break,
            'set_qte_sr': self._command_set_qte_sr,
            'save': self._command_save,
            'load': self._command_load,
            'quicksave': lambda _: self._command_save('quicksave'),
            'quickload': lambda _: self._command_load('quicksave'),
            'main_menu': self._command_main_menu,
            'debug_room': self._command_debug_room,  # Add debug command

            # We will add 'take', 'use', 'search' etc. here later.
        }
        self.logger.info("GameLogic instance created with a lean, focused design.")

    def _initialize_level_data(self, level_id: int):
        """Orchestrates the complete setup of a new level's world state. Injected with robust debugging logic."""
        self.logger.info(f"_initialize_level_data: Executing Rite of Genesis for Level {level_id}...")

        # Step 1: Forge the Rooms
        all_rooms = self.resource_manager.get_data('rooms', {})
        self.logger.debug(f"_initialize_level_data: Loaded all_rooms keys: {list(all_rooms.keys())}")
        master_level_rooms = all_rooms.get(str(level_id))
        if not master_level_rooms:
            self.logger.error(f"_initialize_level_data: No room data found for level {level_id}.")
            raise ValueError(f"No room data found for level {level_id}.")
        self.current_level_rooms_world_state = copy.deepcopy(master_level_rooms)
        
        # --- NEW: Build the coordinate map for this level ---
        entry_room = self.resource_manager.get_data('level_requirements', {}).get(str(level_id), {}).get('entry_room')
        if entry_room:
            self._build_room_coordinate_map(entry_room)
        self.logger.info(f"_initialize_level_data: Step 1: Forged {len(self.current_level_rooms_world_state)} rooms.")

        # Step 2 & 3: Place all items, both static and random
        self._populate_level_with_items(level_id)

        # Step 4: Awaken the Dangers
        if self.hazard_engine:
            self.logger.debug(f"_initialize_level_data: Initializing hazard engine for level {level_id}")
            self.hazard_engine.initialize_for_level(level_id)

        # Omen Library Compilation
        self.logger.debug(f"_initialize_level_data: Compiling omens for level {level_id}")
        self.current_level_omens = self._compile_level_omens(level_id)

        self.logger.info(f"_initialize_level_data: Rite of Genesis for Level {level_id} is complete.")

    # --- NEW: Item Placement Logic ---
    def _populate_level_with_items(self, level_id: int):
        """Places both static and randomly distributed items throughout the level. Injected with robust debugging logic."""
        try:
            self.logger.debug(f"_populate_level_with_items: Populating items for level {level_id}")
            self.current_level_items_world_state = {}
            items_master = self.resource_manager.get_data('items', {})
            self.logger.debug(f"_populate_level_with_items: Loaded items_master keys: {list(items_master.keys())}")

            # --- Stage A: Identify all containers in the level ---
            all_containers = []
            for room_id, room_data in self.current_level_rooms_world_state.items():
                self.logger.debug(f"_populate_level_with_items: Checking room '{room_id}' for containers")
                for furniture in room_data.get('furniture', []):
                    if isinstance(furniture, dict) and furniture.get('is_container'):
                        furniture.setdefault('items', [])
                        all_containers.append({'room': room_id, 'furniture_data': furniture})
                        self.logger.debug(f"_populate_level_with_items: Found container '{furniture.get('name')}' in room '{room_id}'")

            # PATCH: Build set of hazard-spawned entity keys to avoid placing duplicate items
            hazard_spawned_keys = set()
            if self.hazard_engine:
                hazards_master = self.resource_manager.get_data('hazards', {})
                for hazard_id, h_inst in getattr(self.hazard_engine, 'active_hazards', {}).items():
                    h_def = hazards_master.get(h_inst.get('type'), {})
                    for entity_key in h_def.get('spawn_entities', []):
                        if isinstance(entity_key, dict):
                            entity_key = entity_key.get('name', '')
                        normalized = str(entity_key).strip().lower().replace(' ', '_')
                        hazard_spawned_keys.add(normalized)
            self.logger.debug(f"_populate_level_with_items: Hazard-spawned keys to skip: {hazard_spawned_keys}")

            # --- Stage B: Compile the level's loot pool ---
            random_loot_pool = []
            for item_key, item_data in items_master.items():
                self.logger.debug(f"_populate_level_with_items: Checking item '{item_key}' for static placement")
                is_static = False
                for room_data in self.current_level_rooms_world_state.values():
                    # Check both "items" and "items_present" for backward compatibility
                    items_in_room = room_data.get('items', []) + room_data.get('items_present', [])
                    if item_key in items_in_room:
                        # PATCH: Skip if item matches a hazard-spawned entity
                        if item_key in hazard_spawned_keys:
                            self.logger.info(f"_populate_level_with_items: Skipping item '{item_key}' in '{room_data.get('name', 'UNKNOWN')}' (hazard-spawned)")
                            continue
                        self.logger.debug(f"_populate_level_with_items: Placing static item '{item_key}' in room '{room_data.get('name', 'UNKNOWN')}'")
                        self.current_level_items_world_state[item_key] = {"location": room_data.get('name')}
                        is_static = True
                        break
                if not is_static and item_data.get('is_distributable_in_containers'):
                    # PATCH: Skip if item matches a hazard-spawned entity
                    if item_key in hazard_spawned_keys:
                        self.logger.info(f"_populate_level_with_items: Skipping random loot item '{item_key}' (hazard-spawned)")
                        continue
                    random_loot_pool.append(item_key)
                    self.logger.debug(f"_populate_level_with_items: Added '{item_key}' to random loot pool")

            self.logger.info(f"_populate_level_with_items: Step 2: Placed static items. Step 3 will distribute {len(random_loot_pool)} random items.")

            # --- Stage C: Scatter the Threads of Chance ---
            random.shuffle(random_loot_pool)
            self.logger.debug(f"_populate_level_with_items: Shuffled random loot pool: {random_loot_pool}")
            for container_ref in all_containers:
                container = container_ref['furniture_data']
                capacity = container.get('capacity', 0)
                self.logger.debug(f"_populate_level_with_items: Filling container '{container.get('name')}' in room '{container_ref['room']}' with capacity {capacity}")
                while len(container['items']) < capacity and random_loot_pool:
                    item_to_place = random_loot_pool.pop()
                    container['items'].append(item_to_place)
                    self.logger.debug(f"_populate_level_with_items: Placed '{item_to_place}' in '{container.get('name')}' in room '{container_ref['room']}'")
        except Exception as e:
            self.logger.error(f"_populate_level_with_items: Error: {e}", exc_info=True)

    def _generate_intro_disaster(self) -> dict:
        """
        Selects a random disaster and generates the introductory narrative object.
        Handles both disaster and chill intro formats.
        """
        self.logger.info("_generate_intro_disaster: Generating fully detailed random introductory disaster...")

        disasters = self.resource_manager.get_data('disasters', {})
        visionaries = self.resource_manager.get_data('visionaries', {})
        survivor_fates = self.resource_manager.get_data('survivor_fates', {}).get('fates', [])

        self.logger.debug(f"_generate_intro_disaster: Loaded disasters keys: {list(disasters.keys())}")
        self.logger.debug(f"_generate_intro_disaster: Loaded visionaries keys: {list(visionaries.keys())}")
        self.logger.debug(f"_generate_intro_disaster: Loaded survivor fates: {survivor_fates}")

        if not disasters:
            self.logger.error("_generate_intro_disaster: Missing disaster data. Cannot generate intro.")
            return {"event_description": "a system error", "full_description_template": "CRITICAL ERROR: Game data is missing."}

        disaster_key = random.choice(list(disasters.keys()))
        disaster_details = disasters[disaster_key]
        self.logger.debug(f"_generate_intro_disaster: Selected disaster '{disaster_key}' with details: {disaster_details}")

        # If this is a chill intro (no warnings, no visionaries, killed_count is 0 or missing), handle accordingly
        is_chill_intro = (
            (not disaster_details.get("warnings")) and
            (not disaster_details.get("visionary")) and
            (disaster_details.get("killed_count", 0) == 0)
        )

        # Visionary
        if is_chill_intro:
            # Use a generic friend or companion for the chill intro
            visionary_desc = "your friend"
        else:
            if visionaries:
                visionary_category = random.choice(list(visionaries.keys()))
                visionary_desc = random.choice(visionaries[visionary_category])
            else:
                visionary_desc = "a mysterious figure"

        # Killed count
        killed_count_data = disaster_details.get("killed_count", 0)
        killed_count_str = ""
        if isinstance(killed_count_data, int):
            killed_count_str = str(killed_count_data)
            self.logger.debug(f"_generate_intro_disaster: killed_count is int: {killed_count_str}")
        elif isinstance(killed_count_data, dict):
            min_c = killed_count_data.get("min", 10)
            max_c = killed_count_data.get("max", 50)
            killed_count_str = str(random.randint(min_c, max_c))
            self.logger.debug(f"_generate_intro_disaster: killed_count is dict: min={min_c}, max={max_c}, selected={killed_count_str}")

        # Warnings
        warning_list = disaster_details.get("warnings", [])
        if warning_list:
            warning_selected = random.choice(warning_list)
        else:
            # For chill intro, use greeting if present, else a default
            greeting_list = disaster_details.get("greeting", [])
            if greeting_list:
                warning_selected = random.choice(greeting_list)
            else:
                warning_selected = "Ready for a movie?"

        # Survivor fate
        if is_chill_intro:
            survivor_fate_selected = ""
        else:
            survivor_fate_selected = random.choice(survivor_fates) if survivor_fates else "met a strange fate."

        intro_disaster_object = {
            "event_description": disaster_key,
            "full_description_template": disaster_details.get("description", "A terrible fate befell them all..."),
            "visionary": visionary_desc,
            "warning": warning_selected,
            "killed_count": killed_count_str,
            "survivor_fates": survivor_fate_selected
        }

        self.logger.info(f"_generate_intro_disaster: Generated disaster: '{disaster_key}' claiming '{killed_count_str}' lives.")
        self.logger.debug(f"_generate_intro_disaster: Final intro disaster object: {intro_disaster_object}")
        return intro_disaster_object

    def _compile_level_omens(self, level_id: int) -> dict:
        """
        Gathers all environmental omens from disasters, hazards, NPCs,
        and all rooms in the current level (from their environmental_omens_config blocks),
        and organizes them by trigger object.
        Injected with robust debugging logic.
        """
        self.logger.info(f"_compile_level_omens: Compiling Omen Library for level {level_id}...")
        omen_library = {}

        # Sources to search for the 'environmental_omens' key
        sources = [
            ("disasters", self.resource_manager.get_data('disasters', {})),
            ("hazards", self.resource_manager.get_data('hazards', {})),
            ("npcs", self.resource_manager.get_data('npcs', {}))
        ]

        for source_idx, (source_name, source_collection) in enumerate(sources):
            self.logger.debug(f"_compile_level_omens: Searching source '{source_name}' (index {source_idx}) with {len(source_collection)} items.")
            for item_key, item_data in source_collection.items():
                if 'environmental_omens' in item_data:
                    self.logger.debug(f"_compile_level_omens: Found 'environmental_omens' in item '{item_key}' from source '{source_name}'.")
                    for trigger, omen_text in item_data['environmental_omens'].items():
                        if trigger not in omen_library:
                            omen_library[trigger] = []
                            self.logger.debug(f"_compile_level_omens: Created new trigger '{trigger}' from source '{source_name}'.")
                        if isinstance(omen_text, list):
                            self.logger.debug(f"_compile_level_omens: Adding list of omens for trigger '{trigger}' from source '{source_name}'.")
                            omen_library[trigger].extend(omen_text)
                        else:
                            self.logger.debug(f"_compile_level_omens: Adding single omen for trigger '{trigger}' from source '{source_name}'.")
                            omen_library[trigger].append(omen_text)
                else:
                    self.logger.debug(f"_compile_level_omens: No 'environmental_omens' in item '{item_key}' from source '{source_name}'.")

        # --- NEW: Merge in omens from all rooms in the current level ---
        all_rooms = self.resource_manager.get_data('rooms', {})
        level_rooms = all_rooms.get(str(level_id), {})
        for room_id, room_data in (level_rooms or {}).items():
            env_omens_cfg = room_data.get('environmental_omens_config', {})
            if env_omens_cfg:
                self.logger.debug(f"_compile_level_omens: Found 'environmental_omens_config' in room '{room_id}'.")
                for trigger, omen_text in env_omens_cfg.items():
                    if trigger not in omen_library:
                        omen_library[trigger] = []
                        self.logger.debug(f"_compile_level_omens: Created new trigger '{trigger}' from room '{room_id}'.")
                    if isinstance(omen_text, list):
                        self.logger.debug(f"_compile_level_omens: Adding list of omens for trigger '{trigger}' from room '{room_id}'.")
                        omen_library[trigger].extend(omen_text)
                    else:
                        self.logger.debug(f"_compile_level_omens: Adding single omen for trigger '{trigger}' from room '{room_id}'.")
                        omen_library[trigger].append(omen_text)

        self.logger.info(f"_compile_level_omens: Omen Library compiled with {len(omen_library)} trigger types.")
        return omen_library

    # --- Game State Management ---

    def start_new_game(self, character_class="Journalist", start_level=1):
        self.logger.info(f"start_new_game: Starting new game with character: {character_class} on level {start_level}...")

        # --- Ensure all game state is fully reset ---
        self.is_game_over = False
        self.game_won = False
        self.ui_events = []
        self.interaction_flags = set()
        self.player = {}
        self.current_level_rooms_world_state = {}
        self.current_level_items_world_state = {}

        # Remove any lingering game over or death flags
        # (in case previous game ended with death/game over)
        # Also clear any player flags, death reason, death narrative, etc.
        # This ensures a truly clean slate.
        self.player = {}

        char_classes = self.resource_manager.get_data('character_classes', {})
        level_reqs = self.resource_manager.get_data('level_requirements', {})
        game_config = self.resource_manager.get_data('game_config', {})

        self.logger.debug(f"start_new_game: Loaded character_classes keys: {list(char_classes.keys())}")
        self.logger.debug(f"start_new_game: Loaded level_requirements keys: {list(level_reqs.keys())}")
        self.logger.debug(f"start_new_game: Loaded game_config: {game_config}")

        char_data = char_classes.get(character_class, {})
        if not char_data:
            self.logger.warning(f"start_new_game: Character class '{character_class}' not found. Using defaults.")

        level_entry_room = level_reqs.get(str(start_level), {}).get('entry_room', 'UNKNOWN_ROOM')
        self.logger.debug(f"start_new_game: Entry room for level {start_level} is '{level_entry_room}'.")

        if level_entry_room == 'UNKNOWN_ROOM':
            self.logger.error(f"start_new_game: Missing entry_room for level {start_level}")
            raise ValueError(f"Missing entry_room for level {start_level}")

        self.logger.debug("start_new_game: Initializing player dictionary...")
        self.player = {
            "location": level_entry_room,
            "inventory": [],
            "hp": char_data.get('max_hp', 30),
            "max_hp": char_data.get('max_hp', 30),
            "fear": 0.0,
            "score": 0,
            "turns_left": game_config.get('INITIAL_TURNS', 180),
            "actions_taken": 0,
            "visited_rooms": {level_entry_room},
            "current_level": start_level,
            "character_class": character_class,
            # PATCH: status_effects must be a list, not a dict
            "status_effects": [],  # was {}
            "qte_active": False,
            "qte_context": {},
            "evaded_hazards": [],
        }
        self.player['companion_location'] = 'Cineplex Lobby'
        self.logger.debug(f"start_new_game: Player initialized: {self.player}")

        self.logger.debug("start_new_game: Generating intro disaster...")
        self.player['intro_disaster'] = self._generate_intro_disaster()
        self.logger.debug(f"start_new_game: Intro disaster generated: {self.player['intro_disaster']}")

        self.logger.debug("start_new_game: Initializing level data...")
        self._initialize_level_data(start_level)
        self.logger.info(f"New game started successfully. Player is in '{self.player['location']}'.")

        initial_room_id = self.player['location']
        initial_room_data = self.get_room_data(initial_room_id) or {}
        self.logger.debug(f"start_new_game: Initial room data: {initial_room_data}")

        message = self._get_rich_room_description(initial_room_id)
        self.logger.debug(f"start_new_game: Initial room description: {message}")

        ui_events = []

        # PATCH: Always display first_entry_text if present, even on game start
        first_entry_text = initial_room_data.get('first_entry_text')
        if first_entry_text:
            self.logger.info(f"start_new_game: Adding first_entry popup for '{initial_room_id}'")
            ui_events.append(self._make_first_entry_popup_event(initial_room_id, first_entry_text))
        else:
            self.logger.debug(f"start_new_game: No first_entry_text for '{initial_room_id}'")

        self.start_response = {
            "messages": [message],
            "game_state": self.get_current_game_state(),
            "ui_events": ui_events,
            "turn_taken": False,
            "success": True
        }

        self.logger.info("start_new_game: Game initialization complete.")

    def start_next_level(self, level_id: Union[int, str], start_room: Optional[str]):
        """
        Advance to the next level while preserving persistent player stats.
        Only per-level counters and world state are reset.
        Improvements:
        - Robust type handling for level_id
        - Always preserve evaded_hazards and all persistent stats
        - Ensures entry_room fallback logic is correct
        - UI events for first entry popup are always queued
        """
        try:
            level_id = int(level_id) if level_id is not None else int(self.player.get('current_level', 1)) + 1
        except Exception:
            level_id = int(self.player.get('current_level', 1)) + 1

        # --- CLEAR PREVIOUS LEVEL COMPLETION / TRANSITION FLAGS ---
        self.player.pop('level_complete_flag', None)
        self.player.pop('notified_requirements_met', None)
        self.is_transitioning = False

        # --- Preserve persistent stats ---
        inventory       = self.player.get('inventory', [])
        hp              = self.player.get('hp', 30)
        max_hp          = self.player.get('max_hp', 30)
        fear            = self.player.get('fear', 0.0)
        score           = self.player.get('score', 0)
        character_class = self.player.get('character_class')
        flags           = self.player.get('flags', set())
        status_effects  = self.player.get('status_effects', {})
        evaded_hazards  = self.player.get('evaded_hazards', [])

        # --- Reset per-level counters ---
        game_config = self.resource_manager.get_data('game_config', {})
        initial_turns = game_config.get('INITIAL_TURNS', 180)
        self.player['turns_left'] = initial_turns
        self.player['actions_taken'] = 0
        self.player['current_level'] = level_id
        self.player['qte_active'] = False
        self.player['qte_context'] = {}

        # --- Clear per-level collections ---
        self.current_level_rooms_world_state = {}
        self.current_level_items_world_state = {}
        self.interaction_flags = set()

        # --- Rebuild the level world state ---
        self._initialize_level_data(level_id)

        # --- Determine entry room (override with explicit start_room if provided) ---
        entry_room = start_room or self.resource_manager.get_data('level_requirements', {}).get(str(level_id), {}).get('entry_room')
        if not entry_room:
            entry_room = self.player.get('location')  # fallback from initialization

        self.player['location'] = entry_room
        self.player['visited_rooms'] = {entry_room}

        # --- Restore persistent stats back onto player (after level init) ---
        self.player['inventory']       = inventory
        self.player['hp']              = min(hp, max_hp)
        self.player['max_hp']          = max_hp
        self.player['fear']            = fear
        self.player['score']           = score
        self.player['character_class'] = character_class
        self.player['flags']           = flags
        self.player['status_effects']  = status_effects
        self.player['evaded_hazards']  = evaded_hazards

        # --- REBUILD start_response for the new level ---
        initial_room_id = self.player.get('location')
        initial_room_data = self.get_room_data(initial_room_id) or {}
        main_desc = self._get_rich_room_description(initial_room_id)

        ui_events = []
        first_entry_text = initial_room_data.get('first_entry_text')
        if first_entry_text:
            ui_events.append(self._make_first_entry_popup_event(initial_room_id, first_entry_text))

        self.start_response = {
            "messages": [main_desc],
            "game_state": self.get_current_game_state(),
            "ui_events": ui_events,
            "turn_taken": False,
            "success": True
        }

        # First-entry popup for new level (also add to UI events queue for immediate display)
        if first_entry_text:
            self.add_ui_event({
                "event_type": "show_popup",
                "title": initial_room_id.replace("_", " ").title(),
                "message": first_entry_text
            })
        else:
            self.add_ui_event({
                "event_type": "show_popup",
                "title": "Entering Next Area",
                "message": "Stay sharp."
            })
        
    def _command_debug_room(self, _) -> dict:
        """Debug command to show current room data and player inventory."""
        current_room_id = self.player.get('location', '')
        room_data = self.get_room_data(current_room_id)
        
        debug_info = [
            f"=== DEBUG INFO FOR {current_room_id} ===",
            f"Room Data: {room_data}",
            f"Player Inventory: {self.player.get('inventory', [])}",
            f"Player Location: {current_room_id}",
        ]
        
        # Show available exits and their lock status
        if room_data and 'exits' in room_data:
            debug_info.append("=== EXITS ===")
            for direction, dest in room_data['exits'].items():
                if isinstance(dest, dict):
                    debug_info.append(f"  {direction}: BLOCKED ({dest})")
                else:
                    dest_data = self.get_room_data(dest)
                    locked = dest_data.get('locked', False) if dest_data else 'NO DATA'
                    locked_by_mri = dest_data.get('locked_by_mri', False) if dest_data else False
                    locking_info = dest_data.get('locking', {}) if dest_data else {}
                    debug_info.append(f"  {direction} -> {dest}: locked={locked}, locked_by_mri={locked_by_mri}, locking={locking_info}")
        
        # Show key details
        items_master = self.resource_manager.get_data('items', {})
        debug_info.append("=== KEYS IN INVENTORY ===")
        for item_key in self.player.get('inventory', []):
            item_data = items_master.get(item_key, {})
            if item_data.get("type") == "key" or "key" in item_key.lower():
                debug_info.append(f"  {item_key}: {item_data}")
        
        return self._build_response(
            message="\n".join(debug_info),
            turn_taken=False
        )

    def _command_force(self, target_str: str) -> dict:
        """
        Force a door/exit, or apply brute force to a breakable object.
        Supports 'with <tool>' and auto-picks the best tool if not specified.
        Defers to active hazards (e.g., MRI) via HazardEngine (already invoked before command).
        """
        self.logger.debug(f"_command_force called with target_str='{target_str}'")
        try:
            return self._force_main(target_str)
        except Exception as e:
            self.logger.error(f"_command_force: Unexpected error: {e}", exc_info=True)
            return self._build_response(message="Something went wrong while forcing.", turn_taken=False, success=False)

    def _command_break(self, target_name_str: str) -> dict:
        """
        Player intent to break an object; uses same core as 'force', preferring break behavior.
        Supports 'break <target> [with <tool>]'.
        """
        self.logger.debug(f"_command_break called with target_name_str='{target_name_str}'")
        try:
            return self._break_main(target_name_str)
        except Exception as e:
            self.logger.error(f"_command_break: Unexpected error: {e}", exc_info=True)
            return self._build_response(message="Something went wrong while breaking.", turn_taken=False, success=False)

    def _command_main_menu(self, _=None) -> dict:
        """Return to the main menu from the gamescreen, clearing all player and world state."""
        self.logger.info("Returning to main menu via _command_main_menu. Resetting all game state.")

        # Reset all game state to initial values
        self.is_game_over = False
        self.game_won = False
        self.ui_events = []
        self.interaction_flags = set()
        self.player = {}
        self.current_level_rooms_world_state = {}
        self.current_level_items_world_state = {}
        self.last_dialogue_context = {}
        # Optionally reset hazard engine and death AI if needed
        if self.hazard_engine:
            try:
                self.hazard_engine.reset()
            except Exception:
                pass
        if self.death_ai:
            try:
                self.death_ai.reset()
            except Exception:
                pass

        # Add a UI event to trigger the main menu transition
        self.add_ui_event({
            "event_type": "go_to_main_menu"
        })
        return self._build_response(
            message="Returning to main menu...",
            event_type="go_to_main_menu",
            game_state=self.get_current_game_state()
        )

    def _command_map(self, target_str: str = None) -> dict:
        """
        Display the local area map.
        Calls the GUI-compatible 3x3 grid map generator.
        """
        try:
            map_string = self.get_gui_map_string()
            return self._build_response(
                message=map_string,
                turn_taken=False
            )
        except Exception as e:
            self.logger.error(f"_command_map: Error generating map: {e}", exc_info=True)
            return self._build_response(
                message="Your map is unreadable right now.",
                turn_taken=False
            )

    # --- The Rite of Passage ---
    def _command_move(self, direction: str) -> dict:
        """Handles player movement and provides a rich description, plus an optional first-entry popup. Injected with robust debugging logic."""
        self.logger.debug(f"_command_move called with direction='{direction}'")
        current_room_id = self.player['location']
        self.logger.debug(f"_command_move: Current room id is '{current_room_id}'")
        current_room = self.get_room_data(current_room_id)
        if not current_room:
            self.logger.error(f"_command_move: No data found for current room '{current_room_id}'")
            return self._build_response(message="You are lost in the void.", turn_taken=False, success=False)

        exits = current_room.get('exits', {})
        self.logger.debug(f"_command_move: Available exits are {list(exits.keys())}")

        # --- HAZARD INTERACTION CHECK BEFORE MOVING ---
        if self.hazard_engine:
            hazards_master = self.resource_manager.get_data('hazards', {})
            active_hazards = self.hazard_engine.get_active_hazards_for_room(current_room_id)
            for hazard_key in active_hazards:
                h_def = hazards_master.get(hazard_key, {})
                move_rules = h_def.get('player_interaction', {}).get('move', [])
                hazard_state = self.hazard_engine.get_hazard_state(hazard_key, current_room_id)
                for rule in move_rules:
                    # Match direction and required hazard state
                    on_dirs = rule.get('on_direction', [])
                    if isinstance(on_dirs, str):
                        on_dirs = [on_dirs]
                    if direction in on_dirs and (not rule.get('requires_hazard_state') or hazard_state in rule.get('requires_hazard_state', [])):
                        msg = rule.get('message', None)
                        qte_def = rule.get('qte_on_move', None)
                        target_state = rule.get('target_state', None)
                        # If QTE is defined, start it and block move until resolved
                        if qte_def and self.qte_engine:
                            ctx = qte_def.copy()
                            ctx['qte_source_hazard_id'] = hazard_key
                            ctx['next_state_success'] = rule.get('next_state_on_qte_success')
                            ctx['next_state_failure'] = rule.get('next_state_on_qte_failure')
                            ctx['message'] = msg or "You attempt to move, but something happens..."
                            self.player['qte_active'] = True
                            self.qte_engine.start_qte(qte_def.get('qte_type', 'button_mash'), ctx)
                            return self._build_response(message=msg or "You attempt to move, but something happens...", turn_taken=True)
                        # If just a message and/or hazard state change, process it
                        if target_state:
                            self.hazard_engine.set_hazard_state_by_type(current_room_id, hazard_key, target_state)
                        if msg:
                            return self._build_response(message=msg, turn_taken=True)
                        # If rule blocks movement, do not proceed
                        if rule.get('blocks_move', False):
                            return self._build_response(message=msg or "You can't move that way right now.", turn_taken=False, success=False)
                        # Otherwise, allow move to proceed after processing
                        break  # Only process first matching rule

        if direction in exits:
            destination = exits[direction]
            
            if isinstance(destination, dict):
                # Blocked exit
                return self._build_response(message="That way is blocked.", turn_taken=False)
            
            # Check if destination room is locked
            dest_data = self.get_room_data(destination)
            if dest_data and dest_data.get("locked", False):
                # Check if locked by MRI specifically
                if dest_data.get("locked_by_mri"):
                    msg = "The magnetic field has sealed that door shut! You can't force it open."
                else:
                    msg = f"The door to {destination.replace('_', ' ')} is locked."
                
                return self._build_response(message=color_text(msg, "warning", self.resource_manager), turn_taken=False)
            
            destination = exits[direction]
            self.logger.debug(f"_command_move: Destination for direction '{direction}' is '{destination}'")
            if isinstance(destination, dict):
                self.logger.info(f"_command_move: Exit '{direction}' is blocked or complex (dict type)")
                return self._build_response(message="That way is blocked.", turn_taken=False, success=False)
            
            # --- REFINED LOGIC ---
            self.logger.info(f"_command_move: Moving player from '{current_room_id}' to '{destination}'")
            self.player['location'] = destination
            
            is_first_visit = destination not in self.player['visited_rooms']
            self.player['visited_rooms'].add(destination)
            self.logger.debug(f"_command_move: is_first_visit={is_first_visit}")

            # --- Companion follows player movement ---
            try:
                self._move_companion_to_next_room(destination)
            except Exception as e:
                self.logger.error(f"_command_move: Error moving companion: {e}", exc_info=True)

            new_room_data = self.get_room_data(destination) or {}
            self.logger.debug(f"_command_move: New room data for '{destination}': {new_room_data}")

            # The main message is always the rich description.
            message = self._get_rich_room_description(destination)
            self.logger.debug(f"_command_move: Room description: {message}")

            # Check for first_entry_text and create a popup event on the first visit.
            ui_events = []
            if is_first_visit and new_room_data.get('first_entry_text'):
                self.logger.info(f"_command_move: First entry text found for room '{destination}'")
                ui_events.append(self._make_first_entry_popup_event(destination, new_room_data['first_entry_text']))
            else:
                self.logger.debug(f"_command_move: No first entry text for room '{destination}' or not first visit.")

            response = self._build_response(message=message, turn_taken=True, success=True, ui_events=ui_events)
            self.logger.debug(f"_command_move: Returning response: {response}")
            return response
        else:
            self.logger.warning(f"_command_move: Invalid direction '{direction}' from room '{current_room_id}'")
            return self._build_response(message=f"You can't go {direction}.", turn_taken=False, success=False)
    
    # --- The Rite of Observation ---
    def _command_examine(self, target: str) -> dict:
        """Main entry for the 'examine' command, refactored with helpers and robust logging."""
        try:
            return self._examine_main(target)
        except Exception as e:
            self.logger.error(f"_command_examine: Unexpected error: {e}", exc_info=True)
            return self._build_response(message="Something went wrong while examining.", turn_taken=False, success=False)

    # --- The Rite of Acquisition ---
    def _command_take(self, target_str: str) -> dict:
        """
        Handles 'take [item]', 'take [item] from [container]', and 'take all'.
        Moves items from the world (loose or in a container) to player inventory.
        """
        current_room_id = self.player['location']
        items_master = self.resource_manager.get_data('items', {})
        room_data = self.get_room_data(current_room_id) or {}

        # Identify simple single-item take (not 'take all', not container form)
        if target_str and ' from ' not in target_str.lower() and target_str.lower() not in ("all",):
            # Map player input to internal key id (simplified heuristic)
            lowered = target_str.lower().strip()
            key_candidates = {
                "coroner's office key": "coroners_office_key",
                "coroners office key": "coroners_office_key",
                "coroner office key": "coroners_office_key"
            }
            item_key = key_candidates.get(lowered)
            if item_key:
                intercept_resp = self._maybe_intercept_mri_key_take(item_key)
                if intercept_resp:
                    return intercept_resp

        # --- TAKE ALL LOGIC ---
        if target_str and self._norm(target_str) == "all":
            taken = []
            # Take all from searched containers
            for furniture in room_data.get('furniture', []):
                if isinstance(furniture, dict) and furniture.get('is_container'):
                    flag_name = f"searched_{furniture.get('name', '')}"  # exact flag id, matches _command_search
                    if flag_name in self.interaction_flags:
                        items_in_container = furniture.get('items', [])
                        takeable_keys = [
                            key for key in list(items_in_container)
                            if items_master.get(key, {}) or True  # allow matching by display name below
                        ]
                        # Normalize: support entries that are display names
                        resolved_keys = []
                        for val in takeable_keys:
                            for key, data in items_master.items():
                                if (
                                    val == key
                                    or self._norm(val) == self._norm(key)
                                    or self._norm(val) == self._norm(data.get('name', ''))
                                ):
                                    if data.get("takeable", False):
                                        resolved_keys.append(key)
                                    break
                        for key in resolved_keys:
                            if key in items_in_container:
                                furniture['items'].remove(key)
                            else:
                                # remove by display name if that's what's stored
                                disp = items_master.get(key, {}).get('name', key)
                                for i, v in enumerate(list(items_in_container)):
                                    if self._norm(v) == self._norm(disp) or self._norm(v) == self._norm(key):
                                        items_in_container.pop(i)
                                        break
                            self.player['inventory'].append(key)
                            taken.append(self._get_item_display_name(key))

            # Take all loose items in the room
            for key, item_state in list(self.current_level_items_world_state.items()):
                if item_state.get('location') == current_room_id and items_master.get(key, {}).get("takeable", False):
                    self.player['inventory'].append(key)
                    taken.append(self._get_item_display_name(key))
                    del self.current_level_items_world_state[key]

            msg = f"You take: {', '.join(taken)}." if taken else "You don't see any takeable items here."
            return self._build_response(message=msg, turn_taken=True)

        # Parse "take X from Y" syntax
        item_name_to_take = target_str
        container_name = None
        match = re.match(r"(.+?)\s+from\s+(.+)", target_str, re.IGNORECASE)
        if match:
            item_name_to_take = match.group(1).strip()
            container_name = match.group(2).strip()

        item_key = None
        for key, data in items_master.items():
            if self._norm(data.get('name', '')) == self._norm(item_name_to_take):
                item_key = key
                break

        if not item_key:
            return self._build_response(message=f"You don't see any '{item_name_to_take}' to take.", turn_taken=False)

        # --- LOGIC FOR TAKING FROM A SPECIFIC CONTAINER ---
        if container_name:
            container_entity = self._find_entity_in_room(container_name, current_room_id)
            if not container_entity or not container_entity['data'].get('is_container'):
                return self._build_response(message=f"You don't see a container called '{container_name}'.", turn_taken=False)
            if item_key in container_entity['data'].get('items', []):
                container_entity['data']['items'].remove(item_key)
                self.player['inventory'].append(item_key)
            else:
                # support when container stores display names instead of keys
                disp = items_master.get(item_key, {}).get('name', item_key)
                items_in_container = container_entity['data'].get('items', [])
                found = False
                for i, v in enumerate(list(items_in_container)):
                    if self._norm(v) == self._norm(disp) or self._norm(v) == self._norm(item_key):
                        items_in_container.pop(i)
                        self.player['inventory'].append(item_key)
                        found = True
                        break
                if not found:
                    return self._build_response(message=f"The {container_entity['name']} doesn't contain a {item_name_to_take}.", turn_taken=False)
        else:
            # --- LOGIC FOR TAKING FROM SEARCHED CONTAINERS (single item) ---
            found_in_container = False
            for furniture in room_data.get('furniture', []):
                if isinstance(furniture, dict) and furniture.get('is_container'):
                    flag_name = f"searched_{furniture.get('name', '')}"  # exact flag id, matches _command_search
                    if flag_name in self.interaction_flags:
                        if item_key in furniture.get('items', []):
                            furniture['items'].remove(item_key)
                            self.player['inventory'].append(item_key)
                            found_in_container = True
                            break
                        else:
                            # support when container stores display names instead of keys
                            disp = items_master.get(item_key, {}).get('name', item_key)
                            items_in_container = furniture.get('items', [])
                            for i, v in enumerate(list(items_in_container)):
                                if self._norm(v) == self._norm(disp) or self._norm(v) == self._norm(item_key):
                                    items_in_container.pop(i)
                                    self.player['inventory'].append(item_key)
                                    found_in_container = True
                                    break
                    if found_in_container:
                        break
            # --- LOGIC FOR TAKING A LOOSE ITEM ---
            if not found_in_container:
                item_location = self.current_level_items_world_state.get(item_key, {}).get('location')
                if item_location == current_room_id:
                    del self.current_level_items_world_state[item_key]
                    self.player['inventory'].append(item_key)
                else:
                    return self._build_response(message=f"You don't see a '{item_name_to_take}' here.", turn_taken=False)

        display_name = self._get_item_display_name(item_key)
        message = f"You take the {display_name}."
                # After inventory updated successfully:
        try:
            self._maybe_emit_requirements_met_event()
        except Exception as e:
            self.logger.error(f"_command_take: failed to emit requirements-met event: {e}", exc_info=True)
        return self._build_response(message=message, turn_taken=True, success=True)

    # --- NEW: The Rite of Discovery ---
    def _command_search(self, target: str) -> dict:
        """Handles the 'search' command to find items within a container. Injected with robust debugging logic."""
        self.logger.debug(f"_command_search called with target='{target}'")
        current_room_id = self.player['location']

        if not target:
            self.logger.info("_command_search: No target specified")
            return self._build_response(message="Search what?", turn_taken=False, success=False)

        entity = self._find_entity_in_room(target, current_room_id)
        self.logger.debug(f"_command_search: Entity found: {entity}")

        if not entity:
            self.logger.info(f"_command_search: '{target}' not found in room '{current_room_id}'")
            return self._build_response(message=f"You don't see a '{target}' to search here.", turn_taken=False, success=False)

        if entity['type'] != 'furniture' or not entity['data'].get('is_container'):
            self.logger.info(f"_command_search: Entity '{entity['name']}' is not a searchable container")
            return self._build_response(message=f"You can't search the {entity['name']}.", turn_taken=False, success=False)

        container_data = entity['data']
        self.logger.debug(f"_command_search: Container data: {container_data}")

        if container_data.get('locked'):
            self.logger.info(f"_command_search: Container '{entity['name']}' is locked")
            return self._build_response(message=f"The {entity['name']} is locked.", turn_taken=False, success=False)

        items_in_container = container_data.get('items', [])
        self.logger.debug(f"_command_search: Items in container: {items_in_container}")

        self.set_interaction_flag(f"searched_{entity['id_key']}")

        if not items_in_container:
            message = f"You search the {entity['name']} but find nothing."
            self.logger.info(f"_command_search: No items found in '{entity['name']}'")
            return self._build_response(message=message, turn_taken=True, success=True)
        else:
            item_names = [self._get_item_display_name(key) for key in items_in_container]
            colored_item_names = [color_text(name, 'item', self.resource_manager) for name in item_names]
            message = f"You search the {entity['name']} and find: {', '.join(colored_item_names)}."
            self.logger.info(f"_command_search: Found items in '{entity['name']}': {item_names}")
            return self._build_response(message=message, turn_taken=True, success=True)

    def _command_inventory(self, target: str) -> dict:
        """Handles the 'inventory' command by listing the player's items, canonically accurate to engine design."""
        inventory_list = self.player.get('inventory', [])
        
        if not inventory_list:
            message = "You are not carrying anything."
            return self._build_response(message=message, turn_taken=False)

        # Canonical: Support both List[str] and List[dict] inventory entries
        item_names = []
        items_master = self.resource_manager.get_data('items', {})
        for entry in inventory_list:
            if isinstance(entry, str):
                # Try to get display name from master data
                item_names.append(self._get_item_display_name(entry))
            elif isinstance(entry, dict):
                # Try common keys for name/id
                name = entry.get('name') or entry.get('display_name') or entry.get('id') or entry.get('item_id') or entry.get('key')
                if name:
                    item_names.append(self._get_item_display_name(name))
                else:
                    # Fallback: show dict as string
                    item_names.append(str(entry))
            else:
                item_names.append(str(entry))

        colored_item_names = [color_text(name, 'item', self.resource_manager) for name in item_names]
        message = "You are carrying:\n- " + "\n- ".join(colored_item_names)
        return self._build_response(message=message, turn_taken=False)

    def _command_set_qte_sr(self, arg: str) -> dict:
        """
        Developer helper: set the adaptive QTE success rate (0.0–1.0).
        Example: 'set_qte_sr 0.25'
        """
        try:
            val = max(0.0, min(1.0, float((arg or "").strip())))
        except Exception:
            return self._build_response(message="Usage: set_qte_sr <0.0–1.0>", turn_taken=False)

        da = getattr(self, 'death_ai', None)
        if not da:
            return self._build_response(message="DeathAI not available.", turn_taken=False)

        # Prefer the canonical field used by DeathAI.get_status_report
        if hasattr(da, 'player_behavior_patterns'):
            da.player_behavior_patterns['qte_success_rate'] = val
        elif hasattr(da, 'player_patterns'):
            da.player_patterns['qte_success_rate'] = val
        else:
            if not hasattr(da, 'patterns'):
                da.patterns = {}
            da.patterns['qte_success_rate'] = val

        self.logger.info(f"Set adaptive qte_success_rate={val:.2f}")
        return self._build_response(message=f"qte_success_rate set to {val:.2f}", turn_taken=False)

    def _command_save(self, slot_identifier: str = None) -> dict:
        """Save the current game state to a specified slot."""
        if not slot_identifier:
            slot_identifier = "quicksave"
        
        try:
            from .utils import get_save_filepath
            from datetime import datetime
            import json
            
            # Build comprehensive save data
            save_data = {
                "save_info": {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "location": self.get_room_data(self.player.get('location', '')).get('name', 'Unknown'),
                    "character_class": self.player.get('character_class', ''),
                    "turns_left": self.player.get('turns_left', 0),
                    "current_level": self.player.get('current_level', 1),
                    "hp": self.player.get('hp', 0),
                    "fear": self.player.get('fear', 0.0),
                    "score": self.player.get('score', 0)
                },
                "player_state": self.player.copy(),
                "level_rooms_state": self.current_level_rooms_world_state.copy(),
                "level_items_state": self.current_level_items_world_state.copy(),
                "interaction_flags": list(self.interaction_flags),
                "game_flags": {
                    "is_game_over": self.is_game_over,
                    "game_won": self.game_won
                },
                "engine_states": {}
            }
            
            # Save hazard engine state if available
            if self.hazard_engine:
                try:
                    save_data["engine_states"]["hazard_engine"] = self.hazard_engine.get_save_state()
                except Exception as e:
                    self.logger.warning(f"Could not save hazard engine state: {e}")
            
            # Save death AI state if available
            if self.death_ai:
                try:
                    save_data["engine_states"]["death_ai"] = self.death_ai.get_save_state()
                except Exception as e:
                    self.logger.warning(f"Could not save death AI state: {e}")
            
            # Write to file
            save_path = get_save_filepath(slot_identifier)
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, indent=2, ensure_ascii=False, default=str)
            
            self.logger.info(f"Game saved to slot '{slot_identifier}' at {save_path}")
            
            # Trigger achievement for first save
            if self.achievements_system:
                self.achievements_system.unlock("first_save")
            
            return self._build_response(
                message=f"Game saved to {slot_identifier.replace('_', ' ')}.",
                turn_taken=False,
                success=True
            )
            
        except Exception as e:
            self.logger.error(f"Failed to save game to slot '{slot_identifier}': {e}", exc_info=True)
            return self._build_response(
                message=f"Failed to save game: {str(e)}",
                turn_taken=False,
                success=False
            )

    def _command_load(self, slot_identifier: str = None) -> dict:
        """Load game state from a specified slot."""
        if not slot_identifier:
            return self._build_response(
                message="Please specify a save slot (e.g., 'load quicksave' or 'load slot_1').",
                turn_taken=False
            )
        
        try:
            from .utils import get_save_filepath
            import json
            
            save_path = get_save_filepath(slot_identifier)
            
            if not os.path.exists(save_path):
                return self._build_response(
                    message=f"No save file found for slot '{slot_identifier}'.",
                    turn_taken=False,
                    success=False
                )
            
            # Load save data
            with open(save_path, encoding='utf-8') as f:
                save_data = json.load(f)
            
            # Validate save data structure
            if "player_state" not in save_data:
                return self._build_response(
                    message="Save file is corrupted or invalid.",
                    turn_taken=False,
                    success=False
                )
            
            # Restore game state
            self.player = save_data["player_state"].copy()
            self.current_level_rooms_world_state = save_data.get("level_rooms_state", {})
            self.current_level_items_world_state = save_data.get("level_items_state", {})
            self.interaction_flags = set(save_data.get("interaction_flags", []))
            
            # Restore game flags
            game_flags = save_data.get("game_flags", {})
            self.is_game_over = game_flags.get("is_game_over", False)
            self.game_won = game_flags.get("game_won", False)
            
            # Restore engine states if available
            engine_states = save_data.get("engine_states", {})
            
            if self.hazard_engine and "hazard_engine" in engine_states:
                try:
                    self.hazard_engine.load_save_state(engine_states["hazard_engine"])
                except Exception as e:
                    self.logger.warning(f"Could not restore hazard engine state: {e}")
            
            if self.death_ai and "death_ai" in engine_states:
                try:
                    self.death_ai.load_state(engine_states["death_ai"])
                except Exception as e:
                    self.logger.warning(f"Could not restore death AI state: {e}")
            
            # Reset QTE state (don't restore active QTEs)
            self.player['qte_active'] = False
            self.player['qte_context'] = {}
            
            # Rebuild coordinate map for current location
            current_room = self.player.get('location')
            if current_room:
                try:
                    self._build_room_coordinate_map(current_room)
                except Exception as e:
                    self.logger.warning(f"Could not rebuild room coordinate map: {e}")
            
            self.logger.info(f"Game loaded from slot '{slot_identifier}'")
            
            # Update start_response to reflect loaded state
            room_desc = self._get_rich_room_description(self.player.get('location', ''))
            self.start_response = {
                "messages": [room_desc],
                "game_state": self.get_current_game_state(),
                "ui_events": [],
                "turn_taken": False,
                "success": True
            }
            
            return self._build_response(
                message=f"Game loaded from {slot_identifier.replace('_', ' ')}.",
                turn_taken=False,
                success=True,
                ui_events=[{
                    "event_type": "game_loaded",
                    "room_description": room_desc
                }]
            )
            
        except json.JSONDecodeError:
            self.logger.error(f"Save file '{slot_identifier}' is corrupted (invalid JSON)")
            return self._build_response(
                message=f"Save file '{slot_identifier}' is corrupted.",
                turn_taken=False,
                success=False
            )
        except Exception as e:
            self.logger.error(f"Failed to load game from slot '{slot_identifier}': {e}", exc_info=True)
            return self._build_response(
                message=f"Failed to load game: {str(e)}",
                turn_taken=False,
                success=False
            )

    # --- NPC commands ---

    def _command_talk(self, target_name_str: str) -> dict:
        """
        Talk to an NPC: show current dialogue node, options, and apply any on_talk_action.
        Always resolves the current dialogue state using _resolve_npc_dialogue_entry_state.
        """
        target_name_str = (target_name_str or "").strip()
        if not target_name_str:
            self.logger.warning("_command_talk: No target specified.")
            return self._build_response(message="Talk to whom?", turn_taken=False)

        room_id = self.player.get('location')
        npc = self._find_npc_in_room(target_name_str, room_id)
        if not npc:
            self.logger.warning(f"_command_talk: NPC '{target_name_str}' not found in room '{room_id}'.")
            return self._build_response(message=f"You don't see {target_name_str} here.", turn_taken=False)

        try:
            # 1. Resolve dialogue state
            current_state = self._resolve_npc_dialogue_entry_state(npc, room_id)
            node = (npc.get('dialogue_states') or {}).get(current_state)
            if not node:
                self.logger.error(f"_command_talk: NPC '{npc.get('name')}' missing dialogue for state '{current_state}'.")
                return self._build_response(message="They don't seem to have anything to say.", turn_taken=True)

            # 2. Handle special $check_result$/$ticket_check_result$ logic
            if self._is_check_result_node(node):
                return self._handle_check_result_node(npc, node, options_text=self._build_options_text(node))

            # 3. Process on_talk_action
            ui_events = []
            self._process_on_talk_action(npc, node, ui_events)

            # 4. Handle next_state transition
            next_state = node.get('next_state')
            if next_state:
                self._set_npc_state(npc, next_state)
                # Optionally process on_talk_action in the new state
                new_node = (npc.get('dialogue_states') or {}).get(next_state)
                if new_node and 'on_talk_action' in new_node:
                    self._apply_on_talk_action(new_node['on_talk_action'])

            # 5. Re-resolve state for options (in case hazard state changed)
            current_state = self._resolve_npc_dialogue_entry_state(npc, room_id)
            node = (npc.get('dialogue_states') or {}).get(current_state)
            text = node.get('text', "...") if node else "..."
            options_text = self._build_options_text(node)
            self.last_dialogue_context = {"npc_name": npc.get('name'), "options": node.get('options', []) if node else []}

            ui_events.append({
                "event_type": "show_popup",
                "title": npc.get('name', 'NPC'),
                "message": text + (options_text or "")
            })

            self.logger.info(f"_command_talk: Displaying dialogue for '{npc.get('name')}' in state '{current_state}'.")
            return self._build_response(message=f"[{npc.get('name')}]\n{text}", turn_taken=True, ui_events=ui_events)

        except Exception as e:
            self.logger.error(f"_command_talk: Unexpected error: {e}", exc_info=True)
            return self._build_response(message="Something went wrong during the conversation.", turn_taken=True)

    def _command_respond(self, option_str: str) -> dict:
        """
        Choose a numbered dialogue option from the last NPC conversation.
        Handles input validation, option lookup, state transition, and robust error handling.
        """
        option_str = (option_str or "").strip()
        self.logger.debug(f"_command_respond called with option_str='{option_str}'")

        # 1. Parse and validate option number
        opt_num = self._parse_option_number(option_str)
        if opt_num is None:
            return self._build_response(
                message="Please specify a valid option number (e.g., 'respond 1').",
                turn_taken=False
            )

        # 2. Retrieve last dialogue context
        ctx = self.last_dialogue_context or {}
        npc_name = ctx.get("npc_name")
        options = ctx.get("options", [])
        if not npc_name or not options:
            self.logger.warning("_command_respond: No active conversation context.")
            return self._build_response(
                message="There's no active conversation to respond to.",
                turn_taken=False
            )
        if opt_num >= len(options) or opt_num < 0:
            self.logger.warning(f"_command_respond: Option {opt_num+1} out of range for options: {options}")
            return self._build_response(
                message=f"That's not a valid option. Choose between 1 and {len(options)}.",
                turn_taken=False
            )

        # 3. Find the NPC in the current room
        room_id = self.player.get('location')
        npc = self._find_npc_in_room(npc_name, room_id)
        if not npc:
            self.logger.warning(f"_command_respond: NPC '{npc_name}' not found in room '{room_id}'.")
            return self._build_response(
                message="They are no longer here.",
                turn_taken=False
            )

        # 4. Get the selected option and its target state
        selected = options[opt_num]
        target_state = selected.get("target_state")
        if not target_state:
            self.logger.warning(f"_command_respond: Option {opt_num+1} has no target_state.")
            return self._build_response(
                message="That dialogue option leads nowhere.",
                turn_taken=True
            )

        # 5. Advance to the selected state and re-enter talk to render the next node
        self.logger.info(f"_command_respond: Advancing NPC '{npc_name}' to state '{target_state}' via option {opt_num+1}.")
        self._set_npc_state(npc, target_state)
        return self._command_talk(npc_name)
    
    def _command_test_qte(self, qte_type: str) -> dict:
        """A robust debug command to test any QTE defined in qte_definitions.json."""
        self.logger.debug(f"_command_test_qte called with qte_type='{qte_type}'")
        if not self.qte_engine:
            self.logger.warning("_command_test_qte: QTE Engine not connected.")
            return self._build_response(message="QTE Engine not connected.")

        qte_definitions = self.qte_engine.qte_definitions
        available_qtes = sorted(list(qte_definitions.keys()))
        self.logger.debug(f"_command_test_qte: Available QTEs: {available_qtes}")

        # If no qte_type is provided, list all available QTEs for testing.
        if not qte_type:
            message = "Available QTEs for testing:\n- " + "\n- ".join(available_qtes)
            self.logger.info("_command_test_qte: No QTE type provided, listing available QTEs.")
            return self._build_response(message=message)

        if qte_type not in available_qtes:
            self.logger.warning(f"_command_test_qte: Unknown QTE type '{qte_type}' requested.")
            return self._build_response(message=f"Unknown QTE type: '{qte_type}'. Use 'testqte' to see a list.")

        # Use the real QTE definition with minimal test overrides
        qte_def = qte_definitions[qte_type]
        self.logger.debug(f"_command_test_qte: Using real QTE definition for '{qte_type}'")
        
        # Create test context by copying the definition and adding test-specific fields
        test_context = qte_def.copy()
        test_context.update({
            "ui_mode": "in-screen",
            "ui_prompt_message": f"Testing QTE: {qte_type}\n{qte_def.get('ui_prompt_message', 'Follow the instructions!')}",
            "success_message": test_context.get("success_message", "DEBUG: Test Succeeded!"),
            "failure_message": test_context.get("failure_message", "DEBUG: Test Failed!"),
            "hp_damage_on_failure": 0,  # No damage in test mode
        })
        
        self.logger.info(f"_command_test_qte: Starting QTE '{qte_type}' with real definition")
        self.qte_engine.start_qte(qte_type, test_context)
        
        return self._build_response(message=f"Initiating test QTE: {qte_type}", turn_taken=False)

    def _command_unlock(self, target_name_str: str) -> dict:
        """
        Unlock doors (exits) or furniture containers using keys from inventory.
        Integrates with the refined engine's entity finding, locking schema, and response building.
        """
        try:
            if not target_name_str:
                return self._build_response(message="Unlock what?", turn_taken=False)

            self.logger.debug(f"_command_unlock: Attempting to unlock '{target_name_str}'")
            current_room_id = self.player.get('location', '')
            current_room_data = self.get_room_data(current_room_id)
            if not current_room_data:
                return self._build_response(message="You can't unlock anything here.", turn_taken=False)

            target_norm = self._norm(target_name_str)
            available_keys = self._get_player_keys()
            if not available_keys:
                self.logger.debug("_command_unlock: Player has no keys in inventory")
                return self._build_response(message="You don't have any keys.", turn_taken=False)

            self.logger.debug(f"_command_unlock: Available keys: {list(available_keys.keys())}")

            # Try to unlock an exit (door)
            exit_result = self._try_unlock_exit(target_norm, current_room_data, available_keys)
            if exit_result is not None:
                return exit_result

            # Try to unlock furniture
            furniture_result = self._try_unlock_furniture(target_name_str, current_room_id, available_keys)
            if furniture_result is not None:
                return furniture_result

            # Target not found
            return self._build_response(
                message=f"You don't see '{target_name_str}' here to unlock.",
                turn_taken=False
            )

        except Exception as e:
            self.logger.error(f"_command_unlock: Error unlocking '{target_name_str}': {e}", exc_info=True)
            return self._build_response(
                message=f"Something went wrong while trying to unlock {target_name_str}.",
                turn_taken=False
            )

    def _command_use(self, target_str: str) -> dict:
        """Handle the 'use' command. Try room interactables, hazards/objects, then inventory."""
        self.logger.debug(f"_command_use: target='{target_str}'")
        try:
            return self._use_main(target_str)
        except Exception as e:
            self.logger.error(f"_command_use: Unexpected error: {e}", exc_info=True)
            return self._build_response(message="Something went wrong while trying to use that.", turn_taken=False, success=False)

    def _command_wait(self, target: str) -> dict:
        """Handles the 'wait' command, allowing the player to pass a turn."""
        message = "You wait for a moment, observing your surroundings."
        
        # This is the crucial part: it explicitly takes a turn.
        # This will trigger the _process_turn_end method, allowing the
        # HazardEngine and DeathAI to take their actions.
        return self._build_response(message=message, turn_taken=True, success=True)

    def _command_help(self, target: str) -> dict:
        """Handles the 'help' command by listing available actions."""
        # We derive the available commands directly from the command_map.
        # This means as we add new commands, this help text updates automatically!
        
        # We use a set to get only unique method names, then capitalize them.
        available_verbs = sorted(list({v.__name__.replace('_command_', '').capitalize() for v in self.command_map.values()}))
        
        message = "[b]Available Actions:[/b]\n"
        message += ", ".join(available_verbs)
        message += "\n\nTry commands like 'move north', 'examine table', or 'take key'."
        
        return self._build_response(message=message, turn_taken=False)

    # --- NEW: Core Gameplay Loop ---

    def _handle_qte_resolution(self, qte_result: dict) -> dict:
        """
        Main orchestrator for QTE resolution.
        Delegates to specialized helpers for each resolution path.
        """
        try:
            self.logger.info("_handle_qte_resolution: Processing QTE result")
            self.player['qte_active'] = False
            self.add_ui_event({"event_type": "destroy_qte_popup", "priority": 1000})

            # 1. Handle fatal success (e.g., MRI door bisection)
            if self._is_fatal_success(qte_result):
                return self._handle_fatal_success(qte_result)

            # 2. Handle damage and death from failure
            death_response = self._handle_qte_damage_and_death(qte_result)
            if death_response:
                return death_response

            # 3. Apply success effects (unlock rooms, etc.)
            if qte_result.get('success', False):
                self._apply_qte_success_effects(qte_result)

            # 4. Handle pending move after successful QTE
            move_response = self._handle_pending_move(qte_result)
            if move_response:
                return move_response

            # 5. Handle hazard state transitions
            hazard_response = self._handle_hazard_state_transition(qte_result)
            if hazard_response:
                return hazard_response

            # 6. Default: show result popup
            return self._build_qte_result_popup(qte_result)

        except Exception as e:
            self.logger.error(f"_handle_qte_resolution: Unexpected error: {e}", exc_info=True)
            return self._build_response(
                message="Something went wrong processing the QTE result.",
                turn_taken=False
            )

    def _is_fatal_success(self, qte_result: dict) -> bool:
        """Check if QTE was a fatal success (e.g., forcing MRI-sealed door)."""
        return qte_result.get('success', False) and qte_result.get('is_fatal', False)

    def _handle_fatal_success(self, qte_result: dict) -> dict:
        """
        Handle QTE success that results in player death.
        Transitions hazard to death state and triggers game over.
        """
        try:
            self.logger.info("_handle_fatal_success: Processing fatal success scenario")
            hazard_id = qte_result.get('qte_source_hazard_id')
            next_state = qte_result.get('next_state_success')

            # Transition hazard to death state
            if hazard_id and next_state and self.hazard_engine:
                self.logger.info(f"Fatal success: transitioning hazard '{hazard_id}' to '{next_state}'")
                result = self.hazard_engine.set_hazard_state(hazard_id, next_state)
                if result:
                    for cons in result.get('consequences', []):
                        self.handle_hazard_consequence(cons)

            # Trigger game over
            self.is_game_over = True
            death_reason = (
                qte_result.get('death_reason') or
                self.player.get('death_reason') or
                qte_result.get('message', 'Died from a successful but fatal action.')
            )
            self.player['death_reason'] = death_reason
            
            self.add_ui_event({
                "event_type": "game_over",
                "death_reason": death_reason,
                "final_narrative": self.get_death_narrative()
            })
            
            return self._build_response()

        except Exception as e:
            self.logger.error(f"_handle_fatal_success: Error: {e}", exc_info=True)
            # Fallback to generic death
            self.is_game_over = True
            self.player['death_reason'] = "Fatal error during resolution."
            return self._build_response()

    def _handle_qte_damage_and_death(self, qte_result: dict) -> bool:
        """
        Apply HP damage from QTE failure and check for death.
        Returns True if player died, False otherwise.
        """
        if qte_result.get('success', False):
            return False  # No damage on success

        hp_damage = int(qte_result.get('hp_damage', 0))
        if hp_damage <= 0:
            return False  # No damage to apply

        self.logger.info(f"_handle_qte_damage_and_death: Applying {hp_damage} damage")
        
        # Apply damage
        current_hp = int(self.player.get('hp', 30))
        new_hp = max(0, current_hp - hp_damage)
        self.player['hp'] = new_hp
        
        # FIXED: Only trigger death if HP reaches 0 OR if explicitly marked as fatal
        is_explicitly_fatal = bool(qte_result.get('is_fatal', False))
        
        if new_hp <= 0 or is_explicitly_fatal:
            self.logger.info(f"_trigger_qte_death: Player died - {'explicit fatal flag' if is_explicitly_fatal else 'HP depleted'}")
            self._trigger_qte_death(qte_result)
            return True
        
        # Player survived
        self.logger.info(f"_handle_qte_damage_and_death: Player survived with {new_hp} HP remaining")
        return False

    def _trigger_qte_death(self, qte_result: dict) -> dict:
        """Trigger game over from QTE failure."""
        try:
            self.is_game_over = True
            death_reason = (
                qte_result.get('death_reason') or
                self.player.get('death_reason') or
                "QTE failure"
            )
            self.player['death_reason'] = death_reason
            
            self.logger.info(f"_trigger_qte_death: Player died - {death_reason}")
            
            self.add_ui_event({
                "event_type": "game_over",
                "death_reason": death_reason,
                "final_narrative": self.get_death_narrative()
            })
            
            return self._build_response()

        except Exception as e:
            self.logger.error(f"_trigger_qte_death: Error: {e}", exc_info=True)
            self.is_game_over = True
            return self._build_response()

    def _update_health_effects(self):
        """Update UI health status effects based on current HP."""
        try:
            if 0 < self.player['hp'] <= self._low_health_threshold():
                self.add_ui_event({"event_type": "player_low_health_effect"})
            else:
                self.add_ui_event({"event_type": "player_clear_low_health_effect"})
        except Exception as e:
            self.logger.error(f"_update_health_effects: Error: {e}", exc_info=True)

    def _apply_qte_success_effects(self, qte_result: dict):
        """Apply world-state effects from successful QTE (e.g., unlock doors)."""
        try:
            effects = qte_result.get('effects_on_success', [])
            for effect in effects:
                if effect.get('type') == 'unlock_room':
                    self._unlock_room_effect(effect)
        except Exception as e:
            self.logger.error(f"_apply_qte_success_effects: Error: {e}", exc_info=True)

    def _unlock_furniture_effect(self, effect: dict):
        """Unlock a piece of furniture in the live world state."""
        try:
            room_id = effect.get('room_id') or self.player.get('location')
            fname = (effect.get('furniture_name') or "").strip()
            if not (room_id and fname):
                return

            room_state = self.current_level_rooms_world_state.get(room_id)
            if not room_state:
                self.logger.warning(f"_unlock_furniture_effect: Room '{room_id}' not found in world state")
                return

            furn_list = room_state.get('furniture') or []
            norm = self._norm
            updated = False
            for f in furn_list:
                if isinstance(f, dict) and norm(f.get('name')) == norm(fname):
                    # Ensure container dict has a live 'locked' flag and clear it
                    f['locked'] = False
                    # Clear other lock-related hints if present
                    f.pop('locked_by_mri', None)
                    f.pop('requires_key', None)
                    updated = True
                    break

            if updated:
                self.logger.info(f"Unlocked furniture '{fname}' in room '{room_id}'")
                # Nudge UI to refresh
                self.add_ui_event({"event_type": "refresh_context_actions"})
            else:
                self.logger.warning(f"_unlock_furniture_effect: Furniture '{fname}' not found or not a dict in '{room_id}'")
        except Exception as e:
            self.logger.error(f"_unlock_furniture_effect: Error: {e}", exc_info=True)

    def _break_furniture_effect(self, effect: dict):
        """Mark furniture as broken and unlocked in the live world state."""
        try:
            room_id = effect.get('room_id') or self.player.get('location')
            fname = (effect.get('furniture_name') or "").strip()
            if not (room_id and fname):
                return

            room_state = self.current_level_rooms_world_state.get(room_id)
            if not room_state:
                self.logger.warning(f"_break_furniture_effect: Room '{room_id}' not found in world state")
                return

            furn_list = room_state.get('furniture') or []
            norm = self._norm
            updated = False
            for f in furn_list:
                if isinstance(f, dict) and norm(f.get('name')) == norm(fname):
                    f['is_broken'] = True
                    f['locked'] = False
                    updated = True
                    break

            if updated:
                self.logger.info(f"Broke furniture '{fname}' in room '{room_id}'")
                self.add_ui_event({"event_type": "refresh_context_actions"})
            else:
                self.logger.warning(f"_break_furniture_effect: Furniture '{fname}' not found or not a dict in '{room_id}'")
        except Exception as e:
            self.logger.error(f"_break_furniture_effect: Error: {e}", exc_info=True)

    def _unlock_room_effect(self, effect: dict):
        """Unlock a room as a QTE success effect."""
        try:
            room_id = effect.get('room_id')
            if not room_id:
                return
            
            room_state = self.current_level_rooms_world_state.get(room_id)
            if not room_state:
                self.logger.warning(f"_unlock_room_effect: Room '{room_id}' not found in world state")
                return
            
            room_state['locked'] = False
            room_state['locked_by_mri'] = False
            self.logger.info(f"Unlocked room '{room_id}' after QTE success")

        except Exception as e:
            self.logger.error(f"_unlock_room_effect: Error: {e}", exc_info=True)

    def _handle_pending_move(self, qte_result: dict) -> Optional[dict]:
        """
        Execute pending move after successful QTE (e.g., force-door auto-move).
        Returns full response if move executed, None otherwise.
        """
        try:
            if not qte_result.get('success', False):
                return None
            
            pending_move = qte_result.get('pending_move') or self.player.pop('pending_move', None)
            if not pending_move:
                return None
            
            self.logger.info(f"_handle_pending_move: Executing pending move '{pending_move}'")
            move_result = self._command_move(pending_move)
            
            # Merge QTE and move messages
            result = self._build_response()
            result['messages'] = qte_result.get('messages', []) + move_result.get('messages', [])
            result['ui_events'] = self.get_ui_events()
            result['game_state'] = self.get_current_game_state()
            
            return result

        except Exception as e:
            self.logger.error(f"_handle_pending_move: Error: {e}", exc_info=True)
            return None

    def _handle_hazard_state_transition(self, qte_result: dict) -> Optional[dict]:
        """
        Handle hazard state change after QTE resolution.
        Returns response if terminal state reached, None otherwise.
        """
        try:
            hazard_id = qte_result.get('qte_source_hazard_id')
            if not hazard_id or not self.hazard_engine:
                return None
            
            next_state = (
                qte_result['next_state_success'] if qte_result['success']
                else qte_result['next_state_failure']
            )
            
            if not next_state:
                return None
            
            # Check if next state is terminal
            terminal_response = self._handle_terminal_hazard_state(
                hazard_id, next_state, qte_result
            )
            if terminal_response:
                return terminal_response
            
            # Non-terminal state: defer transition to popup dismiss
            return self._defer_hazard_transition(hazard_id, next_state, qte_result)

        except Exception as e:
            self.logger.error(f"_handle_hazard_state_transition: Error: {e}", exc_info=True)
            return None

    def _handle_terminal_hazard_state(
        self, hazard_id: str, next_state: str, qte_result: dict
    ) -> Optional[dict]:
        """
        Handle terminal hazard state (death or level complete).
        Returns response if terminal, None if not terminal.
        """
        try:
            hazards_master = self.resource_manager.get_data('hazards', {})
            h_def = hazards_master.get(hazard_id, {})
            sdef = h_def.get('states', {}).get(next_state, {})
            
            if not (sdef.get('is_terminal_state') or sdef.get('instant_death_in_room')):
                return None  # Not terminal
            
            is_death = bool(sdef.get('instant_death_in_room') or sdef.get('death_message'))
            popup_message = (
                sdef.get('death_message') if is_death
                else sdef.get('description') or "You survived!"
            )
            popup_title = "Notice" if is_death else "Level Complete"
            
            # Build chained popup (QTE result -> terminal state message -> game over/continue)
            consequence = {
                "type": "show_popup",
                "title": popup_title,
                "message": popup_message,
                "output_panel": True,
                "vfx_hint": "damage" if is_death else None
            }
            
            if is_death:
                consequence["on_close_emit_ui_events"] = [{
                    "event_type": "game_over",
                    "death_reason": popup_message,
                    "final_narrative": self.get_death_narrative()
                }]
                self.is_game_over = True
                self.player.setdefault('death_reason', popup_message)
            
            self.add_ui_event({
                "event_type": "show_popup",
                "priority": 50,
                "title": "QTE Result",
                "message": qte_result['message'],
                "on_close_emit_ui_events": [consequence]
            })
            
            # Handle pending move even in terminal state
            pending_move = self.player.pop('pending_move', None)
            if pending_move:
                return self._execute_move_with_health_check(qte_result, pending_move)
            
            self._update_health_effects()
            return self._build_response()

        except Exception as e:
            self.logger.error(f"_handle_terminal_hazard_state: Error: {e}", exc_info=True)
            return None

    def _defer_hazard_transition(
        self, hazard_id: str, next_state: str, qte_result: dict
    ) -> dict:
        """Defer hazard state change to popup dismiss for non-terminal states."""
        try:
            self.add_ui_event({
                "event_type": "show_popup",
                "priority": 50,
                "title": "QTE Result",
                "message": qte_result['message'],
                "on_close_set_hazard_state": {
                    "hazard_id": hazard_id,
                    "target_state": next_state
                }
            })
            
            # Handle pending move
            pending_move = self.player.pop('pending_move', None)
            if pending_move:
                return self._execute_move_with_health_check(qte_result, pending_move)
            
            self._update_health_effects()
            return self._build_response()

        except Exception as e:
            self.logger.error(f"_defer_hazard_transition: Error: {e}", exc_info=True)
            return self._build_response()

    def _execute_move_with_health_check(self, qte_result: dict, direction: str) -> dict:
        """Execute move and merge with QTE result, updating health effects."""
        try:
            self.logger.info(f"_execute_move_with_health_check: Moving '{direction}' after QTE")
            move_result = self._command_move(direction)
            
            self._update_health_effects()
            
            result = self._build_response()
            result['messages'] = qte_result.get('messages', []) + move_result.get('messages', [])
            result['ui_events'] = self.get_ui_events()
            result['game_state'] = self.get_current_game_state()
            
            return result

        except Exception as e:
            self.logger.error(f"_execute_move_with_health_check: Error: {e}", exc_info=True)
            return self._build_response()

    def _build_qte_result_popup(self, qte_result: dict) -> dict:
        """Build default QTE result popup when no special handling needed."""
        try:
            popup_payload = {
                "event_type": "show_popup",
                "priority": 50,
                "title": "QTE Result",
                "message": qte_result['message']
            }
            
            # Add damage VFX hint if player took damage or died
            if not qte_result.get('success', False) and (
                qte_result.get('hp_damage', 0) > 0 or qte_result.get('is_fatal', False)
            ):
                popup_payload["vfx_hint"] = "damage"
            
            self.add_ui_event(popup_payload)
            self._update_health_effects()
            
            return self._build_response()

        except Exception as e:
            self.logger.error(f"_build_qte_result_popup: Error: {e}", exc_info=True)
            return self._build_response()


    def _low_health_threshold(self) -> int:
        """Low-HP cutoff used for UI pulsing. Default: max(5 HP, 15% of max)."""
        try:
            max_hp = int(self.player.get('max_hp', 30))
            return max(5, int(max_hp * 0.15))
        except Exception:
            return 5

    def add_ui_event(self, event: dict):
        """Adds a UI event to the queue for the GameScreen to process."""
        self.ui_events.append(event)
        self.logger.debug(f"UI Event Added: {event}")

    def get_ui_events(self) -> list:
        """Returns all pending UI events and clears the queue."""
        if not self.ui_events:
            return []
        # Return a copy and clear the original list
        events_to_process = self.ui_events[:]
        self.ui_events.clear()
        return events_to_process

    def process_player_input(self, raw_input: Union[str, dict]) -> dict:
        self.logger.debug(f"process_player_input called with raw_input='{raw_input}' (type: {type(raw_input)})")

        # 1) Handle structured QTE events (dict) FIRST, regardless of qte_active flag
        if isinstance(raw_input, dict):
            if self.qte_engine and self.qte_engine.active_qte:
                result = self.qte_engine.handle_qte_input(raw_input)
                if isinstance(result, dict):
                    self.logger.debug("process_player_input: QTE resolved via dict event; delegating to _handle_qte_resolution")
                    return self._handle_qte_resolution(result)
                return { "messages": [], "game_state": self.get_current_game_state(), "ui_events": self.get_ui_events() }
            self.logger.debug("process_player_input: Dict input received but no active QTE. Ignoring safely.")
            return { "messages": [], "game_state": self.get_current_game_state(), "ui_events": self.get_ui_events() }

        # 2) Guard: if game over, bail out
        if self.is_game_over:
            return { "messages": ["The game is over."], "game_state": self.get_current_game_state(), "ui_events": self.get_ui_events() }

        # Handle text input during QTE
        if self.player.get('qte_active', False) and isinstance(raw_input, str):
            if self.qte_engine and self.qte_engine.active_qte:
                result = self.qte_engine.handle_qte_input(raw_input)
                if result:  # QTE resolved
                    return self._handle_qte_resolution(result)
                return self._build_response()  # QTE still in progress

        verb, target = self._parse_command(raw_input)
        
        # --- NEW LOGIC: PROCESS CONSEQUENCES ---
        interaction_response = {}
        if self.hazard_engine:
            interaction_response = self.hazard_engine.process_player_interaction(verb, target)
            for consequence in interaction_response.get('consequences', []):
                self.handle_hazard_consequence(consequence)
        # --- END NEW LOGIC ---

        if interaction_response.get('blocks_action'):
            response = self._build_response(messages=interaction_response.get('messages', []), turn_taken=True)
        else:
            command_method = self.command_map.get(verb)
            if not command_method:
                response = self._build_response(message="You're not sure how to do that.", turn_taken=False)
            else:
                response = command_method(target)
                response = self._merge_responses(response, interaction_response)

        if response.get('turn_taken', False) and not self.is_game_over:
            end_of_turn_response = self._process_turn_end(verb, target, response.get('success', True))
            response = self._merge_responses(response, end_of_turn_response)

        # --- FINAL ASSEMBLY ---
        final_ui_events = response.get("ui_events", []) + self.get_ui_events()
        result = {
            "messages": response.get("messages", []),
            "game_state": self.get_current_game_state(),
            "ui_events": final_ui_events,
        }
        self.check_game_state_transitions()
        result['ui_events'].extend(self.get_ui_events())
        return result

    def handle_hazard_consequence(self, consequence: dict):
        """Handle a single hazard consequence in proper sequence"""
        ctype = consequence.get("type")
        
        if ctype == "show_popup":
            # Just pass the entire consequence dict as the UI event
            event_data = consequence.copy()
            event_data["event_type"] = "show_popup"
            self.add_ui_event(event_data)
        
        elif ctype == "start_qte":
            if self.qte_engine:
                try:
                    self.qte_engine.start_qte(
                        consequence.get("qte_type"),
                        consequence.get("qte_context", {})
                    )
                except Exception as e:
                    self.logger.error(f"Failed to start QTE: {e}")
        
        elif ctype == "hazard_state_change":
            hazard_id = consequence.get("hazard_id")
            target_state = consequence.get("target_state")
            if hazard_id and target_state:
                result = self.hazard_engine.set_hazard_state(hazard_id, target_state)
                # Recursively handle consequences from the state change
                for sub_consequence in result.get("consequences", []):
                    self.handle_hazard_consequence(sub_consequence)
        
        elif ctype == "game_over":
            self.is_game_over = True
            self.player['death_reason'] = consequence.get("death_reason")
            self.add_ui_event({
                "event_type": "game_over",
                "death_reason": self.player['death_reason'],
                "final_narrative": self.get_death_narrative()
            })

    def _process_turn_end(self, verb: str, target: str, success: bool) -> dict:
        """Handles all events that happen after a player's action. Injected with robust debugging logic."""
        self.logger.debug(f"_process_turn_end called with verb='{verb}', target='{target}', success={success}")
        self.player['turns_left'] -= 1
        self.player['actions_taken'] += 1
        self.logger.debug(f"_process_turn_end: Player turns_left={self.player['turns_left']}, actions_taken={self.player['actions_taken']}")

        messages = []

        if self.hazard_engine:
            self.logger.debug("_process_turn_end: HazardEngine processing turn")
            hazard_response = self.hazard_engine.process_turn()
            self.logger.debug(f"_process_turn_end: HazardEngine response: {hazard_response}")
            messages.extend(hazard_response.get('messages', []))
            if hazard_response.get('death_triggered'):
                self.logger.info("_process_turn_end: Death triggered by HazardEngine")
                # Handle death immediately (logic to be added later)

        if self.death_ai:
            self.logger.debug("_process_turn_end: DeathAI analyzing player action")
            self.death_ai.analyze_player_action(verb, target, self.player['location'], success)
            self.death_ai.decay_fear()
            hallucination = self.death_ai.get_fear_hallucination()
            if hallucination:
                self.logger.info(f"_process_turn_end: Level {self.player.get('current_level', 1)} hallucination triggered: {hallucination}")
                messages.append(color_text(hallucination, 'special', self.resource_manager))

        # Add Death's Breath manifestation when fear is very high
        if self.death_ai and self.player.get('fear', 0) > 0.75:
            if random.random() < 0.3:  # 30% chance when fear is very high
                current_room = self.player.get('location')
                self.death_ai.manifest_deaths_presence(current_room)

        # --- CANONICAL GAME OVER HANDLING ---
        if self.player['hp'] <= 0:
            self.is_game_over = True
            if not self.player.get('death_reason'):
                self.player['death_reason'] = "Your injuries are too severe. You succumb to the darkness."
            self.logger.info("_process_turn_end: Player HP <= 0, game over")
            self.add_ui_event({
                "event_type": "game_over",
                "death_reason": self.player['death_reason'],
                "final_narrative": self.get_death_narrative()
            })
        elif self.player['turns_left'] <= 0:
            self.is_game_over = True
            if not self.player.get('death_reason'):
                self.player['death_reason'] = "You've run out of time. You feel a cold presence behind you..."
            self.logger.info("_process_turn_end: Player ran out of turns, game over")
            self.add_ui_event({
                "event_type": "game_over",
                "death_reason": self.player['death_reason'],
                "final_narrative": self.get_death_narrative()
            })

        self.logger.debug(f"_process_turn_end: Returning messages: {messages}, is_game_over={self.is_game_over}")
        return self._build_response(messages=messages)

    # --- NEW: Response Formatting ---

    def _build_response(self, message: Optional[str] = None, turn_taken: bool = False,
                        success: Optional[bool] = None, messages: Optional[list] = None,
                        ui_events: Optional[list] = None, game_state: Optional[dict] = None, **extras) -> dict:
        """
        A helper to construct the standard response dictionary, now with UI events and map refresh.
        Injected with robust debugging logic.
        """
        self.logger.debug(f"_build_response called with message='{message}', turn_taken={turn_taken}, success={success}, messages={messages}, ui_events={ui_events}")
        # Compose messages list
        response_messages = list(messages or [])
        if message:
            if isinstance(message, str):
                response_messages.insert(0, message)
            elif isinstance(message, list):
                response_messages = message + response_messages
        # Compose UI events and ensure map refresh on turn
        ui_events = list(ui_events or [])
        if turn_taken:
            ui_events.append({"event_type": "refresh_map"})
        # Build response dict
        response = {
            "messages": response_messages,
            "turn_taken": turn_taken,
            "success": success if success is not None else True,
            "ui_events": ui_events
        }
        # Optionally include game_state
        if game_state:
            response["game_state"] = game_state
        else:
            response["game_state"] = self.get_current_game_state()
        # Merge any extras
        response.update(extras or {})
        self.logger.debug(f"_build_response returning: {response}")
        return response

    def _merge_responses(self, r1: dict, r2: dict) -> dict:
        """Merges two response dictionaries, now including ui_events."""
        merged = r1.copy()
        merged['messages'] = r1.get('messages', []) + r2.get('messages', [])
        
        # --- NEW: Also merge the ui_events list ---
        merged['ui_events'] = r1.get('ui_events', []) + r2.get('ui_events', [])
        
        for key in ['is_game_over', 'game_won']:
            if key in r2:
                merged[key] = r2[key]
        return merged

    def _player_can_see_omens(self) -> bool:
        """
        Checks if the current player character has the ability to see omens.
        Medium and You: always see omens.
        All others: chance based on perception stat.
        """
        char_class = self.player.get('character_class')
        if char_class in ("Medium", "You"):
            self.logger.debug(f"_player_can_see_omens: {char_class} always sees omens.")
            return True
        else:
            # Use perception stat as percent chance (e.g., 3 = 60%, 5 = 95% max)
            perception = self._get_stat('perception', 1)
            chance = min(perception * 0.2, 0.95)  # e.g., 3 = 60%, 5 = 95% max
            roll = random.random()
            can_see = roll < chance
            self.logger.debug(f"_player_can_see_omens: {char_class} perception={perception}, roll={roll:.2f}, chance={chance:.2f}, can_see={can_see}")
            return can_see

    def _make_first_entry_popup_event(self, room_id: str, text: str) -> dict:
        """Builds the UI event dictionary for a first-entry popup."""
        # PATCH: Always return a dict (even if text is empty, for consistency)
        if text:
            return {
                "event_type": "show_popup",
                "title": room_id.replace("_", " ").title(),
                "message": text
            }
        else:
            # Return empty dict instead of None to avoid list comprehension issues
            return {}

    def get_current_game_state(self) -> dict:
        """Returns a snapshot of the current game state for the UI. Injected with robust debugging logic."""
        player_location = self.player.get('location')
        room_desc = self.current_level_rooms_world_state.get(player_location, {}).get('description')
        state = {
            "player": self.player,
            "current_room_description": room_desc,
            "is_game_over": self.is_game_over,
            "game_won": self.game_won
        }
        self.logger.debug(f"get_current_game_state returning: {state}")
        return state

    def get_initial_ui_state(self) -> dict:
        """Returns the initial UI state. Injected with robust debugging logic."""
        state = self.get_current_game_state()
        self.logger.debug(f"get_initial_ui_state returning: {state}")
        return state

    def _build_room_coordinate_map(self, start_room_id: str):
        """
        Dynamically builds a 2D coordinate map of the level using a breadth-first search.
        This allows for map generation without needing coordinates in the JSON data.
        """
        self.logger.info("Building room coordinate map...")
        self.current_level_coord_map = {}
        q = [(start_room_id, 0, 0)] # A queue of (room_id, x, y)
        visited = {start_room_id}

        while q:
            room_id, x, y = q.pop(0)
            self.current_level_coord_map[room_id] = (x, y)
            
            room_data = self.get_room_data(room_id) or {}
            exits = room_data.get('exits', {})

            for direction, dest_id in exits.items():
                if isinstance(dest_id, dict): continue # Skip complex/locked exits for now
                if dest_id not in visited:
                    visited.add(dest_id)
                    dx, dy = {'north': (0, 1), 'south': (0, -1), 'east': (1, 0), 'west': (-1, 0)}.get(direction, (0, 0))
                    q.append((dest_id, x + dx, y + dy))
        self.logger.info(f"Coordinate map built with {len(self.current_level_coord_map)} locations.")

    def _generate_map_string(self, radius: int = 2) -> str:
        """Generates a text-based map string centered on the player."""
        if not hasattr(self, 'current_level_coord_map'): return "Map data not available."
        
        player_loc = self.player.get('location')
        if not player_loc or player_loc not in self.current_level_coord_map:
            return "Current location unknown."

        px, py = self.current_level_coord_map[player_loc]
        
        # Create a reverse mapping from coordinates to room_id for quick lookups
        coord_to_room = {v: k for k, v in self.current_level_coord_map.items()}
        
        map_str = ""
        for y in range(py + radius, py - radius - 1, -1):
            row_str = ""
            for x in range(px - radius, px + radius + 1):
                is_player = (x == px and y == py)
                room_id = coord_to_room.get((x, y))

                if is_player:
                    row_str += f"[{color_text('P', 'error', self.resource_manager)}]"
                elif room_id:
                    if room_id in self.player['visited_rooms']:
                        row_str += "[ ]"
                    else:
                        # Check if adjacent to a visited room to show it as '?'
                        is_adjacent = False
                        for dx, dy in [(0,1), (0,-1), (1,0), (-1,0)]:
                            if coord_to_room.get((x+dx, y+dy)) in self.player['visited_rooms']:
                                is_adjacent = True
                                break
                        row_str += "[?]" if is_adjacent else "   "
                else:
                    row_str += "   "
            map_str += row_str + "\n"
            
        return map_str

    def get_gui_map_string(self, width=None) -> str:
        """
        Text 3x3 map centered on player. Uses LIVE world state so hazard lock flags are shown.
        """
        rm = self.resource_manager
        current_room_id = self.player.get('location')
        if not current_room_id:
            return "Current location unknown."
        current_room = self.get_room_data(current_room_id) or {}
        # Visibility gate
        vis = current_room.get("visibility", "normal")
        if vis in ["dark", "pitch_black", "zero"] and not self._player_has_active_light_source():
            return color_text("It is too dark to read your map.", "warning", rm)

        exits = current_room.get("exits", {})
        n = exits.get('north')
        s = exits.get('south')
        e = exits.get('east')
        w = exits.get('west')

        # Pull adjacent rooms from LIVE world state, not master templates
        def live_room(exit_value):
            if not exit_value:
                return None, None
            if isinstance(exit_value, dict):
                return exit_value, None
            # (room_data, room_key)
            return self.current_level_rooms_world_state.get(exit_value), exit_value

        north_room, n_key = live_room(n)
        south_room, s_key = live_room(s)
        east_room,  e_key = live_room(e)
        west_room,  w_key = live_room(w)

        def sym(room_data, room_key):
            if not room_data:
                return '   '
            locking = room_data.get("locking", {})
            is_locked = bool(locking.get("locked") or room_data.get("locked") or room_data.get("locked_by_mri"))
            if is_locked:
                return color_text('[X]', 'error', rm)
            if room_key and room_key in self.player.get("visited_rooms", set()):
                return '[ ]'
            return ' ? '

        grid = [
            ['   ', sym(north_room, n_key), '   '],
            [sym(west_room, w_key), color_text('[P]', 'success', rm), sym(east_room, e_key)],
            ['   ', sym(south_room, s_key), '   ']
        ]

        lines = [color_text(f"--- Map centered on: {current_room_id.replace('_', ' ')} ---", "info", rm)]
        for row in grid:
            lines.append(" ".join(row))
        lines.append("\n" + color_text("Legend:", "info", rm))
        lines.append(f"  {color_text('[P]', 'success', rm)} - Your Position")
        lines.append("  [ ] - Visited Room")
        lines.append(f"  {color_text('[X]', 'error', rm)} - Locked Door")
        lines.append("  ?   - Unvisited")
        return "\n".join(lines)

    def _player_has_active_light_source(self) -> bool:
        """Check if player has a working light source."""
        inventory = self.player.get('inventory', {})
        items_master = self.resource_manager.get_data('items', {})
        
        for item_key in inventory:
            item_data = items_master.get(item_key, {})
            if item_data.get('provides_light') and not item_data.get('broken', False):
                return True
        return False

    def get_valid_directions(self):
        """
        Returns a list of valid movement directions (strings) from the current room.
        - Robust: Handles missing player/location, malformed room data, and extensible for special exits.
        - Extensible: Ready for future expansion (e.g., locked exits, context-sensitive directions).
        Injected with robust debugging logic.
        """
        if not self.player or 'location' not in self.player:
            self.logger.warning("get_valid_directions: Player or location not set.")
            return []

        current_room_data = self._get_current_room_data()
        if not current_room_data or not isinstance(current_room_data.get("exits"), dict):
            self.logger.warning(f"get_valid_directions: No valid exits found for room '{self.player.get('location')}'.")
            return []

        # --- 1. Gather standard exits ---
        directions = list(current_room_data["exits"].keys())
        self.logger.debug(f"get_valid_directions: Standard exits found: {directions}")

        # --- 2. Optionally include special exits (future extensibility) ---
        special_exits = current_room_data.get("special_exits", {})
        if isinstance(special_exits, dict):
            special_keys = [d for d in special_exits.keys() if d not in directions]
            directions.extend(special_keys)
            self.logger.debug(f"get_valid_directions: Special exits added: {special_keys}")

        self.logger.debug(f"get_valid_directions: Final directions list: {directions}")
        return directions

    # --- NEW: NORMALIZATION & ENTITY COLLECTION HELPERS ---
    def _norm(self, s: str) -> str:
        """Normalize names for matching: lowercase, strip, collapse spaces/underscores."""
        if not isinstance(s, str): return ""
        s = s.strip().lower()
        return re.sub(r'[\s_]+', ' ', s)

    def _get_all_visible_entities_in_room(self, room_name: str) -> dict:
        """
        Gathers all visible entities: furniture, objects, loose items, and hazard-spawned entities.
        Returns them in a structured dictionary.
        """
        all_entities = {'furniture': [], 'objects': [], 'items': []}
        room_data = self.get_room_data(room_name)
        if not room_data:
            return all_entities

        # Furniture
        for f_data in room_data.get('furniture', []):
            if isinstance(f_data, dict) and 'name' in f_data:
                desc = (
                    f_data.get('description') or
                    f_data.get('examine_details') or
                    "It's a piece of furniture."
                )
                entity = f_data.copy()
                entity['description'] = desc
                all_entities['furniture'].append(entity)

        # Static objects
        for o_data in room_data.get('objects', []):
            if isinstance(o_data, dict) and 'name' in o_data:
                desc = (
                    o_data.get('description') or
                    o_data.get('examine_details') or
                    "It's an object."
                )
                entity = o_data.copy()
                entity['description'] = desc
                all_entities['objects'].append(entity)

        # Loose items in the room
        items_master = self.resource_manager.get_data('items', {})
        for item_key, item_state in self.current_level_items_world_state.items():
            if item_state.get('location') == room_name:
                item_data = items_master.get(item_key, {})
                desc = (
                    item_data.get('description') or
                    item_data.get('examine_details') or
                    "An item."
                )
                entity = {
                    "name": item_data.get('name', item_key),
                    "description": desc,
                    "type": "item",
                    "id_key": item_key,
                    "data": item_data
                }
                all_entities['items'].append(entity)

        # Hazard-spawned entities
        if self.hazard_engine:
            hazards_master = self.resource_manager.get_data('hazards', {})
            active_hazard_keys = self.hazard_engine.get_active_hazards_for_room(room_name)
            for h_key in active_hazard_keys:
                h_def = hazards_master.get(h_key, {})
                for entity_name in h_def.get("spawn_entities", []):
                    entity_type = h_def.get("entity_type", "object")
                    if isinstance(entity_name, dict):
                        entity_name_str = entity_name.get('name') or str(entity_name)
                    else:
                        entity_name_str = str(entity_name)
                    examine_responses = h_def.get("examine_responses", {})
                    desc = (
                        examine_responses.get(entity_name_str, {}).get("base_description") or
                        h_def.get('description') or
                        "It is a product of the hazard in this room."
                    )
                    entity_data = {
                        "name": entity_name_str,
                        "description": desc,
                        "type": "hazard_entity",
                        "hazard_key": h_key
                    }
                    if entity_type == "item":
                        all_entities['items'].append(entity_data)
                    else:
                        all_entities['objects'].append(entity_data)
        return all_entities

    # --- REFINED: The Definitive Entity Finder ---
    def _find_entity_in_room(self, target_str: str, room_name: str) -> Optional[dict]:
        """Finds any entity in the room or inventory with flexible name matching."""
        target_norm = self._norm(target_str)
        if not target_norm:
            return None

        # Priority 1: Player Inventory
        for item_key in self.player.get('inventory', []):
            if self._norm(self._get_item_display_name(item_key)) == target_norm:
                master_data = self.resource_manager.get_data('items', {}).get(item_key, {})
                return {
                    'id_key': item_key,
                    'name': self._get_item_display_name(item_key),
                    'type': 'item_inventory',
                    'data': master_data
                }

        visible_entities = self._get_all_visible_entities_in_room(room_name)

        # Priority 2: Furniture
        for f_data in visible_entities['furniture']:
            if self._norm(f_data.get('name', '')) == target_norm:
                return {
                    'id_key': f_data['name'],
                    'name': f_data['name'].replace('_', ' ').capitalize(),
                    'type': 'furniture',
                    'data': f_data
                }

        # Priority 3: Room Objects (static and hazard-spawned)
        for o_data in visible_entities['objects']:
            # Support matching by name and aliases
            aliases = [self._norm(a) for a in o_data.get('aliases', [])]
            if self._norm(o_data.get('name', '')) == target_norm or target_norm in aliases:
                return {
                    'id_key': o_data.get('id_key', o_data.get('name')),
                    'name': o_data['name'].replace('_', ' ').capitalize(),
                    'type': o_data.get('type', 'object'),
                    'data': o_data
                }
            # Also match hazard-spawned entities by their name
            if o_data.get('type') == 'hazard_entity':
                # --- FIX: Ensure entity_name is a string before using as key ---
                entity_name = o_data.get('name', '')
                if isinstance(entity_name, dict):
                    entity_name_str = entity_name.get('name') or str(entity_name)
                else:
                    entity_name_str = str(entity_name)
                if self._norm(entity_name_str) == target_norm:
                    return {
                        'id_key': o_data.get('hazard_key', entity_name_str),
                        'name': entity_name_str.replace('_', ' ').capitalize(),
                        'type': 'hazard_entity',
                        'data': o_data
                    }

        # Priority 4: Loose Items
        for item_key, world_data in self.current_level_items_world_state.items():
            if world_data.get("location") == room_name:
                if self._norm(self._get_item_display_name(item_key)) == target_norm:
                    master_data = self.resource_manager.get_data('items', {}).get(item_key, {})
                    return {
                        'id_key': item_key,
                        'name': self._get_item_display_name(item_key),
                        'type': 'item',
                        'data': master_data
                    }

        return None

    # --- NPC helpers ---
    def _find_npc_in_room(self, npc_name: str, room_id: str) -> Optional[dict]:
        room = self.get_room_data(room_id) or {}
        npcs = room.get('npcs', []) or []
        target_norm = self._norm(npc_name or "")
        for npc in npcs:
            name = npc.get('name', '')
            if self._norm(name) == target_norm:
                return npc
        return None

    def _npc_key(self, npc: dict) -> str:
        return npc.get('id') or npc.get('name')

    def _get_npc_state(self, npc: dict) -> str:
        key = self._npc_key(npc)
        return self.player.get('npc_states', {}).get(key, npc.get('initial_state'))

    def _set_npc_state(self, npc: dict, state: str):
        key = self._npc_key(npc)
        self.player.setdefault('npc_states', {})[key] = state

    # --- REFINED: Perception Methods ---
    def _get_rich_room_description(self, room_id: str) -> str:
        """
        Compiles a full description, now correctly passing the resource_manager
        to all color_text calls. Now includes NPCs present in the room.
        Ensures NPCs' visible state is updated by calling _resolve_npc_dialogue_entry_state.
        """
        room_data = self.get_room_data(room_id)
        if not room_data:
            return "You are in a featureless void."

        rm = self.resource_manager

        description = f"[b]{color_text(room_id, 'room', rm)}[/b]\n"
        description += room_data.get('description', '')

        visible_entities = self._get_all_visible_entities_in_room(room_id)
        furniture_names = [f['name'] for f in visible_entities['furniture']]

        # Hide Death’s Breath manifestations from the room list, but keep them present/targetable.
        # Also: filter out duplicate objects by name (case-insensitive).
        filtered_objects = []
        seen_object_names = set()
        for o in visible_entities['objects']:
            obj_name_norm = str(o.get('name', '')).strip().lower()
            hidden_names = set()  # Ensure hidden_names is always defined
            # Hide Death's Breath manifestations from the room list
            if o.get('type') == 'hazard_entity' and o.get('hazard_key') in HIDDEN_ROOM_LIST_BY_HAZARD:
                hidden_names = {n.lower() for n in HIDDEN_ROOM_LIST_BY_HAZARD[o['hazard_key']]}
            if obj_name_norm in hidden_names:
                continue  # don’t list this in “You see:”
            # Filter out duplicates
            if obj_name_norm in seen_object_names:
                continue
            seen_object_names.add(obj_name_norm)
            filtered_objects.append(o)

        object_names = [o['name'] for o in filtered_objects]

        # --- NEW: NPCs ---
        npc_names = []
        for npc in room_data.get('npcs', []):
            name = npc.get('name')
            if name:
                # Ensure NPC state is up to date for current world/hazard conditions
                self._resolve_npc_dialogue_entry_state(npc, room_id)
                npc_names.append(color_text(name, 'npc', rm))

        if furniture_names or object_names or npc_names:
            formatted_furniture = [color_text(name.replace('_', ' '), 'furniture', rm) for name in furniture_names]
            formatted_objects = [name.replace('_', ' ') for name in object_names]
            entity_list = formatted_furniture + formatted_objects
            if npc_names:
                entity_list += npc_names
            description += f"\n\nYou see: {', '.join(entity_list)}."

        exits = room_data.get('exits', {})
        if exits:
            exit_texts = []
            for direction, dest_room in exits.items():
                if isinstance(dest_room, dict):
                    dest_name = "[blocked]"
                else:
                    dest_name = color_text(str(dest_room).replace('_', ' '), 'room', rm)
                exit_texts.append(f"{color_text(direction, 'exit', rm)} ({dest_name})")
            description += f"\nExits: {', '.join(exit_texts)}."

        return description

    def get_available_targets(self, verb: str) -> list:
        """
        Returns valid targets for a verb, now including all visible entities.
        Injected with robust logging and error handling.
        """
        try:
            current_room_id = self.player.get('location')
            if not current_room_id:
                self.logger.warning("get_available_targets: No current room set for player.")
                return []

            if verb in ('move', 'go'):
                room_data = self.get_room_data(current_room_id)
                if not room_data:
                    self.logger.warning(f"get_available_targets: No data for current room '{current_room_id}'.")
                    return []
                exits = room_data.get('exits', {})
                self.logger.debug(f"get_available_targets: Exits for move/go: {list(exits.keys())}")
                return sorted(list(exits.keys()))

            targets = set()
            visible = self._get_all_visible_entities_in_room(current_room_id)
            items_master = self.resource_manager.get_data('items', {})

            if verb in ('examine', 'look', 'inspect'):
                for f in visible['furniture']:
                    targets.add(f['name'])
                for o in visible['objects']:
                    targets.add(o['name'])
                for item_key, world_data in self.current_level_items_world_state.items():
                    if world_data.get("location") == current_room_id:
                        targets.add(self._get_item_display_name(item_key))
                self.logger.debug(f"get_available_targets: Examine targets: {targets}")

            elif verb in ('search',):
                for f in visible['furniture']:
                    if f.get('is_container'):
                        targets.add(f['name'])
                self.logger.debug(f"get_available_targets: Search targets: {targets}")

            elif verb in ('take', 'get'):
                # 1) Loose items in the room (takeable)
                for item_key, world_data in self.current_level_items_world_state.items():
                    if world_data.get("location") == current_room_id:
                        item_data = items_master.get(item_key, {})
                        if item_data.get("takeable", False):
                            targets.add(self._get_item_display_name(item_key))

                # 2) Items in containers that have been searched (use exact flag id)
                room_data = self.get_room_data(current_room_id) or {}
                for furniture in room_data.get('furniture', []):
                    if isinstance(furniture, dict) and furniture.get('is_container'):
                        flag_name = f"searched_{furniture.get('name', '')}"  # exact id key, no normalization
                        if flag_name in self.interaction_flags:
                            for val in furniture.get('items', []):
                                # Map 'val' to an item master entry (val can be item key or display name)
                                for key, data in items_master.items():
                                    if (
                                        val == key
                                        or self._norm(val) == self._norm(key)
                                        or self._norm(val) == self._norm(data.get('name', ''))
                                    ):
                                        if data.get("takeable", False):
                                            targets.add(data.get('name', key))
                                        break

                if targets:
                    targets.add("all")
                self.logger.debug(f"get_available_targets: Take targets: {targets}")

            elif verb == 'use':
                # 1. Inventory items (existing logic)
                for item_key in self.player.get('inventory', []):
                    targets.add(self._get_item_display_name(item_key))

                # 2. Room objects/furniture/hazards with a 'use' interaction
                visible = self._get_all_visible_entities_in_room(current_room_id)
                hazards_master = self.resource_manager.get_data('hazards', {})

                # Gather all on_target_names for all active hazards in this room
                active_hazards = []
                if self.hazard_engine:
                    active_hazards = self.hazard_engine.get_active_hazards_for_room(current_room_id)
                use_targets = set()
                for hazard_key in active_hazards:
                    h_def = hazards_master.get(hazard_key, {})
                    use_rules = h_def.get('player_interaction', {}).get('use', [])
                    for rule in use_rules:
                        on_names = rule.get('on_target_name', [])
                        if isinstance(on_names, str):
                            on_names = [on_names]
                        use_targets.update(self._norm(n) for n in on_names)

                # For each visible object/furniture, check if its name or alias matches any on_target_name
                for entity in visible['objects'] + visible['furniture']:
                    names_to_check = [self._norm(entity.get('name', ''))]
                    aliases = entity.get('aliases', [])
                    if aliases:
                        names_to_check.extend(self._norm(a) for a in aliases)
                    if any(n in use_targets for n in names_to_check):
                        targets.add(entity['name'])
                self.logger.debug(f"get_available_targets: Use targets: {targets}")

            # NEW: Unlock targets (key-locked exits/furniture only)
            if verb == 'unlock':
                room = self.get_room_data(current_room_id) or {}
                # exits
                for direction, dest in (room.get('exits') or {}).items():
                    if not isinstance(dest, str):
                        continue
                    dest_master = self.get_room_data(dest) or {}
                    locking = dest_master.get('locking', {}) if isinstance(dest_master.get('locking'), dict) else {}
                    if locking.get('locked'):
                        targets.add(direction)
                # furniture
                for f in (room.get('furniture') or []):
                    if isinstance(f, dict) and (f.get('locked') or (isinstance(f.get('locking'), dict) and f['locking'].get('locked'))):
                        targets.add(f.get('name', 'Locked Object'))

            # NEW: Force targets (locked exits or breakable/forceable/locked furniture)
            if verb == 'force':
                room = self.get_room_data(current_room_id) or {}
                # exits
                for direction, dest in (room.get('exits') or {}).items():
                    if not isinstance(dest, str):
                        continue
                    dest_live = self.current_level_rooms_world_state.get(dest, {}) or {}
                    dest_master = self.get_room_data(dest) or {}
                    locking = dest_master.get('locking', {}) if isinstance(dest_master.get('locking'), dict) else {}
                    key_locked = bool(locking.get('locked'))
                    mri_locked = bool(dest_live.get('locked_by_mri') or dest_master.get('locked_by_mri'))
                    if key_locked or mri_locked or dest_master.get('forceable'):
                        targets.add(direction)
                # furniture
                for f in (room.get('furniture') or []):
                    if not isinstance(f, dict):
                        continue
                    if f.get('locked') or f.get('forceable') or f.get('is_breakable'):
                        targets.add(f.get('name', 'Sturdy Object'))

            # NEW: Talk targets = NPC names in room
            if verb == 'talk':
                room = self.get_room_data(current_room_id) or {}
                npc_names = [n.get('name') for n in room.get('npcs', []) if n.get('name')]
                self.logger.debug(f"get_available_targets: Talk targets: {npc_names}")
                return npc_names

            # NEW: Respond targets = available option numbers
            if verb == 'respond':
                opts = (self.last_dialogue_context or {}).get('options', []) or []
                option_numbers = [str(i + 1) for i in range(len(opts))]
                self.logger.debug(f"get_available_targets: Respond targets: {option_numbers}")
                return option_numbers

            result = sorted([t.replace('_', ' ') for t in targets])
            self.logger.debug(f"get_available_targets: Final targets for verb '{verb}': {result}")
            return result

        except Exception as e:
            self.logger.error(f"get_available_targets: Error for verb '{verb}': {e}", exc_info=True)
            return []

    # --- NEW: Hazard Scripture Reader ---
    def _hazard_examine_text(self, hazard_key: str, target_name: str, room_name: str) -> Optional[str]:
        """
        Pulls a contextual examine message from a hazard's interaction rules based on its current state.
        Injected with robust logging and error handling.
        """
        try:
            self.logger.debug(f"_hazard_examine_text called with hazard_key='{hazard_key}', target_name='{target_name}', room_name='{room_name}'")
            hazards_master = self.resource_manager.get_data('hazards', {})
            h_def = hazards_master.get(hazard_key, {})
            if not h_def:
                self.logger.warning(f"_hazard_examine_text: No hazard definition found for key '{hazard_key}'")
                return None

            curr_state = None
            if self.hazard_engine:
                try:
                    curr_state = self.hazard_engine.get_hazard_state(hazard_key, room_name)
                except Exception as e:
                    self.logger.error(f"_hazard_examine_text: Error getting hazard state: {e}", exc_info=True)
            if not curr_state:
                curr_state = h_def.get("initial_state")
            self.logger.debug(f"_hazard_examine_text: Current state for hazard '{hazard_key}' in room '{room_name}' is '{curr_state}'")

            rules = h_def.get("player_interaction", {}).get("examine", [])
            target_norm = self._norm(target_name)
            self.logger.debug(f"_hazard_examine_text: Normalized target name: '{target_norm}'")

            for rule in rules:
                on_names_norm = [self._norm(n) for n in rule.get("on_target_name", [])]
                required_states = rule.get("requires_hazard_state", [])
                self.logger.debug(f"_hazard_examine_text: Checking rule with on_names_norm={on_names_norm}, required_states={required_states}")
                if target_norm in on_names_norm and curr_state in required_states:
                    msg = rule.get("message")
                    self.logger.info(f"_hazard_examine_text: Matched rule for '{target_name}' in state '{curr_state}': {msg}")
                    return msg
            self.logger.debug(f"_hazard_examine_text: No matching examine rule found for '{target_name}' in state '{curr_state}'")
            return None
        except Exception as e:
            self.logger.error(f"_hazard_examine_text: Unexpected error: {e}", exc_info=True)
            return None

    def check_game_state_transitions(self):
        """Check if the game should transition to end screens and trigger UI events."""
        if self.is_game_over:
            if self.game_won:
                # Player completed all levels
                self.add_ui_event({
                    "event_type": "game_won",
                    "final_score": self.player.get('score', 0)
                })
            else:
                # Player died
                death_reason = self.player.get('death_reason', 'Death caught up with you.')
                self.add_ui_event({
                    "event_type": "game_over",
                    "death_reason": death_reason,
                    "final_narrative": self.get_death_narrative()
                })
            return

        # Notify when requirements met (unchanged)
        if self.check_level_exit_available():
            level_requirements = self.resource_manager.get_data('level_requirements', {})
            current_level = self.player.get('current_level', 1)
            current_level_req = level_requirements.get(str(current_level), {})
            exit_room = current_level_req.get('exit_room', 'UNKNOWN')
            
            if not self.player.get('notified_requirements_met'):
                popup_message = f"You have collected all required items! You may now exit the level via the {exit_room.replace('_', ' ').title()}."
                self.add_ui_event({
                    "event_type": "show_popup",
                    "title": "Level Exit Available",
                    "message": popup_message
                })
                self.player['notified_requirements_met'] = True  # ensure single notification
            return

        # NEW: prevent accidental level completion if requirements are not met
        if self.check_level_completion():
            try:
                met, _missing = self._requirements_met_for_level_exit()
            except Exception:
                met = False
            if not met and not self.player.get('override_requirements', False):
                self.logger.warning("check_game_state_transitions: Level completion requested but requirements are not met; blocking transition.")
                return

            # proceed with original completion UI event
            level_data = self.get_level_completion_data()
            if not isinstance(level_data, dict):
                self.logger.error("check_game_state_transitions: unexpected non-dict level_data; using defaults.")
                level_data = {}
            self.add_ui_event({
                "event_type": "level_complete",
                "level_name": level_data.get('level_name', 'Unknown Area'),
                "narrative": level_data.get('narrative', 'You survived this area.'),
                "score": self.player.get('score', 0),  # Use current player score
                "turns_taken": self.player.get('actions_taken', 0),  # Use current actions taken
                "evidence_count": len(self.player.get('inventory', [])),  # Use current inventory count
                "evaded_hazards": self.player.get('evaded_hazards', []),  # Use current evaded hazards
                "next_level_id": level_data.get('next_level_id'),
                "next_start_room": level_data.get('next_start_room')
            })

    def check_level_exit_available(self) -> bool:
        """
        Returns True if all level exit requirements are met (items/evidence found).
        This only triggers a popup, not a level transition.
        Ensures the player is only notified once per level.
        """
        requirements_met, _ = self._requirements_met_for_level_exit()
        # Only return True if requirements are met and player has NOT already been notified
        return requirements_met and not self.player.get('notified_requirements_met', False)

    def check_level_completion(self) -> bool:
        """
        Returns True if the player has actually triggered the level exit (e.g., reached exit room or set flag).
        """
        # Fallback: Check if player reached an exit trigger
        return self.player.get('level_complete_flag', False)

    def _requirements_met_for_level_exit(self) -> Tuple[bool, list]:
        """
        Determine if level exit requirements are met.
        Returns (requirements_met: bool, missing: List[str]).
        Integrates inventory normalization and next-level info.
        """
        self.logger.debug("_requirements_met_for_level_exit: evaluating requirements")
        level_requirements = self.resource_manager.get_data('level_requirements', {})
        current_level = self.player.get('current_level', 1)
        reqs = level_requirements.get(str(current_level), {}) or {}

        items_needed = list(reqs.get('items_needed', []) or [])
        evidence_needed = list(reqs.get('evidence_needed', []) or [])

        # If no explicit requirements are authored, do not auto-complete via this path
        if not items_needed and not evidence_needed:
            self.logger.debug("_requirements_met_for_level_exit: no requirements authored; returning (False, []) to avoid premature completion")
            return False, []

        # Normalize inventory to a set of ids and names
        inv = self.player.get('inventory', {})
        have_norm: Set[str] = set()

        def _norm(s: str) -> str:
            try:
                return (s or "").strip().lower().replace("’", "'")
            except Exception:
                return str(s).lower()

        if isinstance(inv, dict):
            for item_id, data in inv.items():
                have_norm.add(_norm(item_id))
                if isinstance(data, dict):
                    name = data.get('name') or data.get('display_name')
                    if name:
                        have_norm.add(_norm(name))
        elif isinstance(inv, list):
            for entry in inv:
                if isinstance(entry, str):
                    have_norm.add(_norm(entry))
                elif isinstance(entry, dict):
                    for key in ('id', 'item_id', 'name', 'display_name', 'key'):
                        if key in entry and entry[key]:
                            have_norm.add(_norm(entry[key]))

        missing: List[str] = []
        for need in items_needed:
            if _norm(need) not in have_norm:
                missing.append(str(need))
        for need in evidence_needed:
            if _norm(need) not in have_norm:
                missing.append(str(need))

        met = len(missing) == 0
        self.logger.info(f"_requirements_met_for_level_exit: met={met}, missing={missing}")
        return met, missing

    def get_level_completion_data(self) -> dict:
        """
        Returns a dict with level completion info, integrating normalized inventory and next-level logic.
        """
        level_id = int(self.player.get('current_level', 1) or 1)
        rm = self.resource_manager
        levels_cfg = rm.get_data('level_requirements', {}) or {}
        rooms_all = rm.get_data('rooms', {}) or {}

        cfg = levels_cfg.get(str(level_id), {}) or {}
        next_level_id = cfg.get('next_level_id') or (str(level_id + 1) if str(level_id + 1) in rooms_all else None)
        next_start = cfg.get('next_level_start_room')
        if next_level_id and not next_start:
            next_cfg = levels_cfg.get(str(next_level_id), {}) or {}
            next_start = next_cfg.get('entry_room') or next_cfg.get('next_level_start_room')

        # Normalize inventory keys
        inv = self.player.get('inventory', {}) or {}
        inv_keys = set()
        if isinstance(inv, dict):
            inv_keys = set(inv.keys())
        elif isinstance(inv, list):
            for v in inv:
                if isinstance(v, str):
                    inv_keys.add(v)
                elif isinstance(v, dict):
                    for k in ('id', 'item_id', 'key', 'name'):
                        if k in v and v[k]:
                            inv_keys.add(v[k])

        needed = set(cfg.get('evidence_needed', []) or [])
        return {
            "level_name": cfg.get('level_name') or cfg.get('name') or f"Level {level_id}",
            "narrative": cfg.get('completion_narrative', "You survived. Take a breath..."),
            "score": int(self.player.get('score', 0) or 0),
            "turns_taken": int(self.player.get('actions_taken', 0) or 0),
            "evidence_count": len(inv_keys & needed),
            "evaded_hazards": self.player.get('evaded_hazards', []),
            "next_level_id": next_level_id,
            "next_start_room": next_start,
        }

    # --- NEW: Command Helpers ---
    def _parse_command(self, raw_input: str) -> Tuple[str, str]:
        """Parses raw string input into a verb and a target (case-insensitive). Injected with robust debugging logic."""
        self.logger.debug(f"_parse_command called with raw_input='{raw_input}'")
        parts = raw_input.strip().split()
        self.logger.debug(f"_parse_command: Split parts: {parts}")
        if not parts:
            self.logger.warning("_parse_command: No input provided.")
            return None, None
        verb = parts[0].lower()
        target = " ".join(parts[1:]).lower() if len(parts) > 1 else ""
        self.logger.debug(f"_parse_command: Parsed verb='{verb}', target='{target}'")
        return verb, target
    
    def _parse_use_command(self, target_str: str) -> dict:
        """Parses the 'use' command into an item and an optional target."""
        match = re.match(r"(.+?)\s+on\s+(.+)", target_str, re.IGNORECASE)
        if match:
            return {"item_name": match.group(1).strip(), "target_name": match.group(2).strip()}
        else:
            return {"item_name": target_str.strip(), "target_name": None}

    #--- Room Interactable Triggers ---
    def _try_trigger_room_interactable_use(self, target_name: str) -> bool:
        """
        Handles room-level interactable triggers for the 'use' verb.
        Canonical logic mirrors _try_trigger_room_interactable_examine.
        Returns True if a trigger was processed (even if requirements not met).
        """
        room_id = self.player.get('location')
        if not room_id:
            return False

        level_id = str(self.player.get('current_level', 1))
        rooms_key = f"rooms_level_{level_id}"
        rooms_data = self.resource_manager.get_data(rooms_key, {}) or {}
        room_def = rooms_data.get(room_id) or self.current_level_rooms_world_state.get(room_id, {}) or {}
        triggers = (room_def.get('interactable_triggers') or {})
        if not triggers:
            return False

        tnorm = self._norm(target_name)
        aliases = {"revolving door", "the revolving door", "door", "exit", "revolving-door"}

        def _match():
            for k in triggers.keys():
                kn = self._norm(k)
                if tnorm == kn:
                    return k
                if tnorm in aliases and kn in {"revolving door", "door", "exit"}:
                    return k
                if tnorm in kn or kn in tnorm:
                    return k
            return None

        key = _match()
        if not key:
            return False

        trigger_def = triggers.get(key) or {}
        if trigger_def.get('on_action') != 'use':
            return False

        requirements_met = True
        if trigger_def.get('requires_all_evidence'):
            met, missing = self._requirements_met_for_level_exit()
            self.logger.info(f"_try_trigger_room_interactable_use: requires_all_evidence -> met={met}, missing={missing}")
            requirements_met = met
            if not met:
                self.add_ui_event({
                    "event_type": "show_popup",
                    "title": "Something's missing",
                    "message": f"You still need: {', '.join(missing)}."
                })
                return True

        hazard_change = trigger_def.get('triggers_hazard_state_change') or {}
        hazard_type, target_state = hazard_change.get('hazard_type'), hazard_change.get('target_state')
        if not (hazard_type and target_state):
            return False

        # CRITICAL: Process UI events returned by set_hazard_state
        if trigger_def and requirements_met:
            if hasattr(self.hazard_engine, 'set_hazard_state_by_type'):
                ui_events = self.hazard_engine.set_hazard_state_by_type(
                    room_id, hazard_type, target_state, suppress_entry_effects=False
                )
                if ui_events:
                    for event in ui_events:
                        self.add_ui_event(event)
                self.logger.info(f"_try_trigger_room_interactable_use: set '{hazard_type}' at '{room_id}' -> '{target_state}': True")
                return True

        # Fallback: legacy logic if no UI events returned
        ok = self.hazard_engine.set_hazard_state_by_type(room_id, hazard_type, target_state)
        self.logger.info(f"_try_trigger_room_interactable_use: set '{hazard_type}' at '{room_id}' -> '{target_state}': {ok}")
        return True

    def _try_trigger_room_interactable_search(self, target_name: str) -> bool:
        """
        Handles room-level interactable triggers for the 'search' verb.
        Canonical logic mirrors _try_trigger_room_interactable_examine.
        Returns True if a trigger was processed (even if requirements not met).
        """
        room_id = self.player.get('location')
        if not room_id:
            return False

        level_id = str(self.player.get('current_level', 1))
        rooms_key = f"rooms_level_{level_id}"
        rooms_data = self.resource_manager.get_data(rooms_key, {}) or {}
        room_def = rooms_data.get(room_id) or self.current_level_rooms_world_state.get(room_id, {}) or {}
        triggers = (room_def.get('interactable_triggers') or {})
        if not triggers:
            return False

        tnorm = self._norm(target_name)
        aliases = {"revolving door", "the revolving door", "door", "exit", "revolving-door"}

        def _match():
            for k in triggers.keys():
                kn = self._norm(k)
                if tnorm == kn:
                    return k
                if tnorm in aliases and kn in {"revolving door", "door", "exit"}:
                    return k
                if tnorm in kn or kn in tnorm:
                    return k
            return None

        key = _match()
        if not key:
            return False

        trigger_def = triggers.get(key) or {}
        if trigger_def.get('on_action') != 'search':
            return False

        requirements_met = True
        if trigger_def.get('requires_all_evidence'):
            met, missing = self._requirements_met_for_level_exit()
            self.logger.info(f"_try_trigger_room_interactable_search: requires_all_evidence -> met={met}, missing={missing}")
            requirements_met = met
            if not met:
                self.add_ui_event({
                    "event_type": "show_popup",
                    "title": "Something's missing",
                    "message": f"You still need: {', '.join(missing)}."
                })
                return True

        hazard_change = trigger_def.get('triggers_hazard_state_change') or {}
        hazard_type, target_state = hazard_change.get('hazard_type'), hazard_change.get('target_state')
        if not (hazard_type and target_state):
            return False

        # CRITICAL: Process UI events returned by set_hazard_state
        if trigger_def and requirements_met:
            if hasattr(self.hazard_engine, 'set_hazard_state_by_type'):
                ui_events = self.hazard_engine.set_hazard_state_by_type(
                    room_id, hazard_type, target_state, suppress_entry_effects=False
                )
                if ui_events:
                    for event in ui_events:
                        self.add_ui_event(event)
                self.logger.info(f"_try_trigger_room_interactable_search: set '{hazard_type}' at '{room_id}' -> '{target_state}': True")
                return True

        # Fallback: legacy logic if no UI events returned
        ok = self.hazard_engine.set_hazard_state_by_type(room_id, hazard_type, target_state)
        self.logger.info(f"_try_trigger_room_interactable_search: set '{hazard_type}' at '{room_id}' -> '{target_state}': {ok}")
        return True

    def _try_trigger_room_interactable_take(self, target_name: str) -> bool:
        """
        Handles room-level interactable triggers for the 'take' verb.
        Canonical logic mirrors _try_trigger_room_interactable_examine.
        Returns True if a trigger was processed (even if requirements not met).
        """
        room_id = self.player.get('location')
        if not room_id:
            return False

        level_id = str(self.player.get('current_level', 1))
        rooms_key = f"rooms_level_{level_id}"
        rooms_data = self.resource_manager.get_data(rooms_key, {}) or {}
        room_def = rooms_data.get(room_id) or self.current_level_rooms_world_state.get(room_id, {}) or {}
        triggers = (room_def.get('interactable_triggers') or {})
        if not triggers:
            return False

        tnorm = self._norm(target_name)
        aliases = {"revolving door", "the revolving door", "door", "exit", "revolving-door"}

        def _match():
            for k in triggers.keys():
                kn = self._norm(k)
                if tnorm == kn:
                    return k
                if tnorm in aliases and kn in {"revolving door", "door", "exit"}:
                    return k
                if tnorm in kn or kn in tnorm:
                    return k
            return None

        key = _match()
        if not key:
            return False

        trigger_def = triggers.get(key) or {}
        if trigger_def.get('on_action') != 'take':
            return False

        requirements_met = True
        if trigger_def.get('requires_all_evidence'):
            met, missing = self._requirements_met_for_level_exit()
            self.logger.info(f"_try_trigger_room_interactable_take: requires_all_evidence -> met={met}, missing={missing}")
            requirements_met = met
            if not met:
                self.add_ui_event({
                    "event_type": "show_popup",
                    "title": "Something's missing",
                    "message": f"You still need: {', '.join(missing)}."
                })
                return True

        hazard_change = trigger_def.get('triggers_hazard_state_change') or {}
        hazard_type, target_state = hazard_change.get('hazard_type'), hazard_change.get('target_state')
        if not (hazard_type and target_state):
            return False

        # CRITICAL: Process UI events returned by set_hazard_state
        if trigger_def and requirements_met:
            if hasattr(self.hazard_engine, 'set_hazard_state_by_type'):
                ui_events = self.hazard_engine.set_hazard_state_by_type(
                    room_id, hazard_type, target_state, suppress_entry_effects=False
                )
                if ui_events:
                    for event in ui_events:
                        self.add_ui_event(event)
                self.logger.info(f"_try_trigger_room_interactable_take: set '{hazard_type}' at '{room_id}' -> '{target_state}': True")
                return True

        # Fallback: legacy logic if no UI events returned
        ok = self.hazard_engine.set_hazard_state_by_type(room_id, hazard_type, target_state)
        self.logger.info(f"_try_trigger_room_interactable_take: set '{hazard_type}' at '{room_id}' -> '{target_state}': {ok}")
        return True

    def _try_trigger_room_interactable_examine(self, target_name: str) -> bool:
        room_id = self.player.get('location')
        if not room_id:
            return False

        level_id = str(self.player.get('current_level', 1))
        rooms_key = f"rooms_level_{level_id}"
        rooms_data = self.resource_manager.get_data(rooms_key, {}) or {}
        room_def = rooms_data.get(room_id) or self.current_level_rooms_world_state.get(room_id, {}) or {}
        triggers = (room_def.get('interactable_triggers') or {})
        if not triggers:
            return False

        tnorm = self._norm(target_name)
        aliases = {"revolving door", "the revolving door", "door", "exit", "revolving-door"}

        def _match():
            for k in triggers.keys():
                kn = self._norm(k)
                if tnorm == kn:
                    return k
                if tnorm in aliases and kn in {"revolving door", "door", "exit"}:
                    return k
                if tnorm in kn or kn in tnorm:
                    return k
            return None

        key = _match()
        if not key:
            return False

        trigger_def = triggers.get(key) or {}
        if trigger_def.get('on_action') != 'examine':
            return False

        requirements_met = True
        if trigger_def.get('requires_all_evidence'):
            met, missing = self._requirements_met_for_level_exit()
            self.logger.info(f"_try_trigger_room_interactable_examine: requires_all_evidence -> met={met}, missing={missing}")
            requirements_met = met
            if not met:
                self.add_ui_event({
                    "event_type": "show_popup",
                    "title": "Something's missing",
                    "message": f"You still need: {', '.join(missing)}."
                })
                return True

        hazard_change = trigger_def.get('triggers_hazard_state_change') or {}
        hazard_type, target_state = hazard_change.get('hazard_type'), hazard_change.get('target_state')
        if not (hazard_type and target_state):
            return False

        # CRITICAL: Process UI events returned by set_hazard_state
        if trigger_def and requirements_met:
            if hasattr(self.hazard_engine, 'set_hazard_state_by_type'):
                ui_events = self.hazard_engine.set_hazard_state_by_type(
                    room_id, hazard_type, target_state, suppress_entry_effects=False
                )
                if ui_events:
                    for event in ui_events:
                        self.add_ui_event(event)
                self.logger.info(f"_try_trigger_room_interactable_examine: set '{hazard_type}' at '{room_id}' -> '{target_state}': True")
                return True

        # Fallback: legacy logic if no UI events returned
        ok = self.hazard_engine.set_hazard_state_by_type(room_id, hazard_type, target_state)
        self.logger.info(f"_try_trigger_room_interactable_examine: set '{hazard_type}' at '{room_id}' -> '{target_state}': {ok}")
        return True

    def _is_check_result_node(self, node: dict) -> bool:
        """Detects if the node is a special check_result/ticket_check_result node."""
        text = node.get('text', "")
        return (
            ("$ticket_check_result$" in text or "$check_result$" in text)
            and "on_talk_action" in node
            and "check_for_item" in node["on_talk_action"]
        )

    def _handle_check_result_node(self, npc: dict, node: dict, options_text: str = "") -> dict:
        """Handles special check_result/ticket_check_result dialogue nodes."""
        check = node["on_talk_action"]["check_for_item"]
        item = check.get("item")
        success_state = check.get("success_state")
        failure_state = check.get("failure_state")
        failure_text = check.get("failure_text", "You don't have the required item.")
        inventory = self.player.get("inventory", [])
        has_item = item in inventory

        ui_events = []
        if has_item:
            next_node = npc.get("dialogue_states", {}).get(success_state, {})
            text = next_node.get("text", "You may proceed.")
            if "on_talk_action" in next_node:
                self._apply_on_talk_action(next_node["on_talk_action"])
            if "next_state" in next_node:
                self._set_npc_state(npc, next_node["next_state"])
        else:
            next_node = npc.get("dialogue_states", {}).get(failure_state, {})
            text = next_node.get("text", failure_text)
            if "next_state" in next_node:
                self._set_npc_state(npc, next_node["next_state"])

        ui_events.append({
            "event_type": "show_popup",
            "title": npc.get('name', 'NPC'),
            "message": text + (options_text or "")
        })
        self.logger.info(f"_handle_check_result_node: Player {'has' if has_item else 'does not have'} '{item}'.")
        return self._build_response(message=f"[{npc.get('name')}]\n{text}", turn_taken=True, ui_events=ui_events)

    def _build_options_text(self, node: dict) -> str:
        """Builds the options text for a dialogue node."""
        options = node.get('options', []) if node else []
        if options:
            return "\n[Options:\n" + "\n".join(f"  {i+1}. {opt.get('text','')}" for i, opt in enumerate(options)) + "\nUse 'respond X' to choose.]"
        return ""

    def _process_on_talk_action(self, npc: dict, node: dict, ui_events: list):
        """Processes on_talk_action for a dialogue node, including logging and error handling."""
        action = node.get('on_talk_action') or {}
        if not action:
            return

        # gives_item
        gi = action.get('gives_item')
        if gi and gi not in self.player.get('inventory', []):
            self.player.setdefault('inventory', []).append(gi)
            self.logger.info(f"NPC '{npc.get('name')}' gave player item '{gi}'.")

        # start_qte
        if action.get('start_qte') and self.qte_engine:
            try:
                qte_type = action['start_qte'].get('qte_type')
                qte_context = action['start_qte'].get('qte_context', {})
                self.qte_engine.start_qte(qte_type, qte_context)
            except Exception as e:
                self.logger.error(f"_process_on_talk_action: Failed to start QTE: {e}", exc_info=True)

        # hazard_state_change via HazardEngine
        hsc = action.get('hazard_state_change')
        if hsc and self.hazard_engine:
            try:
                if 'hazard_id' in hsc and 'target_state' in hsc:
                    result = self.hazard_engine.set_hazard_state(hsc['hazard_id'], hsc['target_state'])
                    for c in result.get("consequences", []):
                        self.handle_hazard_consequence(c)
            except Exception as e:
                self.logger.error(f"_process_on_talk_action: hazard_state_change failed: {e}", exc_info=True)

        # extra popup
        pop = action.get('ui_popup_event')
        if pop:
            ui_events.append({
                "event_type": pop.get('type', 'show_popup'),
                "title": pop.get('title', npc.get('name', 'NPC')),
                "message": pop.get('message', ''),
            })

        # Canonical win/lose screen triggers
        if action.get("trigger_win_screen"):
            self.game_won = True
            self.is_game_over = True
            self.logger.info("_process_on_talk_action: WinScreen triggered by dialogue.")
            self.add_ui_event({
                "event_type": "game_won",
                "final_score": self.player.get('score', 0)
            })
            raise StopIteration("Win screen triggered; stop further dialogue processing.")

        if action.get("trigger_lose_screen"):
            self.is_game_over = True
            self.logger.info("_process_on_talk_action: LoseScreen triggered by dialogue.")
            self.player['death_reason'] = action.get("death_reason", "You failed to escape.")
            self.add_ui_event({
                "event_type": "game_over",
                "death_reason": self.player['death_reason'],
                "final_narrative": self.get_death_narrative()
            })
            raise StopIteration("Lose screen triggered; stop further dialogue processing.")

        # Handle trigger_level_transition (legacy/level complete)
        tlt = action.get('trigger_level_transition')
        if tlt is not None:
            next_level_id = None
            if isinstance(tlt, dict):
                next_level_id = tlt.get('next_level_id')
            self.logger.info(f"NPC triggered level transition via dialogue. next_level_id={next_level_id}")
            self.player['level_complete_flag'] = True
            if next_level_id:
                self.player['next_level_id'] = next_level_id
            self.add_ui_event({
                "event_type": "level_complete",
                "title": "Level Complete",
                "message": "You have completed this area.",
                "next_level_id": next_level_id
            })
            raise StopIteration("Level transition triggered; stop further dialogue processing.")
        
    def _apply_on_talk_action(self, action: dict):
        """
        Handles on_talk_action triggers from NPC dialogue nodes.
        Supports reward_item, reveal_item, and unlock_exit.
        """
        if not action:
            return
        if "reward_item" in action:
            reward = action["reward_item"]
            item_name = reward.get("item_name")
            location = reward.get("location", "player_inventory")
            if item_name and location == "player_inventory":
                # Add the item to the player's inventory
                items_master = self.resource_manager.get_data('items', {})
                item_data = items_master.get(item_name.lower()) or items_master.get(item_name)
                if item_data:
                    inv = self.player.setdefault('inventory', {})
                    inv[item_name] = item_data
                    self.logger.info(f"Rewarded item '{item_name}' to player via dialogue.")
                    self.add_ui_event({
                        "event_type": "show_popup",
                        "title": "Item Received",
                        "message": f"You received: {item_data.get('name', item_name)}."
                    })
        if "unlock_exit" in action:
            unlock = action["unlock_exit"]
            direction = unlock.get("direction")
            target_room = unlock.get("target_room")
            current_room = self.player.get("location")
            room_data = self.current_level_rooms_world_state.get(current_room, {})
            exits = room_data.get("exits", {})
            if direction in exits and exits[direction] == target_room:
                # Remove 'locked' flag from the target room
                target_room_data = self.current_level_rooms_world_state.get(target_room, {})
                if target_room_data.get("locked"):
                    target_room_data["locked"] = False
                    self.logger.info(f"Unlocked exit '{direction}' from '{current_room}' to '{target_room}'.")
                # Optionally, remove 'locked' from the exit itself if present
                if "locked" in exits:
                    exits["locked"] = False
                self.add_ui_event({
                    "event_type": "show_popup",
                    "title": "Exit Unlocked",
                    "message": f"The way {direction} is now unlocked."
                })
            else:
                self.logger.warning(f"unlock_exit: Exit '{direction}' to '{target_room}' not found in room '{current_room}'.")
        # ...handle other on_talk_action types...

    def _get_terminal_hazard_description(self) -> str:
        """Return the description of a terminal hazard state that caused death, if any."""
        try:
            if not self.hazard_engine:
                return ""
            for hazard_id, h_inst in self.hazard_engine.active_hazards.items():
                state = h_inst.get('state')
                sdef = (h_inst.get('master_data', {}) or {}).get('states', {}).get(state, {})
                if sdef.get('instant_death_in_room') or sdef.get('is_terminal_state'):
                    return (sdef.get('description') or "").strip()
        except Exception:
            pass
        return ""

    def _compose_disaster_line(self) -> str:
        """
        Build: 'Your story began with {disaster}, {death_narrative}'
        Falls back gracefully if data is missing.
        """
        try:
            intro = self.player.get('intro_disaster', {}) or {}
            disaster_key = (intro.get('event_description') or "").strip()
            if not disaster_key:
                return ""

            disasters_master = self.resource_manager.get_data('disasters', {}) or {}
            dn = (disasters_master.get(disaster_key, {}) or {}).get('death_narrative', "").strip()

            # Start the sentence
            line = f"Your story began with {disaster_key}"
            if dn:
                # Ensure natural flow like ', but ...' or ', and ...'
                if not dn.startswith((",", ";", ":")):
                    line += ", "
                line += dn.lstrip()
            else:
                line += "."

            return line.strip()
        except Exception:
            return ""

    def get_death_narrative(self) -> str:
        """
        Builds the lose-screen narrative, combining the disaster line and
        any terminal hazard description that caused death. Removes generic taglines.
        """
        narrative_parts = []

        # 1) Terminal hazard description (e.g., MRI bisection narrative)
        hazard_desc = self._get_terminal_hazard_description()
        if hazard_desc:
            # Separate paragraphs for readability on the lose screen
            narrative_parts.append(hazard_desc)

        # 2) Disaster opening line + disaster-specific death_narrative
        disaster_line = self._compose_disaster_line()
        if disaster_line:
            narrative_parts.append(disaster_line)

        # 3) Canonical stats block: player's live, cumulative stats
        score = int(self.player.get('score', 0))
        turns_taken = int(self.player.get('actions_taken', 0))
        fear_current = float(self.player.get('fear', 0.0))
        fear_max = float(self.player.get('max_fear', fear_current))
        fear_total_gain = float(self.player.get('fear_gained_total', 0.0))

        omens_seen = 0
        try:
            if self.death_ai and hasattr(self.death_ai, 'omens_seen'):
                omens_seen = int(self.death_ai.omens_seen)
        except Exception:
            pass

        # QTE stats if available
        qte_sr_pct = None
        qte_succ = None
        qte_att = None
        try:
            pbp = getattr(self.death_ai, 'player_behavior_patterns', None) or {}
            qte_sr = float(pbp.get('qte_success_rate', 0.0))
            qte_sr_pct = int(round(qte_sr * 100))
            qte_succ = int(pbp.get('qte_successes', 0))
            qte_att = int(pbp.get('qte_attempts', 0))
        except Exception:
            pass

        evaded = self.player.get('evaded_hazards', []) or []

        stats_lines = []
        stats_lines.append(f"Final Score: {score}")
        stats_lines.append(f"Turns Taken: {turns_taken}")
        stats_lines.append(f"Fear Level (final): {fear_current:.2f}")
        stats_lines.append(f"Highest Fear Reached: {fear_max:.2f}")
        stats_lines.append(f"Total Fear Gained: {fear_total_gain:.2f}")
        stats_lines.append(f"Omens Witnessed: {omens_seen}")
        if qte_sr_pct is not None:
            if qte_succ is not None and qte_att is not None:
                stats_lines.append(f"QTE Success Rate: {qte_sr_pct}% ({qte_succ}/{qte_att})")
            else:
                stats_lines.append(f"QTE Success Rate: {qte_sr_pct}%")
        stats_lines.append(f"Hazards Evaded: {len(evaded)}")
        if evaded:
            stats_lines.append("Hazards Encountered: " + ", ".join(evaded))

        narrative_parts.append("\n".join(stats_lines))

        # Join with blank lines to render as separate paragraphs in UI
        return "\n\n".join([p for p in narrative_parts if p]).strip()

    # --- A Method to Record Memories ---
    def set_interaction_flag(self, flag_name: str):
        """Adds a new flag to the set of recorded interactions. Injected with robust debugging logic."""
        if flag_name not in self.interaction_flags:
            self.logger.info(f"Interaction flag set: '{flag_name}'")
            self.interaction_flags.add(flag_name)
        else:
            self.logger.debug(f"Interaction flag '{flag_name}' already set.")

    # --- Entity Finding Helpers ---
    def get_room_data(self, room_name: str) -> Optional[dict]:
        """
        Returns the live data dictionary for a room, injecting the companion NPC
        only if their location matches the current room.
        """
        room = self.current_level_rooms_world_state.get(room_name)
        if room is None:
            self.logger.debug(f"get_room_data: No data found for room '{room_name}'.")
            return None
        else:
            self.logger.debug(f"get_room_data: Retrieved data for room '{room_name}'.")

        # Inject companion NPC only if their location matches this room
        companion_npc = self._get_companion_npc()
        if companion_npc and self.player.get('companion_location') == room_name:
            # Avoid duplicate insertion if already present
            npcs = room.setdefault('npcs', [])
            if not any(npc.get('id') == companion_npc.get('id') for npc in npcs):
                npcs.append(companion_npc)
        return room

    def _get_item_display_name(self, item_key: str) -> str:
        """Gets the proper display name for an item from its master data. Injected with robust debugging logic."""
        items_master = self.resource_manager.get_data('items', {})
        item_data = items_master.get(item_key)
        if item_data is None:
            self.logger.debug(f"_get_item_display_name: No master data found for item '{item_key}'. Using fallback name.")
            return item_key.replace('_', ' ').capitalize()
        name = item_data.get('name')
        if not name:
            self.logger.debug(f"_get_item_display_name: No 'name' field for item '{item_key}'. Using fallback name.")
            return item_key.replace('_', ' ').capitalize()
        self.logger.debug(f"_get_item_display_name: Found display name '{name}' for item '{item_key}'.")
        return name

    def set_player_flag(self, flag_name: str, value: bool = True):
        """
        Sets or removes a boolean flag on the player object.
        These flags track temporary, narrative states.
        We use a 'set' to efficiently store the flags.
        """
        # Ensure the 'flags' set exists on the player dictionary
        if 'flags' not in self.player:
            self.player['flags'] = set()

        if value:
            # Add the flag to the set
            self.player['flags'].add(flag_name)
            self.logger.info(f"Player flag set: '{flag_name}'")
        else:
            # Remove the flag from the set if it exists
            self.player['flags'].discard(flag_name)
            self.logger.info(f"Player flag removed: '{flag_name}'")

    def get_player_flag(self, flag_name: str) -> bool:
        """
        Checks if a specific flag is currently set on the player.
        Returns True if the flag is present, False otherwise.
        """
        # The .get('flags', set()) ensures we don't crash if 'flags' doesn't exist
        return flag_name in self.player.get('flags', set())
    
    def get_items_in_room(self, room_id: str) -> list:
        """Returns a list of all item objects directly present in a specified room."""
        room_data = self.current_level_data.get(room_id, {})
        item_keys_in_room = room_data.get('items', [])
        
        items_in_room = [item for item in self.items_master_list if item['id'] in item_keys_in_room]
        return items_in_room

    def _maybe_intercept_mri_key_take(self, item_key: str) -> Optional[dict]:
        """
        Intercepts the first attempt to take the Coroner's Office Key in the MRI room
        so the player must try twice before the QTE chain begins.
        Returns a response dict if interception handled the action; otherwise None.
        """
        try:
            # Preconditions
            if item_key not in ("coroners_office_key", "coroner_office_key", "coroner_key"):
                return None
            current_room = self.player.get('current_room')
            if current_room != "mri_scan_room":  # adjust if your room id differs
                return None
            # Find active MRI hazard
            mri_hazards = [h for h_id, h in self.hazard_engine.active_hazards.items()
                           if h.get('master_data', {}).get('id') == 'mri']
            if not mri_hazards:
                return None
            mri = mri_hazards[0]
            state = mri.get('state')

            # Only intercept while in pre‑QTE magnetic lock state
            if state not in ("powered_down", "field_active_doors_locked"):
                return None

            attempts = self.player.setdefault('_mri_key_attempts', 0)

            if attempts == 0:
                # First attempt: block and set state to field_active_doors_locked (if not already)
                self.player['_mri_key_attempts'] = 1
                if state == "powered_down":
                    # Move into the locked state but DO NOT yet start projectile chain
                    self.hazard_engine.set_hazard_state(mri.get('id'), "field_active_doors_locked")
                msg = ("You grasp the cold key, but a humming magnetic field locks it in place. "
                       "It trembles—as if the field is destabilizing. Try again.")
                return self._build_response(message=msg, turn_taken=True)
            else:
                # Second attempt: allow take and kick off projectile sequence
                self.player['_mri_key_attempts'] = attempts + 1
                # Advance hazard manually now
                self.hazard_engine.set_hazard_state(mri.get('id'), "projectile_stage_1_cart")
                # Allow normal take flow to continue (return None → fall through)
                return None
        except Exception as e:
            self.logger.error(f"_maybe_intercept_mri_key_take error: {e}", exc_info=True)
            return None

    def _maybe_emit_requirements_met_event(self):
        """If exit requirements are now met, queue a one-time notification popup."""
        try:
            met, _ = self._requirements_met_for_level_exit()
        except Exception as e:
            self.logger.error(f"_maybe_emit_requirements_met_event: check failed: {e}", exc_info=True)
            return

        if met and not self.player.get('notified_requirements_met'):
            self.player['notified_requirements_met'] = True
            self.add_ui_event({
                "event_type": "show_popup",
                "title": "You're ready to leave",
                "message": "You have everything you need to exit this level. Head to the Hospital Morgue Exit."
            })
            self.logger.info("Level exit requirements met; notification enqueued.")

    def _apply_qte_effects(self, effects: list):
        """
        Apply world changes embedded in QTE results.
        Supported:
        - {'type': 'unlock_room', 'room_id': 'Room Name'}
        - {'type': 'unlock_furniture', 'room_id': 'Room Name', 'furniture_name': 'name'}
        - {'type': 'break_furniture', 'room_id': 'Room Name', 'furniture_name': 'name'}
        """
        try:
            if not effects:
                return
            for eff in effects:
                et = eff.get('type')
                if et == 'unlock_room':
                    rid = eff.get('room_id')
                    if not rid: continue
                    r = self.current_level_rooms_world_state.get(rid)
                    if not r: continue
                    # Respect MRI: do not clear MRI locks here; MRI unlock handler does that
                    if r.get('locked_by_mri'):
                        continue
                    r['locked'] = False
                    if isinstance(r.get('locking'), dict):
                        r['locking']['locked'] = False
                elif et in ('unlock_furniture', 'break_furniture'):
                    rid = eff.get('room_id'); fname = eff.get('furniture_name')
                    if not (rid and fname): continue
                    r = self.current_level_rooms_world_state.get(rid) or {}
                    furns = r.get('furniture', [])
                    for f in furns:
                        if isinstance(f, dict) and self._norm(f.get('name','')) == self._norm(fname):
                            if et == 'unlock_furniture':
                                f['locked'] = False
                            else:
                                f['locked'] = False
                                f['is_broken'] = True
                            break
                # --- PATCH: Use canonical effect handlers for future extensibility ---
                elif et == "unlock_furniture":
                    self._unlock_furniture_effect(eff)
                elif et == "break_furniture":
                    self._break_furniture_effect(eff)
                elif et == "unlock_room":
                    self._unlock_room_effect(eff)
                # ...existing effect types...
        except Exception as e:
            self.logger.error(f"_apply_qte_effects: Error applying effects: {e}", exc_info=True)
        # Make the HUD reflect changes
        self.add_ui_event({"event_type": "refresh_map"})
        
    #--- Force/Break Handlers and Helpers ---
    def _parse_force_command(self, target_str: str) -> dict:
        """
        Parse 'force <target> [with <tool>]' or 'break <target> [with <tool>]'.
        """
        s = (target_str or "").strip()
        m = re.match(r"(.+?)\s+with\s+(.+)$", s, re.IGNORECASE)
        if m:
            return {"target_name": m.group(1).strip(), "tool_name": m.group(2).strip()}
        return {"target_name": s, "tool_name": None}

    def _get_stat(self, stat_name: str, default: int = 0) -> int:
        """
        Pull a character stat from the active class, falling back to defaults.
        """
        try:
            cls = self.player.get('character_class')
            classes = self.resource_manager.get_data('character_classes', {}) or {}
            data = classes.get(cls, {})
            return int(data.get('stats', {}).get(stat_name, data.get(stat_name, default)))
        except Exception:
            return default

    def _is_tool_item(self, item_key: str) -> bool:
        items_master = self.resource_manager.get_data('items', {}) or {}
        d = items_master.get(item_key, {}) or {}
        return bool(d.get('type') == 'tool' or d.get('is_tool'))

    def _tool_bonus(self, item_key: str) -> int:
        items_master = self.resource_manager.get_data('items', {}) or {}
        d = items_master.get(item_key, {}) or {}
        # Prefer explicit bonus; fallback if item tagged as tool
        return int(d.get('force_bonus', 3 if self._is_tool_item(item_key) else 0))

    def _best_tool_in_inventory(self) -> Tuple[Optional[str], int]:
        """Return (tool_key, bonus) for the best force tool in inventory."""
        best_key, best_bonus = None, 0
        items_master = self.resource_manager.get_data('items', {}) or {}
        for key in self.player.get('inventory', []):
            data = items_master.get(key, {}) or {}
            if data.get('type') == 'tool' or data.get('is_tool'):
                bonus = int(data.get('force_bonus', 3))
                if bonus > best_bonus:
                    best_key, best_bonus = key, bonus
        return best_key, best_bonus

    def _compute_force_difficulty(self, room_or_entity: dict, base: int = 16, strength: int = 0, tool_bonus: int = 0) -> int:
        """
        Compute target_mash_count for button-mash QTE.
        - Use room.force_threshold when present
        - Else use base adjusted by character strength and tool bonus
        """
        threshold = None
        if isinstance(room_or_entity, dict):
            threshold = room_or_entity.get('force_threshold')
        if threshold is None:
            # Strength reduces difficulty; tools reduce difficulty
            # Clamp result to a sensible range
            target = base + max(0, 6 - strength*2) - min(6, tool_bonus)
            return max(8, min(35, int(target)))
        return max(8, min(40, int(threshold)))

    def _force_or_break_entity(self, target_name: str, tool_key: Optional[str]) -> dict:
        """Unified handler for forcing/breaking furniture/objects."""
        current_room_id = self.player.get('location')
        entity = self._find_entity_in_room(target_name, current_room_id)
        if not entity:
            return self._build_response(message=f"You don't see a '{target_name}' to force.", turn_taken=False)

        etype = entity.get('type')
        if etype not in ('furniture', 'object'):
            return self._build_response(message=f"You can't force the {entity.get('name')}.", turn_taken=False)

        fdata = entity.get('data', {}) or {}
        display = entity.get('name')
        # Locked container can be forced; else if breakable we can break
        can_force = fdata.get('locked') or fdata.get('forceable') or fdata.get('is_breakable')
        if not can_force:
            return self._build_response(message=f"There's nothing to force about the {display}.", turn_taken=False)

        strength = self._get_stat('strength', 1)
        bonus = self._tool_bonus(tool_key) if tool_key else 0
        tgt_mash = self._compute_force_difficulty(fdata, base=14, strength=strength, tool_bonus=bonus)

        # Effects: unlock if locked, else mark as broken
        effects_on_success = []
        if fdata.get('locked'):
            effects_on_success.append({"type": "unlock_furniture", "room_id": current_room_id, "furniture_name": fdata.get('name')})
            success_msg = f"You pop the {display} open!"
        elif fdata.get('is_breakable') or fdata.get('forceable'):
            effects_on_success.append({"type": "break_furniture", "room_id": current_room_id, "furniture_name": fdata.get('name')})
            success_msg = f"The {display} cracks and gives way!"
        else:
            success_msg = f"You force the {display}."

        ctx = {
            "ui_mode": "in-screen",
            "ui_prompt_message": f"You set your shoulder against the {display}. Mash to apply force!",
            "target_mash_count": tgt_mash,
            "duration": 4.0,
            "success_message": success_msg,
            "failure_message": f"You strain, but the {display} holds.",
            "effects_on_success": effects_on_success,
            "hp_damage_on_failure": 0
        }
        if self.qte_engine:
            self.player['qte_active'] = True
            self.qte_engine.start_qte("button_mash", ctx)
            return self._build_response(message=f"You square up on the {display}...", turn_taken=True)
        else:
            return self._build_response(message=f"You shove the {display}, but nothing happens.", turn_taken=True)

    def delete_save_game(self, slot_identifier: str) -> dict:
        """Delete a save game file."""
        try:
            from .utils import get_save_filepath
            
            save_path = get_save_filepath(slot_identifier)
            
            if not os.path.exists(save_path):
                return {
                    "success": False,
                    "message": f"No save file found for slot '{slot_identifier}'."
                }
            
            os.remove(save_path)
            self.logger.info(f"Deleted save file: {save_path}")
            
            return {
                "success": True,
                "message": f"Save slot '{slot_identifier}' deleted successfully."
            }
            
        except Exception as e:
            self.logger.error(f"Failed to delete save file '{slot_identifier}': {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Failed to delete save: {str(e)}"
            }

    #--- NPC Dialogue Condition Helpers
    def _resolve_npc_dialogue_entry_state(self, npc: dict, room_id: str) -> str:
        """
        Determines the correct dialogue state for an NPC, considering conditional_entry_state.
        Uses _npc_condition_met for condition evaluation.
        """
        initial_state = self._get_npc_state(npc)
        conds = npc.get('conditional_entry_state', [])
        for cond in conds:
            condition = cond.get('condition', {})
            if self._npc_condition_met(condition, room_id=room_id):
                return cond['state']
        return initial_state

    def _move_companion_to_next_room(self, destination):
        """
        Moves the companion NPC to the specified destination room.
        """
        companion_id = self.player.get('companion_id', None) or 'your_friend'
        # Try player-local NPCs first
        npcs = self.player.get('npcs', {})
        if companion_id in npcs:
            npcs[companion_id]['location'] = destination
            self.logger.info(f"Moved companion '{companion_id}' to {destination}")
            return
        # Try global NPCs if present
        if hasattr(self, 'npcs') and companion_id in self.npcs:
            self.npcs[companion_id]['location'] = destination
            self.logger.info(f"Moved global companion '{companion_id}' to {destination}")
            return
        self.logger.warning(f"Companion '{companion_id}' not found; cannot move to {destination}")

    def _npc_condition_met(self, condition: dict, room_id: str = None) -> bool:
        """
        Evaluates if a given condition is met.
        Supports 'or' (recursive), hazard state, and hazard activation.
        Optionally takes a room_id for context (defaults to player's location).
        """
        if "or" in condition:
            for sub in condition["or"]:
                if self._npc_condition_met(sub, room_id=room_id):
                    return True
            return False
        # Use provided room_id or fallback to player's location
        room = room_id or self.player.get('location')
        # Check for hazard state
        for k, v in condition.items():
            if k.endswith("_state"):
                hazard_type = k[:-6]
                for hid, hazard in self.hazard_engine.active_hazards.items():
                    if hazard.get('type') == hazard_type and hazard.get('location') == room:
                        if hazard.get('state') == v:
                            return True
            elif k.endswith("_activated"):
                hazard_type = k[:-10]
                for hid, hazard in self.hazard_engine.active_hazards.items():
                    if hazard.get('type') == hazard_type and hazard.get('location') == room:
                        if hazard.get('started_by_player'):
                            return True
        return False

    def _parse_option_number(self, option_str: str) -> Optional[int]:
        """
        Helper to parse the option number from a respond command.
        Returns zero-based index or None if invalid.
        """
        try:
            opt_num = int(option_str.split()[0]) - 1
            if opt_num < 0:
                return None
            return opt_num
        except Exception as e:
            self.logger.debug(f"_parse_option_number: Failed to parse option_str='{option_str}': {e}")
            return None

    def _get_companion_npc(self):
        # Always pull the latest master data for the companion
        friend_npc = self.resource_manager.get_data('npcs', {}).get('friend', {}).copy()
        if not friend_npc:
            # fallback if not found
            return {
                "id": "companion_friend",
                "name": "Your Friend",
                "description": "Your loyal movie companion.",
                "examinable": True,
                "initial_state": "default",
                "dialogue_states": {
                    "default": {
                        "text": "Ready for the movie?",
                        "options": [
                            {"text": "Let's go!", "target_state": "default"}
                        ]
                    }
                }
            }
        # Set the live state for this instance
        friend_npc['id'] = "companion_friend"
        friend_npc['initial_state'] = self.player.get('friend_dialogue_state', 'default')
        return friend_npc

    def on_hazard_state_change(self, hazard_key, new_state):
        # ...existing logic...
        if hazard_key == "falling_marquee_letters" and new_state == "near_miss":
            self.player['friend_dialogue_state'] = "marquee_near_miss"
        elif hazard_key == "popcorn_oil_flareup" and new_state in ("scattered_sparks", "simmer_down"):
            self.player['friend_dialogue_state'] = "popcorn_flare"
        elif hazard_key == "soda_spill_slip" and new_state in ("hard_fall", "sticky_save"):
            self.player['friend_dialogue_state'] = "soda_fall"
        # ...add more as needed...

    def get_friend_dialogue(self):
        friend_npc = self.resource_manager.get_data('npcs', {}).get('friend', {})
        state = self.player.get('friend_dialogue_state', 'default')
        dialogue = friend_npc.get('dialogue_states', {}).get(state, friend_npc.get('dialogue_states', {}).get('default', {}))
        # Reset after showing special dialogue
        if state != 'default':
            self.player['friend_dialogue_state'] = 'default'
        return dialogue

    def get_room_data(self, room_name: str) -> Optional[dict]:
        room = self.current_level_rooms_world_state.get(room_name)
        if room is None:
            self.logger.debug(f"get_room_data: No data found for room '{room_name}'.")
            return None
        else:
            self.logger.debug(f"get_room_data: Retrieved data for room '{room_name}'.")

        # Inject companion NPC only if their location matches this room
        companion_npc = self._get_companion_npc()
        if companion_npc and self.player.get('companion_location') == room_name:
            npcs = room.setdefault('npcs', [])
            if not any(npc.get('id') == companion_npc.get('id') for npc in npcs):
                npcs.append(companion_npc)
        return room

    #--- Use action handlers
    def _use_main(self, target_str: str) -> dict:
        """
        Main 'use' command handler for room furniture/hazards.
        NEW: Validate hazard state before forwarding to hazard engine.
        """
        target_norm = self._norm(target_str or "")
        if not target_norm:
            self.logger.info("_use_main: No target specified.")
            return {"messages": ["Use what?"], "turn_taken": False}

        current_room_id = self.player['location']

        # 1) Room interactables FIRST
        try:
            if self._try_trigger_room_interactable_use(target_str):
                self.logger.info("_use_main: Room interactable triggered successfully.")
                return {
                    "messages": [],
                    "game_state": self.get_current_game_state(),
                    "ui_events": self.get_ui_events(),
                    "turn_taken": True,
                }
        except Exception as e:
            self.logger.error(f"_use_main: room interactable handling failed: {e}", exc_info=True)

        # 2) Hazards/objects with player_interaction['use']
        # PATCH: Check if target is a hazard-linked object and validate hazard state before forwarding
        visible_entities = self._get_all_visible_entities_in_room(current_room_id)
        hazard_type = None
        for entity in visible_entities['objects']:
            entity_name = entity.get('name', '')
            if target_norm == self._norm(entity_name):
                hazard_type = entity.get('hazard_key')
                break

        if hazard_type:
            self.logger.info(f"_use_main: Object '{target_str}' is linked to hazard '{hazard_type}'. Forwarding to HazardEngine.")
            # NEW: Check if hazard is in a usable state
            hazard_instance = None
            for hid, hinst in (self.hazard_engine.active_hazards.items() if self.hazard_engine else []):
                if hinst.get('type') == hazard_type and hinst.get('location') == current_room_id:
                    hazard_instance = hinst
                    break

            if hazard_instance:
                state = hazard_instance.get('state')
                master_def = hazard_instance.get('master_data', {})
                state_def = (master_def.get('states') or {}).get(state, {})
                if state_def.get('is_terminal_state') or state in ['empty', 'destroyed', 'removed']:
                    return self._build_response(
                        message=f"The {target_str} is no longer usable.",
                        turn_taken=False,
                        success=False
                    )

            # FIXED: Remove room_name argument
            result = self.hazard_engine.process_player_interaction('use', target_str)
            if result:
                return result

        hazard_result = self._use_hazard_object(target_norm, current_room_id)
        if hazard_result:
            return hazard_result

        # 3) Inventory item use logic (support both 'use item' and 'use item on target')
        inventory_result = self._use_inventory_item(target_str, target_norm, current_room_id)
        if inventory_result:
            return inventory_result

        # 4) Try direct use on furniture/object
        entity_result = self._use_direct_entity(target_norm, current_room_id)
        if entity_result:
            return entity_result

        # If nothing matches
        self.logger.info(f"_use_main: No valid use target found for '{target_str}'.")
        item_name = self._parse_use_command(target_str).get('item_name', target_str)
        return self._build_response(message=f"You don't have a {item_name} to use.", turn_taken=False)

    def _use_hazard_object(self, target_norm: str, current_room_id: str) -> Optional[dict]:
        try:
            visible_entities = self._get_all_visible_entities_in_room(current_room_id)
            for entity in visible_entities['objects']:
                entity_name = entity.get('name', '')
                if target_norm == self._norm(entity_name):
                    hazard_key = entity.get('hazard_key')
                    if hazard_key and self.hazard_engine:
                        hazard_state = self.hazard_engine.get_hazard_state(hazard_key, current_room_id)
                        hazards_master = self.resource_manager.get_data('hazards', {})
                        h_def = hazards_master.get(hazard_key, {})
                        use_rules = h_def.get('player_interaction', {}).get('use', [])
                        for rule in use_rules:
                            on_names = rule.get('on_target_name', [])
                            if isinstance(on_names, str):
                                on_names = [on_names]
                            if target_norm in [self._norm(n) for n in on_names]:
                                req_states = rule.get('requires_hazard_state', [])
                                if not req_states or hazard_state in req_states:
                                    msg = rule.get('message')
                                    target_state = rule.get('target_state')
                                    special_action = rule.get('on_trigger_special_action')
                                    ui_events = []
                                    if target_state:
                                        ui_events = self.hazard_engine.set_hazard_state_by_type(
                                            current_room_id, hazard_key, target_state, suppress_entry_effects=False
                                        )
                                        for event in ui_events:
                                            self.add_ui_event(event)
                                    if special_action:
                                        self.hazard_engine._maybe_run_special_action({'on_state_entry_special_action': special_action}, hazard_key)
                                    self.logger.info(f"_use_hazard_object: Used hazard object '{entity_name}' with rule '{rule}'.")
                                    return self._build_response(message=msg, turn_taken=True, ui_events=ui_events)
            return None
        except Exception as e:
            self.logger.error(f"_use_hazard_object: Error: {e}", exc_info=True)
            return self._build_response(message="Something went wrong using the object.", turn_taken=False, success=False)

    def _use_inventory_item(self, target_str: str, target_norm: str, current_room_id: str) -> Optional[dict]:
        try:
            parsed = self._parse_use_command(target_str)
            item_name = parsed['item_name']
            target_name = parsed['target_name']

            item_entity = self._find_entity_in_room(item_name, current_room_id)
            if item_entity and item_entity['type'] == 'item_inventory':
                item_key = item_entity['id_key']
                item_data = item_entity['data']

                # If 'use [item] on [target]'
                if target_name:
                    target_entity = self._find_entity_in_room(target_name, current_room_id)
                    if not target_entity:
                        return self._build_response(message=f"You don't see a '{target_name}' to use that on.", turn_taken=False)

                    # Priority 1: Check if the TARGET (e.g., furniture) has a rule for this ITEM.
                    if target_entity['type'] == 'furniture':
                        interaction_rules = target_entity['data'].get('use_item_interaction', [])
                        for rule in interaction_rules:
                            if item_key in rule.get('item_names_required', []):
                                message = rule.get('message_success', f"You use the {item_entity['name']} on the {target_entity['name']}.").format(item_name=item_entity['name'])
                                self.logger.info(f"_use_inventory_item: Used '{item_key}' on furniture '{target_entity['name']}'.")
                                return self._build_response(message=message, turn_taken=True)

                    # Priority 1.5: Check if the TARGET is an object and has use_item_interaction rules
                    if target_entity['type'] == 'object':
                        interaction_rules = target_entity['data'].get('use_item_interaction', [])
                        for rule in interaction_rules:
                            if item_key in rule.get('item_names_required', []):
                                action_effect = rule.get('action_effect')
                                if action_effect == "trigger_game_over_projectionist_booth":
                                    # Enqueue popup first, then game over event
                                    projectionist_deaths = [
                                        "electrocution from a nearby faulty wire",
                                        "smoke inhalation after being trapped",
                                        "a falling light fixture",
                                        "slipping on a spilled drink and slamming his face into the desk holding the projector, puncturing his eye on a pencil in a cup of random small items",
                                        "cancer.. can you believe that shit? The blood on the wall was just a sticker.",
                                        "electrocution when faulty wiring caused a small smolder he tried to douse with water near an outlet",
                                        "being strangled/crushed after their collar snagged on a projector's take-up reel when dodging a falling film platter",
                                        "asphyxiation from toxic gases released by a shattering projector bulb, triggered by overheating due to a dust-clogged fan",
                                        "a stack of heavy film canisters falling from a vibrating shelf, crushing his skull as he bent down to retrieve a dropped tool"
                                    ]
                                    player_terri_deaths = [
                                        "but as you turn to leave, a speeding ambulance jumps the curb to miss Maya crossing the street -who, after the night's events, had just left early in a panic- obliterating you both.",
                                        "when a fire truck ladder hits a power line overhead; the snapped cable whips down, electrocuting you both instantly on the wet pavement.",
                                        "when suddenly, a detached rotor blade from a low-flying news helicopter slices through the crowd, cutting you both down.",
                                        "when you see a screw fall in front of you.\nWith a deafening groan, the massive cineplex sign tears free from the facade, crushing you both beneath it.",
                                        "when a runaway street food cart slams into you from behind, its propane tank rupturing and pushing you back towards an open manhole.\nYou'd have fallen the 20 feet down if it weren't for the metal ladder rungs your body forcefully, awkwardly and painfully got tangled in on the way down - and you might've lived if your friend didn't fall in directly on top of you.",
                                        "when you step back off the curb to look at the commotion one last time, directly into the path of an oncoming city bus.",
                                        "when a panicked driver jumps the curb to miss Maya crossing the street -who, after the night's events, had just left early in a panic- sending their car spinning into a fire hydrant;\nthe hydrant launches into the air like a missile, striking you both with lethal force."
                                    ]
                                    projectionist_death = random.choice(projectionist_deaths)
                                    player_terri_death = random.choice(player_terri_deaths)
                                    self.player['death_reason'] = (
                                        f"You discover the body of the projectionist alone in the booth, killed by {projectionist_death}. "
                                        "You call for help and the door is opened just as the projector light starts to catch fire.\n"
                                        "You prevent the spread of flames with the help of a nearby soda and see the chaos that almost unfolded - "
                                        "the sprinklers are above lighting installed for a previous movie party that could have electrocuted or fallen on people below.\n\n"
                                        f"You leave the theater with your friend, thankful to be alive, {player_terri_death}"
                                    )
                                    self.player['death_narrative'] = rule.get('message_success')
                                    # Enqueue popup first, then game over event
                                    self.add_ui_event({
                                        "event_type": "show_popup",
                                        "title": "A Terrible Discovery",
                                        "message": rule.get('message_success')
                                    })
                                    self.add_ui_event({
                                        "event_type": "game_over",
                                        "death_reason": self.player['death_reason'],
                                        "final_narrative": ""
                                    })
                                    self.logger.info("_use_inventory_item: Game over triggered by using flashlight on projectionist booth.")
                                    return self._build_response(
                                        message=None,
                                        turn_taken=True,
                                        success=True
                                    )
                                # ...handle other action_effects...
                                message = rule.get('message_success', f"You use the {item_entity['name']} on the {target_entity['name']}.").format(item_name=item_entity['name'])
                                self.logger.info(f"_use_inventory_item: Used '{item_key}' on object '{target_entity['name']}'.")
                                return self._build_response(message=message, turn_taken=True)

                    # Priority 2: Check if the ITEM has a rule for this TARGET.
                    if target_entity['name'].lower() in [t.lower() for t in item_data.get('use_on', [])]:
                        message = item_data.get('use_result', {}).get(target_entity['name'], f"You use the {item_entity['name']} on the {target_entity['name']}.")
                        self.logger.info(f"_use_inventory_item: Used '{item_key}' on '{target_entity['name']}' via item rule.")
                        return self._build_response(message=message, turn_taken=True)

                    self.logger.info(f"_use_inventory_item: Can't use '{item_entity['name']}' on '{target_entity['name']}'.")
                    return self._build_response(message=f"You can't use the {item_entity['name']} on the {target_entity['name']}.", turn_taken=False)

                # If just 'use [item]'
                else:
                    # Check for self-use effects, like healing
                    if 'heal_amount' in item_data:
                        heal_amount = item_data['heal_amount']
                        self.player['hp'] = min(self.player['max_hp'], self.player['hp'] + heal_amount)
                        if item_data.get('consumable_on_use'):
                            self.player['inventory'].remove(item_key)
                        message = item_data.get('use_result', {}).get('general', f"You use the {item_entity['name']} and feel better.")
                        self.logger.info(f"_use_inventory_item: Used '{item_key}' for healing.")
                        return self._build_response(message=message, turn_taken=True)
                    # Add more item self-use logic here as needed
                    self.logger.info(f"_use_inventory_item: No self-use effect for '{item_entity['name']}'.")
                    return self._build_response(message=f"Silly goose, you can't use the {item_entity['name']} by itself.", turn_taken=False)
            return None
        except Exception as e:
            self.logger.error(f"_use_inventory_item: Error: {e}", exc_info=True)
            return self._build_response(message="Something went wrong using the item.", turn_taken=False, success=False)

    def _use_direct_entity(self, target_norm: str, current_room_id: str) -> Optional[dict]:
        try:
            entity = self._find_entity_in_room(target_norm, current_room_id)
            if entity and entity['type'] in ('furniture', 'object'):
                use_rules = entity['data'].get('use_interaction', [])
                for rule in use_rules:
                    if target_norm in [self._norm(n) for n in rule.get('on_target_name', [entity['name']])]:
                        msg = rule.get('message', f"You use the {entity['name']}.")
                        self.logger.info(f"_use_direct_entity: Used '{entity['name']}' via direct use_interaction.")
                        return self._build_response(message=msg, turn_taken=True)
                self.logger.info(f"_use_direct_entity: Fallback use for '{entity['name']}'.")
                return self._build_response(message=f"You use the {entity['name']}.", turn_taken=True)
            return None
        except Exception as e:
            self.logger.error(f"_use_direct_entity: Error: {e}", exc_info=True)
            return self._build_response(message="Something went wrong using the entity.", turn_taken=False, success=False)
            
    #--- Unlock command handlers
    def _get_player_keys(self) -> dict:
        """Return a dict of key_id: key_data for all keys in player inventory."""
        items_master = self.resource_manager.get_data('items', {})
        keys = {}
        for item_key in self.player.get('inventory', []):
            item_data = items_master.get(item_key, {})
            if item_data.get("type") == "key":
                keys[item_key] = item_data
        return keys

    def _try_unlock_exit(self, target_norm: str, current_room_data: dict, available_keys: dict) -> Optional[dict]:
        """Try to unlock an exit (door) in the current room."""
        exits = current_room_data.get('exits', {})
        for direction, dest_room_id in exits.items():
            if isinstance(dest_room_id, dict):
                continue
            if (target_norm == self._norm(direction) or
                target_norm == self._norm(dest_room_id) or
                target_norm == self._norm(f"{direction} door")):
                return self._unlock_exit(direction, dest_room_id, available_keys)
        return None

    def _unlock_exit(self, direction: str, dest_room_id: str, available_keys: dict) -> dict:
        """Unlock the specified exit if the player has the correct key."""
        all_rooms = self.resource_manager.get_data('rooms', {})
        level_rooms = all_rooms.get(str(self.player.get('current_level', 1)), {})
        dest_data = level_rooms.get(dest_room_id)
        if not dest_data:
            return self._build_response(
                message=f"The way to {dest_room_id.replace('_', ' ')} seems blocked.",
                turn_taken=True
            )
        locking = dest_data.get("locking", {})
        if not locking.get("locked", False):
            return self._build_response(
                message=f"The way to {dest_room_id.replace('_', ' ')} is already unlocked.",
                turn_taken=False
            )
        required_key = locking.get("unlocks_with")
        if not required_key:
            return self._build_response(
                message=f"The door to {dest_room_id.replace('_', ' ')} doesn't have a keyhole.",
                turn_taken=False
            )
        for key_id, key_data in available_keys.items():
            unlocks = [self._norm(u) for u in key_data.get("unlocks", [])]
            if (self._norm(required_key) in unlocks or
                self._norm(dest_room_id) in unlocks or
                self._norm(direction) in unlocks or
                "*" in key_data.get("unlocks", []) or
                key_data.get("is_master_key")):
                locking["locked"] = False
                if dest_room_id in self.current_level_rooms_world_state:
                    self.current_level_rooms_world_state[dest_room_id]["locked"] = False
                self.logger.info(f"_command_unlock: Unlocked {dest_room_id} with {key_id}")
                display_name = self._get_item_display_name(key_id)
                message = f"You unlock the door to {dest_room_id.replace('_', ' ')} with the {display_name}."
                return self._build_response(
                    message=color_text(message, "success", self.resource_manager),
                    turn_taken=True,
                    success=True
                )
        return self._build_response(
            message=color_text(
                f"You don't have the right key to unlock the door to {dest_room_id.replace('_', ' ')}.",
                "warning",
                self.resource_manager
            ),
            turn_taken=True,
            success=False
        )

    def _try_unlock_furniture(self, target_name_str: str, current_room_id: str, available_keys: dict) -> Optional[dict]:
        """Try to unlock a furniture container in the current room."""
        entity = self._find_entity_in_room(target_name_str, current_room_id)
        if entity and entity['type'] == 'furniture':
            furniture_data = entity['data']
            if not furniture_data.get("locked", False):
                return self._build_response(
                    message=f"The {entity['name']} is already unlocked.",
                    turn_taken=False
                )
            required_key = furniture_data.get("unlocks_with_item")
            if not required_key:
                return self._build_response(
                    message=f"The {entity['name']} doesn't have a keyhole.",
                    turn_taken=False
                )
            for key_id, key_data in available_keys.items():
                unlocks = [self._norm(u) for u in key_data.get("unlocks", [])]
                if (self._norm(required_key) in unlocks or
                    self._norm(furniture_data.get("name", "")) in unlocks or
                    self._norm(entity['id_key']) in unlocks or
                    "*" in key_data.get("unlocks", []) or
                    key_data.get("is_master_key")):
                    furniture_data["locked"] = False
                    self.logger.info(f"_command_unlock: Unlocked {entity['name']} with {key_id}")
                    display_name = self._get_item_display_name(key_id)
                    message = f"You unlock the {entity['name']} with the {display_name}."
                    return self._build_response(
                        message=color_text(message, "success", self.resource_manager),
                        turn_taken=True,
                        success=True
                    )
            return self._build_response(
                message=color_text(
                    f"You don't have the right key to unlock the {entity['name']}.",
                    "warning",
                    self.resource_manager
                ),
                turn_taken=True,
                success=False
            )
        return None

    # --- 'Examine' handlers
    def _examine_main(self, target: str) -> dict:
        target = (target or "").strip()
        if not target:
            self.logger.info("_examine_main: No target specified.")
            return self._build_response(message="Examine what?", turn_taken=False)

        # 1) Room-level examine triggers FIRST
        try:
            if self._try_trigger_room_interactable_examine(target):
                self.logger.info("_examine_main: Room interactable examine triggered.")
                return {
                    "messages": [],
                    "game_state": self.get_current_game_state(),
                    "ui_events": self.get_ui_events(),
                    "turn_taken": True,
                    "success": True,
                }
        except Exception as e:
            self.logger.error(f"_examine_main: room interactable handling failed: {e}", exc_info=True)

        current_room_id = self.player['location']

        # 2) If examining the room itself
        if not target or self._norm(target) in ['room', 'area', 'surroundings']:
            return self._examine_room(current_room_id)

        # 3) Check for NPCs in the room
        npc_result = self._examine_npc(target, current_room_id)
        if npc_result:
            return npc_result

        # 4) Examine entity (object, furniture, hazard, item)
        return self._examine_entity(target, current_room_id)

    def _examine_room(self, room_id: str) -> dict:
        try:
            room_data = self.get_room_data(room_id)
            description = self._get_rich_room_description(room_id)
            npc_list = room_data.get('npcs', []) if room_data else []
            if npc_list:
                npc_names = [color_text(npc.get('name', ''), 'npc', self.resource_manager) for npc in npc_list if npc.get('name')]
                description += f"\n\nNPCs present: {', '.join(npc_names)}."
            return self._build_response(message=description, turn_taken=True)
        except Exception as e:
            self.logger.error(f"_examine_room: Error: {e}", exc_info=True)
            return self._build_response(message="You see nothing special.", turn_taken=True)

    def _examine_npc(self, target: str, room_id: str) -> Optional[dict]:
        try:
            room_data = self.get_room_data(room_id) or {}
            npcs = room_data.get('npcs', []) or []
            target_norm = self._norm(target)
            for npc in npcs:
                npc_name = npc.get('name', '')
                if self._norm(npc_name) == target_norm:
                    desc = npc.get('examine_details') or npc.get('description') or f"You see {npc_name}. They seem approachable."
                    dialogue_states = npc.get('dialogue_states', {})
                    initial_state = self._get_npc_state(npc)
                    node = dialogue_states.get(initial_state, {})
                    options = node.get('options', []) if node else []
                    if options:
                        opts_text = "\nDialogue options:\n" + "\n".join(f"  {i+1}. {opt.get('text','')}" for i, opt in enumerate(options))
                        desc += opts_text
                    return self._build_response(message=desc, turn_taken=True, success=True)
            return None
        except Exception as e:
            self.logger.error(f"_examine_npc: Error: {e}", exc_info=True)
            return None

    def _examine_entity(self, target: str, room_id: str) -> dict:
        try:
            entity = self._find_entity_in_room(target, room_id)
            if not entity:
                self.logger.info(f"_examine_entity: '{target}' not found in room '{room_id}'")
                return self._build_response(message=f"You see nothing special about '{target}'.", turn_taken=False)

            description = ""
            entity_data = entity.get('data') or entity

            # Check for hazard entity and get contextual examine text
            if entity_data.get('type') == 'hazard_entity':
                description = self._hazard_examine_text(
                    entity_data.get('hazard_key'),
                    entity_data.get('name') or entity['name'],
                    room_id
                )

            if not description:
                description = entity_data.get(
                    'examine_details',
                    entity_data.get('description', f"You see a {entity['name']}.")
                )

            ui_events = []
            self._examine_first_popup(entity_data, room_id, ui_events)
            self._examine_hazard_trigger(entity_data, room_id, ui_events)
            self._examine_omen(entity_data, ui_events)

            return self._build_response(message=description, turn_taken=True, success=True, ui_events=ui_events)
        except Exception as e:
            self.logger.error(f"_examine_entity: Error: {e}", exc_info=True)
            return self._build_response(message="You see nothing special.", turn_taken=True, success=False)

    def _examine_first_popup(self, entity_data: dict, room_id: str, ui_events: list):
        try:
            hazard_key = entity_data.get('hazard_key')
            entity_name = entity_data.get('name')
            if hazard_key and entity_name:
                hazards_master = self.resource_manager.get_data('hazards', {}) or {}
                h_def = hazards_master.get(hazard_key, {}) or {}
                ex_resps = h_def.get('examine_responses', {}) or {}
                resp = ex_resps.get(entity_name) or ex_resps.get(self._norm(entity_name)) or {}
                first_msg = resp.get('first_examine_description')
                if first_msg:
                    flag = f"first_examine_shown::{room_id}::{self._norm(entity_name)}"
                    if flag not in self.interaction_flags:
                        ui_events.append({
                            "event_type": "show_popup",
                            "title": room_id.replace("_", " ").title(),
                            "message": first_msg
                        })
                        self.interaction_flags.add(flag)
        except Exception as e:
            self.logger.error(f"_examine_first_popup: Error: {e}", exc_info=True)

    def _examine_hazard_trigger(self, entity_data: dict, room_id: str, ui_events: list):
        try:
            hazard_trigger = entity_data.get('triggers_hazard_state_change')
            if hazard_trigger and self.hazard_engine:
                hazard_type = hazard_trigger.get('hazard_type')
                target_state = hazard_trigger.get('target_state')
                message = hazard_trigger.get('message')
                if hazard_type and target_state:
                    ok = self.hazard_engine.set_hazard_state_by_type(room_id, hazard_type, target_state)
                    self.logger.info(f"_examine_hazard_trigger: set hazard '{hazard_type}' at '{room_id}' to '{target_state}': {ok}")
                    if message:
                        ui_events.append({
                            "event_type": "show_popup",
                            "title": room_id.replace("_", " ").title(),
                            "message": message
                        })
                    if hazard_trigger.get('triggers_level_transition'):
                        self.player['level_complete_flag'] = True
        except Exception as e:
            self.logger.error(f"_examine_hazard_trigger: Error: {e}", exc_info=True)

    def _examine_omen(self, entity_data: dict, ui_events: list):
        try:
            omen_shown = False
            shown_trigger_key = None
            omen_trigger_key = entity_data.get('is_omen_provider')
            if omen_trigger_key and self._player_can_see_omens():
                if omen_trigger_key in self.current_level_omens:
                    omen_options = self.current_level_omens[omen_trigger_key]
                else:
                    omen_options = None
                omen_text = None

                # If the omen is state-dependent (dict), select by hazard state
                if isinstance(omen_options, dict):
                    hazard_key = None
                    hazard_room = None
                    if omen_trigger_key == "popcorn_oil_flareup":
                        hazard_key = "popcorn_oil_flareup"
                        hazard_room = "Concessions"
                    if hazard_key and hazard_room:
                        hazard_state = self.hazard_engine.get_hazard_state(hazard_key, hazard_room)
                        omen_text = omen_options.get(hazard_state)
                    if not omen_text:
                        omen_text = next(iter(omen_options.values()))
                elif isinstance(omen_options, list):
                    omen_text = random.choice(omen_options)
                elif omen_options is not None:
                    omen_text = str(omen_options)

                if omen_text:
                    omen_popup_command = {
                        "event_type": "show_popup",
                        "title": "A Glimpse of the Design",
                        "message": color_text(omen_text, 'special', self.resource_manager),
                        # NEW: hint UI to show blue fear pulse during this popup
                        "vfx_hint": "fear"
                    }
                    ui_events.append(omen_popup_command)
                    omen_shown = True
                    shown_trigger_key = omen_trigger_key

            if omen_shown and self.death_ai:
                self.death_ai.update_fear('examine_omen')
                self.logger.info(f"Player witnessed omen '{shown_trigger_key}' - fear increased to {self.player.get('fear', 0)}")
            else:
                self.logger.debug("No omen shown; skipping fear update for examine.")
        except Exception as e:
            self.logger.error(f"_examine_omen: Error: {e}", exc_info=True)

    # --- 'Force/Break' handlers
    def _force_main(self, target_str: str) -> dict:
        target_str = (target_str or "").strip()
        if not target_str:
            self.logger.info("_force_main: No target specified.")
            return self._build_response(message="Force what?", turn_taken=False)

        parsed = self._parse_force_command(target_str)
        target_name = parsed['target_name']
        tool_name = parsed['tool_name']

        current_room_id = self.player.get('location')
        room = self.get_room_data(current_room_id) or {}
        exits = room.get('exits', {}) or {}

        tool_key, bonus = self._resolve_force_tool(tool_name, current_room_id)
        if tool_key is False:  # error already returned
            return bonus

        exit_result = self._force_try_exit(target_name, tool_key, bonus, room, exits)
        if exit_result is not None:
            return exit_result

        return self._force_or_break_entity(target_name, tool_key)

    def _break_main(self, target_name_str: str) -> dict:
        target_name_str = (target_name_str or "").strip()
        if not target_name_str:
            self.logger.info("_break_main: No target specified.")
            return self._build_response(message="Break what?", turn_taken=False)

        parsed = self._parse_force_command(target_name_str)
        tool_key = None
        if parsed.get('tool_name'):
            tool_entity = self._find_entity_in_room(parsed['tool_name'], self.player.get('location'))
            if not tool_entity or tool_entity.get('type') != 'item_inventory':
                msg = f"You don't have a {parsed['tool_name']}."
                self.logger.info(f"_break_main: {msg}")
                return self._build_response(message=msg, turn_taken=False)
            if not self._is_tool_item(tool_entity['id_key']):
                msg = f"The {tool_entity['name']} isn't suited for breaking things."
                self.logger.info(f"_break_main: {msg}")
                return self._build_response(message=msg, turn_taken=False)
            tool_key = tool_entity['id_key']
        else:
            tool_key, _ = self._best_tool_in_inventory()

        return self._force_or_break_entity(parsed['target_name'], tool_key)

    def _resolve_force_tool(self, tool_name: str, current_room_id: str):
        """Helper to resolve the tool for forcing, with logging and error handling."""
        try:
            if tool_name:
                tool_entity = self._find_entity_in_room(tool_name, current_room_id)
                if not tool_entity or tool_entity.get('type') != 'item_inventory':
                    msg = f"You don't have a {tool_name}."
                    self.logger.info(f"_resolve_force_tool: {msg}")
                    return False, self._build_response(message=msg, turn_taken=False)
                if not self._is_tool_item(tool_entity['id_key']):
                    msg = f"The {tool_entity['name']} isn't suited for forcing things."
                    self.logger.info(f"_resolve_force_tool: {msg}")
                    return False, self._build_response(message=msg, turn_taken=False)
                tool_key = tool_entity['id_key']
                bonus = self._tool_bonus(tool_key)
                self.logger.debug(f"_resolve_force_tool: Using explicit tool '{tool_key}' with bonus {bonus}")
                return tool_key, bonus
            else:
                tool_key, bonus = self._best_tool_in_inventory()
                self.logger.debug(f"_resolve_force_tool: Using best available tool '{tool_key}' with bonus {bonus}")
                return tool_key, bonus
        except Exception as e:
            self.logger.error(f"_resolve_force_tool: Error: {e}", exc_info=True)
            return False, self._build_response(message="Error resolving tool.", turn_taken=False)
        
    def _force_try_exit(self, target_name: str, tool_key, bonus, room, exits) -> Optional[dict]:
        """Try to force an exit/door, launching a QTE if appropriate, and unlock on success."""
        try:
            tnorm = self._norm(target_name)
            matched = None
            for direction, dest in exits.items():
                if isinstance(dest, dict):
                    continue
                if tnorm in {self._norm(direction), self._norm(f"{direction} door"), self._norm(dest), self._norm("door")}:
                    matched = (direction, dest)
                    break

            if matched:
                direction, dest_room_id = matched
                dest_data = self.get_room_data(dest_room_id) or {}

                # PATCH: Special handling for MRI-sealed doors (fatal on force success)
                current_room_id = self.player.get('location')
                if dest_data.get('locked_by_mri'):
                    # Check if MRI hazard is in an active magnetic state
                    mri_is_active = False
                    if self.hazard_engine:
                        hazards_master = self.resource_manager.get_data('hazards', {})
                        for hid, h_inst in self.hazard_engine.active_hazards.items():
                            if h_inst.get('type') == 'mri' and h_inst.get('location') == current_room_id:
                                state = h_inst.get('state')
                                # Active magnetic states that make forcing fatal
                                active_states = [
                                    'field_active_doors_locked',
                                    'projectile_stage_1_cart',
                                    'projectile_stage_2_window',
                                    'final_barrage_1_wheelchair',
                                    'final_barrage_2_oxygen_tank',
                                    'final_barrage_3_gurney'
                                ]
                                if state in active_states:
                                    mri_is_active = True
                                    mri_hazard_id = hid
                                    break
                    
                    if mri_is_active:
                        # Fatal force QTE: success leads to death_by_door_bisection
                        strength = self._get_stat('strength', 1)
                        tgt_mash = self._compute_force_difficulty(dest_data or room, base=20, strength=strength, tool_bonus=bonus)
                        
                        ctx = {
                            "ui_mode": "in-screen",
                            "qte_source_hazard_id": mri_hazard_id,
                            "qte_context": {
                                "ui_prompt_message": "The magnetic field is immense! MASH to force the door!",
                                "target_mash_count": tgt_mash,
                                "duration": 4.0,
                                "success_message": "With a final heave, you wrench the metal door open just enough to slip through...",
                                "failure_message": "You can't fight the pull! The door remains sealed shut!",
                                "hp_damage_on_failure": 0,
                                "is_fatal_on_success": True,  # CRITICAL: Success is fatal
                                "next_state_after_qte_success": "death_by_door_bisection",
                                "next_state_after_qte_failure": "field_active_doors_locked"
                            }
                        }
                        if self.qte_engine:
                            self.player['qte_active'] = True
                            self.qte_engine.start_qte("button_mash", ctx)
                            self.logger.info(f"_force_try_exit: Started fatal MRI door force QTE for '{dest_room_id}'")
                            return self._build_response(
                                message="You set your shoulder against the magnetically sealed door. This is madness...",
                                turn_taken=True
                            )
                        else:
                            return self._build_response(
                                message="The magnetic field is too strong. You cannot force this door.",
                                turn_taken=True
                            )
                    
                    # If MRI is not active, normal "can't force" message
                    msg = "The magnetic field has sealed that door shut!"
                    self.logger.info(f"_force_try_exit: {msg}")
                    return self._build_response(
                        message=color_text(msg, "warning", self.resource_manager),
                        turn_taken=False
                    )

                # Normal force logic for non-MRI doors
                strength = self._get_stat('strength', 1)
                tgt_mash = self._compute_force_difficulty(dest_data or room, base=16, strength=strength, tool_bonus=bonus)

                ctx = {
                    "ui_mode": "in-screen",
                    "qte_source_hazard_id": f"force_door#{dest_room_id}",
                    "qte_context": {
                        "ui_prompt_message": f"The door resists! {'Use your tool! ' if tool_key else ''}Mash to force it!",
                        "target_mash_count": tgt_mash,
                        "duration": 4.0,
                        "success_message": f"You wrench the door to {dest_room_id.replace('_', ' ')} open just enough to slip through!",
                        "failure_message": "You can't budge it. Your arms ache.",
                        "hp_damage_on_failure": 0,
                        "effects_on_success": [
                            {"type": "unlock_room", "room_id": dest_room_id}
                        ],
                        "pending_move": direction
                    }
                }
                if self.qte_engine:
                    self.player['qte_active'] = True
                    self.qte_engine.start_qte("button_mash", ctx)
                    self.logger.info(f"_force_try_exit: QTE started for forcing door to '{dest_room_id}'")
                    return self._build_response(message="You brace yourself and shove.", turn_taken=True)
                else:
                    self.logger.info("_force_try_exit: No QTE engine, fallback to failure message.")
                    return self._build_response(message="You strain against the door, but nothing happens.", turn_taken=True)
            return None
        except Exception as e:
            self.logger.error(f"_force_try_exit: Error: {e}", exc_info=True)
            return self._build_response(message="Something went wrong while forcing the door.", turn_taken=True, success=False)