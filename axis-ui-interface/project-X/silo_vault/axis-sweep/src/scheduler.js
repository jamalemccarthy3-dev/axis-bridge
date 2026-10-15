// src/scheduler.js - batches background wake-ups: instead of 50 small wake-ups, tasks wait and are released together when the batch is full or the interval has passed.
export class TaskScheduler {
    constructor({ intervalMs = 5000, maxBatch = 50, now = Date.now } = {}) {
        this.intervalMs = intervalMs;
        this.maxBatch = maxBatch;
        this.now = now;
        this.queue = [];
        this.lastFlush = now();
    }

    // queue a task (a function or any value); -> the queue length
    interceptWakeRequests(task) {
        this.queue.push(task);
        return this.queue.length;
    }

    due() {
        return this.queue.length >= this.maxBatch || (this.queue.length > 0 && this.now() - this.lastFlush >= this.intervalMs);
    }

    // release the batch when it is due (or when forced). -> the released tasks (possibly none)
    flush(force = false) {
        if (!force && !this.due()) return [];
        const batch = this.queue.splice(0, this.queue.length);
        this.lastFlush = this.now();
        return batch;
    }
}
