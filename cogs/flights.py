import discord
from discord import app_commands
from discord.ext import commands
import httpx
import json
import random
import datetime
import asyncio
import os
import re
from dotenv import load_dotenv

load_dotenv()
AIRLABS_KEY = os.getenv("AIRLABS_KEY")
GEOAPIFY_KEY = os.getenv("GEOAPIFY_KEY")

COUNTER_FILE = "data/counter.json"
MAX_REQUESTS = 950
MAX_RETRIES = 3

def load_counter():
    with open(COUNTER_FILE, "r") as f:
        return json.load(f)

def save_counter(data):
    with open(COUNTER_FILE, "w") as f:
        json.dump(data, f, indent=4)

def check_and_increment():
    data = load_counter()
    current_month = datetime.datetime.now().month

    if data["month"] != current_month:
        data["count"] = 0
        data["month"] = current_month

    if data["count"] >= MAX_REQUESTS:
        return False

    data["count"] += 1
    save_counter(data)
    return True

def is_commercial(callsign):
    # Commercial flights look like UAL123, DAL4, BAW231 — 3 letters then numbers
    return bool(re.match(r'^[A-Z]{3}\d+$', callsign.strip()))

class Flights(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="randomflight", description="Get a live flight!")
    @app_commands.describe(flight="Optional: enter a callsign (DAL230) or flight number (DL230)")
    async def randomflight(self, interaction: discord.Interaction, flight: str = None):
        await interaction.response.defer()

        if not check_and_increment():
            await interaction.followup.send("✈️ Flight lookups have reached the monthly limit. Try again next month!")
            return

        async with httpx.AsyncClient() as client:
            # Get all live flights from OpenSky
            opensky = await client.get("https://opensky-network.org/api/states/all")
            flights = opensky.json()["states"]

            if flight:
                # User provided a callsign or flight number — try to find it
                flight_upper = flight.strip().upper()
                match = next((f for f in flights if f[1] and f[1].strip().upper() == flight_upper), None)
                if not match:
                    await interaction.followup.send(f"❌ Could not find a live flight with **{flight}**. It may not be airborne right now.")
                    return
                candidates = [match]
            else:
                # Filter to commercial flights only
                valid = [f for f in flights if f[1] and f[5] and f[6] and is_commercial(f[1])]
                if not valid:
                    await interaction.followup.send("❌ Could not find any valid flights right now. Try again in a moment!")
                    return
                # Shuffle so we try different flights each retry
                random.shuffle(valid)
                candidates = valid[:MAX_RETRIES]

            found = None
            for candidate in candidates:
                raw_callsign = candidate[1].strip()
                country = candidate[2]
                latitude = candidate[6]
                longitude = candidate[5]
                altitude = round(candidate[7] * 3.28084) if candidate[7] else "Unknown"
                speed = round(candidate[9] * 1.94384) if candidate[9] else "Unknown"

                # Query Airlabs and Geoapify at the same time
                airlabs_url = f"https://airlabs.co/api/v9/flight?flight_icao={raw_callsign}&api_key={AIRLABS_KEY}"
                map_url = f"https://maps.geoapify.com/v1/staticmap?style=osm-bright&width=600&height=300&center=lonlat:{longitude},{latitude}&zoom=5&marker=lonlat:{longitude},{latitude};color:%23ff0000;size:medium&apiKey={GEOAPIFY_KEY}"

                airlabs_response, _ = await asyncio.gather(
                    client.get(airlabs_url),
                    client.get(map_url)
                )

                airlabs_data = airlabs_response.json()
                flight_info = airlabs_data.get("response", {})
                dep_iata = flight_info.get("dep_iata")
                arr_iata = flight_info.get("arr_iata")
                aircraft = flight_info.get("model", "Unknown")
                registration = flight_info.get("reg_number", "Unknown")

                # Skip if departure or arrival is missing
                if not dep_iata or not arr_iata:
                    continue

                found = {
                    "callsign": raw_callsign,
                    "country": country,
                    "latitude": latitude,
                    "longitude": longitude,
                    "altitude": altitude,
                    "speed": speed,
                    "dep_iata": dep_iata,
                    "arr_iata": arr_iata,
                    "aircraft": aircraft,
                    "registration": registration,
                    "map_url": map_url
                }
                break

            if not found:
                await interaction.followup.send("❌ Couldn't find a flight with full info after several tries. Please try again!")
                return

            embed = discord.Embed(
                title=f"✈️ {found['callsign']}",
                color=discord.Color.blue()
            )
            embed.add_field(name="🌍 Origin Country", value=found["country"], inline=True)
            embed.add_field(name="🛫 Departure", value=found["dep_iata"], inline=True)
            embed.add_field(name="🛬 Arrival", value=found["arr_iata"], inline=True)
            embed.add_field(name="📡 Altitude", value=f"{found['altitude']} ft", inline=True)
            embed.add_field(name="🚀 Speed", value=f"{found['speed']} knots", inline=True)
            embed.add_field(name="📍 Position", value=f"{found['latitude']:.2f}, {found['longitude']:.2f}", inline=True)
            embed.add_field(name="✈️ Aircraft", value=found["aircraft"], inline=True)
            embed.add_field(name="🔢 Registration", value=found["registration"], inline=True)
            embed.set_image(url=found["map_url"])
            embed.set_footer(text="Data: OpenSky Network & Airlabs")

            await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Flights(bot))