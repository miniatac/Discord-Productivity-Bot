# Discord Productivity Bot

This bot provides:
- 📅 **Meeting reminders** for scheduled Discord events (automatic reminders 24h and 1h before).
- 👋 **Welcome and goodbye messages** to onboard members.
- 🔔 **Voice channel notifications** when members join or leave the general VC.
- 📋 **Body doubling study sessions** with task tracking, pings, and summaries.

---

## ⚙️ Features

- **Scheduled event reminders**  
  Automatically posts in your general channel with an @everyone ping and friendly embed.

- **Session system**  
  Members can join a timed session, add tasks, opt in for a ping, and see a final summary when the session ends.

- **Welcome messages**  
  Posts a custom welcome message linking to your server guide and introduction channel.

- **VC monitoring**  
  Logs who joins/leaves the general VC in your staff channel.

---

## 🚀 Setup

### 1. Clone this repository
```bash
git clone https://github.com/yourusername/discord-productivity-bot.git
cd discord-productivity-bot
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure the bot
Open bot.py and locate the CONFIG section. Replace placeholders with your own values:

```python
DISCORD_BOT_TOKEN = "token_here"      # your bot token
GUILD_ID = 0                          # your server ID
GENERAL_CHANNEL_ID = 0                # channel for meeting reminders and welcome messages
MODS_CHANNEL_ID = 0                   # staff channel
RULES_CHANNEL_ID = 0                  # rules channel
SERVER_GUIDE_CHANNEL_ID = 0           # server guide channel
INTRODUCTIONS_CHANNEL_ID = 0          # introductions channel
VC_GENERAL_ID = 0                     # general voice channel
WELCOME_QUESTIONS_URL = "link here"   # link to intro questions message
```

👉 To get IDs: enable Developer Mode in Discord → right-click a channel or server → Copy ID.

### 4. Enable Intents
Go to the Discord Developer Portal:
1. Select your application → Bot
2. Enable:
   - Server Members Intent
   - Message Content Intent

### 5. Run the bot
```bash
python bot.py
```

## 📂 Files
- `bot.py` – main bot script
- `requirements.txt` – dependencies list
- `sessions_state.json` – runtime storage for session data (auto-generated, you can keep an empty template)
- `README.md` – project info

## ⚠️ Notes
- Never share your bot token publicly.
- `sessions_state.json` is automatically created and updated during sessions. You can safely delete it to reset.
- If you want to use environment variables instead of editing `bot.py`, you can add support with `python-dotenv`.
