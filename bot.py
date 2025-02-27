#!/usr/bin/env python
# pylint: disable=unused-argument
# This program is dedicated to the public domain under the CC0 license.


import logging
import telegram
import os
import shutil
import requests
import sys
sys.path.append('/app/functions/series.py')

from functions.series import *

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler, ConversationHandler
from urllib.parse import urlparse

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

tmdb_key = os.getenv("TMDb_KEY")
bot_key = os.getenv("BOT_KEY")
server_ip = os.getenv("SERVER")

async def purge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        directory_path = "/our_root/documents"
        files = os.listdir(directory_path)
        for file in files:
            file_path = os.path.join(directory_path, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
        directory_path = "/our_root/videos"
        files = os.listdir(directory_path)
        for file in files:
            file_path = os.path.join(directory_path, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
        await update.message.reply_text("Purge Completed!")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def fpurge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        directory_path = "/our_root/documents"
        files = os.listdir(directory_path)
        for file in files:
            file_path = os.path.join(directory_path, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
        directory_path = "/our_root/videos"
        files = os.listdir(directory_path)
        for file in files:
            file_path = os.path.join(directory_path, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
        directory_path = "/our_root/temp"
        files = os.listdir(directory_path)
        for file in files:
            file_path = os.path.join(directory_path, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
        await update.message.reply_text("Purge Completed!")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}!",
    )

async def ping(update, context):
    await update.message.reply_text("Pong!")

async def handle_video(update, context):
    if (update.effective_user.id == 933423738 or update.effective_user.id == 648869439):
        media = update.message.video if update.message.video else update.message.document
        if media:
            file_id = media.file_id
            while True:
                try:
                    file_path = await context.bot.get_file(file_id, read_timeout=None)
                    break
                except Exception as e:
                    error_message = str(e)
                    if "httpx.RemoteProtocolError: Server disconnected without sending a response" in error_message:
                        await update.message.reply_text(f'Server disconnected. Retrying...')
                    elif "Wrong file_id or the file is temporarily unavailable" in error_message:
                        await update.message.reply_text(f'The file is temporarily unavailable. Try again later.')
                        return False
            context.user_data['file_path'] = file_path
            context.user_data['video'] = media

            keyboard = [[InlineKeyboardButton('Movie', callback_data='movie'), InlineKeyboardButton('TV Series', callback_data='tv_series')]]
            reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
            await update.message.reply_text('Choose an option:', reply_markup=reply_markup)
        else:
            await update.message.reply_text('Please forward a video file.')
    else:
        await update.message.reply_text('Sorry, You are not allowed to use this bot.')

async def handle_tv_series(update, context):
    query = update.callback_query
    choice = str(query.data)  # Access the callback data from the button
    video = context.user_data.get('video')
    file_name = video.file_name
    location = context.user_data.get('location')
    series_ID = series_id(choice)

    await query.edit_message_text(text=f"{choice}")
    season, ep_no = extract_season_episode(file_name)
    if season == None:
        season = get_season(ep_no, series_ID)
    url = f"https://api.themoviedb.org/3/tv/{series_ID}?api_key={tmdb_key}&append_to_response=season/{season}"
    response = requests.get(url).json()
    target = [movie for movie in response[f'season/{season}']['episodes'] if movie['episode_number'] == ep_no]
    image_url = f'https://image.tmdb.org/t/p/original{target[0]["still_path"]}'
    ep_name = target[0]['name']
    await query.edit_message_text(text = f"{ep_name}")
    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image_url, caption=f"{ep_name}")
    destination = f'/media/TV Shows/{choice}/Season {season}'
    if not os.path.isdir(destination):
        os.makedirs(destination)
    dest = shutil.copyfile(f'/our_root{location}', f'{destination}/S{season} E{ep_no} {ep_name}{file_name[-4:]}')
    await query.edit_message_text(text = f'{file_name} has been pushed to {dest}')

async def new_series(update, context):
    query = update.callback_query
    choice = query.data  # Access the callback data from the button
    await query.edit_message_text(text=f"Enter the name of the Series:")
    
async def handle_user_reply(update, context):
    user_reply = str(update.message.text)
    choice = user_reply
    video = context.user_data.get('video')
    if (context.user_data.get('video')) == None:
        return
    file_name = video.file_name
    location = context.user_data.get('location')
    os.mkdir(f'/media/TV Shows/{user_reply}')
    series_ID = series_id(choice)
    season, ep_no = extract_season_episode(file_name)
    if season == None:
        season = get_season(ep_no, series_ID)
    url = f"https://api.themoviedb.org/3/tv/{series_ID}?api_key={tmdb_key}&append_to_response=season/{season}"
    response = requests.get(url).json()
    target = [movie for movie in response[f'season/{season}']['episodes'] if movie['episode_number'] == ep_no]
    image_url = f'https://image.tmdb.org/t/p/original{target[0]["still_path"]}'
    ep_name = target[0]['name']
    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image_url, caption=f"{ep_name}")
    destination = f'/media/TV Shows/{choice}/Season {season}'
    if not os.path.isdir(destination):
        os.makedirs(destination)
    dest = shutil.copyfile(f'/our_root{location}', f'{destination}/S{season} E{ep_no} {ep_name}{file_name[-4:]}')
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f'{file_name} has been pushed to {dest}')

async def handle_button_click(update, context):
    file_path = context.user_data.get('file_path')
    video = context.user_data.get('video')

    query = update.callback_query
    choice = query.data  # Access the callback data from the button

    # Your existing code to get the file path
    parsed_url = urlparse(file_path.file_path)
    path_components = parsed_url.path.split("/")
    location = "/"+"/".join(path_components[-2:])
    context.user_data['location'] = location
    file_name = video.file_name

    # Handle the user's choice based on the callback data
    if choice == 'movie':
        await query.answer(text='Movie selected')
        await query.edit_message_text(text=f"Movie selected.")
        folder_name = movie_folder_name(file_name)
        os.mkdir(f'/media/Movies/{folder_name}')
        dest = shutil.copyfile(f'/our_root{location}', f'/media/Movies/{folder_name}/{file_name}')
        try:
            query = folder_name[:-7]
            query = query.replace(" ", "+")
            year = folder_name[-5:-1]
            url = requests.get(f"https://api.themoviedb.org/3/search/movie?query={query}&api_key={tmdb_key}").json()
            if url["results"][0]['release_date'].startswith(f'{year}'):
                poster =f'https://image.tmdb.org/t/p/original{url["results"][0]["poster_path"]}'
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=poster, caption=folder_name)
        except Exception as e:
            print("Poster not found.")
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'{file_name} has been pushed to {dest}')
    elif choice == 'tv_series':
        await query.answer(text='TV Series selected')
        await query.edit_message_text(text=f"TV Series selected.")
        keyboard = []
        series = fetch_series_names('/media/TV Shows')
        for serie in series:
            keyboard.append([InlineKeyboardButton(serie, callback_data=serie)])
        keyboard.append([InlineKeyboardButton('New Series', callback_data='new')])
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await query.edit_message_text('Select the Series:', reply_markup=reply_markup)
        #dest = shutil.copyfile(f'/our_root{location}', f'/media/TV Shows/{file_name}')
    else:
        await query.answer(text='Invalid choice!')
        return
        
def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(bot_key).base_url(f"{server_ip}/bot").base_file_url(f"{server_ip}/file/bot").local_mode(local_mode=True).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("purge", purge))
    application.add_handler(CommandHandler("fpurge", fpurge))
    application.add_handler(CommandHandler("ping", ping))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_reply))

    # on non command i.e message - echo the message on Telegram
    application.add_handler(MessageHandler(filters.FORWARDED, handle_video))
    application.add_handler(CallbackQueryHandler(new_series, pattern='new'))
    application.add_handler(CallbackQueryHandler(handle_button_click, pattern='^(movie|tv_series)$'))
    application.add_handler(CallbackQueryHandler(handle_tv_series))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
