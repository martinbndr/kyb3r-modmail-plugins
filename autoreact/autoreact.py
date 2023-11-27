from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional, Union
import os

import discord
from discord.ext import commands, tasks
from discord import utils

from core import checks
from core.models import PermissionLevel, getLogger
from core.time import UserFriendlyTime
from core.paginator import EmbedPaginatorSession, MessagePaginatorSession

logger = getLogger(__name__)

class Autoreact(commands.Cog):
    """
    Automatically reacts with emojis in certain channels.

    You can use this feature in multiple channels with max 20 reactions, but keep in mind of discord ratelimits.\nThe bot could get limited/blocked for spam, specially if these channels are very active.
    """
    def __init__(self, bot):
        self.bot = bot
        self.db = self.bot.plugin_db.get_partition(self)
        self.config = None
        self.default_config = {}
        
    async def cog_load(self):
        self.config = await self.db.find_one({"_id": "autoreact"})
        if self.config is None:
            self.config = self.default_config
            await self.update_config()
        missing = []
        for key in self.default_config.keys():
            if key not in self.config:
                missing.append(key)
        if missing:
            for key in missing:
                self.config[key] = self.default_config[key]
        await self.update_config()

    async def update_config(self):
        await self.db.find_one_and_update(
            {"_id": "autoreact"},
            {"$set": self.config},
            upsert=True,
        )


    @commands.command(name='startreact')
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def startreact(self, ctx: commands.Context, *emojis):
        """
        Enables Autoreact in the current channel.

        **Usage:**
        {prefix}startreact 👀
        {prefix}startreact 🍰 😋
        """
        if not emojis:
            return await ctx.send_help(ctx.command)
        channel_config = self.config.get(str(ctx.channel.id))
        if channel_config:
            embed = discord.Embed(title='Channel already activated', description='Channel already activated. Use ``?stopreact`` first.', color=self.bot.error_color)
            return await ctx.send(embed=embed)
        emojis_to_react = [i for i in emojis]
        if len(emojis_to_react) > 20:
            embed = discord.Embed(title='Reactions limited', description='Discord has a limit of 20 reactions per message.', color=self.bot.error_color)
            return await ctx.send(embed=embed)
        self.config[str(ctx.channel.id)] = {
            "emojis": emojis_to_react
        }
        await self.update_config()
        react_str = ', '.join(emojis_to_react)
        embed = discord.Embed(title='Channel activated', description=f'The bot will autoreact in this channel with the following emojis:\n{react_str}', color=discord.Color.green())
        return await ctx.send(embed=embed)
    
    @commands.command(name='stopreact')
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def stopreact(self, ctx: commands.Context):
        """
        Disables Autoreact in the current channel.
        """
        channel_config = self.config.get(str(ctx.channel.id))
        if not channel_config:
            embed = discord.Embed(title='Channel not activated', description='This channel is not activated yet.', color=self.bot.error_color)
            return await ctx.send(embed=embed)
        self.config.pop(str(ctx.channel.id), None)
        await self.db.find_one_and_update(
            {"_id": "autoreact"},
            {"$unset": {str(ctx.channel.id):None}}
        )
        embed = discord.Embed(title='Channel deactivated', description=f'The bot will no longer autoreact in this channel.', color=discord.Color.green())
        return await ctx.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        await self.bot.wait_until_ready()
        channel_config = self.config.get(str(message.channel.id))
        if channel_config:
            emojis = channel_config['emojis']
            for e in emojis:
                try:
                    await message.add_reaction(e)
                except Exception:
                    logger.exception('Error running autoreact', exc_info=True)

async def setup(bot):
    await bot.add_cog(Autoreact(bot))