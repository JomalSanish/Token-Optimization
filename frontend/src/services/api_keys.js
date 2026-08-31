/**
 * Client-side local storage API keys manager.
 * Supports multiple keys per provider (OpenAI, Gemini, Anthropic) in rotating pools.
 */
export const apiKeysService = {
    getKeys() {
        const data = localStorage.getItem("apiKeys");
        return data ? JSON.parse(data) : { openai: [], google: [], anthropic: [] };
    },

    saveKeys(keys) {
        localStorage.setItem("apiKeys", JSON.stringify(keys));
    },

    addKey(provider, key, label) {
        const keys = this.getKeys();
        if (!keys[provider]) {
            keys[provider] = [];
        }
        keys[provider].push({
            id: 'key_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9),
            key: key,
            label: label || `Key ${keys[provider].length + 1}`,
            exhausted: false,
            lastUsedAt: null
        });
        this.saveKeys(keys);
    },

    removeKey(provider, keyId) {
        const keys = this.getKeys();
        if (keys[provider]) {
            keys[provider] = keys[provider].filter(k => k.id !== keyId);
            this.saveKeys(keys);
        }
    },

    markKeyExhausted(provider, keyId) {
        const keys = this.getKeys();
        if (keys[provider]) {
            const keyObj = keys[provider].find(k => k.id === keyId);
            if (keyObj) {
                keyObj.exhausted = true;
                keyObj.lastUsedAt = new Date().toISOString();
                this.saveKeys(keys);
            }
        }
    },

    resetKeyStatus(provider, keyId) {
        const keys = this.getKeys();
        if (keys[provider]) {
            const keyObj = keys[provider].find(k => k.id === keyId);
            if (keyObj) {
                keyObj.exhausted = false;
                this.saveKeys(keys);
            }
        }
    },

    /**
     * Gets the first active (non-exhausted) key for a provider.
     */
    getActiveKey(provider) {
        const keys = this.getKeys();
        const pool = keys[provider] || [];
        const activeKey = pool.find(k => !k.exhausted);
        if (activeKey) {
            // Update last used timestamp
            activeKey.lastUsedAt = new Date().toISOString();
            this.saveKeys(keys);
            return activeKey;
        }
        return null;
    }
};
