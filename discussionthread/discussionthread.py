import discord
from discord.ext import commands

from core.utils import getLogger

LOGGER = getLogger(__name__)

class DiscussionThread(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_thread_ready(self, thread, creator, category, initial_message):
        if isinstance(thread.channel, discord.TextChannel):
            perms = thread.channel.permissions_for(thread.channel.guild.me)
            if not perms.create_public_threads:
                LOGGER.warning(
                    "Can´t create discussion thread for %s due to missing permissions.", 
                    thread.id
                    )
                return
            embed = discord.Embed(
                title="Discussion",
                description=f"You can make discussions below in the attached thread.",
                color=self.bot.config["main_color"]
            )
            msg = await thread.channel.send(embed=embed)
            try:
                discussion_thread = await thread.channel.create_thread(name="Discussion", auto_archive_duration=4320, message=msg)
            except Exception as e:
                LOGGER.error("Failed to create discussion thread for %s.", thread.id, exc_info=True)



async def setup(bot: commands.Bot):
    await bot.add_cog(DiscussionThread(bot))