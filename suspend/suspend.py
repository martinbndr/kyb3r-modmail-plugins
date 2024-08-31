from typing import Union, Optional, Any, Literal

import discord
from discord.ext import commands

from core import checks
from core.time import UserFriendlyTime
from cogs.utility import PermissionLevel, ModmailHelpCommand

from bot import ModmailBot

class Suspend(commands.Cog):
    """
    Can suspend a thread by closing it normally without deleting the channel.
    """
    def __init__(self, bot: ModmailBot):
        self.bot = bot

    @commands.command(name='suspend', usage="[after] [close message]")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def suspend(
        self,
        ctx,
        option: Optional[Literal["silent", "silently", "cancel"]] = "",
        *,
        after: UserFriendlyTime = None,
    ):
        """
        Suspend the current thread without deleting the channel.

        Close after a period of time:
        - `{prefix}close in 5 hours`
        - `{prefix}close 2m30s`

        Custom close messages:
        - `{prefix}close 2 hours The issue has been resolved.`
        - `{prefix}close We will contact you once we find out more.`

        Silently close a thread (no message)
        - `{prefix}close silently`
        - `{prefix}close silently in 10m`

        Stop a thread from closing:
        - `{prefix}close cancel`
        """

        thread = ctx.thread

        close_after = (after.dt - after.now).total_seconds() if after else 0
        silent = any(x == option for x in {"silent", "silently"})
        cancel = option == "cancel"

        if cancel:
            if thread.close_task is not None or thread.auto_close_task is not None:
                await thread.cancel_closure(all=True)
                embed = discord.Embed(
                    color=self.bot.error_color, description="Scheduled close has been cancelled."
                )
            else:
                embed = discord.Embed(
                    color=self.bot.error_color,
                    description="This thread has not already been scheduled to close.",
                )

            return await ctx.send(embed=embed)

        message = after.arg if after else None
        if self.bot.config["require_close_reason"] and message is None:
            raise commands.BadArgument("Provide a reason for closing the thread.")

        if after and after.dt > after.now:
            cog = self.bot.get_cog('Modmail')
            await cog.send_scheduled_close_message(ctx, after, silent)


        await thread.channel.edit(topic=None)
        await thread.close(closer=ctx.author, after=close_after, message=message, silent=silent, delete_channel=False)
        
        embed = discord.Embed(
            title='Thread suspended',
            description=f'This thread has been suspended by {ctx.author.mention}.',
            color=self.bot.error_color
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Suspend(bot))