#!/usr/bin/env python3
"""Simple test to verify the UnboundLocalError fix."""

def test_fix():
    with open('custom_components/renogy/ble.py', 'r') as f:
        content = f.read()
    
    # Check that the method exists and has variable initialization
    if '_read_modbus_device' in content:
        print("SUCCESS: _read_modbus_device method found")
        
        # Look for the initialization lines we added
        if 'success = False' in content and 'error = None' in content:
            print("SUCCESS: Variable initialization found")
            
            # Check that it's in the right method
            method_start = content.find('async def _read_modbus_device')
            next_method = content.find('async def', method_start + 1)
            if next_method == -1:
                next_method = len(content)
            
            method_content = content[method_start:next_method]
            if 'success = False' in method_content and 'error = None' in method_content:
                print("SUCCESS: Variables initialized in correct method")
                return True
            else:
                print("ERROR: Variables not in correct method")
                return False
        else:
            print("ERROR: Variable initialization not found")
            return False
    else:
        print("ERROR: Method not found")
        return False

if __name__ == '__main__':
    print("Testing UnboundLocalError fix...")
    if test_fix():
        print("PASS: Fix is working correctly!")
    else:
        print("FAIL: Fix needs attention")
