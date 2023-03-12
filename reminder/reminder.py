from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional, Union
import os

import discord
from discord.ext import commands, tasks
from discord import utils
import pytz

from core import checks
from core.models import PermissionLevel
from core.time import UserFriendlyTime
from core.paginator import EmbedPaginatorSession, MessagePaginatorSession


class Reminder(commands.Cog):
    """Reminder Plugin"""
    def __init__(self, bot):
        self.bot = bot
        self.db = self.bot.plugin_db.get_partition(self)
        self.config = None
        self.default_config = {}
        
    async def cog_load(self):
        self.config = await self.db.find_one({"_id": "reminder"})
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
        self.reminder_task.start()
    
    async def cog_unload(self):
        self.reminder_task.stop()

    async def update_config(self):
        await self.db.find_one_and_update(
            {"_id": "reminder"},
            {"$set": self.config},
            upsert=True,
        )
        
    async def get_insert_userdata(self, ctx: commands.Context):
        current_userdata = self.config.get(str(ctx.author.id), None)
        userdata = {}
        if not current_userdata:
            reminder_id = 1
            userdata["reminder_id"] = reminder_id
            userdata["reminders"] = {}
            self.config[str(ctx.author.id)] = userdata
            await self.update_config()
            return reminder_id
        else:
            new_reminder_id = current_userdata["reminder_id"] + 1
            self.config[str(ctx.author.id)]["reminder_id"] = new_reminder_id
            await self.update_config()
            return new_reminder_id

    @checks.has_permissions(PermissionLevel.REGULAR)
    @commands.command(name='remind', aliases=['remindme'])
    async def remind(self, ctx: commands.Context, duration: str, channel: Optional[Union[discord.TextChannel, discord.VoiceChannel, discord.Thread, discord.ForumChannel]] = None, *, text: str):
        """Create a reminder"""
        channel_option = None
        notify_txt = "Direct Message"
        if channel:
            channel_option = channel.id
            notify_txt = f"<#{channel.id}>"
        timeconverter = UserFriendlyTime()
        dt = await timeconverter.convert(ctx=ctx, argument=duration, now=datetime.now())
        reminder_id = await self.get_insert_userdata(ctx)
        
        reminder_data = {"end": dt.dt, "channel_id": channel_option, "text": text}
        self.config[str(ctx.author.id)]["reminders"][str(reminder_id)] = reminder_data
        await self.update_config()
        timestamp = utils.format_dt(dt.dt, 'F')
        embed = discord.Embed(title='Reminder created', description=f'Your reminder has been created successfully!\nReminding at: {timestamp}\nReminding in: {notify_txt}', color=discord.Color.green())
        embed.set_footer(text=f'Reminder ID: {reminder_id}')
        await ctx.send(embed=embed)
    
    @checks.has_permissions(PermissionLevel.REGULAR)
    @commands.command(name='delreminder', aliases=['forgetreminder'])
    async def delreminder(self, ctx: commands.Context, reminder_id: int):
        """Delete a reminder"""
        current_userdata = self.config.get(str(ctx.author.id), None)
        userdata = {}
        if not current_userdata:
            reminder_id = 0
            userdata["reminder_id"] = reminder_id
            userdata["reminders"] = {}
            self.config[str(ctx.author.id)] = userdata
            await self.update_config()
        current_userdata = self.config.get(str(ctx.author.id), None)
        reminder_data = current_userdata["reminders"]
        to_delete_reminder = reminder_data.get(str(reminder_id), None)
        if not to_delete_reminder:
            embed = discord.Embed(title='Reminder not found', description=f'A reminder with the given ID ``{reminder_id}`` was not found.', color=self.bot.error_color)
            return await ctx.send(embed=embed)
        else:
            reminder_data.pop(str(reminder_id), None)
            await self.update_config()
            embed = discord.Embed(title='Reminder deleted', description=f'Your reminder ``{reminder_id}`` has been deleted successfully!', color=discord.Color.green())
            await ctx.send(embed=embed)
            
    @checks.has_permissions(PermissionLevel.REGULAR)
    @commands.command(name='reminders', aliases=['listreminders','lreminders'])
    async def reminders(self, ctx: commands.Context):
        """List your reminders"""
        current_userdata = self.config.get(str(ctx.author.id), None)
        userdata = {}
        if not current_userdata:
            reminder_id = 0
            userdata["reminder_id"] = reminder_id
            userdata["reminders"] = {}
            self.config[str(ctx.author.id)] = userdata
            await self.update_config()
        current_userdata = self.config.get(str(ctx.author.id), None)
        reminder_data = current_userdata["reminders"]
        if len(reminder_data.keys()) == 0:
            embed = discord.Embed(title='No reminders found', description=f'You do not have any active reminders!', color=self.bot.error_color)
            return await ctx.send(embed=embed)
        else:
            embeds = []
            for key, value in reminder_data.items():
                reminder_id = key
                remind_location = "Direct Message"
                if not value["channel_id"] == None:
                    remind_location = f'<#{value["channel_id"]}>'
                timestamp = utils.format_dt(value["end"], "F")
                embed = discord.Embed(title='Your Reminders', description=f'ID: ``{reminder_id}``\nReminding at: {timestamp}\nReminding in: {remind_location}\nReminder Text: {value["text"]}', color=self.bot.main_color)
                embeds.append(embed)
            session = EmbedPaginatorSession(ctx, *embeds)
            await session.run()
                
            
        
        
        
            
            
    @tasks.loop(seconds=10)
    async def reminder_task(self):
        await self.bot.wait_until_ready()
        for key, value in self.config.items():
            if key == '_id':
                continue
            user_id = str(key)
            user_reminders = value['reminders'].copy()
            for k, v in user_reminders.items():
                now = datetime.now()
                reminder_id = str(k)
                reminder_text = v["text"]
                if now >= v['end']:
                    new_conf = self.config.copy()
                    new_conf[user_id]["reminders"].pop(reminder_id, None)
                    self.config = new_conf
                    await self.update_config()
                    if v["channel_id"] == None:
                        try:
                            user = await self.bot.fetch_user(int(user_id))
                            if user:
                                embed = discord.Embed(title=f'Reminder', description=f'{reminder_text}', color=self.bot.main_color)
                                await user.send(embed=embed)
                        except Exception as e:
                            continue
                    else:
                        channel = self.bot.get_channel(int(v["channel_id"]))
                        if channel:
                            embed = discord.Embed(title=f'Reminder', description=f'{reminder_text}', color=self.bot.main_color)
                            await channel.send(content=f'<@{user_id}>', embed=embed)

async def setup(bot):
    await bot.add_cog(Reminder(bot))