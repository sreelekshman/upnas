#!/usr/bin/env python
# pylint: disable=unused-argument
import logging
import os
import shutil
import asyncio
import httpx
import traceback
import html
import sys
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler, 
    filters, CallbackQueryHandler
)
from telegram.constants import ParseMode
from urllib.parse import urlparse

# Ensure functions module is in path
sys.path.append('/app/functions/series.py')
from functions.series import fetch_series_names, get_season, movie_folder_name, series_id, extract_season_episode

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

tmdb_key = os.getenv("TMDb_KEY")
bot_key = os.getenv("BOT_KEY")
server_ip = os.getenv("SERVER")

ALLOWED_USERS = {933423738, 648869439}

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    if update and isinstance(update, Update) and update.effective_chat:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"An error occurred: {html.escape(str(context.error))}",
            parse_mode=ParseMode.HTML
        )

async def purge_dirs(update: Update, directories: list) -> None:
    try:
        count = 0
        for directory_path in directories:
            if not os.path.exists(directory_path):
                continue
            for file in os.listdir(directory_path):
                file_path = os.path.join(directory_path, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    count += 1
        await update.message.reply_text(f"Purge Completed! Removed {count} files.")
    except Exception as e:
        await update.message.reply_text(f"Error during purge: {e}")

async def purge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await purge_dirs(update, ["/our_root/documents", "/our_root/videos"])

async def fpurge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await purge_dirs(update, ["/our_root/documents", "/our_root/videos", "/our_root/temp"])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(rf"Hi {user.mention_html()}! Send me a video file.")

async def async_copyfile_with_progress(src, dst, msg_obj, prefix=""):
    import time
    try:
        total_size = os.path.getsize(src)
    except Exception:
        total_size = 0
        
    copied = 0
    chunk_size = 1024 * 1024 * 4 # 4MB chunks
    last_update = time.time()
    
    with open(src, 'rb') as fsrc, open(dst, 'wb') as fdst:
        while True:
            chunk = fsrc.read(chunk_size)
            if not chunk:
                break
            fdst.write(chunk)
            copied += len(chunk)
            
            now = time.time()
            if now - last_update >= 3:
                if total_size > 0:
                    percent = min((copied / total_size) * 100, 100.0)
                    filled = int(percent / 10)
                    bar = f"[{'█' * filled}{'░' * (10 - filled)}]"
                    text = f"<b>💾 Copying...</b>\n<code>{bar} {percent:5.1f}%\n{copied/1048576:7.1f} MB / {total_size/1048576:7.1f} MB</code>"
                else:
                    text = f"<b>💾 Copying...</b>\n<code>{copied/1048576:7.1f} MB</code>"
                try:
                    full_text = f"{prefix}\n\n{text}" if prefix else text
                    if hasattr(msg_obj, 'edit_message_text'):
                        await msg_obj.edit_message_text(full_text, parse_mode=ParseMode.HTML)
                    else:
                        await msg_obj.edit_text(full_text, parse_mode=ParseMode.HTML)
                except Exception:
                    pass
                last_update = now
            await asyncio.sleep(0.01)

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Pong!")

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text('<b>🚫 Sorry, You are not allowed to use this bot.</b>', parse_mode=ParseMode.HTML)
        return

    media = update.message.video or update.message.document
    if not media:
        await update.message.reply_text('<b>⚠️ Please forward a video file.</b>', parse_mode=ParseMode.HTML)
        return

    status_msg = await update.message.reply_text("<b>🔍 Fetching file info...</b>", parse_mode=ParseMode.HTML)
    file_id = media.file_id
    expected_size = media.file_size
    retries = 3
    file_path = None
    import time

    for attempt in range(retries):
        stop_event = asyncio.Event()
        
        async def monitor_download(msg, exp_size, event):
            while not event.is_set():
                current_size = 0
                latest_time = 0
                now = time.time()
                for d in ['/our_root/documents', '/our_root/videos', '/our_root/temp', '/our_root/animation', '/our_root/audio', '/our_root/voice']:
                    if not os.path.exists(d):
                        continue
                    try:
                        for f in os.listdir(d):
                            fp = os.path.join(d, f)
                            if os.path.isfile(fp):
                                mtime = os.path.getmtime(fp)
                                if now - mtime < 60:
                                    size = os.path.getsize(fp)
                                    if mtime > latest_time:
                                        latest_time = mtime
                                        current_size = size
                    except Exception:
                        pass
                
                if current_size > 0:
                    if exp_size:
                        percent = min((current_size / exp_size) * 100, 100.0)
                        filled = int(percent / 10)
                        bar = f"[{'█' * filled}{'░' * (10 - filled)}]"
                        text = f"<b>📥 Downloading...</b>\n<code>{bar} {percent:5.1f}%\n{current_size/1048576:7.1f} MB / {exp_size/1048576:7.1f} MB</code>"
                    else:
                        text = f"<b>📥 Downloading...</b>\n<code>{current_size/1048576:7.1f} MB (Size Unknown)</code>"
                    try:
                        await msg.edit_text(text, parse_mode=ParseMode.HTML)
                    except Exception:
                        pass
                
                # Check for exit condition more frequently than 3s by sleeping in smaller chunks
                for _ in range(6):
                    if event.is_set():
                        break
                    await asyncio.sleep(0.5)
                
        monitor_task = asyncio.create_task(monitor_download(status_msg, expected_size, stop_event))

        try:
            file_path = await context.bot.get_file(file_id, read_timeout=7200, write_timeout=7200, connect_timeout=7200, pool_timeout=7200)
            stop_event.set()
            await monitor_task
            break
        except Exception as e:
            stop_event.set()
            await monitor_task
            error_message = str(e)
            if "httpx.RemoteProtocolError" in error_message or "Connection aborted" in error_message or "read timeout" in error_message.lower() or "timeout" in error_message.lower():
                if attempt < retries - 1:
                    await status_msg.edit_text(f'<b>⚠️ Network error/Timeout.</b> Retrying ({attempt+1}/{retries})...', parse_mode=ParseMode.HTML)
                    await asyncio.sleep(2)
                    continue
            if "Wrong file_id or the file is temporarily unavailable" in error_message:
                await status_msg.edit_text('<b>❌ The file is temporarily unavailable.</b> Try again later.', parse_mode=ParseMode.HTML)
                return
            await status_msg.edit_text(f'<b>❌ Error fetching file:</b>\n<code>{html.escape(str(e))}</code>', parse_mode=ParseMode.HTML)
            return

    if not file_path:
        return

    context.user_data['file_path'] = file_path
    context.user_data['video'] = media
    
    # Calculate downloaded size for history
    context.user_data['history'] = []
    try:
        real_size = os.path.getsize(file_path.file_path)
    except:
        real_size = expected_size or 0
        
    if real_size > 0:
        sz_mb = real_size / 1048576
        dl_text = f"<b>📥 Downloaded</b>\n<code>[██████████] 100.0%\n{sz_mb:7.1f} MB / {sz_mb:7.1f} MB</code>"
    else:
        dl_text = "<b>📥 Downloaded</b>"
    context.user_data['history'].append(dl_text)
    history_str = "\n\n".join(context.user_data['history'])

    keyboard = [
        [InlineKeyboardButton('Movie', callback_data='movie')],
        [InlineKeyboardButton('TV Series', callback_data='tv_series')]
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await status_msg.edit_text(f'{history_str}\n\n<b>🎬 Choose a category:</b>', reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def handle_tv_series(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    choice = str(query.data)
    await query.answer()

    video = context.user_data.get('video')
    if not video:
        await query.edit_message_text("<b>⚠️ Session expired.</b> Please forward the video again.", parse_mode=ParseMode.HTML)
        return
        
    file_name = video.file_name
    location = context.user_data.get('location')

    history_str = "\n\n".join(context.user_data.get('history', []))
    await query.edit_message_text(text=f"{history_str}\n\n<b>⚙️ Processing:</b> <code>{html.escape(choice)}</code>", parse_mode=ParseMode.HTML)

    s_id = await series_id(choice)
    if not s_id:
        context.user_data['force_save_choice'] = choice
        keyboard = [[
            InlineKeyboardButton('Force Save', callback_data='force_save'),
            InlineKeyboardButton('Cancel', callback_data='cancel')
        ]]
        await query.edit_message_text(f"{history_str}\n\n<b>⚠️ Could not find TV Series:</b> <code>{html.escape(choice)}</code> on TMDb.\nForce save?", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode=ParseMode.HTML)
        return

    season, ep_no = extract_season_episode(file_name)
    if ep_no is None:
        await query.edit_message_text("<b>⚠️ Could not extract episode number from filename.</b>", parse_mode=ParseMode.HTML)
        return

    if season is None:
        season = await get_season(ep_no, s_id)
        
    if season is None:
        season = 1 # Fallback
        
    url = f"https://api.themoviedb.org/3/tv/{s_id}?api_key={tmdb_key}&append_to_response=season/{season}"
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.warning(f"Error fetching episode details: {e}")
            data = {}

    episodes = data.get(f'season/{season}', {}).get('episodes', [])
    target = [ep for ep in episodes if ep.get('episode_number') == ep_no]
    
    ep_name = f"Episode {ep_no}"
    image_url = None

    if target:
        ep_name = target[0].get('name', ep_name)
        still_path = target[0].get("still_path")
        if still_path:
            image_url = f'https://image.tmdb.org/t/p/original{still_path}'

    if not image_url:
        season_poster = data.get(f'season/{season}', {}).get('poster_path')
        series_poster = data.get('poster_path')
        best_poster = season_poster or series_poster
        if best_poster:
            image_url = f'https://image.tmdb.org/t/p/original{best_poster}'
            
    if image_url:
        poster_to_send = image_url
    else:
        poster_to_send = None

    destination_dir = f'/media/TV Shows/{choice}/Season {season}'
    os.makedirs(destination_dir, exist_ok=True)
    
    file_ext = os.path.splitext(file_name)[1]
    final_dest = os.path.join(destination_dir, f'S{season} E{ep_no} {ep_name}{file_ext}')
    
    try:
        await async_copyfile_with_progress(f'/our_root{location}', final_dest, query, prefix=history_str)
        if poster_to_send:
            try:
                await query.message.delete()
            except Exception:
                pass
            try:
                final_size = os.path.getsize(final_dest)
                sz_mb = final_size / 1048576
                cp_text = f"<b>💾 Copied</b>\n<code>[██████████] 100.0%\n{sz_mb:7.1f} MB / {sz_mb:7.1f} MB</code>"
                context.user_data['history'].append(cp_text)
            except:
                pass
            history_str = "\n\n".join(context.user_data.get('history', []))
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=poster_to_send, caption=f"{history_str}\n\n<b>✅ {html.escape(ep_name)}</b>\nSaved to: <code>{html.escape(final_dest)}</code>", parse_mode=ParseMode.HTML)
        else:
            try:
                final_size = os.path.getsize(final_dest)
                sz_mb = final_size / 1048576
                cp_text = f"<b>💾 Copied</b>\n<code>[██████████] 100.0%\n{sz_mb:7.1f} MB / {sz_mb:7.1f} MB</code>"
                context.user_data['history'].append(cp_text)
            except:
                pass
            history_str = "\n\n".join(context.user_data.get('history', []))
            await query.edit_message_text(text=f"{history_str}\n\n<b>✅ {html.escape(ep_name)}</b>\nSaved to: <code>{html.escape(final_dest)}</code>", parse_mode=ParseMode.HTML)
    except Exception as e:
        await query.edit_message_text(text=f'<b>❌ Failed to copy file:</b>\n<code>{html.escape(str(e))}</code>', parse_mode=ParseMode.HTML)


async def new_series(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="<b>📝 Enter the name of the Series:</b>", parse_mode=ParseMode.HTML)
    context.user_data['awaiting_series_name'] = True

async def handle_user_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USERS:
        return
        
    if not context.user_data.get('awaiting_series_name'):
        return

    context.user_data['awaiting_series_name'] = False
    choice = str(update.message.text).strip()
    
    video = context.user_data.get('video')
    if not video:
        await update.message.reply_text("<b>⚠️ Session expired.</b> Please forward the video again.", parse_mode=ParseMode.HTML)
        return
        
    file_name = video.file_name
    location = context.user_data.get('location')

    status_msg = history_str = "\n\n".join(context.user_data.get('history', []))
    status_msg = await update.message.reply_text(f"{history_str}\n\n<b>⚙️ Processing series:</b> <code>{html.escape(choice)}</code>", parse_mode=ParseMode.HTML)
    
    s_id = await series_id(choice)
    if not s_id:
        context.user_data['force_save_choice'] = choice
        keyboard = [[
            InlineKeyboardButton('Force Save', callback_data='force_save'),
            InlineKeyboardButton('Cancel', callback_data='cancel')
        ]]
        await status_msg.edit_text(f"{history_str}\n\n<b>⚠️ Could not find TV Series:</b> <code>{html.escape(choice)}</code> on TMDb.\nForce save?", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode=ParseMode.HTML)
        return

    season, ep_no = extract_season_episode(file_name)
    if ep_no is None:
        await status_msg.edit_text("<b>⚠️ Could not extract episode number from filename.</b>", parse_mode=ParseMode.HTML)
        return

    if season is None:
        season = await get_season(ep_no, s_id)
        if season is None:
            season = 1
            
    url = f"https://api.themoviedb.org/3/tv/{s_id}?api_key={tmdb_key}&append_to_response=season/{season}"
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.warning(f"Error fetching episode details: {e}")
            data = {}

    episodes = data.get(f'season/{season}', {}).get('episodes', [])
    target = [ep for ep in episodes if ep.get('episode_number') == ep_no]
    
    ep_name = f"Episode {ep_no}"
    image_url = None

    if target:
        ep_name = target[0].get('name', ep_name)
        still_path = target[0].get("still_path")
        if still_path:
            image_url = f'https://image.tmdb.org/t/p/original{still_path}'

    if not image_url:
        season_poster = data.get(f'season/{season}', {}).get('poster_path')
        series_poster = data.get('poster_path')
        best_poster = season_poster or series_poster
        if best_poster:
            image_url = f'https://image.tmdb.org/t/p/original{best_poster}'
            
    if image_url:
        poster_to_send = image_url
    else:
        poster_to_send = None

    destination_dir = f'/media/TV Shows/{choice}/Season {season}'
    os.makedirs(destination_dir, exist_ok=True)
    
    file_ext = os.path.splitext(file_name)[1]
    final_dest = os.path.join(destination_dir, f'S{season} E{ep_no} {ep_name}{file_ext}')
    
    try:
        await async_copyfile_with_progress(f'/our_root{location}', final_dest, status_msg, prefix=history_str)
        if poster_to_send:
            try:
                await status_msg.delete()
            except Exception:
                pass
            try:
                final_size = os.path.getsize(final_dest)
                sz_mb = final_size / 1048576
                cp_text = f"<b>💾 Copied</b>\n<code>[██████████] 100.0%\n{sz_mb:7.1f} MB / {sz_mb:7.1f} MB</code>"
                context.user_data['history'].append(cp_text)
            except:
                pass
            history_str = "\n\n".join(context.user_data.get('history', []))
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=poster_to_send, caption=f"{history_str}\n\n<b>✅ {html.escape(ep_name)}</b>\nSaved to: <code>{html.escape(final_dest)}</code>", parse_mode=ParseMode.HTML)
        else:
            try:
                final_size = os.path.getsize(final_dest)
                sz_mb = final_size / 1048576
                cp_text = f"<b>💾 Copied</b>\n<code>[██████████] 100.0%\n{sz_mb:7.1f} MB / {sz_mb:7.1f} MB</code>"
                context.user_data['history'].append(cp_text)
            except:
                pass
            history_str = "\n\n".join(context.user_data.get('history', []))
            await status_msg.edit_text(text=f"{history_str}\n\n<b>✅ {html.escape(ep_name)}</b>\nSaved to: <code>{html.escape(final_dest)}</code>", parse_mode=ParseMode.HTML)
    except Exception as e:
        await status_msg.edit_text(text=f'<b>❌ Failed to copy file:</b>\n<code>{html.escape(str(e))}</code>', parse_mode=ParseMode.HTML)

async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    choice = query.data
    await query.answer()

    file_path = context.user_data.get('file_path')
    video = context.user_data.get('video')
    
    if not file_path or not video:
        await query.edit_message_text("<b>⚠️ Session expired.</b> Please forward the video again.", parse_mode=ParseMode.HTML)
        return

    parsed_url = urlparse(file_path.file_path)
    path_components = parsed_url.path.split("/")
    location = "/" + "/".join(path_components[-2:])
    context.user_data['location'] = location
    file_name = video.file_name

    if choice == 'movie':
        history_str = "\n\n".join(context.user_data.get('history', []))
        await query.edit_message_text(text=f"{history_str}\n\n<b>⚙️ Movie selected. Processing...</b>", parse_mode=ParseMode.HTML)
        folder_name = movie_folder_name(file_name)
        
        if not folder_name:
            folder_name = os.path.splitext(file_name)[0]
            
        dest_dir = f'/media/Movies/{folder_name}'
        os.makedirs(dest_dir, exist_ok=True)
        final_dest = f'{dest_dir}/{file_name}'
        
        try:
            await async_copyfile_with_progress(f'/our_root{location}', final_dest, query, prefix=history_str)
        except Exception as e:
            await query.edit_message_text(text=f'<b>❌ Failed to copy file:</b>\n<code>{html.escape(str(e))}</code>', parse_mode=ParseMode.HTML)
            return
            
        poster = None
        try:
            movie_name = folder_name
            year = ""
            
            # Extract year robustly
            year_match = re.search(r"\[?\(?(\d{4})\]?\)?", file_name)
            if year_match:
                year = year_match.group(1)
                
            if folder_name.endswith(f"({year})"):
                movie_name = folder_name[:-7].strip()
            elif folder_name.endswith(f" {year}"):
                movie_name = folder_name[:-5].strip()
                
            search_query = movie_name.replace(" ", "+")
            
            url = f"https://api.themoviedb.org/3/search/movie?query={search_query}&api_key={tmdb_key}"
            if year:
                url += f"&primary_release_year={year}"
                
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
                
            results = data.get("results", [])
            if results:
                match = next((m for m in results if m.get('release_date', '').startswith(year)), results[0])
                poster_path = match.get("poster_path")
                if poster_path:
                    poster = f'https://image.tmdb.org/t/p/original{poster_path}'
        except Exception as e:
            logger.warning(f"Poster not found or error occurred: {e}")
            
        if poster:
            try:
                await query.message.delete()
            except Exception:
                pass
            try:
                final_size = os.path.getsize(final_dest)
                sz_mb = final_size / 1048576
                cp_text = f"<b>💾 Copied</b>\n<code>[██████████] 100.0%\n{sz_mb:7.1f} MB / {sz_mb:7.1f} MB</code>"
                context.user_data['history'].append(cp_text)
            except:
                pass
            history_str = "\n\n".join(context.user_data.get('history', []))
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=poster, caption=f"{history_str}\n\n<b>✅ Movie Saved</b>\nSaved to: <code>{html.escape(final_dest)}</code>", parse_mode=ParseMode.HTML)
        else:
            try:
                final_size = os.path.getsize(final_dest)
                sz_mb = final_size / 1048576
                cp_text = f"<b>💾 Copied</b>\n<code>[██████████] 100.0%\n{sz_mb:7.1f} MB / {sz_mb:7.1f} MB</code>"
                context.user_data['history'].append(cp_text)
            except:
                pass
            history_str = "\n\n".join(context.user_data.get('history', []))
            await query.edit_message_text(text=f"{history_str}\n\n<b>✅ Movie Saved</b>\nSaved to: <code>{html.escape(final_dest)}</code>", parse_mode=ParseMode.HTML)

    elif choice == 'tv_series':
        keyboard = []
        series_list = fetch_series_names('/media/TV Shows')
        
        row = []
        for serie in series_list:
            row.append(InlineKeyboardButton(serie, callback_data=serie))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
            
        keyboard.append([InlineKeyboardButton('➕ New Series', callback_data='new')])
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        history_str = "\n\n".join(context.user_data.get('history', []))
        await query.edit_message_text(text=f"{history_str}\n\n<b>📺 Select the Series:</b>", reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def handle_force_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    choice = context.user_data.get('force_save_choice')
    video = context.user_data.get('video')
    location = context.user_data.get('location')
    
    if not choice or not video or not location:
        await query.edit_message_text("<b>⚠️ Session expired.</b> Please try again.", parse_mode=ParseMode.HTML)
        return
        
    file_name = video.file_name
    season, ep_no = extract_season_episode(file_name)
    
    if season is None:
        season = 1
    if ep_no is None:
        # Fallback if episode number is missing
        ep_no = 1
        
    destination_dir = f'/media/TV Shows/{choice}/Season {season}'
    os.makedirs(destination_dir, exist_ok=True)
    
    file_ext = os.path.splitext(file_name)[1]
    final_dest = os.path.join(destination_dir, f'{choice} - S{season:02d}E{ep_no:02d}{file_ext}')
    
    history_str = "\n\n".join(context.user_data.get('history', []))
    await query.edit_message_text(text=f"{history_str}\n\n<b>⚙️ Force saving to:</b>\n<code>{html.escape(final_dest)}</code>", parse_mode=ParseMode.HTML)
    
    try:
        await async_copyfile_with_progress(f'/our_root{location}', final_dest, query, prefix=history_str)
        try:
            final_size = os.path.getsize(final_dest)
            sz_mb = final_size / 1048576
            cp_text = f"<b>💾 Copied</b>\n<code>[██████████] 100.0%\n{sz_mb:7.1f} MB / {sz_mb:7.1f} MB</code>"
            context.user_data['history'].append(cp_text)
        except:
            pass
        history_str = "\n\n".join(context.user_data.get('history', []))
        await query.edit_message_text(text=f"{history_str}\n\n<b>✅ Successfully force saved to:</b>\n<code>{html.escape(final_dest)}</code>", parse_mode=ParseMode.HTML)
    except Exception as e:
        await query.edit_message_text(text=f'<b>❌ Failed to copy file:</b>\n<code>{html.escape(str(e))}</code>', parse_mode=ParseMode.HTML)

async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("<b>🚫 Operation cancelled.</b>", parse_mode=ParseMode.HTML)

def main() -> None:
    application = Application.builder().token(bot_key).base_url(f"{server_ip}/bot").base_file_url(f"{server_ip}/file/bot").local_mode(local_mode=True).build()

    application.add_error_handler(error_handler)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("purge", purge))
    application.add_handler(CommandHandler("fpurge", fpurge))
    application.add_handler(CommandHandler("ping", ping))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_reply))
    application.add_handler(MessageHandler(filters.FORWARDED, handle_video))
    application.add_handler(MessageHandler(filters.Document.VIDEO | filters.VIDEO, handle_video))
    
    application.add_handler(CallbackQueryHandler(new_series, pattern='^new$'))
    application.add_handler(CallbackQueryHandler(handle_force_save, pattern='^force_save$'))
    application.add_handler(CallbackQueryHandler(handle_cancel, pattern='^cancel$'))
    application.add_handler(CallbackQueryHandler(handle_button_click, pattern='^(movie|tv_series)$'))
    application.add_handler(CallbackQueryHandler(handle_tv_series, pattern='^(?!movie|tv_series|new).*$'))

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
