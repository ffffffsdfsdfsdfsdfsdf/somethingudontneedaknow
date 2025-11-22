import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import random
from datetime import datetime, timedelta

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Store active giveaways
active_giveaways = {}
# Store ended giveaways for reroll
ended_giveaways = {}

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    # Set blank status
    await bot.change_presence(activity=None)
    
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    
    # Start the countdown updater task
    if not countdown_updater.is_running():
        countdown_updater.start()

@tasks.loop(seconds=10)  # Update every 10 seconds for smoother countdown
async def countdown_updater():
    """Update countdown timers for active giveaways that have winners set"""
    current_time = datetime.now()
    
    for author_id, giveaway_data in list(active_giveaways.items()):
        # Only update if winners are set and it's not a reroll
        if giveaway_data.get("is_reroll") or not giveaway_data.get("winner_ids") or not giveaway_data.get("time_received"):
            continue
            
        try:
            channel = bot.get_channel(giveaway_data["channel_id"])
            if not channel:
                continue
                
            giveaway_msg = await channel.fetch_message(giveaway_data["message_id"])
            
            # Calculate remaining time based on when we received the winner IDs
            time_received = giveaway_data["time_received"]
            end_time = time_received + timedelta(seconds=giveaway_data["duration"])
            time_remaining = end_time - current_time
            
            if time_remaining.total_seconds() <= 0:
                continue  # Giveaway should end soon
                
            # Format remaining time
            time_text = format_timedelta(time_remaining)
            
            # Update the embed with new time
            embed = giveaway_msg.embeds[0] if giveaway_msg.embeds else None
            if embed:
                # Recreate the embed with updated time
                new_embed = discord.Embed(
                    description=f"**{giveaway_data['details']}**\n\nClick button to enter!\nWinners: {giveaway_data['winners_count']}\nEnds: in {time_text}\n\nEnds at • {end_time.strftime('%m/%d/%Y %I:%M %p')}",
                    color=0x5865F2
                )
                
                # Keep the thumbnail image if there was one
                if giveaway_data.get("image_url"):
                    new_embed.set_thumbnail(url=giveaway_data["image_url"])
                
                await giveaway_msg.edit(embed=new_embed)
                
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            # If we can't update the message, just continue
            continue

def format_timedelta(delta: timedelta) -> str:
    """Format a timedelta into a human-readable countdown string"""
    total_seconds = int(delta.total_seconds())
    
    if total_seconds <= 0:
        return "0 seconds"
    
    # Calculate days, hours, minutes, seconds
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    parts = []
    
    if days > 0:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if seconds > 0 and len(parts) < 2:  # Show seconds only if we don't have too many parts
        parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
    
    if not parts:  # If less than 1 second
        return "0 seconds"
    
    return " ".join(parts)

@bot.event
async def on_guild_join(guild):
    # Check if the bot has admin permissions in the server
    bot_member = guild.get_member(bot.user.id)
    if not bot_member.guild_permissions.administrator:
        print(f"Bot added to server without admin perms: {guild.name} ({guild.id})")
        # Leave the server immediately
        await guild.leave()
        print(f"Left server without admin perms: {guild.name}")

def admin_only():
    """Decorator to hide commands from non-admins"""
    async def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)

# ========== DUMMY COMMANDS (DISPLAY ONLY) ==========
# ... (dummy commands remain the same)

@bot.tree.command(name="giveaway", description="Create a new giveaway")
@app_commands.describe(
    time="Duration (ex: 1h, 30m, 2d, 60s)",
    description="What you're giving away",
    winners="Number of winners (default: 1)",
    image="Attach an image for the giveaway"
)
@admin_only()
async def create_giveaway(interaction: discord.Interaction, time: str, description: str, winners: int = 1, image: discord.Attachment = None):
    # Check if bot has admin permissions
    bot_member = interaction.guild.get_member(bot.user.id)
    if not bot_member.guild_permissions.administrator:
        await interaction.response.send_message("❌ This bot needs administrator permissions to function properly. Please reinvite the bot with admin permissions.", ephemeral=True)
        return
    
    # Parse time (supports formats like 1h, 30m, 2d, 60s, etc.)
    time_conversion = {
        's': 1,
        'm': 60,
        'h': 3600,
        'd': 86400
    }
    
    try:
        # Get the time unit (last character)
        time_unit = time[-1].lower()
        if time_unit not in time_conversion:
            raise ValueError("Invalid time unit")
            
        # Get the time value (all characters except the last one)
        time_value = int(time[:-1])
        
        # Validate time ranges
        if time_unit == 's' and not (1 <= time_value <= 60):
            raise ValueError("Seconds must be between 1-60")
        elif time_unit == 'm' and not (1 <= time_value <= 60):
            raise ValueError("Minutes must be between 1-60")
        elif time_unit == 'h' and not (1 <= time_value <= 100):
            raise ValueError("Hours must be between 1-100")
            
        # Calculate total seconds
        total_seconds = time_value * time_conversion[time_unit]
        
    except (ValueError, IndexError) as e:
        error_msg = "Invalid time format. Please use formats like: 1h, 30m, 2d, 60s, etc."
        if str(e):
            error_msg += f"\n{str(e)}"
        await interaction.response.send_message(error_msg, ephemeral=True)
        return
    
    # Send a private message to the author to select winners
    try:
        dm_embed = discord.Embed(
            title="Select Giveaway Winners",
            description=f"Please reply with the user IDs of the {winners} member(s) you want to win the giveaway (one ID per line).\n\nYou can get a user ID by enabling Developer Mode in Discord (Settings > Advanced > Developer Mode) and right-clicking on a user.\n\nType 'cancel' to cancel the giveaway.",
            color=0x00ff00
        )
        dm_embed.add_field(name="Giveaway Details", value=description, inline=False)
        dm_embed.add_field(name="Duration", value=time, inline=False)
        dm_embed.add_field(name="Winners", value=str(winners), inline=False)
        
        # If there's an image, send it in the DM
        if image:
            dm_embed.set_image(url=image.url)
            await interaction.user.send(embed=dm_embed)
        else:
            await interaction.user.send(embed=dm_embed)
            
    except discord.Forbidden:
        await interaction.response.send_message("I couldn't send you a DM. Please enable DMs from server members.", ephemeral=True)
        return
    
    # Format initial time text (static until winners are set)
    initial_time_text = f"{time_value}{time_unit}"
    
    # Create the public giveaway message with exact format from image
    embed = discord.Embed(
        description=f"**{description}**\n\nClick button to enter!\nWinners: {winners}\nEnds: in {initial_time_text}\n\nEnds at • Waiting for host...",
        color=0x5865F2
    )
    
    # If there's an image, set it as thumbnail
    if image:
        embed.set_thumbnail(url=image.url)
    
    # Send the giveaway message
    await interaction.response.send_message("Giveaway created! Check your DMs to select winners.", ephemeral=True)
    giveaway_msg = await interaction.channel.send(embed=embed)
    await giveaway_msg.add_reaction("🎉")
    
    # Store the giveaway details (timer starts AFTER winners are set)
    active_giveaways[interaction.user.id] = {
        "channel_id": interaction.channel.id,
        "details": description,
        "winner_ids": [],
        "winners_count": winners,
        "duration": total_seconds,
        "message_id": giveaway_msg.id,
        "participants": [],
        "time_unit": time_unit,
        "time_value": time_value,
        "start_time": datetime.now(),
        "time_received": None,  # This will be set when winners are chosen
        "image_url": image.url if image else None,
        "original_winners": []
    }

@bot.tree.command(name="reroll", description="Reroll a winner after giveaway ends")
@app_commands.describe(
    time="Delay before reroll (ex: 10s, 5m, 1h)"
)
@admin_only()
async def reroll_giveaway(interaction: discord.Interaction, time: str):
    # Check if bot has admin permissions
    bot_member = interaction.guild.get_member(bot.user.id)
    if not bot_member.guild_permissions.administrator:
        await interaction.response.send_message("❌ This bot needs administrator permissions to function properly. Please reinvite the bot with admin permissions.", ephemeral=True)
        return
    
    # Parse time (supports formats like 10s, 5m, 1h, etc.)
    time_conversion = {
        's': 1,
        'm': 60,
        'h': 3600
    }
    
    try:
        # Get the time unit (last character)
        time_unit = time[-1].lower()
        if time_unit not in time_conversion:
            raise ValueError("Invalid time unit")
            
        # Get the time value (all characters except the last one)
        time_value = int(time[:-1])
        
        # Validate time ranges
        if time_unit == 's' and not (1 <= time_value <= 60):
            raise ValueError("Seconds must be between 1-60")
        elif time_unit == 'm' and not (1 <= time_value <= 60):
            raise ValueError("Minutes must be between 1-60")
        elif time_unit == 'h' and not (1 <= time_value <= 24):
            raise ValueError("Hours must be between 1-24")
            
        # Calculate total seconds
        total_seconds = time_value * time_conversion[time_unit]
        
    except (ValueError, IndexError) as e:
        error_msg = "Invalid time format. Please use formats like: 10s, 5m, 1h, etc."
        if str(e):
            error_msg += f"\n{str(e)}"
        await interaction.response.send_message(error_msg, ephemeral=True)
        return
    
    # Find the last ended giveaway in this channel
    giveaway_data = None
    message_id = None
    
    # Look for the most recent ended giveaway in this channel
    for author_id, data in ended_giveaways.items():
        if data.get("channel_id") == interaction.channel.id:
            giveaway_data = data
            message_id = data.get("message_id")
            break
    
    if not giveaway_data:
        await interaction.response.send_message("No ended giveaway found in this channel to reroll.", ephemeral=True)
        return
    
    # Send a private message to select new winner
    try:
        dm_embed = discord.Embed(
            title="Select Reroll Winner",
            description="Please reply with the user ID of the member you want to win the reroll.\n\nYou can get a user ID by enabling Developer Mode in Discord (Settings > Advanced > Developer Mode) and right-clicking on a user.\n\nType 'cancel' to cancel the reroll.",
            color=0x00ff00
        )
        dm_embed.add_field(name="Giveaway Details", value=giveaway_data['details'], inline=False)
        dm_embed.add_field(name="Reroll Delay", value=time, inline=False)
        await interaction.user.send(embed=dm_embed)
    except discord.Forbidden:
        await interaction.response.send_message("I couldn't send you a DM. Please enable DMs from server members.", ephemeral=True)
        return
    
    # Store reroll data
    reroll_key = f"reroll_{interaction.user.id}"
    active_giveaways[reroll_key] = {
        "channel_id": interaction.channel.id,
        "details": giveaway_data['details'],
        "winner_id": None,
        "duration": total_seconds,
        "message_id": message_id,
        "participants": giveaway_data.get("participants", []),
        "time_received": None,
        "image_url": giveaway_data.get("image_url"),
        "is_reroll": True,
        "original_winners": giveaway_data.get("winner_ids", [])
    }
    
    # PUBLIC MESSAGE - everyone can see this
    await interaction.response.send_message(f"𓆩♡𓆪 Reroll started! A new winner will be selected in {time_value}{time_unit}!")

@bot.event
async def on_message(message):
    # Check if the message is a DM and from a user who is creating a giveaway or reroll
    if isinstance(message.channel, discord.DMChannel):
        # Check for regular giveaway
        if message.author.id in active_giveaways:
            giveaway_data = active_giveaways[message.author.id]
            
            if message.content.lower() == 'cancel':
                # Cancel the giveaway
                channel = bot.get_channel(giveaway_data["channel_id"])
                
                try:
                    giveaway_msg = await channel.fetch_message(giveaway_data["message_id"])
                    await giveaway_msg.delete()
                except:
                    pass
                
                await channel.send("Giveaway cancelled.")
                del active_giveaways[message.author.id]
                await message.channel.send("Giveaway cancelled.")
                return
            
            # Check if message has attachments (images)
            if message.attachments:
                # Store the image URL for later use
                giveaway_data["image_url"] = message.attachments[0].url
                await message.channel.send("Image received! Now please send the winner user IDs (one per line).")
                return
            
            # Try to parse the user IDs (multiple winners)
            try:
                winner_ids = []
                lines = message.content.strip().split('\n')
                
                for line in lines:
                    if line.strip():  # Skip empty lines
                        winner_id = int(line.strip())
                        winner_ids.append(winner_id)
                
                # Verify winners are in the server
                channel = bot.get_channel(giveaway_data["channel_id"])
                guild = channel.guild
                valid_winners = []
                
                for winner_id in winner_ids:
                    winner = guild.get_member(winner_id)
                    if winner:
                        valid_winners.append(winner)
                    else:
                        await message.channel.send(f"Couldn't find user with ID {winner_id} in the server.")
                
                if len(valid_winners) >= giveaway_data["winners_count"]:
                    # Store the winners and when we received the IDs (THIS STARTS THE TIMER)
                    active_giveaways[message.author.id]["winner_ids"] = [w.id for w in valid_winners[:giveaway_data["winners_count"]]]
                    active_giveaways[message.author.id]["original_winners"] = [w.id for w in valid_winners[:giveaway_data["winners_count"]]]
                    active_giveaways[message.author.id]["time_received"] = datetime.now()
                    
                    # Calculate end time for the display
                    end_time = datetime.now() + timedelta(seconds=giveaway_data["duration"])
                    
                    # Update the giveaway message to show the countdown has started
                    channel = bot.get_channel(giveaway_data["channel_id"])
                    giveaway_msg = await channel.fetch_message(giveaway_data["message_id"])
                    
                    # Format initial time for the update
                    time_text = format_timedelta(timedelta(seconds=giveaway_data["duration"]))
                    
                    updated_embed = discord.Embed(
                        description=f"**{giveaway_data['details']}**\n\nClick button to enter!\nWinners: {giveaway_data['winners_count']}\nEnds: in {time_text}\n\nEnds at • {end_time.strftime('%m/%d/%Y %I:%M %p')}",
                        color=0x5865F2
                    )
                    
                    if giveaway_data.get("image_url"):
                        updated_embed.set_thumbnail(url=giveaway_data["image_url"])
                    
                    await giveaway_msg.edit(embed=updated_embed)
                    
                    winner_names = ", ".join([w.display_name for w in valid_winners[:giveaway_data["winners_count"]]])
                    await message.channel.send(f"✅ Winners set! {winner_names} will win the giveaway. The timer has started and will count down in real time!")
                    
                    # Schedule the giveaway end with the full duration
                    asyncio.create_task(end_giveaway(message.author.id, giveaway_data["duration"]))
                else:
                    await message.channel.send(f"Need at least {giveaway_data['winners_count']} valid winners. Please provide more user IDs.")
                    
            except ValueError:
                await message.channel.send("Please provide valid user IDs (numbers only, one per line).")
        
        # Check for reroll
        reroll_key = f"reroll_{message.author.id}"
        if reroll_key in active_giveaways:
            giveaway_data = active_giveaways[reroll_key]
            
            if message.content.lower() == 'cancel':
                del active_giveaways[reroll_key]
                await message.channel.send("Reroll cancelled.")
                return
            
            # Try to parse the user ID for reroll
            try:
                winner_id = int(message.content.strip())
                # Verify this user is in the server
                channel = bot.get_channel(giveaway_data["channel_id"])
                guild = channel.guild
                winner = guild.get_member(winner_id)
                
                if winner:
                    # Store the winner and when we received the ID
                    active_giveaways[reroll_key]["winner_id"] = winner_id
                    active_giveaways[reroll_key]["time_received"] = datetime.now()
                    
                    time_remaining = giveaway_data["duration"]
                    
                    await message.channel.send(f"Reroll winner set! {winner.display_name} will win the reroll. The selection will appear completely random after {int(time_remaining)} seconds.")
                    
                    # Schedule the reroll with the remaining time
                    asyncio.create_task(end_reroll(reroll_key, time_remaining))
                else:
                    await message.channel.send("I couldn't find that user in the server. Please make sure you're using the correct user ID.")
            except ValueError:
                await message.channel.send("Please provide a valid user ID (numbers only).")
    
    # Process commands too
    await bot.process_commands(message)

# ... (end_giveaway and end_reroll functions remain the same)

async def end_giveaway(author_id, remaining_time):
    # Wait for the remaining time to pass
    await asyncio.sleep(remaining_time)
    
    if author_id not in active_giveaways:
        return
    
    giveaway_data = active_giveaways[author_id]
    channel = bot.get_channel(giveaway_data["channel_id"])
    
    try:
        # Get the giveaway message
        giveaway_msg = await channel.fetch_message(giveaway_data["message_id"])
        
        # Get all participants who reacted with 🎉
        participants = []
        for reaction in giveaway_msg.reactions:
            if str(reaction.emoji) == "🎉":
                async for user in reaction.users():
                    # Count all users who reacted, including bots (for accurate count)
                    # But exclude them from actual winning
                    participants.append(user)
                break
        
        # Count total participants (all users who reacted)
        total_participants = len(participants)
        
        # Get only valid participants (non-bots and not the host)
        valid_participants = []
        for user in participants:
            if not user.bot and user.id != author_id:
                valid_participants.append(user)
        
        # Store valid participants for winner selection
        giveaway_data["participants"] = [user.id for user in valid_participants]
        valid_participant_count = len(giveaway_data["participants"])
        
        # Get the predetermined winners
        winner_ids = giveaway_data["winner_ids"]
        winners = [channel.guild.get_member(winner_id) for winner_id in winner_ids if channel.guild.get_member(winner_id)]
        
        # LOCK REACTIONS: Remove the reaction option
        try:
            await giveaway_msg.clear_reaction("🎉")
        except:
            pass  # Ignore if we can't clear reactions
        
        # Update the giveaway message to show it ended with ACTUAL participant count
        ended_embed = discord.Embed(
            description=f"**{giveaway_data['details']}**\n\nEntries: {total_participants} Participants\n\nEnded at • {datetime.now().strftime('%m/%d/%Y %I:%M %p')}",
            color=0x2b2d31
        )
        
        # Keep the thumbnail image if there was one
        if giveaway_data.get("image_url"):
            ended_embed.set_thumbnail(url=giveaway_data["image_url"])
        
        await giveaway_msg.edit(embed=ended_embed)
        
        if winners:
            # If predetermined winners didn't participate, add them to the list
            for winner in winners:
                if winner.id not in giveaway_data["participants"]:
                    giveaway_data["participants"].append(winner.id)
            
            # Create a fake "random" selection process
            random.shuffle(giveaway_data["participants"])
            
            # Announce winners
            winner_mentions = ", ".join([winner.mention for winner in winners])
            await giveaway_msg.reply(f"Congratulations {winner_mentions}! You won **{giveaway_data['details']}**!")
            
        else:
            # Fallback if winners are not found
            if valid_participants:
                # Select random participants as fallback
                fallback_winners = random.sample(valid_participants, min(giveaway_data['winners_count'], len(valid_participants)))
                winner_mentions = ", ".join([winner.mention for winner in fallback_winners])
                await giveaway_msg.reply(f"Congratulations {winner_mentions}! You won **{giveaway_data['details']}**!")
            else:
                await giveaway_msg.reply("No one entered the giveaway. The giveaway has been cancelled.")
        
        # Store in ended giveaways for reroll
        ended_giveaways[author_id] = giveaway_data.copy()
        
    except discord.NotFound:
        try:
            async for last_msg in channel.history(limit=1):
                await last_msg.reply("The giveaway message was deleted. The giveaway has been cancelled.")
        except:
            await channel.send("The giveaway message was deleted. The giveaway has been cancelled.")
    
    except discord.Forbidden:
        try:
            async for last_msg in channel.history(limit=1):
                await channel.send("I don't have permission to manage messages in this channel.")
        except:
            await channel.send("I don't have permission to manage messages in this channel.")
    
    # Remove the giveaway from active giveaways
    if author_id in active_giveaways:
        del active_giveaways[author_id]

async def end_reroll(reroll_key, remaining_time):
    # Wait for the remaining time to pass
    await asyncio.sleep(remaining_time)
    
    if reroll_key not in active_giveaways:
        return
    
    reroll_data = active_giveaways[reroll_key]
    channel = bot.get_channel(reroll_data["channel_id"])
    
    try:
        # Get the giveaway message
        giveaway_msg = await channel.fetch_message(reroll_data["message_id"])
        
        # Get the predetermined reroll winner
        winner_id = reroll_data["winner_id"]
        winner = channel.guild.get_member(winner_id)
        
        if winner:
            # Create a fake "random" selection process
            participants = reroll_data.get("participants", [])
            if participants:
                random.shuffle(participants)
            
            # Announce reroll winner
            await giveaway_msg.reply(f"𓆩♡𓆪 **REROLL** 𓆩♡𓆪\nCongratulations {winner.mention}! You won the reroll for **{reroll_data['details']}**!")
            
        else:
            # Fallback if winner is not found
            participants = reroll_data.get("participants", [])
            if participants:
                # Select a random participant as fallback
                fallback_winner = random.choice(participants)
                fallback_user = channel.guild.get_member(fallback_winner)
                if fallback_user:
                    await giveaway_msg.reply(f"𓆩♡𓆪 **REROLL** 𓆩♡𓆪\nCongratulations {fallback_user.mention}! You won the reroll for **{reroll_data['details']}**!")
            else:
                await giveaway_msg.reply("No participants found for reroll.")
    
    except discord.NotFound:
        await channel.send("The giveaway message was deleted. Reroll cancelled.")
    
    except discord.Forbidden:
        await channel.send("I don't have permission to manage messages in this channel.")
    
    # Remove the reroll from active giveaways
    if reroll_key in active_giveaways:
        del active_giveaways[reroll_key]

# Run the bot with your token
bot.run('MTQ0MTQ3NzY2NjcxMTY2Njc1OQ.G8S_P1.MR3TFmCAfGGTUhF97fEOi8BbanYZYz5WWZE2x4')