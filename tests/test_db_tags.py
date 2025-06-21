"""
Tag System Testing
Comprehensive tests for public and private tag management,
recipe associations, and user ownership validation
"""

import pytest
import sqlite3
import os
from typing import Dict, Any, List
from unittest.mock import patch

from api.db.db_core import Database


class TestPublicTagCRUD:
    """Test CRUD operations for public tags"""

    def test_create_public_tag(self, memory_db_with_schema):
        """Test creating a public tag"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            tag = db.create_public_tag("new_tag")

            assert tag["id"] is not None
            assert tag["name"] == "new_tag"

    def test_create_public_tag_duplicate(self, memory_db_with_schema):
        """Test creating duplicate public tag (should return existing)"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create first tag
            first_tag = db.create_public_tag("new_tag")

            # Create duplicate (should return existing)
            second_tag = db.create_public_tag("new_tag")

            assert first_tag["id"] == second_tag["id"]
            assert first_tag["name"] == second_tag["name"]

    def test_get_public_tag_by_name(self, memory_db_with_schema):
        """Test retrieving public tag by name"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create tag
            created_tag = db.create_public_tag("modern")

            # Retrieve by name
            retrieved_tag = db.get_public_tag_by_name("modern")

            assert retrieved_tag is not None
            assert retrieved_tag["id"] == created_tag["id"]
            assert retrieved_tag["name"] == "modern"

    def test_get_public_tag_by_name_nonexistent(self, memory_db_with_schema):
        """Test retrieving non-existent public tag by name"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            result = db.get_public_tag_by_name("nonexistent")
            assert result is None

    def test_get_public_tags(self, memory_db_with_schema):
        """Test retrieving all public tags"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create multiple tags
            tag_names = ["new_tag", "modern", "tropical", "strong"]
            for name in tag_names:
                db.create_public_tag(name)

            # Retrieve all tags
            all_tags = db.get_public_tags()

            assert len(all_tags) == 6  # There are two tags in the base schema
            retrieved_names = {tag["name"] for tag in all_tags}
            assert retrieved_names == set(tag_names + ["Classic", "Tiki"])


class TestPrivateTagCRUD:
    """Test CRUD operations for private tags"""

    def test_create_private_tag(self, memory_db_with_schema):
        """Test creating a private tag"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            tag = db.create_private_tag("personal", "user123", "testuser")

            assert tag["id"] is not None
            assert tag["name"] == "personal"
            assert tag["cognito_user_id"] == "user123"
            assert tag["cognito_username"] == "testuser"

    def test_create_private_tag_same_name_different_users(self, memory_db_with_schema):
        """Test creating private tags with same name for different users"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # User 1 creates "favorites" tag
            tag1 = db.create_private_tag("favorites", "user1", "user1")

            # User 2 creates "favorites" tag (should be allowed)
            tag2 = db.create_private_tag("favorites", "user2", "user2")

            assert tag1["id"] != tag2["id"]
            assert tag1["name"] == tag2["name"] == "favorites"
            assert tag1["cognito_user_id"] == "user1"
            assert tag2["cognito_user_id"] == "user2"

    def test_create_private_tag_duplicate_same_user(self, memory_db_with_schema):
        """Test creating duplicate private tag for same user (should return existing)"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create first tag
            first_tag = db.create_private_tag("favorites", "user123", "testuser")

            # Create duplicate (should return existing)
            second_tag = db.create_private_tag("favorites", "user123", "testuser")

            assert first_tag["id"] == second_tag["id"]
            assert first_tag["name"] == second_tag["name"]
            assert first_tag["cognito_user_id"] == second_tag["cognito_user_id"]

    def test_get_private_tag_by_name_and_user(self, memory_db_with_schema):
        """Test retrieving private tag by name and user"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create tag
            created_tag = db.create_private_tag("personal", "user123", "testuser")

            # Retrieve by name and user
            retrieved_tag = db.get_private_tag_by_name_and_user("personal", "user123")

            assert retrieved_tag is not None
            assert retrieved_tag["id"] == created_tag["id"]
            assert retrieved_tag["name"] == "personal"
            assert retrieved_tag["cognito_user_id"] == "user123"

    def test_get_private_tag_by_name_and_user_wrong_user(self, memory_db_with_schema):
        """Test retrieving private tag with wrong user"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create tag for user1
            db.create_private_tag("personal", "user1", "user1")

            # Try to retrieve with user2
            result = db.get_private_tag_by_name_and_user("personal", "user2")
            assert result is None

    def test_get_private_tags_for_user(self, memory_db_with_schema):
        """Test retrieving all private tags for a user"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create tags for user1
            user1_tags = ["favorites", "to-try", "party-drinks"]
            for name in user1_tags:
                db.create_private_tag(name, "user1", "user1")

            # Create tags for user2
            db.create_private_tag("favorites", "user2", "user2")
            db.create_private_tag("experimental", "user2", "user2")

            # Retrieve user1's tags
            result = db.get_private_tags("user1")

            assert len(result) == 3
            retrieved_names = {tag["name"] for tag in result}
            assert retrieved_names == set(user1_tags)

            # All should belong to user1
            for tag in result:
                assert tag["cognito_user_id"] == "user1"

    def test_get_private_tags_empty(self, memory_db_with_schema):
        """Test retrieving private tags for user with no tags"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            result = db.get_private_tags("user_with_no_tags")
            assert isinstance(result, list)
            assert len(result) == 0


class TestTagGenericOperations:
    """Test generic tag operations that work with both public and private tags"""

    def test_get_tag_public(self, memory_db_with_schema):
        """Test getting a public tag by ID"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            public_tag = db.create_public_tag("new_tag")

            result = db.get_tag(public_tag["id"])

            assert result is not None
            assert result["id"] == public_tag["id"]
            assert result["name"] == "new_tag"
            assert result["is_private"] == 0

    def test_get_tag_private(self, memory_db_with_schema):
        """Test getting a private tag by ID"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            private_tag = db.create_private_tag("personal", "user123", "testuser")

            result = db.get_tag(private_tag["id"])

            assert result is not None
            assert result["id"] == private_tag["id"]
            assert result["name"] == "personal"
            assert result["is_private"] == 1
            assert result["created_by"] == "user123"

    def test_get_tag_nonexistent(self, memory_db_with_schema):
        """Test getting non-existent tag"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            result = db.get_tag(999)
            assert result is None


class TestRecipeTagAssociations:
    """Test associating tags with recipes"""

    def test_add_public_tag_to_recipe(self, memory_db_with_schema):
        """Test adding public tag to recipe"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipe and tag
            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})
            tag = db.create_public_tag("new_tag")

            # Associate tag with recipe
            result = db.add_public_tag_to_recipe(recipe["id"], tag["id"])
            assert result is True

            # Verify association exists
            tags = db._get_recipe_public_tags(recipe["id"])
            assert len(tags) == 1
            assert tags[0]["id"] == tag["id"]
            assert tags[0]["name"] == "new_tag"

    def test_add_public_tag_duplicate(self, memory_db_with_schema):
        """Test adding same public tag to recipe twice (should be idempotent)"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})
            tag = db.create_public_tag("new_tag")

            # Add tag first time
            result1 = db.add_public_tag_to_recipe(recipe["id"], tag["id"])
            assert result1 is True

            # Add tag second time (should not create duplicate)
            result2 = db.add_public_tag_to_recipe(recipe["id"], tag["id"])
            assert result2 is False  # No new row created

            # Verify only one association exists
            tags = db._get_recipe_public_tags(recipe["id"])
            assert len(tags) == 1

    def test_add_private_tag_to_recipe(self, memory_db_with_schema):
        """Test adding private tag to recipe"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipe and tag
            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})
            tag = db.create_private_tag("favorites", "user123", "testuser")

            # Associate tag with recipe
            result = db.add_private_tag_to_recipe(recipe["id"], tag["id"])
            assert result is True

            # Verify association exists
            tags = db._get_recipe_private_tags(recipe["id"], "user123")
            assert len(tags) == 1
            assert tags[0]["id"] == tag["id"]
            assert tags[0]["name"] == "favorites"

    def test_add_private_tag_duplicate(self, memory_db_with_schema):
        """Test adding same private tag to recipe twice"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})
            tag = db.create_private_tag("favorites", "user123", "testuser")

            # Add tag first time
            result1 = db.add_private_tag_to_recipe(recipe["id"], tag["id"])
            assert result1 is True

            # Add tag second time
            result2 = db.add_private_tag_to_recipe(recipe["id"], tag["id"])
            assert result2 is False  # No new row created

            # Verify only one association exists
            tags = db._get_recipe_private_tags(recipe["id"], "user123")
            assert len(tags) == 1

    def test_add_recipe_tag_generic_public(self, memory_db_with_schema):
        """Test generic add_recipe_tag method with public tag"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})
            tag = db.create_public_tag("modern")

            result = db.add_recipe_tag(
                recipe["id"], tag["id"], is_private=False, user_id="user123"
            )
            assert result is True

            # Verify public tag was added
            public_tags = db._get_recipe_public_tags(recipe["id"])
            assert len(public_tags) == 1
            assert public_tags[0]["name"] == "modern"

    def test_add_recipe_tag_generic_private(self, memory_db_with_schema):
        """Test generic add_recipe_tag method with private tag"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})
            tag = db.create_private_tag("personal", "user123", "testuser")

            result = db.add_recipe_tag(
                recipe["id"], tag["id"], is_private=True, user_id="user123"
            )
            assert result is True

            # Verify private tag was added
            private_tags = db._get_recipe_private_tags(recipe["id"], "user123")
            assert len(private_tags) == 1
            assert private_tags[0]["name"] == "personal"


class TestRecipeTagRemoval:
    """Test removing tags from recipes"""

    def test_remove_public_tag_from_recipe(self, memory_db_with_schema):
        """Test removing public tag from recipe"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create and associate tag
            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})
            tag = db.create_public_tag("new_tag")
            db.add_public_tag_to_recipe(recipe["id"], tag["id"])

            # Verify tag is associated
            tags_before = db._get_recipe_public_tags(recipe["id"])
            assert len(tags_before) == 1

            # Remove tag
            result = db.remove_public_tag_from_recipe(recipe["id"], tag["id"])
            assert result is True

            # Verify tag is removed
            tags_after = db._get_recipe_public_tags(recipe["id"])
            assert len(tags_after) == 0

    def test_remove_public_tag_not_associated(self, memory_db_with_schema):
        """Test removing public tag that's not associated with recipe"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})
            tag = db.create_public_tag("new_tag")

            # Try to remove tag that was never added
            result = db.remove_public_tag_from_recipe(recipe["id"], tag["id"])
            assert result is False

    def test_remove_private_tag_from_recipe(self, memory_db_with_schema):
        """Test removing private tag from recipe"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create and associate tag
            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})
            tag = db.create_private_tag("favorites", "user123", "testuser")
            db.add_private_tag_to_recipe(recipe["id"], tag["id"])

            # Verify tag is associated
            tags_before = db._get_recipe_private_tags(recipe["id"], "user123")
            assert len(tags_before) == 1

            # Remove tag
            result = db.remove_private_tag_from_recipe(
                recipe["id"], tag["id"], "user123"
            )
            assert result is True

            # Verify tag is removed
            tags_after = db._get_recipe_private_tags(recipe["id"], "user123")
            assert len(tags_after) == 0

    def test_remove_private_tag_wrong_user(self, memory_db_with_schema):
        """Test removing private tag with wrong user (should fail)"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create and associate tag for user1
            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})
            tag = db.create_private_tag("favorites", "user1", "user1")
            db.add_private_tag_to_recipe(recipe["id"], tag["id"])

            # Try to remove with user2 (should fail)
            result = db.remove_private_tag_from_recipe(recipe["id"], tag["id"], "user2")
            assert result is False

            # Verify tag is still associated with user1
            tags = db._get_recipe_private_tags(recipe["id"], "user1")
            assert len(tags) == 1

    def test_remove_recipe_tag_generic_public(self, memory_db_with_schema):
        """Test generic remove_recipe_tag method with public tag"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})
            tag = db.create_public_tag("modern")
            db.add_public_tag_to_recipe(recipe["id"], tag["id"])

            result = db.remove_recipe_tag(
                recipe["id"], tag["id"], is_private=False, user_id="user123"
            )
            assert result is True

            # Verify public tag was removed
            public_tags = db._get_recipe_public_tags(recipe["id"])
            assert len(public_tags) == 0

    def test_remove_recipe_tag_generic_private(self, memory_db_with_schema):
        """Test generic remove_recipe_tag method with private tag"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})
            tag = db.create_private_tag("personal", "user123", "testuser")
            db.add_private_tag_to_recipe(recipe["id"], tag["id"])

            result = db.remove_recipe_tag(
                recipe["id"], tag["id"], is_private=True, user_id="user123"
            )
            assert result is True

            # Verify private tag was removed
            private_tags = db._get_recipe_private_tags(recipe["id"], "user123")
            assert len(private_tags) == 0


class TestTagCascadeOperations:
    """Test cascade operations when recipes or tags are deleted"""

    def test_recipe_deletion_removes_tag_associations(self, memory_db_with_schema):
        """Test that deleting recipe removes all tag associations"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipe with both public and private tags
            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})
            public_tag = db.create_public_tag("new_tag")
            private_tag = db.create_private_tag("favorites", "user123", "testuser")

            db.add_public_tag_to_recipe(recipe["id"], public_tag["id"])
            db.add_private_tag_to_recipe(recipe["id"], private_tag["id"])

            # Verify associations exist
            assert len(db._get_recipe_public_tags(recipe["id"])) == 1
            assert len(db._get_recipe_private_tags(recipe["id"], "user123")) == 1

            # Delete recipe
            db.delete_recipe(recipe["id"])

            # Verify tag associations were cascade deleted
            public_associations = db.execute_query(
                "SELECT COUNT(*) as count FROM recipe_public_tags WHERE recipe_id = ?",
                (recipe["id"],),
            )
            private_associations = db.execute_query(
                "SELECT COUNT(*) as count FROM recipe_private_tags WHERE recipe_id = ?",
                (recipe["id"],),
            )

            assert public_associations[0]["count"] == 0
            assert private_associations[0]["count"] == 0

            # Verify tags themselves still exist
            assert db.get_public_tag_by_name("new_tag") is not None
            assert (
                db.get_private_tag_by_name_and_user("favorites", "user123") is not None
            )


class TestTagConstraints:
    """Test tag constraints and validation"""

    def test_public_tag_name_uniqueness(self, memory_db_with_schema):
        """Test that public tag names must be unique"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create first tag
            first_tag = db.create_public_tag("unique")

            # Create duplicate (should return existing)
            second_tag = db.create_public_tag("unique")

            assert first_tag["id"] == second_tag["id"]

    def test_private_tag_name_unique_per_user(self, memory_db_with_schema):
        """Test that private tag names are unique per user"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # User1 creates "favorites"
            tag1 = db.create_private_tag("favorites", "user1", "user1")

            # User1 tries to create "favorites" again (should return existing)
            tag1_dup = db.create_private_tag("favorites", "user1", "user1")
            assert tag1["id"] == tag1_dup["id"]

            # User2 creates "favorites" (should be allowed)
            tag2 = db.create_private_tag("favorites", "user2", "user2")
            assert tag1["id"] != tag2["id"]

    def test_recipe_tag_association_uniqueness(self, memory_db_with_schema):
        """Test that recipe-tag associations are unique"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            recipe = db.create_recipe({"name": "Test Recipe", "instructions": "Test"})
            tag = db.create_public_tag("new_tag")

            # Add association first time
            result1 = db.add_public_tag_to_recipe(recipe["id"], tag["id"])
            assert result1 is True

            # Add same association again (should be idempotent)
            result2 = db.add_public_tag_to_recipe(recipe["id"], tag["id"])
            assert result2 is False  # No new row created


class TestTagEdgeCases:
    """Test edge cases and error conditions"""

    def test_tag_empty_name(self, memory_db_with_schema):
        """Test creating tag with empty name"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            with pytest.raises(Exception):
                db.create_public_tag("")

    def test_tag_very_long_name(self, memory_db_with_schema):
        """Test creating tag with very long name"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            long_name = "a" * 1000
            tag = db.create_public_tag(long_name)
            assert tag["name"] == long_name

    def test_tag_unicode_name(self, memory_db_with_schema):
        """Test creating tag with unicode characters"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            unicode_name = "经典🍸"
            tag = db.create_public_tag(unicode_name)
            assert tag["name"] == unicode_name

    def test_tag_special_characters(self, memory_db_with_schema):
        """Test creating tag with special characters"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            special_name = "classic & modern (2024)"
            tag = db.create_public_tag(special_name)
            assert tag["name"] == special_name

    def test_private_tag_empty_user_id(self, memory_db_with_schema):
        """Test creating private tag with empty user ID"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            with pytest.raises(Exception):
                db.create_private_tag("test", "", "username")

    def test_private_tag_empty_username(self, memory_db_with_schema):
        """Test creating private tag with empty username"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            with pytest.raises(Exception):
                db.create_private_tag("test", "user123", "")


class TestComplexTagScenarios:
    """Test complex tag scenarios"""

    def test_recipe_with_mixed_tags(self, memory_db_with_schema):
        """Test recipe with both public and private tags"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipe
            recipe = db.create_recipe(
                {"name": "Complex Recipe", "instructions": "Test"}
            )

            # Add public tags
            classic_tag = db.create_public_tag("new_tag")
            strong_tag = db.create_public_tag("strong")
            db.add_public_tag_to_recipe(recipe["id"], classic_tag["id"])
            db.add_public_tag_to_recipe(recipe["id"], strong_tag["id"])

            # Add private tags
            favorites_tag = db.create_private_tag("favorites", "user123", "testuser")
            party_tag = db.create_private_tag("party", "user123", "testuser")
            db.add_private_tag_to_recipe(recipe["id"], favorites_tag["id"])
            db.add_private_tag_to_recipe(recipe["id"], party_tag["id"])

            # Retrieve recipe with tags
            result = db.get_recipe(recipe["id"], "user123")

            # Verify all tags are present
            public_tag_names = {
                tag["name"] for tag in result["tags"] if tag["type"] == "public"
            }
            private_tag_names = {
                tag["name"] for tag in result["tags"] if tag["type"] == "private"
            }

            assert public_tag_names == {"new_tag", "strong"}
            assert private_tag_names == {"favorites", "party"}

    def test_multiple_users_private_tags_isolation(self, memory_db_with_schema):
        """Test that private tags are properly isolated between users"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipe
            recipe = db.create_recipe({"name": "Shared Recipe", "instructions": "Test"})

            # User1 adds private tags
            user1_tag = db.create_private_tag("my-favorite", "user1", "user1")
            db.add_private_tag_to_recipe(recipe["id"], user1_tag["id"])

            # User2 adds private tags
            user2_tag = db.create_private_tag("want-to-try", "user2", "user2")
            db.add_private_tag_to_recipe(recipe["id"], user2_tag["id"])

            # User1 should only see their private tags
            recipe_for_user1 = db.get_recipe(recipe["id"], "user1")
            user1_private_tags = [
                tag for tag in recipe_for_user1["tags"] if tag["type"] == "private"
            ]
            assert len(user1_private_tags) == 1
            assert user1_private_tags[0]["name"] == "my-favorite"

            # User2 should only see their private tags
            recipe_for_user2 = db.get_recipe(recipe["id"], "user2")
            user2_private_tags = [
                tag for tag in recipe_for_user2["tags"] if tag["type"] == "private"
            ]
            assert len(user2_private_tags) == 1
            assert user2_private_tags[0]["name"] == "want-to-try"

            # Anonymous user should see no private tags
            recipe_anonymous = db.get_recipe(recipe["id"], None)
            anonymous_private_tags = [
                tag for tag in recipe_anonymous["tags"] if tag["type"] == "private"
            ]
            assert len(anonymous_private_tags) == 0

    def test_tag_operations_performance_many_tags(self, memory_db_with_schema):
        """Test tag operations with many tags"""
        with patch.dict(os.environ, {"DB_PATH": memory_db_with_schema}):
            db = Database()

            # Create recipe
            recipe = db.create_recipe(
                {"name": "Well Tagged Recipe", "instructions": "Test"}
            )

            # Create many public tags
            public_tags = []
            for i in range(20):
                tag = db.create_public_tag(f"public_tag_{i}")
                public_tags.append(tag)
                db.add_public_tag_to_recipe(recipe["id"], tag["id"])

            # Create many private tags
            private_tags = []
            for i in range(20):
                tag = db.create_private_tag(f"private_tag_{i}", "user123", "testuser")
                private_tags.append(tag)
                db.add_private_tag_to_recipe(recipe["id"], tag["id"])

            # Retrieve recipe (should handle many tags efficiently)
            result = db.get_recipe(recipe["id"], "user123")

            # Verify all tags are present
            assert len(result["tags"]) == 40

            public_count = len(
                [tag for tag in result["tags"] if tag["type"] == "public"]
            )
            private_count = len(
                [tag for tag in result["tags"] if tag["type"] == "private"]
            )

            assert public_count == 20
            assert private_count == 20
