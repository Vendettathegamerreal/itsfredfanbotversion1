import os
import time
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import subprocess
import aiohttp
import requests
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

OVERLAY_FILENAME="watermarkitsfredfanbotv2.png"

if not BOT_TOKEN:
    raise ValueError("❌ DISCORD_TOKEN is missing from your environment variables or .env file!")

# Enable required intents
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Queue System Globals ---
dub_queue = asyncio.Queue()
is_processing_queue = False
current_dub_task = None

def render_progress_bar(percent: int, length: int = 15) -> str:
    filled = int(length * percent / 100)
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}] {percent}%"

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.tree.command(name="codec", description="Apply hardware codec crunch (AMR) and output to MP3")
@app_commands.describe(attachment="The audio file to degrade", bitrate="AMR bitrate option (e.g. 4.75k, 7.4k, 12.2k)")
async def codec_effect(interaction: discord.Interaction, attachment: discord.Attachment, bitrate: str = "7.4k"):
    await interaction.response.defer()

    timestamp = int(time.time() * 1000)
    input_file = f"input_{timestamp}{os.path.splitext(attachment.filename)[1]}"
    amr_file = f"temp_{timestamp}.amr"
    output_file = f"codec_output_{timestamp}.mp3"

    try:
        await attachment.save(input_file)

        # Step 1: Convert input to AMR format with bandpass filtering
        cmd_amr = (
            f'ffmpeg -y -i "{input_file}" '
            f'-af "highpass=f=300,lowpass=f=3400,volume=1.5" '
            f'-ar 8000 -ac 1 -c:a libopencore_amrnb -b:a {bitrate} "{amr_file}"'
        )
        proc1 = await asyncio.create_subprocess_shell(cmd_amr, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await proc1.communicate()

        if proc1.returncode != 0:
            raise Exception("FFmpeg failed during AMR encoding. Ensure libopencore-amrnb is installed.")

        # Step 2: Convert AMR back to MP3
        cmd_mp3 = f'ffmpeg -y -i "{amr_file}" -c:a libmp3lame -b:a 128k "{output_file}"'
        proc2 = await asyncio.create_subprocess_shell(cmd_mp3, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await proc2.communicate()

        if proc2.returncode != 0:
            raise Exception("FFmpeg failed during MP3 conversion.")

        discord_file = discord.File(output_file, filename=f"codec_{attachment.filename.rsplit('.', 1)[0]}.mp3")
        await interaction.followup.send(content=f"🎛️ **Codec Effect Applied (AMR @ {bitrate}) & Exported to MP3:**", file=discord_file)

    except Exception as e:
        await interaction.followup.send(content=f"❌ Error: `{str(e)}`", ephemeral=True)

    finally:
        for f in [input_file, amr_file, output_file]:
            if os.path.exists(f):
                try: os.remove(f)
                except: pass

@bot.tree.command(name="phonequality", description="Convert an uploaded audio file to low phone quality standard")
@app_commands.describe(attachment="The audio file you want to convert")
async def phonequality(interaction: discord.Interaction, attachment: discord.Attachment):
    if not attachment.content_type or not attachment.content_type.startswith("audio/"):
        if not attachment.filename.lower().endswith(('.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac')):
            await interaction.response.send_message(" Please upload a valid audio file!", ephemeral=True)
            return

    await interaction.response.defer()

    timestamp = int(time.time() * 1000)
    input_filename = f"temp_input_{timestamp}_{attachment.filename}"
    gsm_filename = f"temp_gsm_{timestamp}.gsm"
    output_filename = f"phone_quality_{timestamp}.mp3"

    try:
        await interaction.edit_original_response(
            content=f"**Downloading audio file...**\n`{render_progress_bar(10)}`"
        )
        await attachment.save(input_filename)

        await interaction.edit_original_response(
            content=f"**Step 1/2:** Applying phone quality filter (300Hz-3400Hz, GSM 8kHz)...\n`{render_progress_bar(35)}`"
        )

        cmd_to_gsm = (
            f'ffmpeg -y -i "{input_filename}" '
            f'-af "highpass=f=300,lowpass=f=3400,acompressor=threshold=0.08:ratio=3:attack=5:release=80,volume=1.5" '
            f'-ac 1 -ar 8000 -c:a libgsm -b:a 13k "{gsm_filename}"'
        )

        proc_gsm = await asyncio.create_subprocess_shell(
            cmd_to_gsm,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc_gsm.communicate()

        if proc_gsm.returncode != 0:
            raise Exception("FFmpeg failed during input to GSM conversion.")

        await interaction.edit_original_response(
            content=f"🎵 **Step 2/2:** Converting GSM file back to MP3...\n`{render_progress_bar(70)}`"
        )

        cmd_to_mp3 = (
            f'ffmpeg -y -i "{gsm_filename}" '
            f'-c:a libmp3lame -preset veryslow "{output_filename}"'
        )

        proc_mp3 = await asyncio.create_subprocess_shell(
            cmd_to_mp3,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc_mp3.communicate()

        if proc_mp3.returncode != 0:
            raise Exception("FFmpeg failed during GSM to MP3 conversion.")

        await interaction.edit_original_response(
            content=f"✅ **Conversion Complete!**\n`{render_progress_bar(100)}`\nUploading phone quality audio..."
        )

        discord_file = discord.File(output_filename, filename=f"phone_{attachment.filename.rsplit('.', 1)[0]}.mp3")
        await interaction.followup.send(content="Here is your low quality phone audio:", file=discord_file)

    except Exception as e:
        await interaction.edit_original_response(content=f"❌ **Error during processing:** `{str(e)}`")

    finally:
        for filepath in [input_filename, gsm_filename, output_filename]:
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception:
                    pass

@bot.tree.command(
    name="testwatermark",
    description="Test watermarking a video with a Sora 2 style overlay.",
)
@app_commands.describe(video="The video file you want to overlay the watermark onto")
async def testwatermark(
    interaction: discord.Interaction,
    video: discord.Attachment,
):
    supported_types = ["video/mp4", "video/mov", "video/webm", "video/mkv"]
    if video.content_type not in supported_types and not video.filename.lower().endswith((".mp4", ".mov", ".webm", ".mkv")):
        await interaction.response.send_message(
            "Please upload a valid video file (MP4, MOV, WEBM, MKV).",
            ephemeral=True,
        )
        return

    if not os.path.exists(OVERLAY_FILENAME):
        await interaction.response.send_message(
            f"Server error: `{OVERLAY_FILENAME}` is missing.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(thinking=True)

    input_path = f"temp_input_{interaction.id}.mp4"
    output_path = f"temp_output_{interaction.id}.mp4"

    try:
        await video.save(input_path)

        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-i", input_path,
            "-i", OVERLAY_FILENAME,
            "-filter_complex", "[1:v]scale=iw*0.80:-1,format=rgba[wm];[0:v][wm]overlay=W-w-50:H-h-50",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-strict", "experimental",
            "-movflags", "+faststart",
            output_path
        ]

        process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            ffmpeg_cmd_no_audio = [
                "ffmpeg",
                "-y",
                "-i", input_path,
                "-i", OVERLAY_FILENAME,
                "-filter_complex", "[1:v]scale=iw*0.20:-1,format=rgba[wm];[0:v][wm]overlay=W-w-15:H-h-15",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-an",
                "-movflags", "+faststart",
                output_path
            ]
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd_no_audio,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

        if process.returncode != 0:
            err_msg = stderr.decode()[-500:] if stderr else "Unknown error"
            await interaction.followup.send(f"❌ FFmpeg processing failed: ```{err_msg}```", ephemeral=True)
            return

        if not os.path.exists(output_path):
            await interaction.followup.send("❌ Watermarked video output was not created.", ephemeral=True)
            return

        result_file = discord.File(output_path, filename="sora2_watermarked.mp4")
        await interaction.followup.send(
            content="✨ **Watermark test complete!**",
            file=result_file
        )

    except Exception as e:
        await interaction.followup.send(f"❌ An error occurred: {e}", ephemeral=True)

    finally:
        if os.path.exists(input_path):
            try:
                os.remove(input_path)
            except Exception:
                pass
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass


# --- Background Worker for Dub Queue ---
async def process_dub_queue():
    global is_processing_queue, current_dub_task
    is_processing_queue = True

    while not dub_queue.empty():
        task_info = await dub_queue.get()
        current_dub_task = task_info
        
        interaction = task_info["interaction"]
        file = task_info["target_file"]
        target_lang = task_info["target_lang"]
        progress_message = task_info["progress_message"]

        file_ext = os.path.splitext(file.filename)[1].lower()
        uploaded_file_path = f"source_media_{interaction.id}{file_ext}"
        dubbed_output_file = f"dubbed_media_{interaction.id}{file_ext if file_ext in ['.mp4', '.mov'] else '.mp3'}"
        final_output_file = f"final_dubbed_{interaction.id}{file_ext if file_ext in ['.mp4', '.mov'] else '.mp3'}"

        loop = asyncio.get_running_loop()
        start_time = time.time()

        def create_progress_embed(percent, stage_name, task_id="N/A"):
            elapsed = int(time.time() - start_time)
            mins, secs = divmod(elapsed, 60)
            time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
            
            filled_blocks = int(percent // 10)
            empty_blocks = 10 - filled_blocks
            bar = "[" + "█" * filled_blocks + "░" * empty_blocks + "]"
            
            embed = discord.Embed(
                title=f"🎬 ElevenLabs Dubbing — {target_lang.upper()}",
                color=discord.Color.blurple()
            )
            embed.add_field(
                name="Progress", 
                value=f"Dubbing... {percent}%\n`{bar}`\n⏱️ **Time:** {time_str}", 
                inline=False
            )
            embed.add_field(
                name="Task ID", 
                value=f"`{task_id}`", 
                inline=False
            )
            embed.set_footer(text=f"Elapsed: {time_str} | Stage: {stage_name}")
            return embed

        try:
            await file.save(uploaded_file_path)

            def check_has_video():
                if file_ext in ['.mp3', '.wav', '.aac', '.m4a']:
                    return False
                cmd = [
                    "ffprobe", "-v", "error", "-select_streams", "v:0", 
                    "-show_entries", "stream=codec_type", "-of", "default=noprint_wrappers=1:nokey=1", 
                    uploaded_file_path
                ]
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                return "video" in result.stdout

            has_video = await loop.run_in_executor(None, check_has_video)
            await progress_message.edit(embed=create_progress_embed(30, "uploading_to_elevenlabs"))

            def request_elevenlabs_dub():
                url_endpoint = "https://api.elevenlabs.io/v1/dubbing"
                headers = {"xi-api-key": ELEVENLABS_API_KEY}
                data = {
                    "target_lang": target_lang,
                    "mode": "automatic",
                    "watermark": "true"
                }
                mime_type = "video/mp4" if has_video else "audio/mpeg"
                if file_ext == ".wav":
                    mime_type = "audio/wav"
                elif file_ext == ".mov":
                    mime_type = "video/quicktime"

                with open(uploaded_file_path, "rb") as src_file:
                    files = {"file": (os.path.basename(uploaded_file_path), src_file, mime_type)}
                    response = requests.post(url_endpoint, headers=headers, data=data, files=files)
                return response.json()

            dub_response = await loop.run_in_executor(None, request_elevenlabs_dub)
            if "dubbing_id" not in dub_response:
                raise Exception(f"ElevenLabs API Error: {dub_response}")

            dubbing_id = dub_response["dubbing_id"]
            media_data = None

            async with aiohttp.ClientSession() as session:
                while True:
                    async with session.get(
                        f"https://api.elevenlabs.io/v1/dubbing/{dubbing_id}",
                        headers={"xi-api-key": ELEVENLABS_API_KEY}
                    ) as resp:
                        status_data = await resp.json()
                        status = status_data.get("status")
                        
                        if status == "dubbed":
                            await progress_message.edit(embed=create_progress_embed(80, "downloading_dubbed_media", dubbing_id))
                            async with session.get(
                                f"https://api.elevenlabs.io/v1/dubbing/{dubbing_id}/audio/{target_lang}",
                                headers={"xi-api-key": ELEVENLABS_API_KEY}
                            ) as media_resp:
                                if media_resp.status == 200:
                                    media_data = await media_resp.read()
                                    break
                                else:
                                    raise Exception("Failed to download dubbed media from ElevenLabs.")
                        elif status == "failed":
                            raise Exception(f"ElevenLabs dubbing failed: {status_data.get('error', 'Unknown error')}")
                        else:
                            await progress_message.edit(embed=create_progress_embed(50, f"processing ({status})", dubbing_id))
                        
                    await asyncio.sleep(5)

            with open(dubbed_output_file, "wb") as f:
                f.write(media_data)

            if has_video:
                await progress_message.edit(embed=create_progress_embed(90, "render_video_watermark", dubbing_id))

                def process_video_watermark():
                    if os.path.exists(OVERLAY_FILENAME):
                        filter_complex = (
                            "[1:v]scale=iw*0.20:-1,format=rgba[wm];"
                            "[0:v][wm]overlay=W-w-15:H-h-15[v]"
                        )
                        cmd = [
                            "ffmpeg", "-y",
                            "-i", uploaded_file_path,
                            "-i", OVERLAY_FILENAME,
                            "-i", dubbed_output_file,
                            "-filter_complex", filter_complex,
                            "-map", "[v]",
                            "-map", "2:a",
                            "-c:v", "libx264",
                            "-preset", "fast",
                            "-c:a", "aac",
                            "-shortest",
                            final_output_file
                        ]
                    else:
                        cmd = [
                            "ffmpeg", "-y",
                            "-i", uploaded_file_path,
                            "-i", dubbed_output_file,
                            "-map", "0:v",
                            "-map", "1:a",
                            "-c:v", "copy",
                            "-c:a", "aac",
                            "-shortest",
                            final_output_file
                        ]
                    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                await loop.run_in_executor(None, process_video_watermark)
            else:
                os.rename(dubbed_output_file, final_output_file)

            final_embed = discord.Embed(
                title="✨ Dubbing Complete!",
                description=f"Requested by {interaction.user.mention}\nTarget Language: `{target_lang.upper()}`",
                color=discord.Color.brand_green()
            )
            
            file_result = discord.File(final_output_file, filename=f"dubbed_{file.filename}")
            await progress_message.delete()
            await interaction.channel.send(embed=final_embed, file=file_result)

        except Exception as e:
            try:
                await progress_message.edit(content=f"❌ An error occurred during dubbing: `{e}`", embed=None)
            except:
                await interaction.followup.send(f"❌ An error occurred during dubbing: `{e}`", ephemeral=True)

        finally:
            for f in [uploaded_file_path, dubbed_output_file, final_output_file]:
                if os.path.exists(f):
                    try: os.remove(f)
                    except: pass
            
            dub_queue.task_done()
            current_dub_task = None

    is_processing_queue = False


@bot.tree.command(name="dub", description="Upload a video/audio file, dub it using ElevenLabs, and apply a watermark if video.")
@app_commands.describe(
    file="Upload your source media file (mp4, mp3, wav, etc.)",
    target_lang="Target language ISO code (e.g., es, fr, de, ja, zh, hi, pt, etc.)"
)
async def dub(interaction: discord.Interaction, file: discord.Attachment, target_lang: str):
    await interaction.response.defer(thinking=True)
    target_lang = target_lang.lower()

    # Send initial placeholder message for queue status
    queue_position = dub_queue.qsize() + (1 if current_dub_task else 0)
    progress_message = await interaction.followup.send(
        content=f"🕒 Added to dub queue! Position in queue: **{queue_position}**",
        ephemeral=True
    )

    # Push task to queue
    task_data = {
        "interaction": interaction,
        "target_file": file,
        "target_lang": target_lang,
        "progress_message": progress_message
    }
    await dub_queue.put(task_data)

    # Start queue processor if not already running
    if not is_processing_queue:
        bot.loop.create_task(process_dub_queue())
    else:
        await progress_message.edit(content=f"🕒 Added to dub queue. Current queue position: **{dub_queue.qsize()}**")


@bot.tree.command(name="queue", description="Check the current active and pending dubbing tasks in the queue.")
async def queue_status(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📋 ElevenLabs Dubbing Queue",
        color=discord.Color.gold()
    )

    if current_dub_task:
        user = current_dub_task["interaction"].user
        lang = current_dub_task["target_lang"].upper()
        embed.add_field(
            name="🔄 Currently Processing",
            value=f"**User:** {user.mention}\n**Language:** `{lang}`",
            inline=False
        )
    else:
        embed.add_field(
            name="🔄 Currently Processing",
            value="*No active task right now.*",
            inline=False
        )

    pending_items = list(dub_queue._queue)
    if pending_items:
        queue_list_str = ""
        for idx, item in enumerate(pending_items, start=1):
            u = item["interaction"].user
            l = item["target_lang"].upper()
            queue_list_str += f"`{idx}.` {u.mention} -> `{l}`\n"
        embed.add_field(
            name=f"⏳ Pending in Queue ({len(pending_items)})",
            value=queue_list_str,
            inline=False
        )
    else:
        embed.add_field(
            name="⏳ Pending in Queue",
            value="*Queue is empty.*",
            inline=False
        )

    await interaction.response.send_message(embed=embed, ephemeral=False)


if __name__ == "__main__":
    bot.run(BOT_TOKEN)