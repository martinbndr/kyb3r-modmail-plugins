from typing import TYPE_CHECKING, Union

import discord
from discord.ext import commands

from core.checks import has_permissions
from core.models import PermissionLevel

if TYPE_CHECKING:
    from bot import ModmailBot

class Dm(commands.Cog):
    """
    Implements a command to send a DM to a specified user.
    """
    def __init__(self, bot: "ModmailBot"):
        self.bot = bot

    @commands.command(name="dm")
    @has_permissions(PermissionLevel.OWNER)
    async def send_dm(
        self, 
        ctx: commands.Context, 
        user: Union[discord.Member, discord.User],
        *,
        content: str
        ):
        """
        Sends a DM to the specified User.

        Keep in mind that your bot can be blocked by discord
        under certain cases for sending many DM´s to users.
        Use it with caution.

        By default it is locked to the OWNER Level for security reasons.
        """

        if user.bot:
            embed = discord.Embed(
                title="Error",
                description=f"You cannot send messages to other bots.",
                color=self.bot.config["error_color"]
            )
            return await ctx.send(embed=embed)
        
        if len(content) > 4096:
            embed = discord.Embed(
                title="Error",
                description=f"Message cannot be longer than 4096 characters.",
                color=self.bot.config["error_color"]
            )
            return await ctx.send(embed=embed)

        try:
            dmembed = discord.Embed(
                description=content,
                color=self.bot.config["main_color"]
            )
            dmembed.set_footer(text=f"Author @{ctx.author}", icon_url=ctx.author.display_avatar.url)

            await user.send(embed=dmembed)
        except discord.Forbidden:
            embed = discord.Embed(
                title="Error",
                description=f"Failed to send DM to {user.mention} (`{user.id}`). Forbidden due to their privacy settings/being blocked or no mutal servers.",
                color=self.bot.config["error_color"]
            )
            return await ctx.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                title="Error",
                description=f"Failed to send dm to {user.mention} (`{user.id}`):\n```{e}```",
                color=self.bot.config["error_color"]
            )
            return await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title="DM sent",
                description=f"DM sent to {user.mention} (`{user.id}`).",
                color=self.bot.config["main_color"]
            )
            return await ctx.send(embed=embed)


async def setup(bot: "ModmailBot"):
    await bot.add_cog(Dm(bot))