# ---------- TICKET SYSTEM (start of file through panel command) ----------
import os
import json
import asyncio
from datetime import datetime

import discord
from discord.ext import commands
from discord import ui
from keep_alive import keep_alive

# ---------- CONFIG ----------
PREFIX = "*"
INTENTS = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=INTENTS)

@bot.event
async def on_ready():
    print("Bot is running...")
    Print(f"Logged in as {bot.user}")

# Panel & categories (use the IDs you gave)
PANEL_CHANNEL_ID = 1439090812289024140  # where *panel command will post
CATEGORY_MAP = {
    "order":       1442732426488054043,
    "suggestions": 1442720316861190185,
    "partnership": 1442731110738956351,
    "apply":       1442731249650372619,
    "support":     1442732224045649930,
    "scam":        1442732547279945799
}

# Roles (confirmed by you)
OWNER_ROLE_ID = 1439122245590057044
COOWNER_ROLE_ID = 1439089267899895900
MODERATOR_ROLE_ID = 1439095082572578908
STAFF_ROLE_ID = 1439096539979972742

# Who counts as staff (can vouch/close and be pinged)
STAFF_ROLES = [STAFF_ROLE_ID, MODERATOR_ROLE_ID, COOWNER_ROLE_ID, OWNER_ROLE_ID]

# Come-team ping list (when owner presses Come Team)
COME_TEAM_ROLE_IDS = [MODERATOR_ROLE_ID, COOWNER_ROLE_ID, OWNER_ROLE_ID]

# Ticket types data (labels, emoji, descriptions)
TICKET_TYPES = {
    "order":       {"label": "Order",       "emoji": "🛒", "desc": "Provide item, amount & payment method."},
    "suggestions": {"label": "Suggestions", "emoji": "💡", "desc": "Share ideas to improve the server."},
    "partnership": {"label": "Partnership", "emoji": "🤝", "desc": "Business or collab inquiries."},
    "apply":       {"label": "ApplyStaff",  "emoji": "📝", "desc": "Apply to join staff (answer inside)."},
    "support":     {"label": "Support",     "emoji": "🎧", "desc": "Report bugs and errors."},
    "scam":        {"label": "Report Scammer","emoji": "🚨","desc":"Provide usernames/screens and proof."}
}

TICKET_FOOTER = "Ticket System"

# Ticket counter file & lock
COUNTERS_FILE = "ticket_counters.json"
COUNTERS_LOCK = asyncio.Lock()

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

# ---------- HELPERS ----------
def is_staff_member(member: discord.Member) -> bool:
    if member is None:
        return False
    return any(role.id in STAFF_ROLES for role in member.roles)

def mention_roles(role_ids):
    return " ".join(f"<@&{rid}>" for rid in role_ids)

# ---------- ON READY: register persistent panel view ----------
@bot.event
async def on_ready():
    try:
        bot.add_view(TicketPanelView())   # persistent panel
        print("TicketPanelView registered.")
    except Exception as e:
        print("Error registering panel view:", e)
    print(f"✅ Logged in as {bot.user} (id: {bot.user.id})")
    await ensure_counters()

# ---------- MANAGEMENT VIEW (per-ticket) ----------
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
        # update embed message if exists
        try:
            msg = await interaction.channel.fetch_message(interaction.message.id)
            if msg and msg.embeds:
                e = msg.embeds[0]
                # change Status and Claimed By fields (try-safe)
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
        # allowed: staff roles (we treat staff roles as helpers) or owner
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
        await interaction.response.send_message(f"✅ Order marked **successful** by {interaction.user.mention}. Buyer may now vouch.", ephemeral=False)

    # Vouch — BUYER ONLY and only after success
    @ui.button(label="Vouch ⭐", style=discord.ButtonStyle.secondary)
    async def vouch_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.creator.id:
            await interaction.response.send_message("❌ Only the buyer can vouch.", ephemeral=True)
            return
        if not self.success:
            await interaction.response.send_message("❌ You can vouch only after the Owner/staff confirms success.", ephemeral=True)
            return
        await interaction.response.send_message("✨ Thank you for the vouch!", ephemeral=True)

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

# ---------- FUNCTION TO CREATE A TICKET ----------
async def create_ticket_for(interaction: discord.Interaction, ticket_key: str):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    user = interaction.user
    if guild is None:
        return await interaction.followup.send("This command can't be used in DMs.", ephemeral=True)

    # find category id
    cat_id = CATEGORY_MAP.get(ticket_key)
    if not cat_id:
        return await interaction.followup.send("Invalid ticket type.", ephemeral=True)

    category = guild.get_channel(cat_id)
    if category is None:
        return await interaction.followup.send("Ticket category not found. Check category IDs.", ephemeral=True)
    if not isinstance(category, discord.CategoryChannel):
        return await interaction.followup.send("Provided category ID is not a category. Use the category ID.", ephemeral=True)

    # numbering
    num = await next_ticket_number(ticket_key)
    channel_name = f"{ticket_key}-{num:03d}"

    # avoid duplicates
    for ch in guild.text_channels:
        if ch.name == channel_name:
            return await interaction.followup.send("A ticket with that name already exists — contact staff.", ephemeral=True)

    # overwrites: hide @everyone, allow buyer and staff+owner
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    }
    # owner + staff roles
    for rid in STAFF_ROLES:
        role_obj = guild.get_role(rid)
        if role_obj:
            overwrites[role_obj] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

    try:
        channel = await guild.create_text_channel(name=channel_name, overwrites=overwrites, category=category,
                                                  reason=f"Ticket {ticket_key} opened by {user}")
    except Exception:
        return await interaction.followup.send("I couldn't create the ticket channel (missing Manage Channels permission?).", ephemeral=True)

    # ping owner + buyer in ticket channel
    try:
        owner_role = guild.get_role(OWNER_ROLE_ID)
        pings = []
        if owner_role:
            pings.append(owner_role.mention)
        pings.append(user.mention)
        await channel.send(f"{' '.join(pings)}\nA staff member will assist you shortly.")
    except Exception:
        pass

    # ticket embed
    desc = TICKET_TYPES[ticket_key].get("desc", f"{user.mention}, staff will assist you shortly.")
    embed = discord.Embed(title=f"{TICKET_TYPES[ticket_key]['emoji']} {TICKET_TYPES[ticket_key]['label']}",
                          description=desc,
                          color=0x6A00FF,
                          timestamp=datetime.utcnow())
    embed.add_field(name="Creator", value=user.mention, inline=False)
    embed.add_field(name="Created", value=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), inline=False)
    embed.add_field(name="Status", value="Open", inline=False)
    embed.add_field(name="Ticket Type", value=TICKET_TYPES[ticket_key]['label'], inline=False)
    embed.add_field(name="Claimed By", value="Unclaimed", inline=False)
    embed.set_footer(text=TICKET_FOOTER)

    # send embed + management view
    manage_view = TicketManageView(ticket_creator=user)
    ticket_msg = await channel.send(embed=embed, view=manage_view)

    await interaction.followup.send(f"✅ Ticket created: {channel.mention}", ephemeral=True)

# ---------- PANEL VIEW (posted with *panel) ----------
class TicketPanelView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        # create a button for each ticket type — aesthetic styles
        order_btn = ui.Button(label="Order", emoji="🛒", style=discord.ButtonStyle.primary)
        order_btn.callback = lambda i, b, k="order": create_ticket_for_callback(i, k)
        self.add_item(order_btn)

        suggest_btn = ui.Button(label="Suggestions", emoji="💡", style=discord.ButtonStyle.secondary)
        suggest_btn.callback = lambda i, b, k="suggestions": create_ticket_for_callback(i, k)
        self.add_item(suggest_btn)

        part_btn = ui.Button(label="Partnership", emoji="🤝", style=discord.ButtonStyle.secondary)
        part_btn.callback = lambda i, b, k="partnership": create_ticket_for_callback(i, k)
        self.add_item(part_btn)

        apply_btn = ui.Button(label="Apply Staff", emoji="📝", style=discord.ButtonStyle.secondary)
        apply_btn.callback = lambda i, b, k="apply": create_ticket_for_callback(i, k)
        self.add_item(apply_btn)

        support_btn = ui.Button(label="Support", emoji="🎧", style=discord.ButtonStyle.secondary)
        support_btn.callback = lambda i, b, k="support": create_ticket_for_callback(i, k)
        self.add_item(support_btn)

        scam_btn = ui.Button(label="Report Scammer", emoji="🚨", style=discord.ButtonStyle.danger)
        scam_btn.callback = lambda i, b, k="scam": create_ticket_for_callback(i, k)
        self.add_item(scam_btn)

# helper wrapper because lambda callback needs to be async
def create_ticket_for_callback(interaction: discord.Interaction, ticket_key: str):
    # wrapper to call async function create_ticket_for
    return asyncio.create_task(create_ticket_for(interaction, ticket_key))

# ---------- PANEL COMMAND (prefix *) ----------
@bot.command()
@commands.has_permissions(administrator=True)
async def panel(ctx):
    """Post the ticket panel (admin only)."""
    if ctx.channel.id != PANEL_CHANNEL_ID:
        # if you want it only in a specific channel, inform user
        await ctx.send(f"Use this command in the designated panel channel (ID: {PANEL_CHANNEL_ID}).", delete_after=8)
        return

    embed = discord.Embed(
        title="🎫 Ticket Panel",
        description=(
            "**Click a button to open a ticket.**\n\n"
            "• Order — purchases & orders\n"
            "• Suggestions — ideas & feedback\n"
            "• Partnership — business/collabs\n"
            "• Apply Staff — apply to be staff\n"
            "• Support — report bugs & errors\n"
            "• Report Scammer — report suspicious users\n        "
        ),
        color=0x2ECC71
    )
    embed.set_footer(text="Ticket System • Click a button below")
    await ctx.send(embed=embed, view=TicketPanelView())

# ============================
# ⭐ VERIFICATION SYSTEM ⭐
# ============================

VERIFY_CHANNEL_ID = 1439090812289024140      # Where the verify panel is sent
VERIFY_ROLE_ID = 1439125802934472856         # Role given after verification

class VerifyButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify", style=discord.ButtonStyle.green, emoji="✅", custom_id="verify_button")
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = interaction.guild.get_role(VERIFY_ROLE_ID)

        if role in interaction.user.roles:
            return await interaction.response.send_message(
                "You are already verified!", ephemeral=True
            )

        await interaction.user.add_roles(role)
        await interaction.response.send_message(
            "You have been verified successfully! 🎉", ephemeral=True
        )

# Send the verification panel
@bot.command()
async def verifysetup(ctx):
    embed = discord.Embed(
        title="🔐 Verification Required",
        description="Click the **Verify** button below to access the server.",
        color=discord.Color.green()
    )
    view = VerifyButton()
    await ctx.send(embed=embed, view=view)

# Activate the button on bot startup
@bot.event
async def on_ready():
    bot.add_view(VerifyButton())
    print(f"✅ Verification system loaded — Logged in as {bot.user}")

#===============================
# ROLES SYSTEM
#===============================
@bot.command()
async def autoroles(ctx):
    embed = discord.Embed(
        title="🌟 Choose Your Ping Roles",
        description="React below to get the roles you want!",
        color=discord.Color.blue()
    )

    embed.add_field(name="🌐 — Maxed Land Ping", value="React: 🌐", inline=False)
    embed.add_field(name="🌲 — Wood Drops Ping", value="React: 🌲", inline=False)
    embed.add_field(name="🏘️ — Bases Ping", value="React: 🏘️", inline=False)
    embed.add_field(name="🎁 — Gift Truckloads Ping", value="React: 🎁", inline=False)
    embed.add_field(name="💵 — Lumber Bucks Ping", value="React: 💵", inline=False)
    embed.add_field(name="💌 — Pink Items Ping", value="React: 💌", inline=False)
    embed.add_field(name="📦 — Gift Drops Ping", value="React: 📦", inline=False)
    embed.add_field(name="🪓 — Axe Drops Ping", value="React: 🪓", inline=False)
    embed.add_field(name="🔐 — Accounts Ping", value="React: 🔐", inline=False)
    embed.add_field(name="🎉 — Giveaways Ping", value="React: 🎉", inline=False)
    embed.add_field(name="📢 — Announcement Ping", value="React: 📢", inline=False)

    msg = await ctx.send(embed=embed)

    emojis = ["🌐","🌲","🏘️","🎁","💵","💌","📦","🪓","🔐","🎉","📢"]
    for emoji in emojis:
        await msg.add_reaction(emoji)

    print(f"Reaction role message ID: {msg.id}")
    
# ================================
# RUN BOT
# ================================
keep_alive()
bot.run(os.getenv("DISCORD_BOT_TOKEN"))
