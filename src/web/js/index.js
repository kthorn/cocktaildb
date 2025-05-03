import { api } from './api.js';
import { initAuth } from './auth.js';
import { createRecipeCard } from './recipeCard.js';

// Global variables for recipe carousel
let allRecipes = [];
let currentRecipeIndex = 0;

// Wait for the DOM to be fully loaded
document.addEventListener('DOMContentLoaded', () => {
    // Initialize authentication UI
    initAuth();
    
    // Fetch and display statistics
    fetchStatistics();
    
    // Set up recipe carousel
    initializeRecipeCarousel();
});

/**
 * Fetch statistics about ingredients and recipes
 */
async function fetchStatistics() {
    try {
        // Fetch ingredients count using the API instance
        const ingredients = await api.getIngredients();
        document.getElementById('total-ingredients').textContent = ingredients.length;

        // Fetch recipes count using the API instance
        const recipes = await api.getRecipes();
        document.getElementById('total-recipes').textContent = recipes.length;
    } catch (error) {
        console.error('Error fetching statistics:', error);
        document.getElementById('total-ingredients').textContent = 'Error';
        document.getElementById('total-recipes').textContent = 'Error';
    }
}

/**
 * Initialize the recipe carousel component
 */
async function initializeRecipeCarousel() {
    const prevButton = document.getElementById('prev-recipe');
    const nextButton = document.getElementById('next-recipe');
    const recipeDisplay = document.getElementById('recipe-display');
    
    if (!prevButton || !nextButton || !recipeDisplay) {
        console.error('Carousel elements not found');
        return;
    }
    
    try {
        // Load all recipes
        allRecipes = await api.getRecipes();
        
        if (allRecipes.length === 0) {
            recipeDisplay.innerHTML = '<p>No recipes available</p>';
            prevButton.disabled = true;
            nextButton.disabled = true;
            return;
        }
        
        // Display the first recipe
        displayCurrentRecipe();
        
        // Set initial button states
        updateButtonStates();
        
        // Add event listeners for navigation
        prevButton.addEventListener('click', showPreviousRecipe);
        nextButton.addEventListener('click', showNextRecipe);
        
    } catch (error) {
        console.error('Error initializing recipe carousel:', error);
        recipeDisplay.innerHTML = '<p>Error loading recipes. Please try again later.</p>';
    }
}

/**
 * Display the current recipe in the carousel
 */
function displayCurrentRecipe() {
    const recipeDisplay = document.getElementById('recipe-display');
    
    if (!recipeDisplay || !allRecipes.length) return;
    
    // Get the current recipe
    const recipe = allRecipes[currentRecipeIndex];
    
    // Clear the display
    recipeDisplay.innerHTML = '';
    
    // Create a recipe card without edit/delete actions
    const card = createRecipeCard(recipe, false);
    card.classList.add('fade-in');
    
    // Append to the display
    recipeDisplay.appendChild(card);
}

/**
 * Show the previous recipe in the carousel
 */
function showPreviousRecipe() {
    if (currentRecipeIndex > 0) {
        currentRecipeIndex--;
        displayCurrentRecipe();
        updateButtonStates();
    }
}

/**
 * Show the next recipe in the carousel
 */
function showNextRecipe() {
    if (currentRecipeIndex < allRecipes.length - 1) {
        currentRecipeIndex++;
        displayCurrentRecipe();
        updateButtonStates();
    }
}

/**
 * Update the enabled/disabled state of the navigation buttons
 */
function updateButtonStates() {
    const prevButton = document.getElementById('prev-recipe');
    const nextButton = document.getElementById('next-recipe');
    
    if (!prevButton || !nextButton) return;
    
    // Disable previous button if at the first recipe
    prevButton.disabled = currentRecipeIndex === 0;
    
    // Disable next button if at the last recipe
    nextButton.disabled = currentRecipeIndex === allRecipes.length - 1;
} 