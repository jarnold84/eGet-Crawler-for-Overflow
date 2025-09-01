# tests/_debug_path.py
import sys

print("\n--- DEBUG: sys.path during pytest collection ---")
for p in sys.path[:5]:
    print(p)
print("--- End of debug ---\n")
