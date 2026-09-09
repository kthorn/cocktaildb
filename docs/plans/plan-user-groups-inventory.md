# User Groups with Shared Inventory

**Status:** Ready to implement; reviewed 2026-09-08.

The [authoritative implementation plan](2026-09-08-user-groups-inventory.md) replaces the earlier design and April implementation draft. Follow that document for exact API behavior, migration SQL, implementation tasks, and verification.

Users share a home bar with family/housemates. Each user has one group after first group/inventory access; inventory belongs to that group. Existing users with inventory receive personal groups during migration. Existing `/user-ingredients` API and Python DB methods remain compatible wrappers.

All members have equal permissions. Joining merges the full current inventory into the destination and moves membership. Leaving creates a personal bar with an explicit choice to copy inventory; removal always gives the removed member a copy. Creating another group while already a member returns 409; rename the existing bar instead. Empty groups persist but their invitation codes cannot be used to rejoin them. Ratings and private tags remain personal.

The reviewed plan resolves migration-number collision and duplicate-user backfill, atomic authorization/membership changes, legacy DB callers and search parameter binding, route ordering/imports, frontend integration, and test/rollout gaps. No application code or database changes were made during plan preparation.
