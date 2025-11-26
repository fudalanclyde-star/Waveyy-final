# main.py — Ticket system single-file (prefix commands, persistent buttons)
# Paste this entire file into your main.py and restart the bot.
# Make sure DISCORD_BOT_TOKEN is set in your environment (Replit Secrets).

import os
import json
import asyncio
from datetime import datetime

import discord
from discord.ext import commands
from discord import ui

# If you use keep_alive.py on Replit, it should define keep_alive()
try:
    from keep_alive import keep_alive
except Exception:
    def keep_alive():
        return None

# ------------- CONFIG -------------
PREFIX = "*"
INTENTS = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=INTENTS)

# ---------- CHANNEL / ROLE IDS (your confirmed values) ----------
PANEL_CHANNEL_ID = 1439090812289024140   # where the ticket panel will be posted

CATEGORY_MAP = {
    "order":       1442732426488054043,
    "suggestions": 1442720316861190185,
    "partnership": 1442731110738956351,
    "apply":       1442731249650372619,
    "support":     1442732224045649930,
    "scam":        1442732547279945799
}

VERIFY_ROLE_ID = 1439125802934472856
LOG_CHANNEL_ID = 1442720316861190185  # optional log channel

# Roles (confirmed)
OWNER_ROLE_ID = 1439122245590057044
COOWNER_ROLE_ID = 1439089267899895900
MODERATOR_ROLE_ID = 1439095082572578908
STAFF_ROLE_ID = 1439096539979972742

STAFF_ROLES = [STAFF_ROLE_ID, MODERATOR_ROLE_ID, COOWNER_ROLE_ID, OWNER_ROLE_ID]
COME_TEAM_ROLE_IDS = [MODERATOR_ROLE_ID, COOWNER_ROLE_ID, OWNER_ROLE_ID]

# Reaction-role mapping (emoji -> role name)
REACTION_ROLES = {
    "🌐": "Maxed Land Ping",
    "🌲": "Wood Drops Ping",
    "🏡": "Bases Ping",
    "🎁": "Gift Truckloads Ping",
    "💸": "Lumber Bucks Ping",
    "💌": "Pink Items Ping",
    "📦": "Gift Drops Ping",
    "🪓": "Axe Drops Ping",
    "🔐": "Accounts Ping",
    "🎉": "Giveaways Ping",
    "📢": "Announcement Ping"
}

# Ticket types & descriptions
TICKET_TYPES = {
    "order":       {"label": "Order",       "emoji": "🛒", "desc": "Provide item, amount and payment method."},
    "suggestions": {"label": "Suggestions", "emoji": "💡", "desc": "Share ideas to improve the server."},
    "partnership": {"label": "Partnership", "emoji": "🤝", "desc": "Business or collaboration inquiries."},
    "apply":       {"label": "ApplyStaff",  "emoji": "📝", "desc": "Apply to join staff — answer the questions posted."},
    "support":     {"label": "Support",     "emoji": "🎧", "desc": "Support — report bugs and errors."},
    "scam":        {"label": "Report Scammer","emoji": "🚨","desc":"Report scammers with proof/screens."}
}

TICKET_FOOTER = "Ticket System • Crystal Neon"

# Counters file & lock
COUNTERS_FILE = "ticket_counters.json"
COUNTERS_LOCK = asyncio.Lock()

# ------------- COUNTER HELPERS -------------
async def ensure_counters():
    async with COUNTERS_LOCK:
        if not os.path.exists(COUNTERS_FILE):
            data = {k: 0 for k in TICKET_TYPES.keys()}
            with open(COUNTERS_FILE, "w") as f:
                json.dump(data, f)
            return data
        else:
            try:
                with open(COUNTERS_FILE, "r") as f:
                    data = json.load(f)
            except Exception:
                data = {k: 0 for k in TICKET_TYPES.keys()}
            # ensure keys exist
            for k in TICKET_TYPES.keys():
                if k not in data:
                    data[k] = 0
            with open(COUNTERS_FILE, "w") as f:
                json.dump(data, f)
            return data

async def next_ticket_number(ticket_type: str) -> int:
    async with COUNTERS_LOCK:
        data = await ensure_counters()
        data[ticket_type] = data.get(ticket_type, 0) + 1
        with open(COUNTERS_FILE, "w") as f:
            json.dump(data, f)
        return data[ticket_type]

# ------------- HELPERS -------------
def is_staff_member(member: discord.Member) -> bool:
    if member is None:
        return False
    return any(role.id in STAFF_ROLES for role in member.roles)

def mention_roles(role_ids):
    return " ".join(f"<@&{rid}>" for rid in role_ids)

# ------------- PERSISTENT VIEWS REGISTER ON READY -------------
@bot.event
async def on_ready():
    try:
        # register persistent views so button callbacks survive restarts
        bot.add_view(TicketPanelView())
        bot.add_view(VerifyView())
        print("Persistent views registered.")
    except Exception as e:
        print("View registration failed:", e)

    print(f"✅ Logged in as {bot.user} (id: {bot.user.id})")
    await ensure_counters()

# ------------- MANAGEMENT VIEW (per-ticket) -------------
class TicketManageView(ui.View):
    def __init__(self, ticket_creator: discord.Member):
        super().__init__(timeout=None)
        self.creator = ticket_creator
        self.claimed_by = None
        self.claimed = False
        self.success = False

    # Claim button — OWNER ONLY
    @ui.button(label="Claim ✨", style=discord.ButtonStyle.primary)
    async def claim_button(self, interaction: discord.Interaction, button: ui.Button):
        # only owner can claim
        if not any(role.id == OWNER_ROLE_ID for role in interaction.user.roles):
            await interaction.response.send_message("❌ Only the Owner can claim this ticket.", ephemeral=True)
            return
        if self.claimed:
            await interaction.response.send_message(f"❗ Already claimed by {self.claimed_by.mention}", ephemeral=True)
            return
        self.claimed = True
        self.claimed_by = interaction.user

        # edit the ticket embed (best-effort)
        try:
            msg = await interaction.channel.fetch_message(interaction.message.id)
            if msg and msg.embeds:
                e = msg.embeds[0]
                # attempt to update Status and Claimed By fields
                # fields order: Creator, Created, Status, Ticket Type, Claimed By
                for i, f in enumerate(e.fields):
                    if f.name.lower().startswith("status"):
                        e.set_field_at(i, name="Status", value=f"Claimed by {interaction.user.display_name}", inline=False)
                    if f.name.lower().startswith("claimed"):
                        e.set_field_at(i, name="Claimed By", value=interaction.user.mention, inline=False)
                await msg.edit(embed=e, view=self)
        except Exception:
            pass

        await interaction.response.send_message(f"✨ Ticket claimed by {interaction.user.mention}", ephemeral=False)

    # Success button — OWNER or staff helpers allowed
    @ui.button(label="Success", style=discord.ButtonStyle.success)
    async def success_button(self, interaction: discord.Interaction, button: ui.Button):
        # allowed: any STAFF_ROLES or owner
        allowed = any(role.id in STAFF_ROLES for role in interaction.user.roles)
        if not allowed:
            await interaction.response.send_message("❌ Only Owner or staff helpers can confirm success.", ephemeral=True)
            return
        if not self.claimed:
            await interaction.response.send_message("❌ Ticket must be claimed by Owner first.", ephemeral=True)
            return
        if self.success:
            await interaction.response.send_message("❗ Already marked as success.", ephemeral=True)
            return
        self.success = True
        await interaction.response.send_message(f"✅ Marked successful by {interaction.user.mention}. Buyer may now vouch.", ephemeral=False)

    # Vouch — BUYER ONLY and only after success
    @ui.button(label="Vouch ⭐", style=discord.ButtonStyle.secondary)
    async def vouch_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.creator.id:
            await interaction.response.send_message("❌ Only the buyer can vouch.", ephemeral=True)
            return
        if not self.success:
            await interaction.response.send_message("❌ You can vouch only after Owner/staff confirms success.", ephemeral=True)
            return
        await interaction.response.send_message("✨ Thank you for the vouch!", ephemeral=True)

    # Come Team — OWNER only: pings mod/co-owner/owner
    @ui.button(label="Come Team 👑", style=discord.ButtonStyle.secondary)
    async def cometeam_button(self, interaction: discord.Interaction, button: ui.Button):
        owner_role_obj = interaction.guild.get_role(OWNER_ROLE_ID)
        if owner_role_obj is None or owner_role_obj not in interaction.user.roles:
            await interaction.response.send_message("❌ Only the Owner can call the team.", ephemeral=True)
            return
        ping_text = mention_roles(COME_TEAM_ROLE_IDS)
        await interaction.response.send_message(f"📣 Come team! {ping_text}", ephemeral=False)

    # Close — staff/owner can close (delete channel)
    @ui.button(label="Close 🗑️", style=discord.ButtonStyle.danger)
    async def close_button(self, interaction: discord.Interaction, button: ui.Button):
        allowed = any(role.id in STAFF_ROLES for role in interaction.user.roles)
        if not allowed:
            await interaction.response.send_message("❌ Only staff can close the ticket.", ephemeral=True)
            return
        await interaction.response.send_message("🗑️ Closing ticket...", ephemeral=True)
        await asyncio.sleep(1.0)
        try:
            await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")
        except Exception:
            try:
                await interaction.followup.send("Could not delete channel (missing permission).", ephemeral=True)
            except Exception:
                pass

# ------------- CREATE TICKET FUNCTION -------------
async def create_ticket_for(interaction: discord.Interaction, ticket_key: str):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    user = interaction.user
    if guild is None:
        return await interaction.followup.send("This can't be used in DMs.", ephemeral=True)

    cat_id = CATEGORY_MAP.get(ticket_key)
    if not cat_id:
        return await interaction.followup.send("Invalid ticket type.", ephemeral=True)

    category = guild.get_channel(cat_id)
    if category is None:
        return await interaction.followup.send("Ticket category not found. Check category IDs.", ephemeral=True)
    if not isinstance(category, discord.CategoryChannel):
        return await interaction.followup.send("Category ID is not a category. Use the category ID.", ephemeral=True)

    # numbering & name
    number = await next_ticket_number(ticket_key)
    channel_name = f"{ticket_key}-{number:03d}"

    # prevent duplicate
    for ch in guild.text_channels:
        if ch.name == channel_name:
            return await interaction.followup.send("A ticket with that name already exists — contact staff.", ephemeral=True)

    # overwrites
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    }
    # add staff roles
    for rid in STAFF_ROLES:
        role = guild.get_role(rid)
        if role:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

    try:
        channel = await guild.create_text_channel(
            name=channel_name,
            overwrites=overwrites,
            category=category,
            reason=f"{TICKET_TYPES[ticket_key]['label']} ticket opened by {user}"
        )
    except Exception:
        return await interaction.followup.send("I couldn't create the ticket channel (missing Manage Channels permission?).", ephemeral=True)

    # ping owner + buyer (best-effort)
    try:
        owner_role = guild.get_role(OWNER_ROLE_ID)
        pings = []
        if owner_role:
            pings.append(owner_role.mention)
        pings.append(user.mention)
        await channel.send(f"{' '.join(pings)}\nA staff member will assist you shortly.")
    except Exception:
        pass

    # embed in ticket
    desc = TICKET_TYPES[ticket_key].get("desc", f"{user.mention}, staff will assist you shortly.")
    embed = discord.Embed(
        title=f"{TICKET_TYPES[ticket_key]['emoji']} {TICKET_TYPES[ticket_key]['label']}",
        description=desc,
        color=0x6A00FF,
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="Creator", value=user.mention, inline=False)
    embed.add_field(name="Created", value=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), inline=False)
    embed.add_field(name="Status", value="Open", inline=False)
    embed.add_field(name="Ticket Type", value=TICKET_TYPES[ticket_key]['label'], inline=False)
    embed.add_field(name="Claimed By", value="Unclaimed", inline=False)
    embed.set_footer(text=TICKET_FOOTER)

    manage_view = TicketManageView(ticket_creator=user)
    ticket_msg = await channel.send(embed=embed, view=manage_view)

    await interaction.followup.send(f"✅ Ticket created: {channel.mention}", ephemeral=True)

# ------------- TICKET PANEL VIEW -------------
class TicketPanelView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        # create a button per ticket type (aesthetic)
        for key, info in TICKET_TYPES.items():
            btn = ui.Button(label=info["label"], emoji=info["emoji"], style=discord.ButtonStyle.primary if key=="order" else discord.ButtonStyle.secondary)
            # bind callback using closure
            async def _cb(interaction: discord.Interaction, k=key):
                await create_ticket_for(interaction, k)
            btn.callback = _cb
            self.add_item(btn)

# ------------- PANEL COMMAND (prefix *) -------------
@bot.command()
@commands.has_permissions(administrator=True)
async def panel(ctx):
    """Post the ticket panel in the panel channel (admin only)."""
    panel_ch = bot.get_channel(PANEL_CHANNEL_ID)
    if panel_ch is None:
        return await ctx.send("❌ Panel channel not found. Check PANEL_CHANNEL_ID.")
    embed = discord.Embed(
        title="🎫 Ticket Center",
        description="Click a button below to open a ticket.",
        color=0x7A00FF
    )
    embed.set_footer(text="Ticket System • Click a button")
    await panel_ch.send(embed=embed, view=TicketPanelView())
    await ctx.send(f"✅ Ticket panel posted in {panel_ch.mention}", delete_after=6)

# ------------- VERIFICATION VIEW -------------
class VerifyView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Verify", style=discord.ButtonStyle.success, emoji="✅")
    async def verify(self, interaction: discord.Interaction, button: ui.Button):
        role = interaction.guild.get_role(VERIFY_ROLE_ID)
        if role is None:
            return await interaction.response.send_message("Verify role not found. Ask an admin.", ephemeral=True)
        if role in interaction.user.roles:
            return await interaction.response.send_message("You are already verified.", ephemeral=True)
        try:
            await interaction.user.add_roles(role)
            await interaction.response.send_message("✅ You are now verified!", ephemeral=True)
        except Exception:
            await interaction.response.send_message("Failed to add verify role (missing perms).", ephemeral=True)

@bot.command()
@commands.has_permissions(administrator=True)
async def verifypanel(ctx):
    embed = discord.Embed(title="🔒 Verification", description="Click the button to verify and get access.", color=0x2ecc71)
    await ctx.send(embed=embed, view=VerifyView())

# ------------- REACTION ROLES PANEL -------------
@bot.command()
@commands.has_permissions(administrator=True)
async def sendreactionroles(ctx):
    channel = bot.get_channel(PANEL_CHANNEL_ID)
    if channel is None:
        return await ctx.send("❌ Panel channel not found. Check PANEL_CHANNEL_ID.")
    embed = discord.Embed(title="🌟 Choose Your Ping Roles", description="\n".join([f"{e} — **{n}**" for e, n in REACTION_ROLES.items()]), color=0x8A2BE2)
    msg = await channel.send(embed=embed)
    for e in REACTION_ROLES.keys():
        try:
            await msg.add_reaction(e)
        except Exception:
            pass
    await ctx.send("✅ Reaction role panel posted.", delete_after=6)

@bot.event
async def on_raw_reaction_add(payload):
    if payload.channel_id != PANEL_CHANNEL_ID:
        return
    if payload.user_id == bot.user.id:
        return
    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return
    emoji = str(payload.emoji)
    if emoji not in REACTION_ROLES:
        return
    role_name = REACTION_ROLES[emoji]
    role = discord.utils.get(guild.roles, name=role_name)
    if role is None:
        return
    member = guild.get_member(payload.user_id)
    if member is None or member.bot:
        return
    try:
        await member.add_roles(role)
    except Exception:
        pass

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.channel_id != PANEL_CHANNEL_ID:
        return
    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return
    emoji = str(payload.emoji)
    if emoji not in REACTION_ROLES:
        return
    role_name = REACTION_ROLES[emoji]
    role = discord.utils.get(guild.roles, name=role_name)
    if role is None:
        return
    member = guild.get_member(payload.user_id)
    if member is None or member.bot:
        return
    try:
        await member.remove_roles(role)
    except Exception:
        pass

# ------------- UTIL COMMANDS -------------
@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int = 10):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 Cleared {amount} messages.", delete_after=5)

# ------------- RUN -------------
if __name__ == "__main__":
    keep_alive()
    TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
    if not TOKEN:
        print("No DISCORD_BOT_TOKEN env var found — using placeholder 'bayot'. Replace with real token in env.")
        TOKEN = "TOKEN"
    bot.run(TOKEN)
