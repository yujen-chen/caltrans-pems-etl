#!/usr/bin/env python3
"""Verify correct import methods"""
import sys
from pathlib import Path

print("=" * 60)
print("Test 1: Using pems.storage (Recommended method)")
print("=" * 60)

try:
    from pems.storage import R2StorageHandler
    print("✅ from pems.storage import R2StorageHandler - Success")
    print(f"   Module path: {R2StorageHandler.__module__}")

    # Check module file location
    import pems.storage
    print(f"   Actual file: {pems.storage.__file__}")
except ModuleNotFoundError as e:
    print(f"❌ Failed: {e}")

print("\n" + "=" * 60)
print("Test 2: Using src.pems.storage (Not recommended)")
print("=" * 60)

try:
    # Temporarily remove project root (if present)
    project_root = str(Path(__file__).parent.parent)
    if project_root in sys.path:
        sys.path.remove(project_root)
        print(f"   Removed project root from sys.path: {project_root}")

    from src.pems.storage import R2StorageHandler as R2Handler2
    print("⚠️  from src.pems.storage import R2StorageHandler - Success")
    print(f"   Module path: {R2Handler2.__module__}")
    print("   Note: This only works when project root is in Python path")
except ModuleNotFoundError as e:
    print(f"✅ Failed (as expected): {e}")
    print("   This is correct behavior! After package installation, should not use src.pems")

print("\n" + "=" * 60)
print("Conclusion")
print("=" * 60)
print("✅ Correct method: from pems.storage import R2StorageHandler")
print("❌ Wrong method: from src.pems.storage import R2StorageHandler")
print("\nReasons:")
print("1. pyproject.toml defines package name as 'pems' (without 'src')")
print("2. After installation, Python only recognizes 'pems' as package name")
print("3. 'src' is just development directory structure, not part of package name")
