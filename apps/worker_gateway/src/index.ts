/**
 * Cloudflare Workers – Discord Interaction Gateway
 *
 * Responsibilities (spec §16):
 *   1. Verify Discord Ed25519 signature
 *   2. Authorise user (ALLOWED_DISCORD_USER_ID)
 *   3. Return deferred ack (type 5) for commands
 *   4. ctx.waitUntil() → POST backend enqueue API
 *
 * Does NOT: fetch pixiv, translate, build EPUB, send Kindle.
 */

export interface Env {
	DISCORD_PUBLIC_KEY: string;
	DISCORD_APPLICATION_ID: string;
	ALLOWED_DISCORD_USER_ID: string;
	INTERNAL_API_TOKEN: string;
	BACKEND_BASE_URL: string;
}

// Discord interaction types
const PING = 1;
const APPLICATION_COMMAND = 2;

// Discord response types
const PONG = 1;
const CHANNEL_MESSAGE_WITH_SOURCE = 4;
const DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE = 5;

// ── Signature verification ────────────────────────────

async function verifySignature(
	request: Request,
	publicKey: string,
): Promise<{ valid: boolean; body: string }> {
	const signature = request.headers.get("X-Signature-Ed25519") ?? "";
	const timestamp = request.headers.get("X-Signature-Timestamp") ?? "";
	const body = await request.text();

	const encoder = new TextEncoder();
	const message = encoder.encode(timestamp + body);

	const key = await crypto.subtle.importKey(
		"raw",
		hexToUint8Array(publicKey),
		{ name: "Ed25519", namedCurve: "Ed25519" },
		false,
		["verify"],
	);

	const valid = await crypto.subtle.verify(
		"Ed25519",
		key,
		hexToUint8Array(signature),
		message,
	);

	return { valid, body };
}

function hexToUint8Array(hex: string): Uint8Array {
	const arr = new Uint8Array(hex.length / 2);
	for (let i = 0; i < hex.length; i += 2) {
		arr[i / 2] = parseInt(hex.substring(i, i + 2), 16);
	}
	return arr;
}

// ── Option extraction ─────────────────────────────────

interface CommandOption {
	name: string;
	value: unknown;
	type: number;
}

function getOption<T>(
	options: CommandOption[] | undefined,
	name: string,
	fallback: T,
): T {
	if (!options) return fallback;
	const opt = options.find((o) => o.name === name);
	return opt ? (opt.value as T) : fallback;
}

// ── JSON helpers ──────────────────────────────────────

function jsonResponse(data: unknown, status = 200): Response {
	return new Response(JSON.stringify(data), {
		status,
		headers: { "content-type": "application/json" },
	});
}

function ephemeralMessage(content: string): Response {
	return jsonResponse({
		type: CHANNEL_MESSAGE_WITH_SOURCE,
		data: { content, flags: 64 },
	});
}

// ── Main handler ──────────────────────────────────────

export default {
	async fetch(
		request: Request,
		env: Env,
		ctx: ExecutionContext,
	): Promise<Response> {
		// Only accept POST.
		if (request.method !== "POST") {
			return new Response("Method not allowed", { status: 405 });
		}

		// 1. Verify Discord signature.
		const { valid, body } = await verifySignature(
			request,
			env.DISCORD_PUBLIC_KEY,
		);
		if (!valid) {
			return new Response("Invalid signature", { status: 401 });
		}

		const interaction = JSON.parse(body);
		const interactionType: number = interaction.type;

		// 2. Handle PING.
		if (interactionType === PING) {
			return jsonResponse({ type: PONG });
		}

		// 3. Handle APPLICATION_COMMAND.
		if (interactionType === APPLICATION_COMMAND) {
			// Authorise user.
			const user =
				interaction.member?.user ?? interaction.user ?? {};
			const userId: string = user.id ?? "";

			if (userId !== env.ALLOWED_DISCORD_USER_ID) {
				console.warn(`Unauthorised user: ${userId}`);
				return ephemeralMessage("❌ 你沒有使用此指令的權限");
			}

			// Parse command options.
			const options: CommandOption[] | undefined =
				interaction.data?.options;

			const novelInput = getOption<string>(options, "novel", "");
			const translate = getOption<boolean>(options, "translate", false);
			const targetLang = getOption<string>(
				options,
				"target_lang",
				"zh-TW",
			);

			if (!novelInput) {
				return ephemeralMessage("❌ 請提供 pixiv 小說 URL 或 ID");
			}

			// Build enqueue payload.
			const requestId = crypto.randomUUID();
			const payload = {
				request_id: requestId,
				discord: {
					application_id: env.DISCORD_APPLICATION_ID,
					interaction_token: interaction.token,
					channel_id: interaction.channel_id ?? null,
					guild_id: interaction.guild_id ?? null,
				},
				user: {
					discord_user_id: userId,
				},
				command: {
					novel_input: String(novelInput),
					translate: Boolean(translate),
					target_lang: String(targetLang),
				},
			};

			console.log(
				`[interaction] request_id=${requestId} novel=${novelInput} user=${userId}`,
			);

			// 4. Fire-and-forget backend enqueue via waitUntil.
			const backendUrl = `${env.BACKEND_BASE_URL}/internal/enqueue/pixiv-to-kindle`;

			ctx.waitUntil(
				fetch(backendUrl, {
					method: "POST",
					headers: {
						"Content-Type": "application/json",
						"X-Internal-Token": env.INTERNAL_API_TOKEN,
					},
					body: JSON.stringify(payload),
				})
					.then(async (resp) => {
						if (!resp.ok) {
							const text = await resp.text();
							console.error(
								`Backend enqueue failed: ${resp.status} – ${text}`,
							);
						} else {
							console.log(
								`Backend enqueue accepted for ${requestId}`,
							);
						}
					})
					.catch((err) => {
						console.error(`Backend enqueue error: ${err}`);
					}),
			);

			// 5. Return deferred ack immediately.
			return jsonResponse({ type: DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE });
		}

		// Unknown interaction type.
		return jsonResponse({ error: "Unknown interaction type" }, 400);
	},
};
