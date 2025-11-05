"""
The Chronicler of Deeds.

This system tracks player achievements, evidence collected, and stories unlocked.
It provides the methods for recording and retrieving player legacy.
"""

import logging
import json
import os
from datetime import datetime
from .resource_manager import ResourceManager

class AchievementsSystem:
    def __init__(self, resource_manager: ResourceManager, notify_callback=None):
        self.logger = logging.getLogger("AchievementsSystem")
        self.resource_manager = resource_manager
        self.notify_callback = notify_callback
        
        # File paths for persistence
        self.save_dir = "saves"
        self.achievements_file = os.path.join(self.save_dir, "achievements.json")
        
        # Initialize collections
        self.achievements = {}
        self.evidence_collection = {}
        self.unlocked_stories = set()
        
        # Ensure save directory exists
        os.makedirs(self.save_dir, exist_ok=True)
        
        self.logger.info("Chronicler of Deeds initialized.")

    def load_achievements(self):
        """Load achievements and evidence from persistent storage."""
        try:
            if os.path.exists(self.achievements_file):
                with open(self.achievements_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Load achievements
                self.achievements = data.get('achievements', {})
                
                # Load evidence collection
                self.evidence_collection = data.get('evidence_collection', {})
                
                # Load unlocked stories (convert from list to set)
                self.unlocked_stories = set(data.get('unlocked_stories', []))
                
                self.logger.info(f"Loaded {len(self.achievements)} achievements, "
                               f"{len(self.evidence_collection)} evidence pieces, "
                               f"{len(self.unlocked_stories)} unlocked stories")
            else:
                # Initialize from master data if no save file exists
                master_achievements = self.resource_manager.get_data('player_achievements', {})
                if 'achievements' in master_achievements:
                    # Set all achievements as locked initially
                    for ach_id, ach_data in master_achievements['achievements'].items():
                        self.achievements[ach_id] = {
                            **ach_data,
                            'unlocked': False,
                            'unlock_date': None
                        }
                
                self.logger.info("No save file found. Starting with fresh achievements.")
                
        except Exception as e:
            self.logger.error(f"Error loading achievements: {e}", exc_info=True)
            self.achievements = {}
            self.evidence_collection = {}
            self.unlocked_stories = set()

    def save_achievements(self):
        """Save achievements and evidence to persistent storage."""
        try:
            data = {
                'achievements': self.achievements,
                'evidence_collection': self.evidence_collection,
                'unlocked_stories': list(self.unlocked_stories),  # Convert set to list for JSON
                'last_updated': datetime.now().isoformat()
            }
            
            with open(self.achievements_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
            self.logger.info("Achievements saved successfully.")
            
        except Exception as e:
            self.logger.error(f"Error saving achievements: {e}", exc_info=True)

    def unlock(self, achievement_id: str) -> bool:
        """Unlock an achievement if it exists and isn't already unlocked."""
        try:
            # Get master achievement data
            master_achievements = self.resource_manager.get_data('player_achievements', {})
            master_ach_data = master_achievements.get('achievements', {}).get(achievement_id)
            
            if not master_ach_data:
                self.logger.warning(f"Achievement '{achievement_id}' not found in master data")
                return False
            
            # Check if already unlocked
            if self.achievements.get(achievement_id, {}).get('unlocked', False):
                self.logger.debug(f"Achievement '{achievement_id}' already unlocked")
                return False
            
            # Unlock the achievement
            self.achievements[achievement_id] = {
                **master_ach_data,
                'unlocked': True,
                'unlock_date': datetime.now().isoformat()
            }
            
            self.logger.info(f"Achievement unlocked: '{achievement_id}'")
            
            # Notify UI if callback provided
            if self.notify_callback:
                self.notify_callback(
                    "Achievement Unlocked!",
                    f"{master_ach_data.get('icon', '🏆')} {master_ach_data.get('name', achievement_id)}"
                )
            
            # Auto-save after unlocking
            self.save_achievements()
            return True
            
        except Exception as e:
            self.logger.error(f"Error unlocking achievement '{achievement_id}': {e}", exc_info=True)
            return False

    def record_evidence(self, evidence_id: str, name: str, description: str):
        """Record a piece of evidence in the collection."""
        try:
            if evidence_id in self.evidence_collection:
                self.logger.debug(f"Evidence '{evidence_id}' already recorded")
                return
            
            # Get additional details from items.json if available
            items_data = self.resource_manager.get_data('items', {})
            item_details = items_data.get(evidence_id, {})
            
            # Record the evidence
            self.evidence_collection[evidence_id] = {
                'name': name,
                'description': description,
                'examine_details': item_details.get('examine_details', description),
                'character_connection': item_details.get('character_connection', ''),
                'found_date': datetime.now().isoformat(),
                'type': item_details.get('type', 'evidence')
            }
            
            self.logger.info(f"Evidence recorded: '{evidence_id}' - {name}")
            
            # Check for story completion
            self._check_for_story_completion(evidence_id)
            
            # Check for evidence-based achievements
            self._check_evidence_achievements()
            
            # Auto-save after recording evidence
            self.save_achievements()
            
        except Exception as e:
            self.logger.error(f"Error recording evidence '{evidence_id}': {e}", exc_info=True)

    def _check_for_story_completion(self, new_evidence_id: str):
        """Check if collecting this evidence completes any story sets."""
        try:
            evidence_by_source = self.resource_manager.get_data('evidence_by_source', {})
            collected_ids = set(self.evidence_collection.keys())
            
            for story_name, story_data in evidence_by_source.items():
                required_ids = set(story_data.get('evidence_list', []))
                
                # Check if this evidence belongs to this story
                if new_evidence_id in required_ids:
                    # Check if all required evidence is collected
                    if required_ids.issubset(collected_ids):
                        if story_name not in self.unlocked_stories:
                            self.unlocked_stories.add(story_name)
                            self.logger.info(f"Story completed: '{story_name}'")
                            
                            # Notify UI
                            if self.notify_callback:
                                self.notify_callback(
                                    "Story Unlocked!",
                                    f"You've collected all evidence for '{story_name}'. Read the full story in your journal."
                                )
                            
                            # Unlock story-related achievements
                            if len(self.unlocked_stories) == 1:
                                self.unlock("lore_master")  # First story
                            elif len(self.unlocked_stories) >= 5:
                                self.unlock("historian")   # Multiple stories
                                
        except Exception as e:
            self.logger.error(f"Error checking story completion: {e}", exc_info=True)

    def _check_evidence_achievements(self):
        """Check for achievements based on evidence collection milestones."""
        try:
            evidence_count = len(self.evidence_collection)
            
            # Evidence collection milestones
            if evidence_count >= 1:
                self.unlock("first_evidence")
            if evidence_count >= 10:
                self.unlock("evidence_collector")
            if evidence_count >= 25:
                self.unlock("master_investigator")
                
        except Exception as e:
            self.logger.error(f"Error checking evidence achievements: {e}", exc_info=True)

    def has_evidence(self, evidence_id: str) -> bool:
        """Check if a piece of evidence has been collected."""
        return evidence_id in self.evidence_collection

    def get_all_achievements(self):
        """Return all achievements with their current status."""
        try:
            # Return the loaded achievements, or fall back to master data
            if self.achievements:
                return list(self.achievements.values())
            else:
                # Fallback to master data with all locked
                master_data = self.resource_manager.get_data('player_achievements', {})
                achievements = []
                for ach_data in master_data.get('achievements', {}).values():
                    achievements.append({
                        **ach_data,
                        'unlocked': False,
                        'unlock_date': None
                    })
                return achievements
                
        except Exception as e:
            self.logger.error(f"Error getting achievements: {e}", exc_info=True)
            return []