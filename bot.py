import discord
from discord.ext import commands
import logging
import json
import os

TOKEN = os.getenv("MY_TOKEN_KEY")  # Your bot token here or env var
CRAFT_CHANNEL_ID = 1377981360618209332  # Your craft channel ID

ROLE_EMOJI_MAP = {
    "Blacksmiths (Weapons)": "<:balcksmithweapon:1372649321396310110>",
    "Blacksmiths (Armor)": "<:blacksmitharmor:1372649310495309834>",
    "Alchemists": "<:alchemy:1372649308993753258>",
    "Enchanters": "<:enchanting:1372649311862657034>",
    "Engineers": "<:engineering:1372649313745764392>",
    "Scribes (Inscription)": "<:inscription:1372649314970767491>",
    "Jewelcrafters": "<:jewelcrafting:1372649316782706769>",
    "Leatherworkers (Mail)": "<:leatherworkersmail:1372649478556749894>",
    "Leatherworkers (Leather)": "<:leatherworkingleather:1372649318099452035>",
    "Tailors": "<:tailoring:1372649319718715423>",
}

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)8s] %(name)s: %(message)s')
logger = logging.getLogger("CraftBot")

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True
intents.guilds = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "craft_data.json"
craft_data = {
    "total": 0,
    "by_role": {},
    "reacted_messages": {},  # message_id: set(user_ids)
    "status_message_id": None  # To store the status message ID for updating
}

def save_data():
    serializable_data = {
        "total": craft_data["total"],
        "by_role": craft_data["by_role"],
        "reacted_messages": {k: list(v) for k, v in craft_data["reacted_messages"].items()},
        "status_message_id": craft_data.get("status_message_id")
    }
    with open(DATA_FILE, 'w') as f:
        json.dump(serializable_data, f)

def load_data():
    global craft_data
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            loaded = json.load(f)
            craft_data["total"] = loaded.get("total", 0)
            craft_data["by_role"] = loaded.get("by_role", {})
            craft_data["reacted_messages"] = {k: set(v) for k, v in loaded.get("reacted_messages", {}).items()}
            craft_data["status_message_id"] = loaded.get("status_message_id")
    else:
        craft_data["total"] = 0
        craft_data["by_role"] = {}
        craft_data["reacted_messages"] = {}
        craft_data["status_message_id"] = None

async def update_status_message():
    channel = bot.get_channel(CRAFT_CHANNEL_ID)
    if not channel:
        logger.error("Craft channel not found for status update!")
        return

    lines = [f"📊 Total completed crafts: {craft_data['total']}"]
    for role, emoji in ROLE_EMOJI_MAP.items():
        count = craft_data["by_role"].get(role, 0)
        lines.append(f"{emoji} {role}: {count}")
    content = "\n".join(lines)

    status_msg_id = craft_data.get("status_message_id")
    if status_msg_id:
        try:
            msg = await channel.fetch_message(status_msg_id)
            await msg.edit(content=content)
            logger.info("Updated status message")
            return
        except Exception as e:
            logger.warning(f"Failed to fetch or edit status message: {e}")

    # If no status message exists or fetch failed, send a new one
    msg = await channel.send(content)
    craft_data["status_message_id"] = msg.id
    save_data()
    logger.info("Sent new status message")

@bot.event
async def on_ready():
    load_data()
    logger.info(f"Bot is ready! Logged in as {bot.user}")
    await update_status_message()

@bot.event
async def on_message(message):
    if message.channel.id != CRAFT_CHANNEL_ID:
        return

    if message.author.bot:
        return

    if message.content.startswith("!"):
        ctx = await bot.get_context(message)
        if ctx.command is None:
            await message.delete()
            valid_commands = ["!status", "!reset", "!remove"]
            await message.channel.send(f"{message.author.mention} Wrong command. Valid commands are: {', '.join(valid_commands)}")
        else:
            await bot.process_commands(message)
    elif message.role_mentions:
        logger.debug(f"[TRACKED] Tracked message with role mention ID: {message.id}")
    else:
        logger.debug(f"[IGNORED] Message without mention ID: {message.id}")

@bot.command()
async def status(ctx):
    await update_status_message()

@bot.command()
async def reset(ctx):
    craft_data["total"] = 0
    craft_data["by_role"] = {}
    craft_data["reacted_messages"] = {}
    save_data()
    await update_status_message()
    await ctx.send("✅ Craft data has been reset.")

@bot.command()
async def remove(ctx, number: int):
    craft_data["total"] = max(0, craft_data["total"] - number)
    save_data()
    await update_status_message()
    await ctx.send(f"✅ Removed {number} crafts from total.")

async def get_role_from_message(message):
    for role in message.role_mentions:
        if role.name in ROLE_EMOJI_MAP:
            return role.name
    return None

async def increment_craft_count(role_name, message_id):
    craft_data["total"] += 1
    craft_data["by_role"][role_name] = craft_data["by_role"].get(role_name, 0) + 1
    logger.info(f"[COUNTED] +1 craft by role {role_name}, message ID: {message_id}")
    save_data()
    await update_status_message()

async def decrement_craft_count(role_name, message_id):
    craft_data["total"] = max(0, craft_data["total"] - 1)
    craft_data["by_role"][role_name] = max(0, craft_data["by_role"].get(role_name, 0) - 1)
    logger.info(f"[REMOVED] -1 craft from role {role_name}, message ID: {message_id}")
    save_data()
    await update_status_message()

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot or reaction.message.channel.id != CRAFT_CHANNEL_ID:
        return

    message = reaction.message
    role_name = await get_role_from_message(message)
    if not role_name:
        return

    member = message.guild.get_member(user.id)
    if not member or discord.utils.get(member.roles, name=role_name) is None:
        return

    msg_id = str(message.id)
    users_set = craft_data["reacted_messages"].get(msg_id, set())

    if not users_set:
        await increment_craft_count(role_name, msg_id)

    users_set.add(user.id)
    craft_data["reacted_messages"][msg_id] = users_set
    save_data()

    try:
        await message.delete()
        logger.info(f"Deleted message ID {msg_id} after valid reaction by user {user}")
    except Exception as e:
        logger.warning(f"Failed to delete message ID {msg_id}: {e}")

@bot.event
async def on_reaction_remove(reaction, user):
    if user.bot or reaction.message.channel.id != CRAFT_CHANNEL_ID:
        return

    message = reaction.message
    role_name = await get_role_from_message(message)
    if not role_name:
        return

    msg_id = str(message.id)
    users_set = craft_data["reacted_messages"].get(msg_id)
    if not users_set or user.id not in users_set:
        return

    member = message.guild.get_member(user.id)
    if not member or discord.utils.get(member.roles, name=role_name) is None:
        return

    users_set.remove(user.id)

    if len(users_set) == 0:
        craft_data["reacted_messages"].pop(msg_id)
        await decrement_craft_count(role_name, msg_id)
    else:
        craft_data["reacted_messages"][msg_id] = users_set
        save_data()

bot.run(TOKEN)
