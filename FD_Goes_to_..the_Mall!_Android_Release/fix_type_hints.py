import re
import os

def fix_type_hints_in_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        code = f.read()

    # --- 1. Replace Optional[X] and Optional[X] with Optional[X] ---
    code = re.sub(r'(\w+)\s*\|\s*None', r'Optional[\1]', code)
    code = re.sub(r'None\s*\|\s*(\w+)', r'Optional[\1]', code)
    code = re.sub(r'->\s*([\w\.]+)\s*\|\s*None', r'-> Optional[\1]', code)
    code = re.sub(r'->\s*None\s*\|\s*([\w\.]+)', r'-> Optional[\1]', code)

    # --- 2. Replace Union[X, Y] with Union[X, Y] (but not if X or Y is None, already handled above) ---
    # This handles simple cases; for complex nested types, a parser would be needed.
    code = re.sub(r'(\w+)\s*\|\s*(\w+)', r'Union[\1, \2]', code)

    # --- 3. Replace built-in generics with typing equivalents ---
    # Handles nested generics (e.g., List[Dict[str, int]])
    code = re.sub(r'\blist\[(.*?)\]', r'List[\1]', code)
    code = re.sub(r'\bdict\[(.*?)\]', r'Dict[\1]', code)
    code = re.sub(r'\bset\[(.*?)\]', r'Set[\1]', code)
    code = re.sub(r'\btuple\[(.*?)\]', r'Tuple[\1]', code)

    # --- 4. Add missing typing imports if needed ---
    imports = []
    if re.search(r'\bOptional\[', code) and 'from typing import Optional' not in code:
        imports.append('Optional')
    if re.search(r'\bUnion\[', code) and 'from typing import Union' not in code:
        imports.append('Union')
    if re.search(r'\bList\[', code) and 'from typing import List' not in code:
        imports.append('List')
    if re.search(r'\bDict\[', code) and 'from typing import Dict' not in code:
        imports.append('Dict')
    if re.search(r'\bSet\[', code) and 'from typing import Set' not in code:
        imports.append('Set')
    if re.search(r'\bTuple\[', code) and 'from typing import Tuple' not in code:
        imports.append('Tuple')
    # For TypedDict and NotRequired (Python <3.8)
    if re.search(r'\bTypedDict\b', code) and 'from typing import TypedDict' not in code and 'from typing_extensions import TypedDict' not in code:
        code = re.sub(
            r'(import [^\n]+\n)',
            r"\1try:\n    from typing import TypedDict, NotRequired\nexcept ImportError:\n    from typing_extensions import TypedDict, NotRequired\n",
            code,
            count=1
        )
    elif re.search(r'\bNotRequired\b', code) and 'from typing import NotRequired' not in code and 'from typing_extensions import NotRequired' not in code:
        code = re.sub(
            r'(import [^\n]+\n)',
            r"\1try:\n    from typing import NotRequired\nexcept ImportError:\n    from typing_extensions import NotRequired\n",
            code,
            count=1
        )
    # Add the rest of the imports
    if imports:
        code = re.sub(
            r'(import [^\n]+\n)',
            r'\1from typing import ' + ', '.join(imports) + '\n',
            code,
            count=1
        )

    # --- 5. Warn about match/case (Python 3.10+ only) ---
    if re.search(r'\bmatch\b.*:', code) and re.search(r'\bcase\b.*:', code):
        print(f"WARNING: 'match/case' syntax found in {filepath}. This is not supported in Python <3.10.")

    # --- 6. Write back the fixed code ---
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(code)

for root, dirs, files in os.walk('.'):
    for file in files:
        if file.endswith('.py'):
            fix_type_hints_in_file(os.path.join(root, file))