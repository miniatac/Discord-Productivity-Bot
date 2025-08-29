import os
import json
import discord
import asyncio
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta, timezone

# allow pinging @everyone in scheduled event reminders
AllowedPingEveryone = discord.AllowedMentions(everyone=True)

# -------- env helpers --------
def _env_int(name: str, default: int | None = None) -> int | None:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    try:
        return int(v)
    except ValueError:
        raise ValueError(f"env var {name} must be an integer")

def _env_str(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    return v if v is not None and v.strip() != "" else default

# ===== CONFIG via environment =====
DISCORD_BOT_TOKEN = _env_str("DISCORD_BOT_TOKEN", "token_here") # your bot token
GUILD_ID = _env_int("GUILD_ID", 0)                           # your server id
GENERAL_CHANNEL_ID = _env_int("GENERAL_CHANNEL_ID", 0)           # channel for meeting reminders and welcome messages
MODS_CHANNEL_ID = _env_int("MODS_CHANNEL_ID", 0)                 # staff channel
RULES_CHANNEL_ID = _env_int("RULES_CHANNEL_ID", 0)               # rules channel
SERVER_GUIDE_CHANNEL_ID = _env_int("SERVER_GUIDE_CHANNEL_ID", 0) # server guide channel
INTRODUCTIONS_CHANNEL_ID = _env_int("INTRODUCTIONS_CHANNEL_ID", 0) # introductions channel
VC_GENERAL_ID = _env_int("VC_GENERAL_ID", 0)                     # general voice channel
WELCOME_QUESTIONS_URL = "link here" # link to the welcome questions


# file used for session persistence
SESSION_STATE_PATH = os.getenv("SESSION_STATE_PATH", "sessions_state.json")

# basic checks to avoid silent misconfigurations
if not DISCORD_BOT_TOKEN or DISCORD_BOT_TOKEN == "token_here":
    raise RuntimeError("set DISCORD_BOT_TOKEN env var")
for name, val in {
    "GUILD_ID": GUILD_ID,
    "GENERAL_CHANNEL_ID": GENERAL_CHANNEL_ID,
    "MODS_CHANNEL_ID": MODS_CHANNEL_ID,
    "RULES_CHANNEL_ID": RULES_CHANNEL_ID,
    "SERVER_GUIDE_CHANNEL_ID": SERVER_GUIDE_CHANNEL_ID,
    "INTRODUCTIONS_CHANNEL_ID": INTRODUCTIONS_CHANNEL_ID,
    "VC_GENERAL_ID": VC_GENERAL_ID,
}.items():
    if not isinstance(val, int) or val <= 0:
        raise RuntimeError(f"set a valid integer env var for {name}")

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

# -------------------- persistence utilities --------------------
def _default_state():
    return {
        "session_active": False,
        "session_channel_id": None,
        "session_tasks": {},         # str(user_id) -> [task, ...]
        "session_ping_optin": []     # [user_id, ...]
    }

def load_state():
    try:
        with open(SESSION_STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("session_active", False)
        data.setdefault("session_channel_id", None)
        data.setdefault("session_tasks", {})
        data.setdefault("session_ping_optin", [])
        return data
    except FileNotFoundError:
        return _default_state()
    except Exception as e:
        print(f"error reading {SESSION_STATE_PATH}: {e}")
        return _default_state()

def save_state():
    try:
        data = {
            "session_active": session_active,
            "session_channel_id": session_channel_id,
            "session_tasks": {str(k): v for k, v in session_tasks.items()},
            "session_ping_optin": list(session_ping_optin),
        }
        with open(SESSION_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"error saving {SESSION_STATE_PATH}: {e}")

# -------------------- meeting reminders --------------------
scheduled_reminders: dict[int, list[asyncio.Task]] = {}

def _seconds_until(target_dt_utc: datetime) -> float:
    return (target_dt_utc - datetime.now(timezone.utc)).total_seconds()

def _event_target_text(ev: discord.ScheduledEvent) -> str:
    if ev.entity_type == discord.EntityType.external:
        return ev.location or "external"
    try:
        if ev.channel:
            return f"channel {ev.channel.name}"
    except Exception:
        pass
    return "unspecified"

async def send_event_reminder(channel: discord.TextChannel, ev: discord.ScheduledEvent, label: str):
    await channel.send("@everyone", allowed_mentions=AllowedPingEveryone)

    ts = int(ev.start_time.timestamp())
    when_txt = f"<t:{ts}:F> • (<t:{ts}:R>)"

    lines = [
        f"📅 {ev.name}",
        f"🕒 starts {when_txt}"
    ]
    where_txt = _event_target_text(ev)
    if where_txt:
        lines.append(f"📍 {where_txt}")
    if ev.description:
        lines.append(f"💡 {ev.description}")

    embed = discord.Embed(
        title="reminder",
        description="\n".join(lines),
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="see you there")
    await channel.send(embed=embed)

async def _sleep_then_remind(ev: discord.ScheduledEvent, label: str):
    channel = bot.get_channel(GENERAL_CHANNEL_ID)
    if not channel:
        print("general channel not found. check GENERAL_CHANNEL_ID")
        return
    await send_event_reminder(channel, ev, label)

async def _schedule_after(delay_sec: float, ev: discord.ScheduledEvent, label: str):
    try:
        print(f"scheduling {label} for event {ev.id} in {int(delay_sec)}s")
        await asyncio.sleep(delay_sec)
        await _sleep_then_remind(ev, label)
    except asyncio.CancelledError:
        print(f"cancelled scheduled {label} for event {ev.id}")
        return

async def schedule_reminders_for_event(ev: discord.ScheduledEvent):
    await cancel_reminders_for_event(ev.id)
    if not ev.start_time:
        return
    tasks: list[asyncio.Task] = []

    t24 = _seconds_until(ev.start_time - timedelta(hours=24))
    if t24 > 0:
        tasks.append(asyncio.create_task(_schedule_after(t24, ev, "24h")))
    else:
        print(f"skip 24h reminder for {ev.id}")

    t1 = _seconds_until(ev.start_time - timedelta(hours=1))
    if t1 > 0:
        tasks.append(asyncio.create_task(_schedule_after(t1, ev, "1h")))
    else:
        print(f"skip 1h reminder for {ev.id}")

    scheduled_reminders[ev.id] = tasks

async def cancel_reminders_for_event(event_id: int):
    tasks = scheduled_reminders.pop(event_id, [])
    for t in tasks:
        if not t.done():
            t.cancel()

async def schedule_all_existing_events():
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print("guild not found, check GUILD_ID")
        return
    now = datetime.now(timezone.utc)
    events = await guild.fetch_scheduled_events()
    for ev in events:
        if ev.start_time and ev.start_time > now:
            await schedule_reminders_for_event(ev)

# -------------------- bot events --------------------
@bot.event
async def on_ready():
    print(f"{bot.user} is now running")
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

    state = load_state()
    global session_active, session_tasks, session_ping_optin, session_channel_id, session_end_task
    session_active = state["session_active"]
    session_channel_id = state["session_channel_id"]
    session_tasks = {int(k): list(map(str, v)) for k, v in state["session_tasks"].items()}
    session_ping_optin = set(int(x) for x in state["session_ping_optin"])
    session_end_task = None

    if session_active:
        session_active = False
        save_state()
        if session_channel_id:
            ch = bot.get_channel(session_channel_id)
            if ch:
                await ch.send("previous session data restored after a restart. session is not running anymore.")

    await schedule_all_existing_events()

@bot.event
async def on_member_join(member: discord.Member):
    channel_general = bot.get_channel(GENERAL_CHANNEL_ID)
    if not channel_general:
        return
    server_guide_mention = f"<#{SERVER_GUIDE_CHANNEL_ID}>"
    introductions_mention = f"<#{INTRODUCTIONS_CHANNEL_ID}>"
    msg = (
        f"Welcome {member.mention}!\n"
        f"You can learn more about the group at {server_guide_mention}\n"
        f"Please introduce yourself by answering the [questions]({WELCOME_QUESTIONS_URL})\n"
        f"in {introductions_mention} when you have time!"
    )
    await channel_general.send(msg)

@bot.event
async def on_member_remove(member: discord.Member):
    channel_mods = bot.get_channel(MODS_CHANNEL_ID)
    if channel_mods:
        try:
            await channel_mods.send(f"{member.mention} has left")
        except discord.Forbidden:
            print("missing access to mods channel")

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    channel_mods = bot.get_channel(MODS_CHANNEL_ID)
    if not channel_mods:
        return
    if before.channel is None and after.channel and after.channel.id == VC_GENERAL_ID:
        await channel_mods.send(f"🔊 {member.mention} has joined the general VC.")
    elif before.channel and before.channel.id == VC_GENERAL_ID and (after.channel is None or after.channel.id != VC_GENERAL_ID):
        await channel_mods.send(f"👋 {member.mention} has left the general VC.")

@bot.event
async def on_scheduled_event_create(event: discord.ScheduledEvent):
    await schedule_reminders_for_event(event)

@bot.event
async def on_scheduled_event_update(before: discord.ScheduledEvent, after: discord.ScheduledEvent):
    await schedule_reminders_for_event(after)

@bot.event
async def on_scheduled_event_delete(event: discord.ScheduledEvent):
    await cancel_reminders_for_event(event.id)

# -------------------- session tracking --------------------
session_active = False
session_tasks: dict[int, list[str]] = {}
session_ping_optin: set[int] = set()
session_channel_id: int | None = None
session_end_task: asyncio.Task | None = None

async def session_timer(duration: int):
    await asyncio.sleep(duration * 60)
    channel = bot.get_channel(session_channel_id)
    if channel:
        if session_ping_optin:
            mentions = " ".join(f"<@{uid}>" for uid in session_ping_optin)
            await channel.send(mentions)
        if session_tasks:
            lines = []
            for user_id, tasks in session_tasks.items():
                user = await bot.fetch_user(user_id)
                task_lines = "\n".join(f"- {t}" for t in tasks)
                lines.append(f"{user.display_name}\n{task_lines}")
            summary_text = "\n\n".join(lines)
        else:
            summary_text = "no tasks were recorded."
        embed_timer = discord.Embed(
            title="session has ended",
            description=f"session summary:\n\n{summary_text}",
            timestamp=datetime.now(timezone.utc)
        )
        await channel.send(embed=embed_timer)
    await end_session_cleanup()
    save_state()

async def end_session_cleanup():
    global session_active, session_tasks, session_ping_optin, session_channel_id, session_end_task
    session_active = False
    session_tasks = {}
    session_ping_optin = set()
    session_channel_id = None
    if session_end_task:
        session_end_task.cancel()
        session_end_task = None

async def build_tasks_text() -> str:
    if not session_tasks:
        return "no tasks yet."
    parts = []
    for uid, tasks in session_tasks.items():
        user = await bot.fetch_user(uid)
        parts.append(f"{user.display_name}\n" + "\n".join(f"- {t}" for t in tasks))
    return "\n\n".join(parts)

# -------------------- session ui --------------------
class NewTaskModal(discord.ui.Modal, title="add a task for this session"):
    task = discord.ui.TextInput(label="task", placeholder="what will you work on", required=True, max_length=200)
    async def on_submit(self, interaction: discord.Interaction):
        global session_tasks
        if not session_active:
            await interaction.response.send_message("no active session. use start_session.", ephemeral=True)
            return
        session_tasks.setdefault(interaction.user.id, []).append(str(self.task))
        save_state()
        await interaction.response.send_message(f"task added: {self.task}", ephemeral=True)

class SessionView(discord.ui.View):
    def __init__(self, *, timeout: float | None = None):
        super().__init__(timeout=timeout)

    @discord.ui.button(label="🔔 ping me", style=discord.ButtonStyle.danger)
    async def ping_me_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        global session_ping_optin
        if not session_active:
            await interaction.response.send_message("no active session.", ephemeral=True)
            return
        session_ping_optin.add(interaction.user.id)
        save_state()
        await interaction.response.send_message("ok. you will be pinged when the session ends.", ephemeral=True)

    @discord.ui.button(label="📝 new task", style=discord.ButtonStyle.primary)
    async def new_task_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(NewTaskModal())

    @discord.ui.button(label="tasks list", style=discord.ButtonStyle.secondary)
    async def tasks_list_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not session_active:
            await interaction.response.send_message("no active session.", ephemeral=True)
            return
        text = await build_tasks_text()
        await interaction.response.send_message(text, ephemeral=True)

# -------------------- session command --------------------
@bot.tree.command(guild=discord.Object(id=GUILD_ID), name="start_session")
@app_commands.describe(duration="duration of the session in minutes")
async def start_session(interaction: discord.Interaction, duration: int):
    global session_active, session_tasks, session_ping_optin, session_channel_id, session_end_task
    if session_active:
        await interaction.response.send_message("a session is already running.", ephemeral=True)
        return
    session_active = True
    session_tasks = {}
    session_ping_optin = set()
    session_channel_id = interaction.channel.id
    description = (
        "put down what you want to get done this session using the buttons below.\n\n"
        "buttons:\n"
        "- 🔔 ping me: receive a ping when the session ends.\n"
        "- 📝 new task: add the task you want to work on.\n"
        "- tasks list: see the current tasks privately during the session."
    )
    embed_todo = discord.Embed(
        title=f"Body Doubling Session of {duration} minutes",
        description=description,
        timestamp=datetime.now(timezone.utc)
    )
    await interaction.response.send_message(embed=embed_todo, view=SessionView())
    session_end_task = asyncio.create_task(session_timer(duration))
    save_state()

# -------------------- start the bot --------------------
bot.run(DISCORD_BOT_TOKEN)
