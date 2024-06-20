#!/usr/bin/env python
# pylint: disable=unused-argument
# This program is dedicated to the public domain under the CC0 license.


import logging
import telegram
import os
import shutil
import re
import requests
import json

from telegram import ForceReply, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler, ConversationHandler
from urllib.parse import urlparse

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

CHOOSING, CHOSEN = range(2)

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
        reply_markup=ForceReply(selective=True),
    )

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Echo the user message."""
    await update.message.reply_text(update.message.text)

async def handle_video(update, context):
    if (update.effective_user.id == 933423738 or update.effective_user.id == 648869439):
        if update.message.video:
            video = update.message.video
            file_id = video.file_id
            file_path = (await context.bot.get_file(file_id, read_timeout=None))

            # Store the file_path and video in context.user_data
            context.user_data['file_path'] = file_path
            context.user_data['video'] = video

            keyboard = [[InlineKeyboardButton('Movie', callback_data='movie'), InlineKeyboardButton('TV Series', callback_data='tv_series')]]
            reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
            await update.message.reply_text('Choose an option:', reply_markup=reply_markup)
            return CHOOSING

        elif update.message.document:
            document = update.message.document
            file_id = document.file_id
            try:
                file_path = await context.bot.get_file(file_id, read_timeout=None)
            except Exception as e:
                await update.message.reply_text(f"Error: {e}")
                return

            # Store the file_path and video in context.user_data
            context.user_data['file_path'] = file_path
            context.user_data['video'] = document
            keyboard = [[InlineKeyboardButton('Movie', callback_data='movie'), InlineKeyboardButton('TV Series', callback_data='tv_series')]]
            reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
            await update.message.reply_text('Choose an option:', reply_markup=reply_markup)
            return CHOOSING
        else:
            await update.message.reply_text('Please forward a video file.')
    else:
        await update.message.reply_text('Sorry, You are not allowed to use this bot.')

async def handle_button_click(update, context):
    file_path = context.user_data.get('file_path')
    video = context.user_data.get('video')

    query = update.callback_query
    choice = query.data  # Access the callback data from the button

    # Your existing code to get the file path
    parsed_url = urlparse(file_path.file_path)
    path_components = parsed_url.path.split("/")
    location = "/"+"/".join(path_components[-2:])
    file_name = video.file_name

    # Handle the user's choice based on the callback data
    if choice == 'movie':
        await query.answer(text='Movie selected')
        await query.edit_message_text(text=f"Movie selected.")
        folder_name = movie_folder_name(file_name)
        os.mkdir(f'/media/Movies/{folder_name}')
        dest = shutil.copyfile(f'/our_root{location}', f'/media/Movies/{folder_name}/{file_name}')
        await query.edit_message_text(text = f'{file_name} has been pushed to {dest}')
    elif choice == 'tv_series':
        await query.answer(text='TV Series selected')
        await query.edit_message_text(text=f"TV Series selected.")
        keyboard = [[InlineKeyboardButton('One Piece', callback_data='onepiece'), InlineKeyboardButton('Other', callback_data='other')]]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await query.edit_message_text('Select the Series:', reply_markup=reply_markup)
        #dest = shutil.copyfile(f'/our_root{location}', f'/media/TV Shows/{file_name}')
    elif choice == 'onepiece':
        await query.answer(text='One Piece selected')
        await query.edit_message_text(text=f"One Piece selected.")

        #OnePiece Anime Season and Episode Metadata
        def get_season(ep_no):
            if 1<=ep_no<=61:
                season = 1
            elif 62<=ep_no<=77:
                season = 2
            elif 78<=ep_no<=91:
                season = 3
            elif 92<=ep_no<=130:
                season = 4
            elif 131<=ep_no<=143:
                season = 5
            elif 144<=ep_no<=195:
                season = 6
            elif 196<=ep_no<=228:
                season = 7
            elif 229<=ep_no<=263:
                season = 8
            elif 264<=ep_no<=336:
                season = 9
            elif 337<=ep_no<=381:
                season = 10
            return season
        
        ep_no = int(file_name[12:15])
        season = get_season(ep_no)
        print(season)
        url = f"https://api.themoviedb.org/3/tv/37854?api_key=API_KEY&append_to_response=season/{season}"
        response = requests.get(url).json()
        target = [movie for movie in response[f'season/{season}']['episodes'] if movie['episode_number'] == ep_no]
        image_url = f'https://image.tmdb.org/t/p/original{target[0]["still_path"]}'
        ep_name = target[0]['name']
        await query.edit_message_text(text = f"{ep_name}")
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image_url, caption=f"{file_name[:-4]}")
        destination = f'/media/TV Shows/One Piece/Season {season}'
        if not os.path.isdir(destination):
            os.makedirs(destination)
        dest = shutil.copyfile(f'/our_root{location}', f'{destination}/{ep_no} {ep_name}{file_name[-4:]}')
        await query.edit_message_text(text = f'{file_name} has been pushed to {dest}')
        


        
    else:
        await query.answer(text='Invalid choice!')
        return

    return CHOSEN

def cancel(update, context):
    """Cancel the conversation."""
    update.message.reply_text("Conversation cancelled.")
    return ConversationHandler.END

conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.FORWARDED, handle_video)],
    states={
        CHOOSING: [CallbackQueryHandler(handle_button_click)],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

def movie_folder_name(filename):
  # Regex pattern to match year in various formats (brackets or not)
  year_pattern = r"\[?\(?(\d{4})\]?\)?"

  # Split the filename based on year pattern
  parts = re.split(year_pattern, filename, maxsplit=1)

  if len(parts) < 2:
    # Year not found
    return None

  # Remove dots (".") that might be used instead of spaces
  movie_name = parts[0].replace(".", " ")

  # Extract year from the second part
  year_match = re.search(year_pattern, parts[1])
  if year_match:
    year = year_match.group(1)
  else:
    # Year not found in second part, might be incomplete filename
    return None

  # Combine movie name and year in desired format
  return f"{movie_name}({year})"
        
def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token("YOUR TOKEN").base_url("http://localhost:8081/bot").base_file_url("http://localhost:8081/file/bot").local_mode(local_mode=True).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("purge", purge))
    application.add_handler(CommandHandler("fpurge", fpurge))

    # on non command i.e message - echo the message on Telegram
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    application.add_handler(MessageHandler(filters.FORWARDED, handle_video))
    application.add_handler(CallbackQueryHandler(handle_button_click))
    application.add_handler(conv_handler)

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)



if __name__ == "__main__":
    main()
