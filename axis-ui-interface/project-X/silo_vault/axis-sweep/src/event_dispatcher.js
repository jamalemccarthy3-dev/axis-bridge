// src/event_dispatcher.js - a small event bus. One failing listener never stops the others; its error is returned to the caller of emit().
export const Dispatcher = {
    listeners: {},

    subscribe(event, callback) {
        if (!this.listeners[event]) this.listeners[event] = [];
        this.listeners[event].push(callback);
        return () => this.unsubscribe(event, callback);
    },

    unsubscribe(event, callback) {
        this.listeners[event] = (this.listeners[event] || []).filter(cb => cb !== callback);
    },

    // -> { delivered, errors: [Error] }
    emit(event, data) {
        const errors = [];
        let delivered = 0;
        for (const cb of [...(this.listeners[event] || [])]) {
            try { cb(data); delivered++; } catch (e) { errors.push(e); }
        }
        return { delivered, errors };
    }
};
