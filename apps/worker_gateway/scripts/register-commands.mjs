/**
 * Register Discord slash commands for /pixiv2kindle.
 *
 * Usage:
 *   DISCORD_APPLICATION_ID=... DISCORD_BOT_TOKEN=... node scripts/register-commands.mjs
 *
 * Or from the worker_gateway dir:
 *   npm run register-commands
 *
 * Spec reference: §8.
 */

const APPLICATION_ID = process.env.DISCORD_APPLICATION_ID;
const BOT_TOKEN = process.env.DISCORD_BOT_TOKEN;

if (!APPLICATION_ID || !BOT_TOKEN) {
	console.error(
		"Missing DISCORD_APPLICATION_ID or DISCORD_BOT_TOKEN env vars",
	);
	process.exit(1);
}

const commands = [
	{
		name: "pixiv2kindle",
		description: "將 pixiv 小說轉為 EPUB 寄送到 Kindle",
		options: [
			{
				name: "novel",
				description: "pixiv 小說 URL 或 ID",
				type: 3, // STRING
				required: true,
			},
			{
				name: "translate",
				description: "是否進行翻譯",
				type: 5, // BOOLEAN
				required: false,
			},
			{
				name: "target_lang",
				description: "翻譯目標語言（預設 zh-TW）",
				type: 3, // STRING
				required: false,
			},
		],
	},
];

const url = `https://discord.com/api/v10/applications/${APPLICATION_ID}/commands`;

const response = await fetch(url, {
	method: "PUT",
	headers: {
		"Content-Type": "application/json",
		Authorization: `Bot ${BOT_TOKEN}`,
	},
	body: JSON.stringify(commands),
});

if (response.ok) {
	const data = await response.json();
	console.log(`✅ Registered ${data.length} command(s):`);
	for (const cmd of data) {
		console.log(`   /${cmd.name} (id: ${cmd.id})`);
	}
} else {
	const text = await response.text();
	console.error(`❌ Failed to register commands: ${response.status}`);
	console.error(text);
	process.exit(1);
}
