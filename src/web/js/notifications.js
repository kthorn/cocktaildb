// Page notifications, shown in a region fixed to the viewport so they are
// visible however far the page has scrolled.
//
// Errors go in a role="alert" stack and stay until dismissed. Success and info
// messages go in a role="status" stack and hide themselves after a few seconds.
// Both stacks exist before any message is added: screen readers announce
// changes to an existing live region more reliably than a newly inserted one.

const AUTO_HIDE_MS = 5000;
const LEAVE_MS = 300;
const MAX_PER_STACK = 4;

let region = null;
const hideTimers = new WeakMap();

function getRegion() {
    if (region) return region;
    if (typeof document === 'undefined' || !document.body) return null;

    const root = document.createElement('div');
    root.className = 'notification-region';

    const errors = document.createElement('div');
    errors.className = 'notification-stack';
    errors.setAttribute('role', 'alert');

    const statuses = document.createElement('div');
    statuses.className = 'notification-stack';
    statuses.setAttribute('role', 'status');

    root.append(errors, statuses);
    document.body.appendChild(root);
    region = { root, errors, statuses };
    return region;
}

/**
 * Remove a notification returned by showNotification. Safe to call more than
 * once, or with null.
 */
export function dismissNotification(notification) {
    if (!notification || notification.dataset.leaving) return;
    notification.dataset.leaving = 'true';
    clearTimeout(hideTimers.get(notification));
    notification.classList.add('is-leaving');
    setTimeout(() => notification.remove(), LEAVE_MS);
}

/**
 * Show a message to the user.
 *
 * @param {string} message - Plain text; it is never parsed as HTML.
 * @param {'error'|'success'|'info'} [type='info'] - Errors persist until
 *     dismissed; other types hide after a few seconds.
 * @returns {HTMLElement|null} The notification, for dismissNotification.
 */
export function showNotification(message, type = 'info') {
    const target = getRegion();
    if (!target) return null;

    const kind = type === 'error' || type === 'success' ? type : 'info';
    const isError = kind === 'error';
    const stack = isError ? target.errors : target.statuses;
    const text = String(message);

    // Showing the same message again (say, a second failed save) replaces the
    // first copy rather than stacking a duplicate, and is announced again.
    Array.from(stack.children)
        .filter((item) => item.dataset.message === text)
        .forEach((item) => {
            clearTimeout(hideTimers.get(item));
            item.remove();
        });
    // Keep the stack short: the oldest messages make way for the new one.
    const showing = Array.from(stack.children).filter((item) => !item.dataset.leaving);
    const excess = showing.length - (MAX_PER_STACK - 1);
    if (excess > 0) showing.slice(0, excess).forEach(dismissNotification);

    const notification = document.createElement('div');
    notification.className = `notification ${kind}`;
    notification.dataset.message = text;

    const body = document.createElement('p');
    body.className = 'notification-message';
    body.textContent = text;

    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'notification-dismiss';
    close.setAttribute('aria-label', 'Dismiss notification');
    close.textContent = '×';
    close.addEventListener('click', () => dismissNotification(notification));

    notification.append(body, close);
    stack.appendChild(notification);

    if (!isError) {
        hideTimers.set(
            notification,
            setTimeout(() => dismissNotification(notification), AUTO_HIDE_MS),
        );
    }
    return notification;
}

// Create the live regions as soon as the page has a body, ahead of the first
// message.
if (typeof document !== 'undefined') {
    if (document.body) {
        getRegion();
    } else if (typeof document.addEventListener === 'function') {
        document.addEventListener('DOMContentLoaded', getRegion, { once: true });
    }
}
