# Frontend Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Resolve the still-current opportunities in `docs/frontend-cleanup.md` while preserving frontend behavior.

**Architecture:** Keep the static HTML/vanilla JavaScript deployment. Share ingredient hierarchy operations, isolate recipe-card features without circular dependencies, and share chart tooltip handlers. Load metadata and render-blocking stylesheets directly in each HTML head, replacing the JavaScript visibility workaround. Keep dynamic visualization geometry in JavaScript and static presentation in CSS.

**Tech Stack:** Static HTML/CSS, ES modules, D3, dependency-free Node tests, pre-commit.

## Tasks
1. Extract ingredient tree construction/render traversal in `src/web/js/components/ingredientTree.js`; update both ingredient pages and replace global click handlers with delegation. Test filtered roots, sorting, input preservation, and page actions.
2. Split `src/web/js/recipeCard.js` along existing feature boundaries and reuse one tag-chip renderer. Test extracted behavior using actual module imports.
3. Consolidate tooltip binding in `src/web/js/charts/ingredientTreeChart.js`, leaving coordinates and transitions dynamic.
4. Populate static heads in `src/web/*.html` and `api/templates/{base,recipe}.html`, remove head injection/visibility overrides from `src/web/js/common.js`, and verify metadata and styles exist without JavaScript.
5. Replace static inline HTML/admin styles with named classes in `src/web/styles.css`; remove production debug logging while retaining errors and warnings.
6. Review each original opportunity, retire the obsolete backlog, run `node --test tests/test_*.js tests/test_*.mjs`, syntax checks and all pre-commit checks; review the complete diff, commit, push and open a PR.

## Decisions
Use static head markup rather than adding a build/template dependency. Remove debug logs rather than introduce a global debug setting. Preserve runtime styles for state/geometry where classes would obscure behavior. Existing frontend tests passed (11 files) before changes.

## Outcome
All original opportunities were still present and have been addressed. The original backlog document is removed because its work is complete. Recipe cards retain orchestration and card refresh logic while ratings rendering, tag editing, tag presentation, sharing, and ingredient formatting now live in feature modules. Nested ingredient lists use a consistent CSS indentation per level rather than increasingly large inline margins. Runtime tooltip coordinates and other interaction state remain in JavaScript.
