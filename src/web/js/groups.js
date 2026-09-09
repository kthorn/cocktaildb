import { api as defaultApi } from './api.js';
import { getUserInfo, isAuthenticated, startLogin } from './auth.js';

const MUTATION_IDS = [
    'group-name',
    'group-description',
    'save-group-btn',
    'copy-invite-btn',
    'rotate-invite-btn',
    'join-invite-code',
    'join-group-btn',
    'leave-copy-inventory',
    'leave-group-btn',
];

function setHidden(element, hidden) {
    if (!element) return;
    element.classList.toggle('hidden', hidden);
}

function messageFromError(error, fallback) {
    return error?.message || fallback;
}

function currentUserInfo() {
    try {
        return getUserInfo() || {};
    } catch {
        return {};
    }
}

/** Manage the current user's one shared bar. */
export class GroupPage {
    constructor({ api = defaultApi, userInfo } = {}) {
        this.api = api;
        this.userInfo = userInfo || currentUserInfo();
        this.group = null;
        this.pending = false;
        this.pendingToken = null;
        this.bound = false;
        this.loadGeneration = 0;
        this.authenticated = false;
    }

    element(id) {
        return document.getElementById(id);
    }

    init() {
        this.userInfo = currentUserInfo();
        this.bindEvents();
        document.addEventListener('auth-state-changed', (event) => {
            this.handleAuthChange(event.detail || {});
        });

        if (!isAuthenticated()) {
            this.authenticated = false;
            this.showAuthRequired();
            this.showStatus('Please log in to manage your shared bar.');
            return;
        }
        this.authenticated = true;
        this.showAuthenticatedContent();
        void this.load();
    }

    bindEvents() {
        if (this.bound) return;
        this.bound = true;

        this.element('save-group-btn')?.addEventListener('click', () => this.saveGroup());
        this.element('copy-invite-btn')?.addEventListener('click', () => this.copyInviteCode());
        this.element('rotate-invite-btn')?.addEventListener('click', () =>
            this.regenerateInviteCode(),
        );
        this.element('join-group-form')?.addEventListener('submit', (event) => {
            event.preventDefault();
            void this.joinGroup();
        });
        this.element('leave-group-btn')?.addEventListener('click', () => this.leaveGroup());
        this.element('groups-retry')?.addEventListener('click', () => this.load());

        const loginButton = this.element('groups-login-btn');
        loginButton?.addEventListener('click', () => {
            const headerLogin = this.element('login-btn');
            if (headerLogin) {
                headerLogin.click();
                return;
            }
            void startLogin().catch((error) =>
                this.showError(messageFromError(error, 'Unable to start login.')),
            );
        });
    }

    handleAuthChange({ isAuthenticated: authenticated } = {}) {
        const loggedIn = authenticated ?? isAuthenticated();
        const nextUserInfo = currentUserInfo();
        const principalChanged = this.userInfo?.cognitoUserId !== nextUserInfo.cognitoUserId;
        if (!loggedIn) {
            if (!this.authenticated && !this.group) return;
            this.authenticated = false;
            this.userInfo = nextUserInfo;
            this.loadGeneration += 1;
            this.pending = false;
            this.pendingToken = null;
            this.setMutationsDisabled(false);
            this.group = null;
            this.clearGroupDisplay();
            this.showAuthRequired();
            this.showStatus('Please log in to manage your shared bar.');
            return;
        }

        if (principalChanged) {
            this.authenticated = true;
            this.userInfo = nextUserInfo;
            this.loadGeneration += 1;
            this.pending = false;
            this.pendingToken = null;
            this.setMutationsDisabled(false);
            this.group = null;
            this.clearGroupDisplay();
            this.showAuthenticatedContent();
            void this.load();
            return;
        }

        if (this.authenticated && this.group) return;
        this.userInfo = nextUserInfo;
        this.authenticated = true;
        this.showAuthenticatedContent();
        void this.load();
    }

    showAuthRequired() {
        setHidden(this.element('groups-content'), true);
        setHidden(this.element('groups-auth-message'), false);
        setHidden(this.element('groups-retry'), true);
    }

    showAuthenticatedContent() {
        setHidden(this.element('groups-content'), false);
        setHidden(this.element('groups-auth-message'), true);
    }

    clearGroupDisplay() {
        const name = this.element('group-name');
        const description = this.element('group-description');
        const inviteCode = this.element('group-invite-code');
        const members = this.element('group-members');
        const memberCount = this.element('group-member-count');
        if (name) name.value = '';
        if (description) description.value = '';
        if (inviteCode) inviteCode.value = '';
        if (members) members.textContent = '';
        if (memberCount) memberCount.textContent = '';
        setHidden(this.element('leave-group-section'), true);
    }

    async load() {
        if (!isAuthenticated()) {
            this.handleAuthChange({ isAuthenticated: false });
            return null;
        }

        const generation = ++this.loadGeneration;
        this.showStatus('Loading your shared bar…');
        setHidden(this.element('groups-retry'), true);

        try {
            const group = await this.api.getMyGroup();
            if (generation !== this.loadGeneration) return null;
            this.group = group;
            this.showAuthenticatedContent();
            this.renderGroup();
            this.showStatus(`Loaded ${group.name || 'your shared bar'}.`);
            return group;
        } catch (error) {
            if (generation !== this.loadGeneration) return null;
            this.showError(messageFromError(error, 'Unable to load your shared bar.'));
            setHidden(this.element('groups-retry'), false);
            return null;
        }
    }

    renderGroup() {
        if (!this.group) {
            this.clearGroupDisplay();
            return;
        }

        const name = this.element('group-name');
        const description = this.element('group-description');
        const inviteCode = this.element('group-invite-code');
        if (name) name.value = this.group.name || '';
        if (description) description.value = this.group.description || '';
        if (inviteCode) inviteCode.value = this.group.invite_code || '';
        const memberCount = this.group.member_count ?? this.group.members?.length ?? 0;
        const memberCountLabel = this.element('group-member-count');
        if (memberCountLabel) {
            memberCountLabel.textContent = `(${memberCount} member${memberCount === 1 ? '' : 's'})`;
        }

        this.renderMembers();
        setHidden(this.element('leave-group-section'), memberCount < 2);
    }

    renderMembers() {
        const container = this.element('group-members');
        if (!container) return;
        container.textContent = '';

        const members = Array.isArray(this.group?.members) ? this.group.members : [];
        if (members.length === 0) {
            const empty = document.createElement('p');
            empty.className = 'empty-state';
            empty.textContent = 'No members found.';
            container.appendChild(empty);
            return;
        }

        const selfId = this.userInfo?.cognitoUserId;
        members.forEach((member) => {
            const row = document.createElement('div');
            row.className = 'group-member-row';

            const identity = document.createElement('span');
            identity.className = 'group-member-id';
            identity.textContent = member.cognito_user_id || 'Unknown member';
            row.appendChild(identity);

            if (member.cognito_user_id === selfId) {
                const selfLabel = document.createElement('span');
                selfLabel.className = 'group-member-self';
                selfLabel.textContent = ' (you)';
                row.appendChild(selfLabel);
            } else {
                const memberId = String(member.cognito_user_id || 'member');
                const kickButton = document.createElement('button');
                kickButton.type = 'button';
                kickButton.className = 'btn btn-danger btn-small kick-member-btn';
                kickButton.textContent = 'Remove member';
                kickButton.setAttribute('aria-label', `Remove member ${memberId}`);
                kickButton.addEventListener('click', () =>
                    this.removeGroupMember(member.cognito_user_id),
                );
                row.appendChild(kickButton);
            }

            container.appendChild(row);
        });
    }

    mutationControls() {
        const controls = MUTATION_IDS.map((id) => this.element(id)).filter(Boolean);
        const memberButtons = document.querySelectorAll('.kick-member-btn');
        return [...controls, ...memberButtons];
    }

    setMutationsDisabled(disabled) {
        this.mutationControls().forEach((control) => {
            control.disabled = disabled;
        });
    }

    async runMutation(operation, successMessage, { reload = false } = {}) {
        if (this.pending || !this.group) return null;
        const generation = this.loadGeneration;
        const mutationToken = Symbol('group-mutation');
        this.pending = true;
        this.pendingToken = mutationToken;
        this.setMutationsDisabled(true);
        try {
            const result = await operation();
            // A logout/login or a newer load invalidates the old response.
            if (generation !== this.loadGeneration) return null;
            if (reload) {
                const refreshedGroup = await this.load();
                if (!refreshedGroup) return result;
            } else if (result && result.id !== undefined) {
                this.group = result;
                this.renderGroup();
            }
            this.showStatus(successMessage);
            return result;
        } catch (error) {
            if (generation !== this.loadGeneration) return null;
            const errorMessage = messageFromError(error, 'The action could not be completed.');
            if (this.isStaleGroupError(error)) {
                if (!isAuthenticated()) {
                    this.handleAuthChange({ isAuthenticated: false });
                    return null;
                }
                const refreshedGroup = await this.load();
                if (refreshedGroup) this.showError(errorMessage);
                return null;
            }
            this.showError(errorMessage);
            return null;
        } finally {
            if (this.pendingToken === mutationToken) {
                this.pending = false;
                this.pendingToken = null;
                this.setMutationsDisabled(false);
            }
        }
    }

    async saveGroup() {
        const name = this.element('group-name')?.value.trim() || '';
        const description = this.element('group-description')?.value.trim() || null;
        if (!name) {
            this.showError('Enter a name for your shared bar.');
            return null;
        }
        return this.runMutation(
            () => this.api.updateGroup(this.group.id, { name, description }),
            'Shared bar details saved.',
        );
    }

    async copyInviteCode() {
        const code = this.element('group-invite-code')?.value || '';
        if (!code) return;
        try {
            if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
            await navigator.clipboard.writeText(code);
            this.showStatus('Invite code copied.');
        } catch {
            const input = this.element('group-invite-code');
            input?.focus();
            input?.select?.();
            this.showError('Clipboard access is unavailable. Select and copy the invite code.');
        }
    }

    async regenerateInviteCode() {
        return this.runMutation(
            () => this.api.regenerateInviteCode(this.group.id),
            'Invite code regenerated.',
        );
    }

    async joinGroup() {
        const input = this.element('join-invite-code');
        const inviteCode = input?.value.trim() || '';
        if (!inviteCode) {
            this.showError('Enter an invite code to join a shared bar.');
            return null;
        }
        const warning =
            'Joining copies all ingredients from your current bar into the bar you are joining. Existing members of that bar will see and share those additions. Continue?';
        if (typeof window.confirm === 'function' && !window.confirm(warning)) return null;

        return this.runMutation(
            () => this.api.joinGroup(inviteCode),
            'You joined the shared bar.',
            { reload: true },
        );
    }

    async leaveGroup() {
        const copy = this.element('leave-copy-inventory')?.checked ?? true;
        const warning = copy
            ? 'Leaving copies the full shared bar inventory into your new personal bar. Continue?'
            : 'Leave this shared bar without copying its inventory?';
        if (typeof window.confirm === 'function' && !window.confirm(warning)) return null;

        return this.runMutation(
            () => this.api.leaveGroup(this.group.id, copy),
            'You left the shared bar.',
            { reload: true },
        );
    }

    async removeGroupMember(cognitoUserId) {
        if (!cognitoUserId || cognitoUserId === this.userInfo?.cognitoUserId) return null;
        if (
            typeof window.confirm === 'function' &&
            !window.confirm(
                `Removing ${cognitoUserId} creates a personal bar for them and copies the full shared bar inventory. Continue?`,
            )
        )
            return null;

        return this.runMutation(
            () => this.api.removeGroupMember(this.group.id, cognitoUserId),
            'Member removed. Their personal bar received a copy of the inventory.',
            { reload: true },
        );
    }

    isStaleGroupError(error) {
        const status = error?.status;
        return status === 401 || status === 403 || status === 404;
    }

    showStatus(message) {
        const status = this.element('groups-status');
        if (!status) return;
        status.className = 'groups-status';
        status.textContent = message;
    }

    showError(message) {
        const status = this.element('groups-status');
        if (!status) return;
        status.className = 'groups-status groups-status-error';
        status.textContent = message;
    }
}

export function initGroupsPage(options = {}) {
    const page = new GroupPage(options);
    page.init();
    return page;
}

// Keep a descriptive compatibility name for pages that instantiate managers directly.
export const GroupsManager = GroupPage;

if (typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', () => {
        initGroupsPage();
    });
}
