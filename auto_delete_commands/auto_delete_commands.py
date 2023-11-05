import discord
from discord.ext import commands

class AutoDeleteCommands(commands.Cog):
    """This Plugin makes all commands delete automatically"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command(self, ctx: commands.Context):
        await ctx.message.delete()

async def setup(bot: commands.Bot):
    await bot.add_cog(AutoDeleteCommands(bot))