/**
 * Backend enqueue with retry, plus a Discord fallback message.
 *
 * Cloud Run scales to zero. On a cold start it sometimes answers 500
 * ("no available instance") before the instance is up — a few seconds
 * later the same request succeeds. Without a retry the novel was silently
 * dropped and Discord stayed on "thinking…" forever.
 *
 * Retrying is safe: the backend ignores a task whose request_id it has
 * already accepted.
 */

type FetchFn = (url: string, init: RequestInit) => Promise<Response>;

export interface RetryOptions {
	fetchFn?: FetchFn;
	sleep?: (ms: number) => Promise<void>;
	now?: () => number;
	/** Wait before each retry; its length is the number of retries. */
	delaysMs?: number[];
	/** ctx.waitUntil() is cut off ~30s after the response; stay under it. */
	budgetMs?: number;
}

export interface EnqueueResult {
	ok: boolean;
	status: number | null; // null = network error
	attempts: number;
	detail: string;
}

const DEFAULT_DELAYS_MS = [2000, 4000, 8000];
const DEFAULT_BUDGET_MS = 25_000;

function isRetryable(status: number): boolean {
	return status >= 500 || status === 429;
}

export async function enqueueWithRetry(
	url: string,
	init: RequestInit,
	opts: RetryOptions = {},
): Promise<EnqueueResult> {
	const fetchFn = opts.fetchFn ?? ((u, i) => fetch(u, i));
	const sleep = opts.sleep ?? ((ms) => new Promise<void>((r) => setTimeout(r, ms)));
	const now = opts.now ?? (() => Date.now());
	const delays = opts.delaysMs ?? DEFAULT_DELAYS_MS;
	const budget = opts.budgetMs ?? DEFAULT_BUDGET_MS;

	const start = now();
	let result: EnqueueResult = { ok: false, status: null, attempts: 0, detail: "" };

	for (let attempt = 0; attempt <= delays.length; attempt++) {
		if (attempt > 0) {
			const wait = delays[attempt - 1];
			if (now() - start + wait > budget) break;
			await sleep(wait);
		}

		try {
			const resp = await fetchFn(url, init);
			const text = resp.ok ? "" : await resp.text();
			result = { ok: resp.ok, status: resp.status, attempts: attempt + 1, detail: text };
			if (resp.ok || !isRetryable(resp.status)) return result;
		} catch (err) {
			result = { ok: false, status: null, attempts: attempt + 1, detail: String(err) };
		}

		console.warn(
			`Backend enqueue attempt ${attempt + 1} failed: ${result.status ?? "network"} – ${result.detail.slice(0, 200)}`,
		);
	}
	return result;
}

/** Replace the deferred "thinking…" reply with an error. Never throws. */
export async function notifyDiscordFailure(
	applicationId: string,
	interactionToken: string,
	content: string,
	fetchFn: FetchFn = (u, i) => fetch(u, i),
): Promise<void> {
	const url = `https://discord.com/api/v10/webhooks/${applicationId}/${interactionToken}/messages/@original`;
	try {
		const resp = await fetchFn(url, {
			method: "PATCH",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ content }),
		});
		if (!resp.ok) {
			console.error(`Discord failure notice failed: ${resp.status}`);
		}
	} catch (err) {
		console.error(`Discord failure notice error: ${err}`);
	}
}
