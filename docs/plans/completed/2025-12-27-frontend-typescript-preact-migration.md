# Frontend Migration: TypeScript + Preact

## Goals

1. **Simplify DOM management** - Replace scattered `document.getElementById()` and manual updates with reactive state
2. **Enable code reuse** - Extract repeated patterns (ingredient inputs, autocomplete, validation) into shared components
3. **Improve debugging** - TypeScript catches type errors at compile time, not runtime

## Non-Goals

- Converting to a single-page app (keeping MPA structure)
- Rewriting D3 chart logic (wrap existing code in components)
- Adding a state management library (page-level state is sufficient)

## Technology Choices

| Choice | Reasoning |
|--------|-----------|
| **Preact** | React-compatible API at 3KB. JSX composition handles complex forms well. Large ecosystem. |
| **TypeScript** | Type safety for API responses, props, state. Catches errors at compile time. |
| **Vite** | Fast dev server with HMR. Native TypeScript/JSX support. Multi-page app mode. Asset fingerprinting. |

### Alternatives Considered

**Lit**: Better for incremental adoption with Web Components, but JSX composition is more ergonomic for the complex form patterns in this codebase (nested ingredient inputs, conditional validation). Page-by-page rewrite favors Preact's component model.

## Project Structure

```
src/
├── web/                    # HTML pages (modified to load new entry points)
│   ├── index.html
│   ├── recipes.html
│   ├── search.html
│   └── ...
├── frontend/               # New TypeScript source
│   ├── apps/               # One entry per HTML page
│   │   ├── about.tsx
│   │   ├── recipe.tsx
│   │   ├── recipes.tsx
│   │   ├── search.tsx
│   │   ├── ingredients.tsx
│   │   ├── analytics.tsx
│   │   ├── user-ingredients.tsx
│   │   ├── admin.tsx
│   │   └── index.tsx
│   ├── components/         # Shared UI components
│   │   ├── IngredientInput.tsx
│   │   ├── AutoComplete.tsx
│   │   ├── FieldError.tsx
│   │   ├── RatingStars.tsx
│   │   ├── RecipeCard.tsx
│   │   └── Pagination.tsx
│   ├── hooks/              # Shared React hooks
│   │   ├── useApi.ts
│   │   └── useAuth.ts
│   ├── api/                # Typed API client
│   │   └── client.ts
│   └── types/              # Shared TypeScript types
│       ├── models.ts
│       └── api.ts
├── js/                     # Legacy JS (removed as pages migrate)
├── styles.css              # Unchanged
├── normalize.css           # Unchanged
├── vite.config.ts
├── tsconfig.json
└── package.json
```

## Vite Configuration

```typescript
// vite.config.ts
import { defineConfig } from 'vite';
import preact from '@preact/preset-vite';
import { resolve } from 'path';

export default defineConfig({
  plugins: [preact()],
  root: 'src/web',

  build: {
    outDir: '../../dist',
    emptyOutDir: true,

    // Asset fingerprinting (enabled by default, explicit for clarity)
    rollupOptions: {
      input: {
        // HTML pages as entry points
        index: resolve(__dirname, 'src/web/index.html'),
        about: resolve(__dirname, 'src/web/about.html'),
        recipe: resolve(__dirname, 'src/web/recipe.html'),
        recipes: resolve(__dirname, 'src/web/recipes.html'),
        search: resolve(__dirname, 'src/web/search.html'),
        ingredients: resolve(__dirname, 'src/web/ingredients.html'),
        analytics: resolve(__dirname, 'src/web/analytics.html'),
        'user-ingredients': resolve(__dirname, 'src/web/user-ingredients.html'),
        admin: resolve(__dirname, 'src/web/admin.html'),
        login: resolve(__dirname, 'src/web/login.html'),
        logout: resolve(__dirname, 'src/web/logout.html'),
        callback: resolve(__dirname, 'src/web/callback.html'),
      },
      output: {
        // Fingerprinted asset names
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]',
      },
    },
  },

  resolve: {
    alias: {
      '@': resolve(__dirname, 'src/frontend'),
      'react': 'preact/compat',
      'react-dom': 'preact/compat',
    },
  },
});
```

### Asset Fingerprinting

Vite automatically handles cache busting:

- **Development**: Files served directly, no hashing
- **Production**: All JS/CSS files get content hashes (e.g., `recipes-a1b2c3d4.js`)
- **HTML injection**: Vite rewrites `<script>` tags in HTML to reference hashed filenames
- **Long-term caching**: Serve assets with `Cache-Control: max-age=31536000, immutable`

Caddy configuration update:

```caddyfile
# Static assets with fingerprinted names - cache forever
@immutable path /assets/*
header @immutable Cache-Control "public, max-age=31536000, immutable"

# HTML pages - no cache or short cache
@html path *.html /
header @html Cache-Control "no-cache"
```

## Component Architecture

### State Management

Each page owns its state at the root component level. Child components receive data via props and emit changes via callbacks.

```tsx
// apps/recipes.tsx
import { useState } from 'preact/hooks';
import { RecipeForm } from '@/components/RecipeForm';
import { api } from '@/api/client';
import type { Recipe, ValidationErrors } from '@/types/models';

function RecipesApp() {
  const [recipe, setRecipe] = useState<Partial<Recipe>>({
    name: '',
    description: '',
    instructions: '',
    ingredients: [],
  });
  const [errors, setErrors] = useState<ValidationErrors>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit() {
    setIsSubmitting(true);
    try {
      await api.createRecipe(recipe);
      // Reset form...
    } catch (err) {
      setErrors(parseApiErrors(err));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <RecipeForm
      value={recipe}
      errors={errors}
      disabled={isSubmitting}
      onChange={setRecipe}
      onSubmit={handleSubmit}
    />
  );
}
```

### Shared Components

| Component | Props | Used In |
|-----------|-------|---------|
| `IngredientInput` | `value`, `onChange`, `onRemove`, `error` | recipes, search |
| `AutoComplete<T>` | `items`, `value`, `onChange`, `renderItem`, `filterFn` | recipes, ingredients, search |
| `FieldError` | `message` | All forms |
| `RatingStars` | `value`, `onChange?`, `readonly?` | recipe, search |
| `RecipeCard` | `recipe`, `onClick?` | search, analytics |
| `Pagination` | `page`, `totalPages`, `onPageChange` | search |

### Example: AutoComplete Component

```tsx
// components/AutoComplete.tsx
import { useState, useRef } from 'preact/hooks';

interface AutoCompleteProps<T> {
  items: T[];
  value: string;
  onChange: (value: string, item?: T) => void;
  getLabel: (item: T) => string;
  placeholder?: string;
  error?: string;
}

export function AutoComplete<T>({
  items,
  value,
  onChange,
  getLabel,
  placeholder,
  error
}: AutoCompleteProps<T>) {
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  const filtered = items.filter(item =>
    getLabel(item).toLowerCase().includes(value.toLowerCase())
  );

  function handleSelect(item: T) {
    onChange(getLabel(item), item);
    setIsOpen(false);
  }

  return (
    <div class="autocomplete">
      <input
        type="text"
        value={value}
        placeholder={placeholder}
        onInput={(e) => onChange(e.currentTarget.value)}
        onFocus={() => setIsOpen(true)}
        onBlur={() => setTimeout(() => setIsOpen(false), 200)}
        onKeyDown={(e) => handleKeyNav(e, filtered, activeIndex, setActiveIndex, handleSelect)}
      />
      {isOpen && filtered.length > 0 && (
        <div class="autocomplete-dropdown">
          {filtered.map((item, i) => (
            <div
              class={`autocomplete-item ${i === activeIndex ? 'active' : ''}`}
              onClick={() => handleSelect(item)}
            >
              {getLabel(item)}
            </div>
          ))}
        </div>
      )}
      {error && <FieldError message={error} />}
    </div>
  );
}
```

## Typed API Client

Direct port of existing `api.js` with TypeScript types:

```typescript
// types/models.ts
export interface Recipe {
  id: number;
  name: string;
  description: string;
  instructions: string;
  source?: string;
  source_url?: string;
  ingredients: RecipeIngredient[];
  avg_rating?: number;
  rating_count?: number;
  public_tags?: Tag[];
  private_tags?: Tag[];
}

export interface RecipeIngredient {
  ingredient_id: number;
  ingredient_name: string;
  amount: number | null;
  unit_id: number;
  unit_name: string;
}

export interface Ingredient {
  id: number;
  name: string;
  parent_id?: number;
  path?: string;
}

export interface Unit {
  id: number;
  name: string;
  abbreviation: string;
}

export interface Tag {
  id: number;
  name: string;
}

export interface PaginatedResponse<T> {
  recipes: T[];
  pagination: {
    page: number;
    limit: number;
    total_count: number;
    has_next: boolean;
    has_previous: boolean;
  };
}

export interface SearchQuery {
  name?: string;
  ingredients?: string[];
  tags?: string[];
  rating?: number;
  rating_type?: 'average' | 'user';
  inventory?: boolean;
}

export interface ValidationErrors {
  [field: string]: string;
}
```

```typescript
// api/client.ts
import config from './config';
import type { Recipe, Ingredient, Unit, PaginatedResponse, SearchQuery } from '@/types/models';

class CocktailAPI {
  private baseUrl: string;

  constructor(baseUrl?: string) {
    this.baseUrl = baseUrl || config.apiUrl;
  }

  private async request<T>(
    path: string,
    method = 'GET',
    body?: unknown,
    requiresAuth = false
  ): Promise<T> {
    const options = this.getFetchOptions(method, body, requiresAuth);
    const response = await fetch(`${this.baseUrl}${path}`, options);
    return this.handleResponse<T>(response);
  }

  // Ingredients
  async getIngredients(): Promise<Ingredient[]> {
    return this.request('/ingredients');
  }

  async getIngredient(id: number): Promise<Ingredient> {
    return this.request(`/ingredients/${id}`);
  }

  // Recipes
  async getRecipe(id: number): Promise<Recipe> {
    return this.request(`/recipes/${id}`);
  }

  async createRecipe(data: Omit<Recipe, 'id'>): Promise<Recipe> {
    return this.request('/recipes', 'POST', data);
  }

  async updateRecipe(id: number, data: Partial<Recipe>): Promise<Recipe> {
    return this.request(`/recipes/${id}`, 'PUT', data);
  }

  async deleteRecipe(id: number): Promise<void> {
    return this.request(`/recipes/${id}`, 'DELETE');
  }

  async searchRecipes(
    query: SearchQuery,
    page = 1,
    limit = 20,
    sortBy = 'name',
    sortOrder = 'asc'
  ): Promise<PaginatedResponse<Recipe>> {
    const params = new URLSearchParams({
      page: page.toString(),
      limit: limit.toString(),
      sort_by: sortBy,
      sort_order: sortOrder,
    });

    if (query.name) params.append('q', query.name);
    if (query.rating) params.append('min_rating', query.rating.toString());
    if (query.tags?.length) params.append('tags', query.tags.join(','));
    if (query.ingredients?.length) params.append('ingredients', query.ingredients.join(','));

    const endpoint = this.isAuthenticated()
      ? '/recipes/search/authenticated'
      : '/recipes/search';

    return this.request(`${endpoint}?${params}`, 'GET', null, this.isAuthenticated());
  }

  // Units
  async getUnits(): Promise<Unit[]> {
    return this.request('/units');
  }

  // Auth helpers (same logic as existing)
  isAuthenticated(): boolean {
    return !!localStorage.getItem('token');
  }

  isEditor(): boolean {
    // Same JWT decoding logic as existing api.js
  }
}

export const api = new CocktailAPI();
```

## Migration Order

| Phase | Page | Components Created | Complexity |
|-------|------|-------------------|------------|
| 1 | about | (none - static) | Low |
| 2 | recipe | `RatingStars`, `RecipeCard` | Low-Medium |
| 3 | search | `AutoComplete`, `Pagination`, reuse `RecipeCard` | Medium |
| 4 | recipes | `IngredientInput`, `FieldError`, reuse `AutoComplete` | High |
| 5 | ingredients | Reuse `FieldError`, `AutoComplete` | Medium |
| 6 | analytics | Chart wrapper components | Medium |
| 7 | user-ingredients | Reuse existing components | Low-Medium |
| 8 | admin | Reuse existing components | Medium |
| 9 | auth pages | Minimal logic, mostly redirects | Low |

### Phase 1: Setup & About Page

1. Install dependencies: `npm install preact vite @preact/preset-vite typescript`
2. Configure Vite, TypeScript
3. Migrate `about.html` - static content, validates build pipeline works
4. Update deployment to serve from `dist/`

### Phase 2-4: Core Pages

Build shared components incrementally as each page needs them. By the time `recipes.tsx` is tackled, `AutoComplete` and validation patterns are already proven.

### D3 Charts

Wrap existing chart code rather than rewriting:

```tsx
// components/charts/IngredientUsageChart.tsx
import { useEffect, useRef } from 'preact/hooks';
import { renderIngredientUsageChart } from '@/legacy/charts/ingredientUsageChart';

interface Props {
  data: IngredientUsageData;
}

export function IngredientUsageChart({ data }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current && data) {
      // Clear previous chart
      containerRef.current.innerHTML = '';
      // Render using existing D3 code
      renderIngredientUsageChart(containerRef.current, data);
    }
  }, [data]);

  return <div ref={containerRef} class="chart-container" />;
}
```

## Transition Period

During migration, legacy JS and new TypeScript coexist:

```
src/web/
├── index.html          # Loads legacy js/index.js
├── about.html          # Loads /frontend/apps/about.tsx (migrated)
├── recipe.html         # Loads /frontend/apps/recipe.tsx (migrated)
├── recipes.html        # Loads legacy js/recipes.js (pending)
```

### HTML Changes Per Page

```html
<!-- Before (legacy) -->
<script type="module" src="js/recipes.js"></script>

<!-- After (migrated) -->
<script type="module" src="/frontend/apps/recipes.tsx"></script>
```

Vite transforms `.tsx` to `.js` and injects the fingerprinted filename in production.

### Removing Legacy Code

As each page is migrated:
1. Update HTML to load new entry point
2. Delete corresponding `js/*.js` file
3. Once all pages migrated, remove `js/` directory entirely

## What Stays The Same

- **CSS**: `styles.css` and `normalize.css` unchanged. Components use existing class names.
- **HTML structure**: Components mount into existing containers (e.g., `<div id="app">`)
- **API endpoints**: Same backend, typed client
- **Auth flow**: Same Cognito integration, tokens in localStorage
- **URL structure**: Same multi-page URLs

## Commands

```bash
# Development
npm run dev          # Start Vite dev server with HMR

# Production build
npm run build        # Output fingerprinted assets to dist/

# Type checking
npm run typecheck    # Run tsc --noEmit

# Preview production build locally
npm run preview      # Serve dist/ folder
```

## Success Criteria

1. All pages render correctly with new components
2. No runtime type errors in production
3. Shared components used across 3+ pages
4. Build produces fingerprinted assets
5. Bundle size per page < 50KB gzipped (excluding D3)
6. Legacy `js/` directory deleted
