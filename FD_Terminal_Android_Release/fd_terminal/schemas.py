# schemas.py
"""
The Tablets of Law.

Defines the data structures for all game entities using TypedDict for schema validation.
This is the single source of truth for data integrity, ensuring that all Scrolls of Destiny
(JSON files) adhere to the Architect's Design.
"""
from typing import List, Dict, Any, Union, Set
from typing import Dict, Set
try:
    from typing import NotRequired
except ImportError:
    from typing_extensions import NotRequired

try:
    from typing import TypedDict, NotRequired
except ImportError:
    from typing_extensions import TypedDict, NotRequired

# --- CORE CONFIGURATION SCHEMAS ---

class GameConfigTypedDict(TypedDict, total=False):
    GAME_NAME: str
    GAME_VERSION: str
    INITIAL_TURNS: int
    MAX_SAVE_SLOTS: int
    WEIGHT_CATEGORIES: Dict[str, float]

class ConstantsTypedDict(TypedDict, total=False):
    pass

class QTEDefinitionTypedDict(TypedDict, total=False):
    name: str
    input_type: str
    valid_responses: List[str]
    default_duration: Union[int, float]

# --- NEW: Specific TypedDicts for Hazard Interactions ---
class PlayerInteractionRuleTypedDict(TypedDict, total=False):
    on_target_name: Union[str, List[str]]
    requires_hazard_state: List[str]
    qte_to_trigger: str
    on_success: Dict[str, str]
    on_failure: Dict[str, str]
    message: str
    blocks_action_success: bool

class RoomActionTriggerRuleTypedDict(TypedDict, total=False):
    action_verb: str
    on_target_name: str
    requires_hazard_state: List[str]
    effect_on_self: Dict[str, Any]
    blocks_action_success: bool

# --- NEW: Hyper-Specific Schemas for Nested Data ---

class QTEContextTypedDict(TypedDict, total=False):
    """Defines the highly variable structure of a QTE's context data."""
    ui_prompt_message: str
    expected_input_word: str
    success_message: str
    failure_message_wrong_input: str
    failure_message_timeout: str
    is_fatal_on_failure: bool
    next_state_after_qte_success: str
    next_state_after_qte_failure: str
    next_state_after_timeout: str
    # For branching QTEs
    expected_input_options: List[str]
    input_to_next_state: Dict[str, str]
    success_messages: List[str]
    # For custom logic
    qte_source_hazard_id: str

    # --- NEW: per-character tunables (allow scalar or {"default":X,"EMT":Y}) ---
    target_mash_count: Union[int, Dict[str, int]]
    required_tap_count: Union[int, Dict[str, int]]
    required_hold_time: Union[float, Dict[str, float]]
    target_alternations_default: Union[int, Dict[str, int]]
    target_beats: Union[int, Dict[str, int]]
    keys_default: List[str]
    required_sequence: List[str]
    required_code: List[str]

class QTETriggerTypedDict(TypedDict, total=False):
    """Defines the structure for a QTE trigger within a hazard state."""
    qte_type: str
    duration: Union[int, float]
    # REFINED: Uses the new specific context schema
    qte_context: QTEContextTypedDict

class UIPopupEventTypedDict(TypedDict, total=False):
    """Defines the structure for a UI popup event."""
    type: str
    title: str
    text: str

class RoomActionEffectTypedDict(TypedDict, total=False):
    """Defines the effects of a room action trigger."""
    target_state: str
    ui_popup_event: UIPopupEventTypedDict # Now using our precise law

class RoomActionTriggerRuleTypedDict(TypedDict, total=False):
    action_verb: str
    on_target_name: str
    requires_hazard_state: List[str]
    # REFINED: Uses the new specific effect schema
    effect_on_self: RoomActionEffectTypedDict
    blocks_action_success: bool

class EnvironmentalEffectTypedDict(TypedDict, total=False):
    noise_level: Union[int, str]
    is_sparking: bool
    visibility: str
    temperature_celsius: int
    gas_level: int
    is_electrified: bool
    is_on_fire: bool

class FurnitureUseInteractionRuleTypedDict(TypedDict, total=False):
    item_names_required: List[str]
    action_effect: str
    message_success: str
    message_fail_item: str
    mri_states_can_deactivate: List[str]
    message_fail_mri_state: str

class FurnitureOnBreakSpillItem(TypedDict):
    name: str
    quantity: Union[int, str]

# --- GAMEPLAY OBJECT SCHEMAS ---

class ItemTypedDict(TypedDict):
    name: str
    description: str
    type: str
    examine_details: NotRequired[str]
    subtype: NotRequired[str]
    level: NotRequired[Union[int, str, List[int]]]
    weight: NotRequired[Union[str, float, int]]
    takeable: NotRequired[bool]
    is_hidden: NotRequired[bool]
    is_evidence: NotRequired[bool]
    is_critical: NotRequired[bool]
    is_flammable: NotRequired[bool]
    is_metallic: NotRequired[bool]
    is_distributable_in_containers: NotRequired[bool]
    consumable_on_use: NotRequired[bool]
    unlocks: NotRequired[List[str]]
    use_on: NotRequired[List[str]]
    use_result: NotRequired[Dict[str, str]]
    trigger_hazard_on_action: NotRequired[Dict[str, str]]
    character_connection: NotRequired[str]
    special_property: NotRequired[str]

class FurnitureTypedDict(TypedDict):
    name: str
    description: str
    is_container: NotRequired[bool]
    locked: NotRequired[bool]
    capacity: NotRequired[int]
    items: NotRequired[List[str]]
    is_metallic: NotRequired[bool]
    is_breakable: NotRequired[bool]
    break_integrity: NotRequired[int]
    on_break_success_message: NotRequired[str]
    on_break_spill_items: NotRequired[List[FurnitureOnBreakSpillItem]]
    use_item_interaction: NotRequired[List[FurnitureUseInteractionRuleTypedDict]]
    unlocks_with_item: NotRequired[str]

class RoomObjectTypedDict(TypedDict, total=False):
    name: str
    id_key: str
    description: str
    is_omen_provider: NotRequired[str]
    aliases: NotRequired[List[str]]

class RoomTypedDict(TypedDict):
    description: str
    exits: Dict[str, Union[str, Dict[str, Any]]]
    examine_details: NotRequired[Dict[str, str]]
    furniture: NotRequired[List[Union[str, FurnitureTypedDict]]]
    objects: NotRequired[List[Union[str, RoomObjectTypedDict]]]
    items_present: NotRequired[List[str]]
    hazards_present: NotRequired[List[Union[str, Dict[str, Any]]]]
    possible_hazards: NotRequired[List[Union[str, Dict[str, Any]]]]
    first_entry_text: NotRequired[Union[str, None]]
    state_descriptions: NotRequired[Dict[str, str]]
    state_examine_details: NotRequired[Dict[str, Dict[str, str]]]
    floor: NotRequired[int]
    locked: NotRequired[bool]
    unlocks_with: NotRequired[Union[str, None]]
    forceable: NotRequired[bool]
    force_threshold: NotRequired[int]
    npcs: NotRequired[List["NPCTypedDict"]]
    npcs_present: NotRequired[List["NPCTypedDict"]]
# --- HAZARD & CHALLENGE SCHEMAS ---

class HazardStateChangeTriggerTypedDict(TypedDict, total=False):
    """
    Trigger object for spawning/advancing hazards when a state is entered.
    Supports both old and new key names.
    """
    # Hazard type to act on (aliases supported)
    type: str                 # alias for hazard_type (as used in hazards.json)
    hazard_type: str          # canonical key (engine also accepts 'type')

    # State to apply (aliases supported)
    target_state: str         # preferred key in data
    initial_state: str        # legacy alias

    # Optional fields
    location: str
    chance: Union[int, float]
    message: str
    options: List[str]

class HazardStateTypedDict(TypedDict, total=False):
    description: str
    environmental_effect: "EnvironmentalEffectTypedDict"
    triggers_qte_on_entry: "QTETriggerTypedDict"
    chance_to_progress: Union[int, float]
    next_state: str
    instant_death_in_room: bool
    death_message: str
    on_state_entry_special_action: str
    is_terminal_state: bool
    autonomous_action: str
    duration_in_state: Union[int, float]
    # REFINED: precise trigger schema instead of List[Dict[str, Any]]
    triggers_hazard_on_state_change: List[HazardStateChangeTriggerTypedDict]

class HazardTypedDict(TypedDict, total=False):
    name: str
    initial_state: str
    states: Dict[str, HazardStateTypedDict]
    sabotage: Dict[str, Any]
    object_name_options: List[str]
    player_interaction: Dict[str, List[PlayerInteractionRuleTypedDict]]
    triggered_by_room_action: List[RoomActionTriggerRuleTypedDict]
    can_move_between_rooms: bool

# --- NARRATIVE & CHARACTER SCHEMAS ---

class CharacterClassTypedDict(TypedDict):
    name: NotRequired[str]
    description: str
    max_hp: int
    perception: int
    intuition: int
    strength: float

class DisasterTypedDict(TypedDict):
    name: NotRequired[str]
    description: str
    killed_count: Union[Dict[str, int], int]
    warnings: List[str]
    related_evidence: NotRequired[List[str]]
    death_narrative: NotRequired[str]
    environmental_omens: NotRequired[Dict[str, Union[str, List[str]]]]

class DialogueStateTypedDict(TypedDict):
    text: str
    on_talk_action: NotRequired[Dict[str, Union[str, Dict[str, Any]]]]
    next_state: NotRequired[str]

class NPCTypedDict(TypedDict):
    name: str
    description: str
    initial_state: str
    dialogue_states: Dict[str, DialogueStateTypedDict]

class LevelRequirementTypedDict(TypedDict):
    entry_room: str
    exit_room: str
    items_needed: List[str]
    evidence_needed: List[str]
    name: str
    next_level_id: Union[int, None]
    next_level_start_room: Union[str, None]
    completion_hazard: NotRequired[str]

class EvidenceSourceTypedDict(TypedDict):
    backstory: str
    evidence_list: List[str]

class HazardSynergiesTypedDict(TypedDict, total=False):
    water: List[str]
    electrical: List[str]
    fire: List[str]
    flammable_gas: List[str]

class StatusEffectsFileTypedDict(TypedDict, total=False):
    status_effects_definitions: Dict[str, Any]
    VISIBILITY_LEVELS_SEVERITY: Dict[str, int]
    SMELL_LEVELS_PRIORITY: Dict[str, int]

class SurvivorFatesFileTypedDict(TypedDict):
    fates: List[str]

class TemperatureMappingsFileTypedDict(TypedDict, total=False):
    normal: int
    cold: int
    freezing: int
    hot: int

class VisionariesFileTypedDict(TypedDict, total=False):
    strangers_distinctive: List[str]
    children_youths: List[str]
    family_friends: List[str]
    emergency_services: List[str]
    service_workers_venue: List[str]

# --- PLAYER STATE & PROGRESS SCHEMAS ---

class PlayerTypedDict(TypedDict):
    location: str
    # inventory is treated as a dict by the engine when awarding items
    inventory: Union[Dict[str, Any], List[Union[str, Dict[str, Any]]]]
    hp: int
    max_hp: int
    fear: float
    score: int
    turns_left: int
    actions_taken: int
    visited_rooms: Set[str]
    current_level: int
    character_class: str
    status_effects: Dict[str, int]
    qte_active: Union[bool, str]
    qte_context: Dict[str, Any]
    qte_duration: float
    intro_disaster: Dict[str, Any]

class AchievementTypedDict(TypedDict):
    name: str
    unlocked: bool
    icon: str
    description: str

class PlayerAchievementsFileTypedDict(TypedDict):
    achievements: Dict[str, AchievementTypedDict]
    evidence_collection: Dict[str, Any]
    unlocked_stories: List[str]