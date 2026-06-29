#!/usr/bin/env python3
"""
Preflight check script for the TSAB Analytics Platform.
Runs code syntax checks and executes pytest test suites using ASCII characters for Windows compatibility.
"""
import os
import sys
import py_compile
import subprocess

def check_syntax():
    print("=== Step 1: Syntax compilation check ===")
    success = True
    python_files = []
    
    # Traverse directories to find python files
    for root, dirs, files in os.walk('.'):
        # Skip pycache and virtual environments
        if any(ignored in root for ignored in ['.venv', 'venv', '__pycache__', '.git', '.agents']):
            continue
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
                
    for filepath in python_files:
        try:
            py_compile.compile(filepath, doraise=True)
            print(f"  [OK] {filepath} compiles successfully.")
        except py_compile.PyCompileError as e:
            print(f"  [FAIL] {filepath} compilation FAILED:")
            print(e)
            success = False
            
    return success

def run_tests():
    print("\n=== Step 2: Running unit tests via pytest ===")
    # Run python -m pytest to execute the tests
    result = subprocess.run([sys.executable, "-m", "pytest", "-v"], capture_output=False)
    return result.returncode == 0

def main():
    print("TSAB Analytics Platform Preflight Check")
    print("=" * 40)
    
    # Force stdout to use utf-8 if supported, else fallback gracefully
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

    syntax_ok = check_syntax()
    if not syntax_ok:
        print("\n[FAIL] Preflight FAILED: Syntax errors detected.")
        sys.exit(1)
        
    tests_ok = run_tests()
    if not tests_ok:
        print("\n[FAIL] Preflight FAILED: Unit tests failed.")
        sys.exit(1)
        
    print("\n[SUCCESS] Preflight PASSED! You are ready to commit and push.")
    sys.exit(0)

if __name__ == '__main__':
    main()
