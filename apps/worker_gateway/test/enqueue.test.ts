// Run: npm test
import { test } from "node:test";
import assert from "node:assert/strict";

import { enqueueWithRetry, notifyDiscordFailure } from "../src/enqueue.ts";

const noSleep = async () => {};

function fakeFetch(replies: Array<number | Error>) {
	const calls: Array<{ url: string; init: RequestInit }> = [];
	const fn = async (url: string, init: RequestInit): Promise<Response> => {
		calls.push({ url, init });
		const r = replies.shift();
		if (r instanceof Error) throw r;
		return new Response(`status ${r}`, { status: r });
	};
	return { fn, calls };
}

const req = { url: "https://backend/internal/enqueue", init: { method: "POST", body: "{}" } };

test("succeeds on first try without retrying", async () => {
	const f = fakeFetch([200]);
	const r = await enqueueWithRetry(req.url, req.init, { fetchFn: f.fn, sleep: noSleep });
	assert.equal(r.ok, true);
	assert.equal(r.attempts, 1);
});

test("retries on 5xx until it succeeds (cold start: no available instance)", async () => {
	const f = fakeFetch([500, 503, 200]);
	const r = await enqueueWithRetry(req.url, req.init, { fetchFn: f.fn, sleep: noSleep });
	assert.equal(r.ok, true);
	assert.equal(r.attempts, 3);
	assert.equal(f.calls.length, 3);
});

test("retries on network errors", async () => {
	const f = fakeFetch([new TypeError("network down"), 200]);
	const r = await enqueueWithRetry(req.url, req.init, { fetchFn: f.fn, sleep: noSleep });
	assert.equal(r.ok, true);
	assert.equal(r.attempts, 2);
});

test("retries on 429", async () => {
	const f = fakeFetch([429, 200]);
	const r = await enqueueWithRetry(req.url, req.init, { fetchFn: f.fn, sleep: noSleep });
	assert.equal(r.ok, true);
});

test("does not retry 4xx client errors (e.g. bad internal token)", async () => {
	const f = fakeFetch([403, 200]);
	const r = await enqueueWithRetry(req.url, req.init, { fetchFn: f.fn, sleep: noSleep });
	assert.equal(r.ok, false);
	assert.equal(r.status, 403);
	assert.equal(f.calls.length, 1);
});

test("gives up after all retries and reports the last status", async () => {
	const f = fakeFetch([500, 500, 500, 500, 500]);
	const r = await enqueueWithRetry(req.url, req.init, {
		fetchFn: f.fn,
		sleep: noSleep,
		delaysMs: [1, 1, 1],
	});
	assert.equal(r.ok, false);
	assert.equal(r.status, 500);
	assert.equal(r.attempts, 4);
});

test("waits the configured delays between attempts", async () => {
	const waited: number[] = [];
	const f = fakeFetch([500, 500, 200]);
	await enqueueWithRetry(req.url, req.init, {
		fetchFn: f.fn,
		sleep: async (ms) => void waited.push(ms),
		delaysMs: [2000, 4000, 8000],
	});
	assert.deepEqual(waited, [2000, 4000]);
});

test("stops retrying when the next wait would pass the time budget", async () => {
	let now = 0;
	const f = fakeFetch([500, 500, 500, 200]);
	const r = await enqueueWithRetry(req.url, req.init, {
		fetchFn: async (u, i) => {
			now += 10_000; // each attempt takes 10s (slow cold start)
			return f.fn(u, i);
		},
		sleep: async (ms) => void (now += ms),
		now: () => now,
		delaysMs: [2000, 4000, 8000],
		budgetMs: 25_000,
	});
	// 10s + 2s wait + 10s = 22s; another 4s wait would pass 25s → stop.
	assert.equal(r.ok, false);
	assert.equal(r.attempts, 2);
});

test("notifyDiscordFailure edits the deferred reply", async () => {
	const f = fakeFetch([200]);
	await notifyDiscordFailure("app123", "tok456", "boom", f.fn);
	assert.equal(f.calls.length, 1);
	assert.equal(
		f.calls[0].url,
		"https://discord.com/api/v10/webhooks/app123/tok456/messages/@original",
	);
	assert.equal(f.calls[0].init.method, "PATCH");
	assert.match(String(f.calls[0].init.body), /boom/);
});

test("notifyDiscordFailure never throws", async () => {
	const f = fakeFetch([new TypeError("discord down")]);
	await notifyDiscordFailure("a", "t", "x", f.fn);
});
