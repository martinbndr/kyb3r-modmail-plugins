from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional, Union
import os
from contextlib import suppress

import asyncio
import discord
from discord.ext import commands, tasks
from discord import utils

from core import checks
from core.models import PermissionLevel, getLogger
from core.paginator import EmbedPaginatorSession, MessagePaginatorSession

logger = getLogger(__name__)

class Sticky(commands.Cog):
    """
    Sticky - Manage Sticky Messages
    """
    def __init__(self, bot):
        self.bot = bot
        self.db = self.bot.plugin_db.get_partition(self)
        self.config = None
        self.default_config = {}
        self.default_channel_config = {"message": "Sticky message", "stopped": False, "color": str(discord.Color.blurple().value)}
        self.sticked_messages = {}
        self.delay = 5
        self.locked_channels = set()

    async def cog_load(self):
        self.config = await self.db.find_one({"_id": "sticky"})
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
        channel_ids = []
        for k, v in self.config.items():
            channel_ids = []
            if not k == "_id":
                channel_ids.append(k)
        if channel_ids:
            for c in channel_ids:
                missing_default_channel_keys = []
                channel_config = self.config[c]
                for default_channel_conf_key in self.default_channel_config.keys():
                    if default_channel_conf_key not in channel_config:
                        missing_default_channel_keys.append(default_channel_conf_key)
                if missing_default_channel_keys:
                    for missing_key in missing_default_channel_keys:
                        channel_config[missing_key] = self.default_channel_config[missing_key]
                self.config[c] = channel_config
        await self.update_config()



    async def update_config(self):
        await self.db.find_one_and_update(
            {"_id": "sticky"},
            {"$set": self.config},
            upsert=True,
        )


    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @commands.command(name='stick')
    async def stick(self, ctx: commands.Context, channel: Union[discord.TextChannel, discord.VoiceChannel, discord.Thread], *, message: str):
        """
        Adds a sticky message to a channel.
        """
        if self.config.get(str(channel.id), None):
            embed = discord.Embed(description=f'This channel already has a sticked message.\nUse ``{self.bot.prefix}unsticky`` first to remove it.', color=self.bot.error_color)
            return await ctx.send(embed=embed)
        perms = channel.permissions_for(ctx.guild.me)
        needed_perms = [perms.send_messages, perms.embed_links]
        if not all(needed_perms):
            embed = discord.Embed(description=f'The bot is missing permissions in channel {channel.mention}.\nNeeded Permissions: Send_Messages, Embed_Links', color=self.bot.error_color)
            return await ctx.send(embed=embed)
        sticky_channel_data = {}
        sticky_channel_data['message'] = str(message)
        sticky_channel_data['stopped'] = False
        sticky_channel_data['color'] = str(discord.Color.blurple().value)

        embed = discord.Embed(description=sticky_channel_data['message'], color=discord.Color.blurple())
        msg = await channel.send(embed=embed)

        sticky_channel_data['last_message_id'] = str(msg.id)
        self.sticked_messages[str(channel.id)] = msg
        self.config[str(channel.id)] = sticky_channel_data
        await self.update_config()
        logger.info('Sticky Message added by %s to channel %s (%s)', ctx.author, channel.name, channel.id)
        embed = discord.Embed(description=f'Sticky message enabled in {channel.mention}.', color=discord.Color.green())
        await ctx.send(embed=embed)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @commands.command(name='stickremove')
    async def stickremove(self, ctx: commands.Context, channel: Union[discord.TextChannel, discord.VoiceChannel, discord.Thread]):
        """
        Removes a sticky message from a channel.
        """
        current_channel_settings = self.config.get(str(channel.id), None)
        if not current_channel_settings:
            embed = discord.Embed(description=f'This channel has no sticky message enabled.', color=self.bot.error_color)
            return await ctx.send(embed=embed)
        self.config.pop(str(channel.id), None)
        self.sticked_messages.pop(str(channel.id), None)
        await self.db.find_one_and_update(
            {"_id": "sticky"},
            {"$unset": {str(channel.id):current_channel_settings}}
        )
        logger.info('Sticky Message removed from %s (%s) by %s', channel.name, channel.id, ctx.author)
        embed = discord.Embed(description=f'Sticky message removed from {channel}.', color=discord.Color.green())
        await ctx.send(embed=embed)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @commands.command(name='stickstop')
    async def stickstop(self, ctx: commands.Context, channel: Union[discord.TextChannel, discord.VoiceChannel, discord.Thread]):
        """
        Pauses an active sticky channel.
        """
        if not self.config.get(str(channel.id), None):
            embed = discord.Embed(description=f'This channel has no sticky message enabled.', color=self.bot.error_color)
            return await ctx.send(embed=embed)
        self.config[str(channel.id)]['stopped'] = True
        await self.update_config()
        embed = discord.Embed(description=f'Sticky message paused in {channel}.', color=discord.Color.green())
        await ctx.send(embed=embed)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @commands.command(name='stickstart')
    async def stickstart(self, ctx: commands.Context, channel: Union[discord.TextChannel, discord.VoiceChannel, discord.Thread]):
        """
        Pauses an active sticky channel.
        """
        if not self.config.get(str(channel.id), None):
            embed = discord.Embed(description=f'This channel has no sticky message enabled.', color=self.bot.error_color)
            return await ctx.send(embed=embed)
        self.config[str(channel.id)]['stopped'] = False
        await self.update_config()
        embed = discord.Embed(description=f'Sticky message started in {channel}.', color=discord.Color.green())
        await ctx.send(embed=embed)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @commands.command(name='stickcolor')
    async def stickcolor(self, ctx: commands.Context, channel: Union[discord.TextChannel, discord.VoiceChannel, discord.Thread], *, color: discord.Color):
        """
        Changes the embed color of the sticky embed.
        """
        if not self.config.get(str(channel.id), None):
            embed = discord.Embed(description=f'This channel has no sticky message enabled.', color=self.bot.error_color)
            return await ctx.send(embed=embed)
        self.config[str(channel.id)]['color'] = str(color.value)
        await self.update_config()
        embed = discord.Embed(description=f'Sticky message embed color changed in {channel.mention}.', color=discord.Color.green())
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if isinstance(message.channel, discord.DMChannel) or message.author.bot or message.content.startswith(self.bot.prefix):
            return
        await self.bot.wait_until_ready()
        channel_id = message.channel.id
        channel_conf = self.config.get(str(channel_id), None)
        if not channel_conf or channel_id in self.locked_channels or channel_conf['stopped'] is True:
            return
        self.locked_channels.add(channel_id)
        last_sticked_msg = None
        if self.sticked_messages.get(str(channel_id), None):
            last_sticked_msg = self.sticked_messages[str(channel_id)]
        else:
            with suppress(discord.NotFound):
                r = await message.channel.fetch_message(int(channel_conf['last_message_id']))
                if r:
                    last_sticked_msg = r
        if last_sticked_msg:
            await asyncio.sleep(self.delay)
            with suppress(discord.NotFound):
                await last_sticked_msg.delete()

        
        embed = discord.Embed(description=channel_conf['message'], color=discord.Color(int(channel_conf['color'])))
        new_msg = await message.channel.send(embed=embed)
        self.config[str(channel_id)]['last_message_id'] = str(new_msg.id)
        await self.update_config()
        self.sticked_messages[str(channel_id)] = new_msg
        with suppress(KeyError):
            self.locked_channels.remove(channel_id)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        await self.bot.wait_until_ready()
        channel_conf = self.config.get(str(payload.channel_id), None)
        if channel_conf:
            if payload.message_id == int(channel_conf['last_message_id']):
                if channel_conf['stopped'] is True:
                    return
                if payload.channel_id in self.locked_channels:
                    return
                self.locked_channels.add(payload.channel_id)
                channel = self.bot.get_channel(payload.channel_id)
                await asyncio.sleep(self.delay)
                embed = discord.Embed(description=channel_conf['message'], color=discord.Color(int(channel_conf['color'])))
                new_msg = await channel.send(embed=embed)
                self.config[str(payload.channel_id)]['last_message_id'] = str(new_msg.id)
                await self.update_config()
                self.sticked_messages[str(payload.channel_id)] = new_msg
                with suppress(KeyError):
                    self.locked_channels.remove(payload.channel_id)

        



async def setup(bot):
    await bot.add_cog(Sticky(bot))