# delete_quicksave_files.py
import os
import glob

# Determine the saves directory (works for both dev and packaged app)
saves_dir = os.path.join(os.getcwd(), 'saves')

# Pattern to match all quicksave files (including backups/corrupted)
patterns = [
    "savegame_quicksave*",
    "*quicksave*"
]

deleted = []
for pattern in patterns:
    for filepath in glob.glob(os.path.join(saves_dir, pattern)):
        try:
            os.remove(filepath)
            deleted.append(filepath)
        except Exception as e:
            print(f"Could not delete {filepath}: {e}")

if deleted:
    print("Deleted quicksave files:")
    for f in deleted:
        print(f"  {f}")
else:
    print("No quicksave files found.")