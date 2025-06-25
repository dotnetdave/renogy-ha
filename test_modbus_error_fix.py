#!/usr/bin/env python3
"""Test script to verify the UnboundLocalError fix in _read_modbus_device method."""

import ast
import sys

def test_variable_initialization():
    """Test that success and error variables are properly initialized."""
    
    # Read the ble.py file
    with open('custom_components/renogy/ble.py', 'r') as f:
        content = f.read()
    
    # Parse the AST to check for proper variable initialization
    tree = ast.parse(content)
    
    # Find the _read_modbus_device method
    modbus_method = None
    for node in ast.walk(tree):
        if (isinstance(node, ast.FunctionDef) and 
            node.name == '_read_modbus_device'):
            modbus_method = node
            break
    
    if modbus_method is None:
        print("❌ Could not find _read_modbus_device method")
        return False
    
    # Check for variable initialization
    success_initialized = False
    error_initialized = False
    
    # Look for assignments in the method body
    for stmt in modbus_method.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    if target.id == 'success':
                        success_initialized = True
                    elif target.id == 'error':
                        error_initialized = True
    
    print(f"✓ _read_modbus_device method found")
    print(f"✓ success variable initialized: {success_initialized}")
    print(f"✓ error variable initialized: {error_initialized}")
      if success_initialized and error_initialized:
        print("PASS: Both success and error variables are properly initialized")
        return True
    else:
        print("FAIL: Variables not properly initialized")
        return False

def test_syntax_validity():
    """Test that the file has valid Python syntax."""
    try:
        with open('custom_components/renogy/ble.py', 'r') as f:
            content = f.read()
        
        ast.parse(content)
        print("✅ PASS: File has valid Python syntax")
        return True
    except SyntaxError as e:
        print(f"❌ FAIL: Syntax error - {e}")
        return False

if __name__ == '__main__':
    print("Testing UnboundLocalError fix in _read_modbus_device method...")
    print("=" * 60)
    
    syntax_ok = test_syntax_validity()
    variables_ok = test_variable_initialization()
    
    print("=" * 60)
    if syntax_ok and variables_ok:
        print("🎉 ALL TESTS PASSED: UnboundLocalError fix is successful!")
        sys.exit(0)
    else:
        print("💥 TESTS FAILED: Fix needs attention")
        sys.exit(1)
