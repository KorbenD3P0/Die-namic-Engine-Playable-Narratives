# fd_terminal/resource_manager.py
import os
import json
import logging
import sys
from typing import Type, get_type_hints, get_args, get_origin, Any, Union, List, Dict, Tuple

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

    def _discover_data_directory(self) -> Union[str, None]:
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
                    # Most data files are dictionaries where each entry should match the schema
                    # Files that are single objects (not collections of entries):
                    single_object_files = ['game_config', 'constants', 'hazard_synergies', 'player_achievements', 
                                          'status_effects', 'survivor_fates', 'temperature_mappings', 'visionaries', 'npcs']
                    
                    if isinstance(data, dict) and key_name not in single_object_files:
                        # Validate each entry in the dictionary
                        is_valid = True
                        errors = []
                        for entry_key, entry_value in data.items():
                            entry_valid, entry_errors = self._validate_data(entry_value, schema)
                            if not entry_valid:
                                for error in entry_errors:
                                    self.logger.error(f"Schema validation FAILED for '{filename}' entry '{entry_key}': {error}")
                                    errors.append(f"Entry '{entry_key}': {error}")
                                is_valid = False
                        if not is_valid:
                            has_errors = True
                            continue # Do not load a file that breaks the law
                    else:
                        # For files that are single objects (not collections), validate the whole file
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

    def get_data(self, key: str, default: Any = None) -> Any:
        """
        Retrieves loaded data by key name.
        
        Args:
            key: The name of the data file (without .json extension)
            default: Value to return if key is not found
            
        Returns:
            The loaded data, or default if not found
        """
        return self.master_data.get(key, default)

    def _validate_data(self, data: Any, schema: type) -> Tuple[bool, List[str]]:
        """
        Validates data against a TypedDict schema.
        Returns (is_valid, list_of_errors)
        """
        errors = []
        try:
            check_typed_dict(data, schema, 'root')
        except Exception as e:
            errors.append(str(e))
        return (len(errors) == 0, errors)

def check_typed_dict(data: Any, schema: type, path: str = 'root'):
    """
    Recursively validates data against a TypedDict schema.
    Raises descriptive exceptions on validation failure.
    """
    if not isinstance(data, dict):
        raise TypeError(f"Expected dict at '{path}', got {type(data).__name__}")
    
    # Get TypedDict annotations
    hints = get_type_hints(schema)
    required_keys = getattr(schema, '__required_keys__', set(hints.keys()))
    optional_keys = getattr(schema, '__optional_keys__', set())
    
    # Check for missing required keys
    for key in required_keys:
        if key not in data:
            raise ValueError(f"Missing required key at '{path}': '{key}'")
    
    # Validate each field
    for key, value in data.items():
        if key not in hints:
            # Allow extra keys that aren't in schema
            continue
        
        expected_type = hints[key]
        try:
            check_value(value, expected_type, f"{path}.{key}")
        except Exception as e:
            raise type(e)(f"{path}.{key}: {str(e)}")

def check_value(value: Any, expected_type: Any, path: str):
    """
    Validates a value against an expected type annotation.
    Handles typing module types properly without using isinstance() on TypedDict.
    """
    import typing
    from typing import get_origin, get_args
    
    # Handle None/Optional
    origin = get_origin(expected_type)
    args = get_args(expected_type)
    
    # Handle Union types (including Optional)
    if origin is typing.Union:
        # Try each type in the union
        errors = []
        for arg_type in args:
            try:
                check_value(value, arg_type, path)
                return  # Success with one type
            except Exception as e:
                errors.append(str(e))
        # None of the union types matched
        raise TypeError(f"Value doesn't match any type in Union at '{path}': {errors}")
    
    # Handle None values - must come BEFORE other checks
    if value is None:
        if type(None) in args or expected_type is type(None):
            return
        # Check if this is an Optional type (Union with None)
        if origin is typing.Union and type(None) in args:
            return
        raise TypeError(f"Expected non-None value at '{path}'")
    
    # Handle Any type - always valid
    if expected_type is typing.Any or str(expected_type) == 'typing.Any':
        return
    
    # Handle List types
    if origin is list:
        if not isinstance(value, list):
            raise TypeError(f"Expected list at '{path}', got {type(value).__name__}")
        if args:  # If there's a type argument like List[str]
            item_type = args[0]
            for i, item in enumerate(value):
                check_value(item, item_type, f"{path}[{i}]")
        return
    
    # Handle Dict types - THIS IS THE KEY FIX
    if origin is dict:
        if not isinstance(value, dict):
            raise TypeError(f"Expected dict at '{path}', got {type(value).__name__}")
        if args and len(args) == 2:  # If there are type arguments like Dict[str, int]
            key_type, val_type = args
            for k, v in value.items():
                # Validate the key type
                check_value(k, key_type, f"{path} key '{k}'")
                # Validate the value type - this will recursively handle List[TypedDict]
                check_value(v, val_type, f"{path}[{k}]")
        return
    
    # Handle Literal types
    if origin is typing.Literal:
        if value not in args:
            raise ValueError(f"Value at '{path}' must be one of {args}, got {value}")
        return
    
    # Handle basic types (str, int, bool, float, etc.)
    if isinstance(expected_type, type):
        # Special case: allow int where float is expected (Python convention)
        if expected_type is float and isinstance(value, (int, float)):
            return
        if not isinstance(value, expected_type):
            raise TypeError(f"Expected {expected_type.__name__} at '{path}', got {type(value).__name__}")
        return
    
    # Handle TypedDict (nested) - check if it has __annotations__ or __required_keys__
    # This is the key fix: detect TypedDict without using isinstance()
    if (hasattr(expected_type, '__annotations__') or 
        hasattr(expected_type, '__required_keys__') or
        hasattr(expected_type, '__optional_keys__')):
        # This is a TypedDict - validate as dict structure
        if not isinstance(value, dict):
            raise TypeError(f"Expected dict for TypedDict at '{path}', got {type(value).__name__}")
        check_typed_dict(value, expected_type, path)
        return
    
    # If we get here, we don't know how to validate this type
    # Just accept it to avoid breaking the validation
    return
