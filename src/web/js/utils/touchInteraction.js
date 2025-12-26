/**
 * Touch Interaction Utility
 * Provides tap and double-tap detection for D3 chart elements
 */

const DOUBLE_TAP_THRESHOLD_MS = 300;
const TOOLTIP_TIMEOUT_MS = 3000;

/**
 * Get a stable identifier for a D3 datum
 * Used for comparing taps on the same element across potential data rebinds
 */
function getDataId(d) {
    if (!d) return null;
    // Support both direct data objects and D3 hierarchy nodes
    const data = d.data || d;
    return data.id || data.ingredient_id || data.recipe_id || data.name || null;
}

/**
 * Creates touch handlers for a D3 selection
 * @param {Object} options
 * @param {Function} options.onTap - Called on single tap with (event, datum)
 * @param {Function} options.onDoubleTap - Called on double tap with (event, datum)
 * @returns {Object} Handler functions to attach to D3 selection
 */
export function createTouchHandlers(options = {}) {
    let lastTapTime = 0;
    let tapTimeout = null;
    let pendingTapDataId = null;

    function handleTouchStart(event, d) {
        // Prevent default to avoid 300ms click delay on mobile
        // But don't prevent if it's a two-finger gesture (for pan/zoom)
        if (event.touches && event.touches.length === 1) {
            const now = Date.now();
            const timeSinceLastTap = now - lastTapTime;
            const currentDataId = getDataId(d);

            // Compare by stable ID instead of object reference
            if (timeSinceLastTap < DOUBLE_TAP_THRESHOLD_MS && pendingTapDataId === currentDataId) {
                // Double tap detected
                clearTimeout(tapTimeout);
                tapTimeout = null;
                pendingTapDataId = null;
                lastTapTime = 0;

                if (options.onDoubleTap) {
                    options.onDoubleTap(event, d);
                }
            } else {
                // Potential single tap - wait to see if double tap follows
                lastTapTime = now;
                pendingTapDataId = currentDataId;

                clearTimeout(tapTimeout);
                tapTimeout = setTimeout(() => {
                    if (options.onTap) {
                        options.onTap(event, d);
                    }
                    pendingTapDataId = null;
                }, DOUBLE_TAP_THRESHOLD_MS);
            }
        }
    }

    function handleTouchEnd(event) {
        // No-op for now, keeping for potential future use
    }

    return {
        touchstart: handleTouchStart,
        touchend: handleTouchEnd
    };
}

/**
 * Detect if device supports touch
 * @returns {boolean}
 */
export function isTouchDevice() {
    return 'ontouchstart' in window || navigator.maxTouchPoints > 0;
}

/**
 * Detect if viewport is mobile-sized
 * @returns {boolean}
 */
export function isMobileViewport() {
    return window.innerWidth < 768;
}

/**
 * Create a tooltip manager for mobile
 * Handles showing/hiding tooltips with timeout
 * @param {HTMLElement} tooltipElement - The tooltip DOM element
 * @returns {Object} Tooltip controller
 */
export function createMobileTooltipManager(tooltipElement) {
    let hideTimeout = null;

    function show(html, x, y) {
        clearTimeout(hideTimeout);

        tooltipElement.innerHTML = html;
        tooltipElement.style.left = `${x}px`;
        tooltipElement.style.top = `${y}px`;
        tooltipElement.style.opacity = '1';
        tooltipElement.style.visibility = 'visible';

        // Auto-hide after timeout on mobile
        if (isTouchDevice()) {
            hideTimeout = setTimeout(hide, TOOLTIP_TIMEOUT_MS);
        }
    }

    function hide() {
        clearTimeout(hideTimeout);
        tooltipElement.style.opacity = '0';
        tooltipElement.style.visibility = 'hidden';
    }

    // Hide tooltip when tapping elsewhere
    function setupDismissHandler() {
        document.addEventListener('touchstart', (event) => {
            if (!tooltipElement.contains(event.target)) {
                hide();
            }
        }, { passive: true });
    }

    return { show, hide, setupDismissHandler };
}
