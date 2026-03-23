import ssl
import certifi
import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv
import asyncio
import os

# Load the secret tokens from .env file
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

async def main():
    # Set up SSL
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(ssl=ssl_context)

    # Set up the bot
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents, connector=connector)

    # Load the flights cog
    await bot.load_extension("cogs.flights")

    @bot.event
    async def on_ready():
        await bot.tree.sync()
        print(f"Bot is online as {bot.user}")

    await bot.start(TOKEN)

asyncio.run(main())