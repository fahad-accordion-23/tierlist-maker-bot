# Environment
from dotenv import load_dotenv
import os

# Discord API
import requests
import discord
from discord import app_commands
from discord.ext import commands

# Coding
from dataclasses import dataclass
from enum import Enum, IntEnum, auto
from typing import Dict, Optional, Any

# Rendering
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import math

# Sessions and Threads
import asyncio
import aiohttp

@dataclass
class Member:
    name: str
    avatar_url: str

class Tier(Enum):
    S = 0
    A = 1
    B = 2
    C = 3
    D = 4
    F = 5

class Tierlist:
    def __init__(self):
        self.tiers: Dict[Tier, Dict[int, Member]] = {tier: {} for tier in Tier}

    def add_member(self, _id: int, _data: Member, target_tier: Tier) -> bool:
        if target_tier not in Tier:
            return False
    
        for tier in self.tiers:
            if _id in self.tiers[tier]:
                del self.tiers[tier][_id]
                break

        self.tiers[target_tier][_id] = _data
        return True

    def remove_member(self, _id: int) -> bool:
        for tier in self.tiers:
            if _id in self.tiers[tier]:
                del self.tiers[tier][_id]
                return True

        return False

class TierlistError(IntEnum):
    SUCCESS = auto()
    USER_NOT_FOUND = auto()
    INVALID_TIER = auto()
    TIERLIST_NOT_ACTIVE = auto()
    TIERLIST_ALREADY_ACTIVE = auto()

class TierlistManager:
    def __init__(self) -> None:
        self.tierlists: Dict[str, Tierlist] = {}
        self.currently_active = None

    def begin_tierlist(self, name: str) -> TierlistError:
        if self.currently_active is not None:               # If some tierlist is already selected
            return TierlistError.TIERLIST_ALREADY_ACTIVE
        elif name in self.tierlists:                        # If no tierlist selected but target exists
            self.currently_active = name                    # already
            return TierlistError.SUCCESS
        else:                                               # None selected but target doesn't exist
            self.tierlists[name] = Tierlist()
            self.currently_active = name
            return TierlistError.SUCCESS

    def end_tierlist(self) -> TierlistError:
        if self.currently_active is not None:
            self.currently_active = None
            return TierlistError.SUCCESS
        else:
            return TierlistError.TIERLIST_NOT_ACTIVE

    def add_to_tierlist(self, _id: int, _data: Member, target_tier: Tier) -> TierlistError:
        if self.currently_active is None:
            return TierlistError.TIERLIST_NOT_ACTIVE

        if not self.tierlists[self.currently_active].add_member(_id, _data, target_tier):
            return TierlistError.INVALID_TIER
            
        return TierlistError.SUCCESS

    def remove_from_tierlist(self, _id: int) -> TierlistError:
        if self.currently_active is None:
            return TierlistError.TIERLIST_NOT_ACTIVE
        
        if not self.tierlists[self.currently_active].remove_member(_id):
            return TierlistError.USER_NOT_FOUND
        else:
            return TierlistError.SUCCESS    


# Tierlist Renderer Stuff

class TierlistRenderer:
    def __init__(self) -> None:
        self.total_width = 1000
        self.avatar_size = 100
        self.padding = 10
        self.text_height = 20
        self.min_tier_height = 100
        self.label_width = int(self.total_width * 0.15)
        self.content_width = self.total_width - self.label_width
        
        self.tier_colors = {
            'S': (255, 127, 127),
            'A': (255, 191, 127),
            'B': (255, 255, 127),
            'C': (127, 255, 127),
            'D': (127, 127, 255),
            'F': (255, 127, 255)
        }
        
        try:
            self.font_label = ImageFont.truetype("arial.ttf", 40)
            self.font_names = ImageFont.truetype("arial.ttf", 15)
        except IOError:
            self.font_label = ImageFont.load_default()
            self.font_name = ImageFont.load_default()
        
    def _calc_tier_height(self, num_members: int) -> int:
        if num_members == 0:
            return self.min_tier_height + (self.padding * 2)
            
        unit_width = self.avatar_size + self.padding
        avatars_per_row = self.content_width // unit_width
        if avatars_per_row < 1:
            avatars_per_row = 1
            
        unit_height = self.avatar_size + self.text_height + self.padding
        required_rows = math.ceil(num_members / avatars_per_row)
        total_height = (required_rows * unit_height) + self.padding
        
        return total_height
        
    async def render(self, tierlist: Tierlist) -> BytesIO:
        avatar_images = {}
        async with aiohttp.ClientSession() as session:
            tasks = []
            for tier_data in tierlist.tiers.values():
                for uid, member in tier_data.items():
                    tasks.append(self._download(session, uid, member.avatar_url))
            
            results = await asyncio.gather(*tasks)
            for uid, data in results:
                if data: avatar_images[uid] = data

        return await asyncio.to_thread(self._draw, tierlist, avatar_images)
        
    async def _download(self, session, user_id: int, url):
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    return user_id, BytesIO(data)
        except:
            pass
            
        return user_id, None
        
    def _draw(self, tierlist: Tierlist, avatar_images: Dict[int, BytesIO]) -> BytesIO:
        tier_heights = {}
        total_canvas_height = 0
        
        for tier, members in tierlist.tiers.items():
            h = self._calc_tier_height(len(members))
            tier_heights[tier] = h
            total_canvas_height += h
            
        canvas = Image.new("RGB", (self.total_width, total_canvas_height), (30, 30, 30))
        draw = ImageDraw.Draw(canvas)
        
        current_y = 0
        for tier, members in tierlist.tiers.items():
            row_h = tier_heights[tier]
            
            # left label box
            draw.rectangle(
                [(0, current_y), (self.label_width, current_y + row_h)],
                fill=self.tier_colors.get(tier.name, (100, 100, 100)),
                outline=(0,0,0)
            )
            
            # left label text
            draw.text(
                (self.label_width / 2, current_y + row_h / 2),
                tier.name,
                fill=(0,0,0),
                font=self.font_label,
                anchor="mm"
            )
            
            # right side
            unit_width = self.avatar_size + self.padding
            unit_height = self.avatar_size + self.text_height + self.padding
            avatars_per_row = self.content_width // unit_width
            if avatars_per_row < 1: 
                avatars_per_row = 1
                
            start_x = self.label_width + self.padding
            start_y = current_y + self.padding
            
            for index, (user_id, member) in enumerate(members.items()):
                if user_id in avatar_images:
                    col = index % avatars_per_row
                    row = index // avatars_per_row
                    
                    x_pos = start_x + (col * unit_width)
                    y_pos = start_y + (row * unit_height)
                    
                    try:
                        img = Image.open(avatar_images[user_id]).convert("RGBA")
                        img = img.resize((self.avatar_size, self.avatar_size))
                        canvas.paste(img, (x_pos, y_pos), img)
                    except Exception as e:
                        print(f"Error pasting avatar: {e}")
                        
                    display_name = member.name
                    if len(display_name) > 10:
                        display_name = display_name[:9] + ".."
                        
                    draw.text(
                        (x_pos + (self.avatar_size / 2), y_pos + self.avatar_size + 2),
                        display_name,
                        fill=(200, 200, 200),
                        font=self.font_name,
                        anchor="mt"
                    )
                 
            # separator
            draw.line(
                [(0, current_y + row_h), (self.total_width, current_y + row_h)], 
                fill=(0,0,0), 
                width=2
            )
            current_y += row_h
            
        output = BytesIO()
        canvas.save(output, format='PNG')
        output.seek(0)
        return output

# Configuring bot connection

load_dotenv()
token = os.getenv('TOKEN')

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

class Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="$", intents=intents)
        
    async def setup_hook(self):    
        await self.tree.sync()
    
bot = Bot()
manager = TierlistManager()
renderer = TierlistRenderer()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.tree.command(name="hello", description="Says hello (privately)")
async def hello(interaction: discord.Interaction):
    await interaction.response.send_message("Hello!", ephemeral=True)

@bot.tree.command(name="begin", description="Start a new tierlist")
async def begin(interaction: discord.Interaction, name: str):
    result = manager.begin_tierlist(name)
    await interaction.response.send_message(f"Result: {result.name}", ephemeral=True)

@bot.tree.command(name="end", description="End the current tierlist")
async def end(interaction: discord.Interaction):
    result = manager.end_tierlist()
    await interaction.response.send_message(f"Result: {result.name}", ephemeral=True)

@bot.tree.command(name="add", description="Add a member to a specific tier")
@app_commands.choices(tier=[
    app_commands.Choice(name="S Tier", value="S"),
    app_commands.Choice(name="A Tier", value="A"),
    app_commands.Choice(name="B Tier", value="B"),
    app_commands.Choice(name="C Tier", value="C"),
    app_commands.Choice(name="D Tier", value="D"),
    app_commands.Choice(name="F Tier", value="F"),
])
async def add(interaction: discord.Interaction, member: discord.Member, tier: app_commands.Choice[str]):
    try:
        target_tier = Tier[tier.value]
    except KeyError:
        await interaction.response.send_message("Invalid Tier.", ephemeral=True)
        return

    user_data = Member(name=member.display_name, avatar_url=member.display_avatar.url)
    result = manager.add_to_tierlist(member.id, user_data, target_tier)
    
    if result == TierlistError.SUCCESS:
        await interaction.response.send_message(f"Added {member.display_name} to Tier {target_tier.name}", ephemeral=True)
    else:
        await interaction.response.send_message(f"Error: {result.name}", ephemeral=True)

@bot.tree.command(name="remove", description="Remove a member from the tierlist")
async def remove(interaction: discord.Interaction, member: discord.Member):
    result = manager.remove_from_tierlist(member.id)
    await interaction.response.send_message(f"Result: {result.name}", ephemeral=True)

@bot.tree.command(name="show", description="Render the current tierlist image")
async def show(interaction: discord.Interaction):
    if not manager.currently_active:
        await interaction.response.send_message("No active tierlist.", ephemeral=True)
        return
        
    await interaction.response.defer(thinking=True, ephemeral=True)

    active_list = manager.tierlists[manager.currently_active]
    image_buffer = await renderer.render(active_list)
    
    file = discord.File(image_buffer, filename="tierlist.png")
    await interaction.followup.send(file=file, ephemeral=True)

if token:
    bot.run(token)
