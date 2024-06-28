
# upNAS Telegram Bot

UPNAS is a Telegram bot designed to facilitate the easy pushing of media files, such as movies or TV series, to various types of storage solutions, including SMB storage. This bot leverages the power of the Telegram platform to provide a user-friendly interface for managing and transferring your media files efficiently.

## Features

- **File Transfer**: Easily push media files to different storage solutions directly from Telegram.
- **Support for Various Storage Types**: Compatible with multiple storage types, including SMB.
- **User-Friendly Interface**: Utilizes Telegram's interactive buttons and commands for a smooth user experience.
- **Secure**: Implements Telegram's security protocols to ensure safe file transfers.

## Getting Started

To get started with upNAS, follow these steps:

### Prerequisites

- A Telegram account.
- A local ```telegram-bot-api``` (hosted at 192.168.1.8:9099 here).
- Access to a server or device where the bot can be hosted (I am hosting it as a docker container on my TrueNAS Scale server).
- Storage solutions (like SMB storage) set up to receive files.
- TMDb API key for fetching metadata (optional).

### Installation

1. Clone this repository to your local machine.
2. Install the required dependencies by running:

```
pip install -r requirements.txt
```
3. Obtain a Telegram Bot API token by creating a bot using BotFather (https://core.telegram.org/bots/tutorial).
4. Replace the following placeholders in bot.py:

+ ```os.getenv("BOT_KEY")``` : Your Telegram Bot API token or set your token as an environment variable.
+ ```/our_root``` : Path to the telegram-bot-api's token specific directory.
+ ```/media``` : Path to the media directory (destination).
5. Run ```bot.py```.

### Usage

#### commands
- ```/strart``` : To start the bot.
- ```/ping```   : To check if bot is alive or not. There will be a replay "```Pong!```" if bot is alive.
- ```/purge``` : To clear the files from api's ```documents``` and ```videos``` directory.
- ```fpurge``` : To clear files like ```/purge``` including the ```temp``` files.
- Forward files to the bot and it downloads and push it to the destination (```/media``` here).


#### Docker

Build the dockerfile provided and run it on any machines.