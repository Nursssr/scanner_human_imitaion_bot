import os
from telethon import TelegramClient
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
SESSION = os.getenv("TG_SESSION", "scanner_session")  # имя сессии (файл)

def main():
    client = TelegramClient(SESSION, API_ID, API_HASH)
    print("Starting interactive authorization (phone -> code).")
    client.start()  # интерактивно запросит телефон и код, если сессии нет
    print("Authorization successful. Session saved as:", SESSION)
    client.disconnect()

if __name__ == "__main__":
    main()

# интерактивная авторизация userbot (Telethon)