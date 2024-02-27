import discord
from discord.ext import commands
from discord.utils import utcnow
from motor import motor_asyncio

from core import checks
from core.models import PermissionLevel, getLogger

from bot import ModmailBot

logger = getLogger(__name__)


async def claim_check(ctx):
    cog = ctx.bot.get_cog("Claim")
    thread_data = await cog.db.find_one({"channel_id": str(ctx.thread.channel.id)})
    allowed_to_reply = False
    if thread_data is None:
        if cog.config["require_claim"] is False:
            allowed_to_reply = True
    else:
        if str(ctx.author.id) in thread_data["claimers"]:
            allowed_to_reply = True
    if ctx.author.bot:
        allowed_to_reply = True
    return allowed_to_reply


class Claim(commands.Cog):
    """
    Adds claim functionality to your modmail bot.

    Only members claimed a thread can reply to the thread via the reply commands.

    The plugin is still work in progress, update frequenze vary due to realife.
    """

    def __init__(self, bot: ModmailBot):
        self.bot: ModmailBot = bot
        self.db: motor_asyncio.AsyncIOMotorCollection = bot.api.get_plugin_partition(self)
        self.reply_commands = ["reply", "areply", "freply", "fareply", "fareply", "preply", "pareply"]
        self.config = {}
        self.default_config = {"require_claim": True}
        self.initialized = False

    async def cog_load(self):
        """
        Verifies plugin config, adds the claim check on cog load/plugin installation.
        """
        if not self.initialized:
            self.config = await self.db.find_one({"_id": "config"})
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

            for i in self.reply_commands:
                cmd = self.bot.get_command(i)
                if not claim_check in cmd.checks:
                    cmd.add_check(claim_check)
            self.initialized = True

    async def update_config(self):
        await self.db.find_one_and_update(
            {"_id": "config"},
            {"$set": self.config},
            upsert=True,
        )

    async def cog_unload(self):
        """
        Removes the claim check on cog unload/plugin removal.
        """
        self.initialized = False
        for i in self.reply_commands:
            cmd = self.bot.get_command(i)
            if claim_check in cmd.checks:
                cmd.remove_check(claim_check)

    @commands.command(name="claim")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    @commands.max_concurrency(number=1, per=commands.BucketType.channel, wait=False)
    async def claim(self, ctx: commands.Context):
        """
        Claims thread on behalf of you.
        """
        thread_data = await self.db.find_one({"channel_id": str(ctx.thread.channel.id)})
        if thread_data is None:
            await self.db.insert_one(
                {
                    "channel_id": str(ctx.thread.channel.id),
                    "main_claimer": str(ctx.author.id),
                    "claimed_at": utcnow(),
                    "claimers": [str(ctx.author.id)],
                }
            )
            embed = discord.Embed(
                title="Thread claimed",
                description="You successfully claimed this thread.",
                color=ctx.bot.main_color,
            )
            return await ctx.send(embed=embed)
        else:
            claimers_mentions = [f"<@{i}>" for i in thread_data["claimers"]]
            claimers_mentions_str = ", ".join(claimers_mentions)
            embed = discord.Embed(
                title="Thread already claimed",
                description=f"This thread is already claimed by {claimers_mentions_str}.",
                color=ctx.bot.error_color,
            )
            await ctx.send(embed=embed)

    @commands.command(name="addclaim")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def addclaim(self, ctx: commands.Context, *, member: discord.Member):
        """
        Adds another member to your claim.

        This allows all manually added members to reply in threads.
        """
        thread_data = await self.db.find_one({"channel_id": str(ctx.thread.channel.id)})
        if thread_data is None:
            embed = discord.Embed(
                title="Thread not claimed",
                description=f"This thread is not claimed by anyone.",
                color=ctx.bot.error_color,
            )
            return await ctx.send(embed=embed)
        if not str(ctx.author.id) == thread_data["main_claimer"]:
            embed = discord.Embed(
                title="Thread not claimed by you.",
                description=f"You have not claimed this thread. Ask <@{thread_data['main_claimer']}> to add you as claimer.",
                color=ctx.bot.error_color,
            )
            return await ctx.send(embed=embed)
        if str(member.id) in thread_data["claimers"]:
            embed = discord.Embed(
                title="Member already added",
                description=f"The member {member.mention} is already added to the claimers.",
                color=ctx.bot.error_color,
            )
            return await ctx.send(embed=embed)
        thread_data["claimers"].append(str(member.id))
        await self.db.update_one({"channel_id": str(ctx.thread.channel.id)}, {"$set": thread_data})
        embed = discord.Embed(
            title="Member added",
            description=f"You successfully added {member.mention} to the claimers.",
            color=ctx.bot.main_color,
        )
        await ctx.send(embed=embed)

    @commands.command(name="removeclaim")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def removeclaim(self, ctx: commands.Context, *, member: discord.Member):
        """
        Removes a member from your claim.

        This removes an added member from the thread claimers. They can no longer reply.
        """
        thread_data = await self.db.find_one({"channel_id": str(ctx.thread.channel.id)})
        if thread_data is None:
            embed = discord.Embed(
                title="Thread not claimed",
                description=f"This thread is not claimed by anyone.",
                color=ctx.bot.error_color,
            )
            return await ctx.send(embed=embed)
        if not str(ctx.author.id) == thread_data["main_claimer"]:
            embed = discord.Embed(
                title="Thread not claimed by you.",
                description=f"You have not claimed this thread. Ask <@{thread_data['main_claimer']}> remove you from the claimers.",
                color=ctx.bot.error_color,
            )
            return await ctx.send(embed=embed)

        if not str(member.id) in thread_data["claimers"]:
            embed = discord.Embed(
                title="Member not added",
                description=f"The member {member.mention} is not added to the claimers.",
                color=ctx.bot.error_color,
            )
            return await ctx.send(embed=embed)
        if str(member.id) == str(ctx.author.id):
            embed = discord.Embed(
                title="You cannot remove yourself",
                description=f"You cannot remove yourself from the claimers. Unclaim the thread instead.",
                color=ctx.bot.error_color,
            )
            return await ctx.send(embed=embed)
        thread_data["claimers"].remove(str(member.id))
        await self.db.update_one({"channel_id": str(ctx.thread.channel.id)}, {"$set": thread_data})
        embed = discord.Embed(
            title="Member removed",
            description=f"You successfully removed {member.mention} from the claimers.",
            color=ctx.bot.main_color,
        )
        await ctx.send(embed=embed)

    @commands.command(name="unclaim")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def unclaim(self, ctx: commands.Context):
        """
        Unclaims a thread if claimed by yourself.
        """
        thread_data = await self.db.find_one({"channel_id": str(ctx.thread.channel.id)})
        if thread_data is None:
            embed = discord.Embed(
                title="Thread not claimed",
                description=f"This thread is not claimed by anyone.",
                color=ctx.bot.error_color,
            )
            return await ctx.send(embed=embed)
        if not str(ctx.author.id) == thread_data["main_claimer"]:
            embed = discord.Embed(
                title="Thread not claimed by you.",
                description=f"You have not claimed this thread. Ask the claimer <@{thread_data['main_claimer']}> to unclaim it.",
                color=ctx.bot.error_color,
            )
            return await ctx.send(embed=embed)
        await self.db.delete_one({"channel_id": str(ctx.thread.channel.id)})
        embed = discord.Embed(
            title="Thread unclaimed",
            description="You successfully unclaimed this thread.",
            color=ctx.bot.main_color,
        )
        return await ctx.send(embed=embed)

    @commands.command(name="faddclaim")
    @checks.has_permissions(PermissionLevel.MODERATOR)
    @checks.thread_only()
    async def faddclaim(self, ctx: commands.Context, *, member: discord.Member):
        """
        Forces addclaim of a thread via the MODERATOR permission.

        Allowes moderators to force addclaim a thread. It does not check anything regarding thread claimer.
        You can overwrite the permissions via the ``perms override`` commmand if needed.
        """
        thread_data = await self.db.find_one({"channel_id": str(ctx.thread.channel.id)})
        if thread_data is None:
            embed = discord.Embed(
                title="Thread not claimed",
                description=f"This thread is not claimed by anyone.",
                color=ctx.bot.error_color,
            )
            return await ctx.send(embed=embed)
        if str(member.id) in thread_data["claimers"]:
            embed = discord.Embed(
                title="Member already added",
                description=f"The member {member.mention} is already added to the claimers.",
                color=ctx.bot.error_color,
            )
            return await ctx.send(embed=embed)
        thread_data["claimers"].append(str(member.id))
        await self.db.update_one({"channel_id": str(ctx.thread.channel.id)}, {"$set": thread_data})
        embed = discord.Embed(
            title="Member added",
            description=f"You successfully added {member.mention} to the claimers.",
            color=ctx.bot.main_color,
        )
        await ctx.send(embed=embed)

    @commands.command(name="fremoveclaim")
    @checks.has_permissions(PermissionLevel.MODERATOR)
    @checks.thread_only()
    async def fremoveclaim(self, ctx: commands.Context, *, member: discord.Member):
        """
        Forces removeclaim of a thread via the MODERATOR permission.

        Allowes moderators to force removeclaim a thread. It does not check anything regarding thread claimer.
        You can overwrite the permissions via the ``perms override`` commmand if needed.
        """
        thread_data = await self.db.find_one({"channel_id": str(ctx.thread.channel.id)})
        if thread_data is None:
            embed = discord.Embed(
                title="Thread not claimed",
                description=f"This thread is not claimed by anyone.",
                color=ctx.bot.error_color,
            )
            return await ctx.send(embed=embed)
        if not str(member.id) in thread_data["claimers"]:
            embed = discord.Embed(
                title="Member not added",
                description=f"The member {member.mention} is not added to the claimers.",
                color=ctx.bot.error_color,
            )
            return await ctx.send(embed=embed)
        if str(member.id) == str(ctx.author.id):
            embed = discord.Embed(
                title="You cannot remove yourself",
                description=f"You cannot remove yourself from the claimers. Unclaim the thread instead.",
                color=ctx.bot.error_color,
            )
            return await ctx.send(embed=embed)
        thread_data["claimers"].remove(str(member.id))
        await self.db.update_one({"channel_id": str(ctx.thread.channel.id)}, {"$set": thread_data})
        embed = discord.Embed(
            title="Member removed",
            description=f"You successfully removed {member.mention} from the claimers.",
            color=ctx.bot.main_color,
        )
        await ctx.send(embed=embed)

    @commands.command(name="funclaim")
    @checks.has_permissions(PermissionLevel.MODERATOR)
    @checks.thread_only()
    async def funclaim(self, ctx: commands.Context):
        """
        Forces unclaim of a thread via the MODERATOR permission.

        Allowes moderators to force unclaim a thread. It does not check anything regarding thread claimer.
        You can overwrite the permissions via the ``perms override`` commmand if needed.
        """
        thread_data = await self.db.find_one({"channel_id": str(ctx.thread.channel.id)})
        if thread_data is None:
            embed = discord.Embed(
                title="Thread not claimed",
                description=f"This thread is not claimed by anyone.",
                color=ctx.bot.error_color,
            )
            return await ctx.send(embed=embed)
        await self.db.delete_one({"channel_id": str(ctx.thread.channel.id)})
        embed = discord.Embed(
            title="Thread unclaimed",
            description="You successfully forced unclaim of this thread.",
            color=ctx.bot.main_color,
        )
        return await ctx.send(embed=embed)

    @commands.group(name="claimconfig", invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.OWNER)
    async def claimconfig(self, ctx: commands.Context):
        """
        Plugin configuration management.

        This is still work in progress.
        """
        await ctx.send_help(ctx.command)


async def setup(bot: ModmailBot):
    await bot.add_cog(Claim(bot))
