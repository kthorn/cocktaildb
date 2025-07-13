#!/usr/bin/env python3
"""Test script to verify inventory filtering fix"""

import requests
import json

def test_inventory_no_auth():
    """Test inventory filtering without authentication"""
    url = "http://localhost:8000/recipes/search?inventory=true"
    
    response = requests.get(url)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
    
    # Should return 400 with validation error
    expected_status = 400
    if response.status_code == expected_status:
        print("✓ Test passed: Inventory filtering correctly requires authentication")
    else:
        print(f"✗ Test failed: Expected {expected_status}, got {response.status_code}")

def test_regular_search():
    """Test regular search without inventory filtering"""
    url = "http://localhost:8000/recipes/search?q=vodka"
    
    response = requests.get(url)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text[:200]}...")
    
    # Should return 200 with results
    expected_status = 200
    if response.status_code == expected_status:
        print("✓ Test passed: Regular search works")
    else:
        print(f"✗ Test failed: Expected {expected_status}, got {response.status_code}")

if __name__ == "__main__":
    print("Testing inventory filtering fix...")
    test_inventory_no_auth()
    print("\nTesting regular search...")
    test_regular_search()