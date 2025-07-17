#!/usr/bin/env python3
"""
Test script for the updated add_user_ingredient method
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'api'))

from db.db_core import Database

def test_add_user_ingredient():
    """Test the add_user_ingredient method with parent ingredients"""
    db = Database()
    
    # Test user ID
    test_user_id = "test-user-123"
    
    try:
        # First, let's check what ingredients exist and their hierarchy
        print("=== Testing add_user_ingredient with parent ingredients ===")
        
        # Get some ingredients to test with
        ingredients = db.get_ingredients()
        print(f"Total ingredients in database: {len(ingredients)}")
        
        # Find an ingredient that has parents (path length > 1)
        test_ingredient = None
        for ing in ingredients:
            if ing['path'] and len(ing['path'].split('/')) > 3:  # Has at least one parent
                test_ingredient = ing
                break
        
        if not test_ingredient:
            print("No ingredient with parents found, creating a test hierarchy...")
            # Create a test parent ingredient
            parent_data = {
                "name": "Test Parent Category",
                "description": "Test parent ingredient",
                "parent_id": None
            }
            parent = db.create_ingredient(parent_data)
            print(f"Created parent ingredient: {parent}")
            
            # Create a child ingredient
            child_data = {
                "name": "Test Child Ingredient",
                "description": "Test child ingredient",
                "parent_id": parent["id"]
            }
            child = db.create_ingredient(child_data)
            print(f"Created child ingredient: {child}")
            test_ingredient = child
        
        print(f"Testing with ingredient: {test_ingredient['name']} (ID: {test_ingredient['id']})")
        print(f"Ingredient path: {test_ingredient['path']}")
        
        # Clear any existing user ingredients for clean test
        try:
            existing_user_ingredients = db.get_user_ingredients(test_user_id)
            for ui in existing_user_ingredients:
                db.remove_user_ingredient(test_user_id, ui['ingredient_id'])
        except:
            pass  # User might not exist yet
        
        # Test adding the ingredient
        result = db.add_user_ingredient(test_user_id, test_ingredient['id'])
        print(f"Added ingredient result: {result}")
        
        # Check what ingredients were added
        user_ingredients = db.get_user_ingredients(test_user_id)
        print(f"User now has {len(user_ingredients)} ingredients:")
        for ui in user_ingredients:
            print(f"  - {ui['name']} (ID: {ui['ingredient_id']})")
        
        # Test adding the same ingredient again (should raise error)
        try:
            result2 = db.add_user_ingredient(test_user_id, test_ingredient['id'])
            print("ERROR: Should have raised exception for duplicate ingredient")
        except ValueError as e:
            print(f"Correctly raised exception for duplicate: {e}")
        
        # Test adding a parent ingredient that already exists (should not raise error)
        path_parts = [part for part in test_ingredient['path'].split('/') if part]
        if len(path_parts) > 1:
            parent_id = int(path_parts[-2])  # Second to last is the direct parent
            try:
                result3 = db.add_user_ingredient(test_user_id, parent_id)
                print(f"ERROR: Should have raised exception for duplicate parent: {result3}")
            except ValueError as e:
                print(f"Correctly raised exception for duplicate parent: {e}")
        
        print("\n=== Test completed successfully! ===")
        
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up test data
        try:
            existing_user_ingredients = db.get_user_ingredients(test_user_id)
            for ui in existing_user_ingredients:
                db.remove_user_ingredient(test_user_id, ui['ingredient_id'])
        except:
            pass

if __name__ == "__main__":
    test_add_user_ingredient()