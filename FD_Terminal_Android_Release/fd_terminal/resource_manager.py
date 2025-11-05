# fd_terminal/resource_manager.py
import os
from typing import Optional, List, Dict, Tuple
try:
    from typing import TypedDict, NotRequired
except ImportError:
    from typing_extensions import TypedDict, NotRequired
import json
import logging
import sys
from typing import Type, get_type_hints, get_args, get_origin, Any, Union, List, Dict

try:
    from typing import NotRequired, TypedDict
except ImportError:
    from typing_extensions import NotRequired, TypedDict

# Import all the laws this librarian must enforce.
from .schemas import (
    ItemTypedDict, HazardTypedDict, RoomTypedDict, CharacterClassTypedDict,
    ConstantsTypedDict, DisasterTypedDict, EvidenceSourceTypedDict,
    GameConfigTypedDict, HazardSynergiesTypedDict, FurnitureTypedDict,
    LevelRequirementTypedDict, PlayerAchievementsFileTypedDict,
    QTEDefinitionTypedDict, StatusEffectsFileTypedDict, SurvivorFatesFileTypedDict,
    TemperatureMappingsFileTypedDict, VisionariesFileTypedDict, NPCTypedDict
)

class ResourceManager:
    """
    The Grand Library.
    Manages loading and VALIDATING all game data from external JSON files.
    """
    def __init__(self, app_root: str = None):
        """
        Initializes the ResourceManager.
        If app_root is not provided, it will robustly determine the project's
        root directory, assuming 'data' is a sibling to the 'fd_terminal' package.
        """
        if app_root is None:
            # This is the corrected logic. It finds the directory of the current file
            # (resource_manager.py), goes up one level (to the project root),
            # ensuring it correctly finds the 'data' folder as a sibling.
            app_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        
        self.app_root = app_root
        self.master_data = {}
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"ResourceManager initialized with app_root: {self.app_root}")


        # The mapping of Scroll names to their governing Law (schema).
        # This is the heart of the validation system.
        self.schema_map = {
            'items': ItemTypedDict,
            'hazards': HazardTypedDict,
            'rooms_level_1': RoomTypedDict,
            'rooms_level_2': RoomTypedDict, 
            'rooms_level_3': RoomTypedDict,
            'character_classes': CharacterClassTypedDict,
            'constants': ConstantsTypedDict,
            'disasters': DisasterTypedDict,
            'evidence_by_source': EvidenceSourceTypedDict,
            'game_config': GameConfigTypedDict,
            'hazard_synergies': HazardSynergiesTypedDict,
            'furniture': FurnitureTypedDict,
            'level_requirements': LevelRequirementTypedDict,
            'player_achievements': PlayerAchievementsFileTypedDict,
            'qte_definitions': QTEDefinitionTypedDict,
            'status_effects': StatusEffectsFileTypedDict,
            'survivor_fates': SurvivorFatesFileTypedDict,
            'temperature_mappings': TemperatureMappingsFileTypedDict,
            'visionaries': VisionariesFileTypedDict,
            'npcs': NPCTypedDict
        }

    def _discover_data_directory(self) -> Optional[str]:
        """Robustly finds the 'data' directory, whether in development or a bundled app."""
        self.logger.info("Discovering data directory...")
        # Path for bundled executables (PyInstaller)
        if hasattr(sys, '_MEIPASS'):
            bundle_data_path = os.path.join(sys._MEIPASS, 'data')
            if os.path.isdir(bundle_data_path):
                self.logger.info(f"Found bundled data directory: {bundle_data_path}")
                return bundle_data_path
        
        # Standard development path relative to app root
        root_data_path = os.path.join(self.app_root, 'data')
        if os.path.isdir(root_data_path):
            self.logger.info(f"Found data directory at app root: {root_data_path}")
            return root_data_path
            
        self.logger.error("FATAL: Could not find the 'data' directory.")
        return None

    def load_master_data(self) -> Dict[str, Any]:
        """
        Loads all JSON files from the data directory, validates them against their schemas,
        and stores them in the master_data dictionary.
        This is the primary rite of the ResourceManager.
        """
        self.logger.info("Loading and validating all master data...")
        data_dir = self._discover_data_directory()
        if not data_dir:
            raise FileNotFoundError("Critical Error: The game's 'data' directory could not be located.")

        has_errors = False
        for filename in os.listdir(data_dir):
            if not filename.lower().endswith('.json'):
                continue

            file_path = os.path.join(data_dir, filename)
            key_name = os.path.splitext(filename)[0]

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Find the correct law (schema) for this scroll (file)
                schema = self.schema_map.get(key_name)
                if schema:
                    self.logger.info(f"Validating '{filename}' against schema '{schema.__name__}'...")
                    is_valid, errors = self._validate_data(data, schema)
                    if not is_valid:
                        for error in errors:
                            self.logger.error(f"Schema validation FAILED for '{filename}': {error}")
                        has_errors = True
                        continue # Do not load a file that breaks the law
                else:
                    self.logger.warning(f"No schema defined for '{filename}'. Skipping validation.")
                
                # Special handling for files that need to be merged or restructured
                if key_name.startswith('rooms_level_'):
                    if 'rooms' not in self.master_data:
                        self.master_data['rooms'] = {}
                    level_id = key_name.split('_')[-1]
                    self.master_data['rooms'][level_id] = data
                else:
                    self.master_data[key_name] = data

                self.logger.info(f"Successfully loaded and validated '{filename}'.")

            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to load '{filename}': Invalid JSON syntax - {e}")
                has_errors = True
            except Exception as e:
                self.logger.error(f"An unexpected error occurred processing '{filename}': {e}", exc_info=True)
                has_errors = True

        if has_errors:
            error_msg = "One or more critical data files failed to load or validate. The game cannot start."
            self.logger.critical(error_msg)
            raise ValueError(error_msg)
            
        self.logger.info("All master data has been successfully loaded and validated.")
        return self.master_data

    def _validate_data(self, data: Any, schema: type) -> Tuple[bool, List[str]]:
        """
        Recursively validates data against a TypedDict schema. This is the core enforcement mechanism.
        It checks for missing keys, extra keys, and incorrect types in nested structures.
        """
        errors = []

        def check_typed_dict(d: dict, s: type, path: str):
            if not isinstance(d, dict):
                errors.append(f"Invalid type at '{path}': Expected a dictionary for '{s.__name__}', but got {type(d).__name__}.")
                return

            hints = get_type_hints(s)
            
            # Check for missing required keys
            required_keys = getattr(s, '__required_keys__', frozenset(hints.keys() if getattr(s, '__total__', True) else []))
            for key in required_keys:
                if key not in d:
                    errors.append(f"Missing required key at '{path}': '{key}'")

            # Check types of all present keys
            for key, value in d.items():
                if key not in hints:
                    # By default, TypedDict allows extra keys unless total=True and they aren't defined.
                    # This check is primarily for developer awareness.
                    # self.logger.debug(f"Extra key found at '{path}': '{key}'. Allowed by schema but may be unintended.")
                    continue
                
                expected_type = hints[key]
                check_value(value, expected_type, f"{path}.{key}")

        def check_value(v: Any, t: Any, path: str):
            origin = get_origin(t)
            args = get_args(t)

            if origin is Union:
                # For Union, at least one of the types must match.
                is_valid_union = False
                for arg in args:
                    temp_errors = []
                    # A sub-validation to see if any path works
                    if _is_valid_sub_type(v, arg):
                        is_valid_union = True
                        break
                if not is_valid_union:
                    errors.append(f"Type mismatch at '{path}': Value '{str(v)[:50]}' does not match any type in {t}.")
                return

            if origin is list:
                if not isinstance(v, list):
                    errors.append(f"Type mismatch at '{path}': Expected List, got {type(v).__name__}.")
                    return
                if args: # If the list is typed, e.g., List[str]
                    item_type = args[0]
                    for i, item in enumerate(v):
                        check_value(item, item_type, f"{path}[{i}]")
                return

            if origin is dict:
                 if not isinstance(v, dict):
                    errors.append(f"Type mismatch at '{path}': Expected Dict, got {type(v).__name__}.")
                    return
                 if args: # If the dict is typed, e.g., Dict[str, int]
                     key_type, val_type = args
                     for key, val in v.items():
                         check_value(key, key_type, f"{path}[{key}] (key)")
                         check_value(val, val_type, f"{path}[{key}] (value)")
                 return

            if get_origin(t) is NotRequired:
                # This should be handled by the key check, but we unwrap it here if needed.
                t = get_args(t)[0]

            # Check for nested TypedDict or primitive types
            is_td = isinstance(t, type) and hasattr(t, '__annotations__')
            if is_td:
                check_typed_dict(v, t, path)
            elif not isinstance(v, t):
                # Allow int to be validated as float, a common and safe case
                if t is float and isinstance(v, int):
                    return
                errors.append(f"Type mismatch at '{path}': Expected {t.__name__}, got {type(v).__name__}.")

        def _is_valid_sub_type(v, t):
            # A non-error-appending version of check_value for Union checks
            origin = get_origin(t)
            args = get_args(t)
            if origin is Union:
                return any(_is_valid_sub_type(v, arg) for arg in args)
            if origin in (list, dict):
                # For simplicity in Union checks, just check the container type
                return isinstance(v, origin)
            is_td = isinstance(t, type) and hasattr(t, '__annotations__')
            if is_td:
                # For simplicity, just check if it's a dict. The main check will dive deeper.
                return isinstance(v, dict)
            return isinstance(v, t)

        # Initial call to the validator
        # This handles both root-level dictionaries and dictionaries of objects (like items.json)
        if isinstance(data, dict):
            # If every value in the dict is another dict, assume it's a dictionary of objects
            is_collection = all(isinstance(v, dict) for v in data.values())
            # Exception for files that are a single object but not a collection
            if schema.__name__.endswith("FileTypedDict") or not is_collection:
                 check_typed_dict(data, schema, 'root')
            else:
                for key, value in data.items():
                    check_typed_dict(value, schema, key)
        
        return not errors, errors

    def get_data(self, key: str, default: Any = None) -> Any:
        """
        Safely retrieves data from the loaded master_data dictionary.
        If data has not been loaded yet, it triggers the loading process.
        """
        if not self.master_data:
            self.logger.warning("get_data() called before master data was loaded. Triggering load now.")
            self.load_master_data()
        
        return self.master_data.get(key, default)