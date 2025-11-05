import json

# Check character_classes.json
print('=== character_classes.json ===')
with open('data/character_classes.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
    for key, value in data.items():
        missing = [f for f in ['description', 'intuition', 'perception', 'strength', 'max_hp'] if f not in value]
        if missing:
            print(f'{key}: Missing {missing}')

# Check disasters.json
print('\n=== disasters.json ===')
with open('data/disasters.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
    for key, value in data.items():
        if isinstance(value, dict):
            missing = [f for f in ['description', 'killed_count', 'warnings'] if f not in value]
            if missing:
                print(f'{key}: Missing {missing}')

# Check evidence_by_source.json
print('\n=== evidence_by_source.json ===')
with open('data/evidence_by_source.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
    for key, value in data.items():
        missing = [f for f in ['backstory', 'evidence_list'] if f not in value]
        if missing:
            print(f'{key}: Missing {missing}')

# Check furniture.json
print('\n=== furniture.json ===')
with open('data/furniture.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
    for key, value in data.items():
        missing = [f for f in ['name', 'description'] if f not in value]
        if missing:
            print(f'{key}: Missing {missing}')

# Check items.json
print('\n=== items.json ===')
with open('data/items.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
    for key, value in data.items():
        missing = [f for f in ['name', 'description', 'type'] if f not in value]
        if missing:
            print(f'{key}: Missing {missing}')

# Check level_requirements.json
print('\n=== level_requirements.json ===')
with open('data/level_requirements.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
    for key, value in data.items():
        missing = [f for f in ['entry_room', 'exit_room', 'items_needed', 'evidence_needed', 'name', 'next_level_id', 'next_level_start_room'] if f not in value]
        if missing:
            print(f'{key}: Missing {missing}')
