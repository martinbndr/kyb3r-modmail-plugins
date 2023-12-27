from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional, Union
import os

import discord
from discord.ext import commands, tasks
from discord import utils
import aiocron
import croniter
import pytz

from core import checks
from core.models import PermissionLevel, DMDisabled, getLogger
from core.time import UserFriendlyTime
from core.paginator import EmbedPaginatorSession, MessagePaginatorSession

logger = getLogger(__name__)

class SupportTimes(commands.Cog):
    """
    Support-Times Plugin

    With this plugin you can set certain times where modmail should be enabled/disabled automatically.
    Practical for regular support times / business hours.
    """
    def __init__(self, bot):
        self.bot = bot
        self.db = self.bot.plugin_db.get_partition(self)
        self.config = None
        self.default_config = {"mode": 1, "enable_schedules": [], "disable_schedules": [], "timezone": None, "log_actions": False}
        self.schedules_loaded = False
        self.enable_schedules = []
        self.disable_schedules = []
        
    async def cog_load(self):
        self.config = await self.db.find_one({"_id": "support-times"})
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
        await self.load_schedules_startup()
    
    async def cog_unload(self):
        for i in self.enable_schedules:
            i.stop()
        for i in self.disable_schedules:
            i.stop()

    async def update_config(self):
        await self.db.find_one_and_update(
            {"_id": "support-times"},
            {"$set": self.config},
            upsert=True,
        )

    async def load_schedules_startup(self):
        await self.bot.wait_until_ready()
        if self.schedules_loaded is False:
            schedule_timezone = None if self.config['timezone'] is None else pytz.timezone(self.config['timezone'])
            if not len(self.config["enable_schedules"]) == 0:
                for i in self.config["enable_schedules"]:
                    enable_scheduler = aiocron.crontab(i, func=self.enable_modmail, tz=schedule_timezone, start=True)
                    self.enable_schedules.append(enable_scheduler)
            if not len(self.config["disable_schedules"]) == 0:
                for i in self.config["disable_schedules"]:
                    disable_scheduler = aiocron.crontab(i, func=self.disable_modmail, tz=schedule_timezone, start=True)
                    self.disable_schedules.append(disable_scheduler)
            self.schedules_loaded = True

    def format_schedules(self, enable: list, disable: list):
        enabled_list = ["No schedules added"]
        disabled_list = ["No schedules added"]
        if not len(enable) == 0:
            enabled_list.clear()
            idx = 0
            for i in enable:
                idx += 1
                enabled_list.append(f'{idx}: ``{i}``')
        if not len(disable) == 0:
            disabled_list.clear()
            idx = 0
            for i in disable:
                idx += 1
                disabled_list.append(f'{idx}: ``{i}``')
        enable_str = "\n".join(enabled_list)
        disable_str = "\n".join(disabled_list)
        return enable_str, disable_str
    
    async def update_schedules(self):
        for i in self.enable_schedules:
            i.stop()
        for i in self.disable_schedules:
            i.stop()
        self.enable_schedules.clear()
        self.disable_schedules.clear()
        schedule_timezone = None if self.config['timezone'] is None else pytz.timezone(self.config['timezone'])
        if not len(self.config["enable_schedules"]) == 0:
            for i in self.config["enable_schedules"]:
                enable_scheduler = aiocron.crontab(i, func=self.enable_modmail, tz=schedule_timezone, start=True)
                self.enable_schedules.append(enable_scheduler)
        if not len(self.config["disable_schedules"]) == 0:
            for i in self.config["disable_schedules"]:
                disable_scheduler = aiocron.crontab(i, func=self.disable_modmail, tz=schedule_timezone, start=True)
                self.disable_schedules.append(disable_scheduler)


    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @commands.group(name='support-times', invoke_without_command=True)
    async def support_times(self, ctx: commands.Context):
        """
        Support-Times Plugin - Schedule enabling/disabling Modmail

        What is this?
        With this plugin you can set certain times where modmail should be enabled/disabled.
        It can be manually done with ``{prefix}disable / {prefix}enable``. 
        This plugin does that automatically for you. Practical for regular support times / business hours.

        How does the plugin work?
        The plugin is based on cron jobs to handle enabling/disabling at certain times.

        Resources:
        [Learn more about Cron Jobs](https://de.wikipedia.org/wiki/Cron)
        [Cronjob Examples](https://crontab.guru/examples.html)
        """
        await ctx.send_help(ctx.command)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @support_times.command(name='show', aliases=['config','settings'])
    async def support_times_show(self, ctx: commands.Context):
        """
        Shows current plugin configuration.
        """
        disable_mode = "new threads" if self.config['mode'] == 1 else "all threads"
        configured_timezone = "None (uses default system time)" if self.config['timezone'] is None else self.config['timezone']
        log_actions = "enabled" if self.config['log_actions'] is True else "disabled"
        enable_schedules = self.config['enable_schedules']
        disable_schedules = self.config['disable_schedules']

        embed = discord.Embed(
            title='Support-Times - Current Settings',
            description=f'''
            Disable Mode: ``{disable_mode}``
            Timezone: ``{configured_timezone}``   
            Log: ``{log_actions}``    
            ''',
            color=self.bot.main_color
        )
        schedules = self.format_schedules(enable_schedules, disable_schedules)
        embed2 = discord.Embed(description=f'Modmail enable schedules:\n{schedules[0]}\n\nModmail disable schedules:\n{schedules[1]}', color=self.bot.main_color)

        await ctx.send(embeds=[embed, embed2])

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @support_times.command(name='scheduleadd', aliases=['addschedule', 'add'])
    async def support_times_scheduleadd(self, ctx: commands.Context, mode: str = None, *, cron: str = None):
        """
        Adds a schedule for automatic enabeling/disabling modmail.

        This is the important part of the plugin.
        With this command you configure when modmail is going be disabled or enabled automatically.

        Modes:
        enable - Adds a schedule for automatically enabeling modmail
        disable - Adds a schedule for automatically disabling modmail

        Examples:
        ``{prefix}support-times scheduleadd disable 0 22 * * *`` (disables every day at 10pm)
        ``{prefix}support-times scheduleadd enable 0 8 * * *`` (enables every day at 8am)
        ``{prefix}support-times scheduleadd disable 0 23 * * 1-5`` (disables from Monday-Friday at 11pm)
        ``{prefix}support-times scheduleadd enable 0 9 * * 1-5`` (enables from Monday-Friday at 9am)

        [Cronjob Examples](https://crontab.guru/examples.html)
        """
        enable_schedules = self.config['enable_schedules']
        disable_schedules = self.config['disable_schedules']
        if mode is None or cron is None:
            return await ctx.send_help(ctx.command)
        mode_str = mode.lower()
        if not mode_str in ['disable', 'enable']:
            embed = discord.Embed(description=f'The Mode needs to be ``disable`` or ``enable``.', color=self.bot.error_color)
            return await ctx.send(embed=embed)
        valid_cron = croniter.croniter.is_valid(cron)
        if not valid_cron:
            embed = discord.Embed(description=f'The cron job you provided, is invalid.', color=self.bot.error_color)
            view = discord.ui.View().add_item(discord.ui.Button(style=discord.ButtonStyle.link, label='Cronjob Examples', url='https://crontab.guru/examples.html'))
            return await ctx.send(embed=embed, view=view)
        if cron in enable_schedules or cron in disable_schedules:
            embed = discord.Embed(description=f'You already have this cronjob added to either enabling or disabling schedules.', color=self.bot.error_color)
            return await ctx.send(embed=embed)
        if mode_str == "disable":
            self.config['disable_schedules'].append(cron)
        else:
            self.config['enable_schedules'].append(cron)
        await self.update_config()
        await self.update_schedules()
        logger.info('Schedule %s has been added.', cron)
        embed = discord.Embed(description=f'Successfully added schedule ``{cron}``!\nIf this schedule will run it is going to **{mode_str}** modmail.', color=discord.Color.green())
        embed.add_field(name='Good to know', value=f'If the added schedule won´t **{mode_str}** modmail or it will run at a wrong time, set your timezone.')
        return await ctx.send(embed=embed)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @support_times.command(name='scheduleremove', aliases=['removeschedule', 'remove'])
    async def support_times_scheduleremove(self, ctx: commands.Context, *, cron: str = None):
        """
        Removes a schedule.

        The current added schedules can be viewed with the command ``{prefix}support-times show``.

        Examples:
        ``{prefix}support-times scheduleremove 0 22 * * *``
        """
        enable_schedules = self.config['enable_schedules']
        disable_schedules = self.config['disable_schedules']
        if cron is None:
            return await ctx.send_help(ctx.command)
        if not cron in enable_schedules and not cron in disable_schedules:
            embed = discord.Embed(description=f'The cron job does not exist.', color=self.bot.error_color)
            return await ctx.send(embed=embed)
        
        if cron in enable_schedules:
            self.config['enable_schedules'].remove(cron)
        else:
            self.config['disable_schedules'].remove(cron)
        await self.update_config()
        await self.update_schedules()
        logger.info('Schedule %s has been removed.', cron)
        embed = discord.Embed(description=f'Successfully removed schedule ``{cron}``!', color=discord.Color.green())
        return await ctx.send(embed=embed)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @support_times.command(name='mode')
    async def support_times_mode(self, ctx: commands.Context, mode: str = None):
        """
        Sets disabled mode (disable all or only new threads)

        If the bot executes disabling Modmail automatically based on your schedules, it can either disable all threads or only new threads.
        Same way like ``{prefix}disable`` command just automatically.

        Default:
        New Threads

        Examples:
        ``{prefix}support-times mode all``
        ``{prefix}support-times mode new``
        """
        if mode is None:
            return await ctx.send_help(ctx.command)
        mode_input = mode.lower()
        if not mode_input in ['new', 'all']:
            embed = discord.Embed(description='Invalid mode. It needs to be either ``new`` or ``all``.', color=self.bot.error_color)
            return await ctx.send(embed=embed)
        new_mode = DMDisabled.NEW_THREADS if mode_input == "new" else DMDisabled.ALL_THREADS
        self.config['mode'] = new_mode
        await self.update_config()
        logger.info('Mode has been set to %s.', new_mode)
        embed = discord.Embed(description=f'Automatic disabling schedules will disable **{("new threads" if new_mode == 1 else "all threads")}**.', color=discord.Color.green())
        return await ctx.send(embed=embed)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @support_times.command(name='timezone', aliases=['tz'])
    async def support_times_timezone(self, ctx: commands.Context, timezone: str = None):
        """
        Sets timezone for schedules (optional).

        You can optionally set a different timezone if needed.
        Useful if the host system is in a different location than your discord community.

        Default:
        None (uses default system time)

        Examples:
        `{prefix}support-times timezone Europe/Berlin`
        `{prefix}support-times timezone America/New_York`
        `{prefix}support-times timezone none` - Uses default system time

        Resources:
        [Timezone List](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones#Time_Zone_abbreviations)
        (The "TZ identifier" column needs to be used for this command)
        """
        if timezone is None:
            return await ctx.send_help(ctx.command)
        timezone_input = timezone.lower()
        if timezone_input == 'none':
            self.config['timezone'] = None
            await self.update_config()
            await self.update_schedules()
            logger.info('Timezone has been set to default system time.')
            embed = discord.Embed(description='The timezone has been set to default. It now uses the default system time.', color=discord.Color.green())
            return await ctx.send(embed=embed)

        try:
            pytz_timezone = pytz.timezone(timezone_input)
        except pytz.exceptions.UnknownTimeZoneError:
            embed = discord.Embed(description='The timezone you provided is invalid.', color=self.bot.error_color)
            return await ctx.send(embed=embed)
        self.config['timezone'] = str(pytz_timezone)
        await self.update_config()
        await self.update_schedules()
        logger.info('Timezone has been to %s.', self.config["timezone"])
        embed = discord.Embed(description=f'The timezone has been set to ``{self.config["timezone"]}``.', color=discord.Color.green())
        return await ctx.send(embed=embed)
    
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @support_times.command(name='log', aliases=['log_channel'])
    async def support_times_log(self, ctx: commands.Context, mode: bool = None):
        """
        Toggles logging (optional).

        You can optionally toggle logging for schedules.
        If enabled, the bot will log enabling/disabling Modmail in the modmail log.
        The log channel can be set with `{prefix}config set log_channel_id`.

        Default:
        False (disabled)

        Examples:
        `{prefix}support-times log True`
        `{prefix}support-times log False`
        """
        if mode is None:
            return await ctx.send_help(ctx.command)
        self.config['log_actions'] = mode
        await self.update_config()
        logger.info('Timezone has been set %s.', mode)
        embed = discord.Embed(description=f'The logging has been **{("enabled" if mode else "disabled")}**.', color=discord.Color.green())
        if mode is True and self.bot.config["log_channel_id"] is None:
            embed.description += f'\nMake sure to set the config option ``log_channel_id``.'
        return await ctx.send(embed=embed)

    async def enable_modmail(self):
        await self.bot.wait_until_ready()
        if self.bot.config["dm_disabled"] != DMDisabled.NONE:
            self.bot.config["dm_disabled"] = DMDisabled.NONE
            await self.bot.config.update()
            logger.info('Modmail has been automatically enabled.')
            if self.bot.config["log_channel_id"] is not None:
                log_channel = self.bot.get_channel(int(self.bot.config["log_channel_id"]))
                if log_channel:
                    embed = discord.Embed(title='Modmail is now enabled!', description=f'Modmail has been automatically enabled.', timestamp=discord.utils.utcnow(), color=self.bot.main_color)
                    embed.set_footer(text='Support-Times Plugin')
                    await log_channel.send(embed=embed)

    async def disable_modmail(self):
        await self.bot.wait_until_ready()
        close_mode = DMDisabled.NEW_THREADS if self.config['mode'] == 1 else DMDisabled.ALL_THREADS
        if self.bot.config["dm_disabled"] != close_mode:
            self.bot.config["dm_disabled"] = close_mode
            await self.bot.config.update()
            logger.info('Modmail has been automatically disabled.')
            if self.bot.config["log_channel_id"] is not None:
                log_channel = self.bot.get_channel(int(self.bot.config["log_channel_id"]))
                if log_channel:
                    embed = discord.Embed(title='Modmail is now disabled!', description=f'Modmail has been automatically disabled.', timestamp=discord.utils.utcnow(), color=self.bot.error_color)
                    embed.set_footer(text='Support-Times Plugin')
                    await log_channel.send(embed=embed)

async def setup(bot):
    await bot.add_cog(SupportTimes(bot))