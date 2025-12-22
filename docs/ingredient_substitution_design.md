# Ingredient Substitution System Design

## Overview
The ingredient substitution system allows recipes to specify ingredients at different levels of specificity while maintaining makeable recipe detection based on user inventory and substitutability rules.

## Hierarchy Structure

### Level 1: Base Categories
- **Examples**: Whiskey, Rum, Gin, Vodka, etc.
- **substitution_level**: 1 (allow substitution within sub-categories)
- **Purpose**: Top-level spirit/ingredient types

### Level 2: Sub-Categories  
- **Examples**: Light Rum, Dark Rum, London Dry Gin, Italian Bitter Liqueur
- **substitution_level**: 
  - 1: Allow brand substitution (e.g., Light Rum - any light rum brand works)
  - 0: No substitution (e.g., Plymouth Gin - only Plymouth gin works)
- **Purpose**: Specific styles or types within a category

### Level 3+: Brands/Specific Items
- **Examples**: Bacardi Superior, Tanqueray, Aperol, Campari
- **substitution_level**:
  - NULL: Inherit from parent (most common)
  - 0: No substitution allowed (e.g., Aperol must be Aperol specifically)
- **Purpose**: Specific brands or unique ingredients

## Substitution Level Rules

### substitution_level = 0 (No Substitution)
- Requires exact ingredient match
- Used for unique ingredients where no substitute works
- **Examples**: Aperol, Campari, Plymouth Gin
- **Recipe behavior**: "2 oz Aperol" requires specifically Aperol

### substitution_level = 1 (Parent-Level Substitution)  
- Allows any sibling ingredient (same parent) to substitute
- Used for categories where brands are interchangeable
- **Examples**: Light Rum category, Orange Liqueur category
- **Recipe behavior**: "2 oz Light Rum" works with any light rum brand

### substitution_level = 2 (Grandparent-Level Substitution)
- Allows broader substitution within grandparent category
- Used for very generic ingredients
- **Recipe behavior**: "2 oz Rum" could work with any rum type/brand

### substitution_level = NULL (Inherit)
- Uses parent's substitution level
- Default for specific brands under substitutable categories

## Recipe Authoring Examples

### Specific Brand Required
```sql
-- Recipe calls for specific Aperol (no substitution)
INSERT INTO recipe_ingredients (recipe_id, ingredient_id, amount, unit_id)
VALUES (1, (SELECT id FROM ingredients WHERE name = 'Aperol'), 2, (SELECT id FROM units WHERE name = 'Ounce'));
```

### Category-Level (Brand Flexible)
```sql  
-- Recipe calls for any light rum
INSERT INTO recipe_ingredients (recipe_id, ingredient_id, amount, unit_id)
VALUES (1, (SELECT id FROM ingredients WHERE name = 'Light Rum'), 2, (SELECT id FROM units WHERE name = 'Ounce'));
```

## Inventory Matching Logic

When checking if a recipe is makeable:

1. **For each recipe ingredient**:
   - Check its `substitution_level`
   - If level = 0: Look for exact match in user inventory
   - If level = 1: Look for any ingredient in user inventory that shares the same parent
   - If level = 2: Look for any ingredient in user inventory that shares the same grandparent
   - If level = NULL: Use parent's substitution level

2. **Path-based matching**:
   - Use existing path field for efficient ancestor queries
   - Recipe ingredient path: `/2/8/` (Light Rum)
   - User inventory: `/2/8/12/` (Bacardi Superior) 
   - Match: User ingredient path contains recipe ingredient path

## Implementation Notes

- Backward compatible with existing single-level ingredient system
- Recipes can reference any level of the hierarchy as needed
- User inventory typically contains specific brands (leaf nodes)
- Search algorithm uses path-based SQL queries for efficiency
- Substitution rules are configurable per ingredient category