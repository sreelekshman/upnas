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

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Pong!")

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text('Sorry, You are not allowed to use this bot.')
        return

    media = update.message.video or update.message.document
    if not media:
        await update.message.reply_text('Please forward a video file.')
        return

    status_msg = await update.message.reply_text("Fetching file info...")
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
                        text = f"Downloading... {percent:.1f}% ({current_size/1048576:.1f}MB / {exp_size/1048576:.1f}MB)"
                    else:
                        text = f"Downloading... {current_size/1048576:.1f}MB"
                    try:
                        await msg.edit_text(text)
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
                    await status_msg.edit_text(f'Network error/Timeout. Retrying ({attempt+1}/{retries})...')
                    await asyncio.sleep(2)
                    continue
            if "Wrong file_id or the file is temporarily unavailable" in error_message:
                await status_msg.edit_text('The file is temporarily unavailable. Try again later.')
                return
            await status_msg.edit_text(f'Error fetching file: {e}')
            return

    if not file_path:
        return

    context.user_data['file_path'] = file_path
    context.user_data['video'] = media

    keyboard = [
        [InlineKeyboardButton('Movie', callback_data='movie')],
        [InlineKeyboardButton('TV Series', callback_data='tv_series')]
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await status_msg.edit_text('Choose an option:', reply_markup=reply_markup)

async def handle_tv_series(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    choice = str(query.data)
    await query.answer()

    video = context.user_data.get('video')
    if not video:
        await query.edit_message_text("Session expired. Please forward the video again.")
        return
        
    file_name = video.file_name
    location = context.user_data.get('location')

    await query.edit_message_text(text=f"Processing {choice}...")

    s_id = await series_id(choice)
    if not s_id:
        context.user_data['force_save_choice'] = choice
        keyboard = [[
            InlineKeyboardButton('Force Save', callback_data='force_save'),
            InlineKeyboardButton('Cancel', callback_data='cancel')
        ]]
        await query.edit_message_text(f"Could not find TV Series: {choice} on TMDb. Force save?", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        return

    season, ep_no = extract_season_episode(file_name)
    if ep_no is None:
        await query.edit_message_text("Could not extract episode number from filename.")
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
        except httpx.RequestError as e:
            await query.edit_message_text(f"Error fetching episode details: {e}")
            return

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
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image_url, caption=ep_name)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=ep_name)

    destination_dir = f'/media/TV Shows/{choice}/Season {season}'
    os.makedirs(destination_dir, exist_ok=True)
    
    file_ext = os.path.splitext(file_name)[1]
    final_dest = os.path.join(destination_dir, f'S{season} E{ep_no} {ep_name}{file_ext}')
    
    try:
        shutil.copyfile(f'/our_root{location}', final_dest)
        await query.edit_message_text(text=f'Saved to: {final_dest}')
    except Exception as e:
        await query.edit_message_text(text=f'Failed to copy file: {e}')


async def new_series(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="Enter the name of the Series:")
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
        await update.message.reply_text("Session expired. Please forward the video again.")
        return
        
    file_name = video.file_name
    location = context.user_data.get('location')

    status_msg = await update.message.reply_text(f"Processing series: {choice}...")
    
    s_id = await series_id(choice)
    if not s_id:
        context.user_data['force_save_choice'] = choice
        keyboard = [[
            InlineKeyboardButton('Force Save', callback_data='force_save'),
            InlineKeyboardButton('Cancel', callback_data='cancel')
        ]]
        await status_msg.edit_text(f"Could not find TV Series: {choice} on TMDb. Force save?", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        return

    season, ep_no = extract_season_episode(file_name)
    if ep_no is None:
        await status_msg.edit_text("Could not extract episode number from filename.")
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
        except httpx.RequestError as e:
            await status_msg.edit_text(f"Error fetching episode details: {e}")
            return

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
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image_url, caption=ep_name)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=ep_name)

    destination_dir = f'/media/TV Shows/{choice}/Season {season}'
    os.makedirs(destination_dir, exist_ok=True)
    
    file_ext = os.path.splitext(file_name)[1]
    final_dest = os.path.join(destination_dir, f'S{season} E{ep_no} {ep_name}{file_ext}')
    
    try:
        shutil.copyfile(f'/our_root{location}', final_dest)
        await status_msg.edit_text(text=f'Saved to: {final_dest}')
    except Exception as e:
        await status_msg.edit_text(text=f'Failed to copy file: {e}')

async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    choice = query.data
    await query.answer()

    file_path = context.user_data.get('file_path')
    video = context.user_data.get('video')
    
    if not file_path or not video:
        await query.edit_message_text("Session expired. Please forward the video again.")
        return

    parsed_url = urlparse(file_path.file_path)
    path_components = parsed_url.path.split("/")
    location = "/" + "/".join(path_components[-2:])
    context.user_data['location'] = location
    file_name = video.file_name

    if choice == 'movie':
        await query.edit_message_text(text="Movie selected. Processing...")
        folder_name = movie_folder_name(file_name)
        
        if not folder_name:
            folder_name = os.path.splitext(file_name)[0]
            
        dest_dir = f'/media/Movies/{folder_name}'
        os.makedirs(dest_dir, exist_ok=True)
        final_dest = f'{dest_dir}/{file_name}'
        
        try:
            shutil.copyfile(f'/our_root{location}', final_dest)
        except Exception as e:
            await query.edit_message_text(text=f'Failed to copy file: {e}')
            return
            
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
                    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=poster, caption=folder_name)
        except Exception as e:
            logger.warning(f"Poster not found or error occurred: {e}")
            
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'{file_name} has been pushed to {final_dest}')

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
        await query.edit_message_text('Select the Series:', reply_markup=reply_markup)

async def handle_force_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    choice = context.user_data.get('force_save_choice')
    video = context.user_data.get('video')
    location = context.user_data.get('location')
    
    if not choice or not video or not location:
        await query.edit_message_text("Session expired. Please try again.")
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
    
    await query.edit_message_text(text=f'Force saving to {final_dest}...')
    
    try:
        shutil.copyfile(f'/our_root{location}', final_dest)
        await query.edit_message_text(text=f'Successfully forced saved to: {final_dest}')
    except Exception as e:
        await query.edit_message_text(text=f'Failed to copy file: {e}')

async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Operation cancelled.")

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
