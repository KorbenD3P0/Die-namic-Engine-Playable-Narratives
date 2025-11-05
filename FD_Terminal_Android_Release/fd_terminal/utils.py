import re
from typing import Optional
import os
import json
import logging
from .resource_manager import ResourceManager
# === COLOR CONSTANTS ===

def color_text(text: str, text_type: str, resource_manager: ResourceManager) -> str:
    """
    Applies Kivy color markup by looking up semantic types and colors
    from the constants loaded by the ResourceManager.
    """
    if not resource_manager:
        return text # Failsafe

    constants = resource_manager.get_data('constants', {})
    semantic_map = constants.get('SEMANTIC_COLOR_MAP', {})
    colors = constants.get('COLORS', {})

    color_name = semantic_map.get(text_type, 'WHITE')
    color_hex = colors.get(color_name, 'ffffff')
    
    return f"[color={color_hex}]{text}[/color]"

def get_save_filepath(slot_identifier: str = "quicksave") -> str:
    """
    Generates the absolute filepath for a given save slot identifier.
    This is the single source of truth for where save files are stored.

    Args:
        slot_identifier (str): The name of the save slot (e.g., "quicksave", "slot_1").

    Returns:
        str: The full path to the save file.
    """
    try:
        # This will work when the Kivy app is running.
        from kivy.app import App
        save_dir = os.path.join(App.get_running_app().user_data_dir, 'saves')
    except (ImportError, AttributeError):
        # This provides a fallback for testing outside of a Kivy app context.
        save_dir = os.path.join(os.getcwd(), 'saves')
    
    os.makedirs(save_dir, exist_ok=True)
    filename = f"savegame_{slot_identifier}.json"
    return os.path.join(save_dir, filename)

def get_save_slot_info(slot_id: str) -> Optional[dict]:
    """
    Reads the 'save_info' block from a save file for UI previews, without
    loading the entire game state. This is a lightweight, UI-facing utility.

    Args:
        slot_id (str): The identifier for the save slot.

    Returns:
        A dictionary with preview info, a dictionary indicating corruption, or None if the file doesn't exist.
    """
    save_path = get_save_filepath(slot_id)
    if not os.path.exists(save_path):
        return None
        
    try:
        with open(save_path, "r", encoding="utf-8") as f:
            content = f.read()
            if not content.strip(): # Handle empty files
                return None
            save_data = json.loads(content)

        # The 'save_info' block is designed specifically for this kind of preview
        info = save_data.get("save_info", {})
        return {
            "timestamp": info.get("timestamp", "No date"),
            "location": info.get("location", "?"),
            "character_class": info.get("character_class", "Unknown"),
            "turns_left": info.get("turns_left", "--"),
            "score": info.get("score", 0),
            "corrupted": False
        }
    except (json.JSONDecodeError, KeyError) as e:
        logging.error(f"Save file for slot '{slot_id}' appears corrupted: {e}")
        # Return a specific structure that the UI can check for
        return {"corrupted": True, "timestamp": "Corrupted File"}
    except Exception as e: 
        logging.error(f"An unexpected error occurred reading save slot info for '{slot_id}': {e}", exc_info=True)
        return {"corrupted": True, "timestamp": "Read Error"}