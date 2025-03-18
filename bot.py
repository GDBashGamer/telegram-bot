import os
import random
import string
from pymongo import MongoClient
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext

# MongoDB Setup
MONGO_URI = os.getenv("MONGO_URI")  # Get MongoDB connection string from environment variables
client = MongoClient(MONGO_URI)
db = client.telegram_bot  # Database name
files_collection = db.files  # Collection for saved files
temp_files_collection = db.temp_files  # Collection for temporary files

# Hardcoded Owner ID (replace with your Telegram user ID)
OWNER_ID = int(os.getenv("OWNER_ID"))  # Get owner ID from environment variables

def generate_code():
    return "".join(random.choices(string.ascii_letters + string.digits, k=8))

async def file_handler(update: Update, context: CallbackContext):
    # Check if the user is the owner
    if update.message.from_user.id != OWNER_ID:
        await update.message.reply_text("You are not authorized to upload files.")
        return

    file = None
    file_type = ""
    caption = update.message.caption  # Extract the caption (if any)

    if update.message.document:
        file = update.message.document
        file_type = "document"
    elif update.message.photo:
        file = update.message.photo[-1]  # Use highest resolution photo
        file_type = "photo"
    elif update.message.audio:
        file = update.message.audio
        file_type = "audio"
    elif update.message.video:
        file = update.message.video
        file_type = "video"
    elif update.message.voice:
        file = update.message.voice
        file_type = "voice"
    elif update.message.video_note:
        file = update.message.video_note
        file_type = "video_note"
    elif update.message.animation:
        file = update.message.animation
        file_type = "animation"
    elif update.message.sticker:
        file = update.message.sticker
        file_type = "sticker"
    else:
        return  # Unsupported type, ignore it

    file_id = file.file_id
    user_id = update.message.from_user.id
    temp_files_collection.insert_one({
        "user_id": user_id,
        "file_id": file_id,
        "file_type": file_type,
        "caption": caption
    })
    await update.message.reply_text("File received! Use /savefiles to save it.")

async def save_files(update: Update, context: CallbackContext):
    # Check if the user is the owner
    if update.message.from_user.id != OWNER_ID:
        await update.message.reply_text("You are not authorized to save files.")
        return

    user_id = update.message.from_user.id
    code = generate_code()
    temp_files = list(temp_files_collection.find({"user_id": user_id}))
    if not temp_files:
        await update.message.reply_text("No files found! Please upload files before using this command.")
        return

    for file_entry in temp_files:
        files_collection.insert_one({
            "file_id": file_entry["file_id"],
            "code": code,
            "user_id": user_id,
            "file_type": file_entry["file_type"],
            "caption": file_entry["caption"]
        })
    temp_files_collection.delete_many({"user_id": user_id})
    deep_link = f"https://t.me/{context.bot.username}?start={code}"
    await update.message.reply_text(f"Files saved! Share this link: {deep_link}")

async def start(update: Update, context: CallbackContext):
    if context.args:
        code = context.args[0]
        saved_files = list(files_collection.find({"code": code}))
        if saved_files:
            for file_entry in saved_files:
                file_id = file_entry["file_id"]
                file_type = file_entry["file_type"]
                caption = file_entry["caption"]
                if file_type == "photo":
                    await update.message.reply_photo(photo=file_id, caption=caption)
                elif file_type == "audio":
                    await update.message.reply_audio(audio=file_id, caption=caption)
                elif file_type == "video":
                    await update.message.reply_video(video=file_id, caption=caption)
                elif file_type == "voice":
                    await update.message.reply_voice(voice=file_id, caption=caption)
                elif file_type == "video_note":
                    await update.message.reply_video_note(video_note=file_id)
                elif file_type == "animation":
                    await update.message.reply_animation(animation=file_id, caption=caption)
                elif file_type == "sticker":
                    await update.message.reply_sticker(sticker=file_id)
                else:
                    await update.message.reply_document(document=file_id, caption=caption)
        else:
            await update.message.reply_text("Invalid or expired link.")
    else:
        await update.message.reply_text("Welcome! Upload files first, then use /savefiles to save them.")

async def delete_files(update: Update, context: CallbackContext):
    # Check if the user is the owner
    if update.message.from_user.id != OWNER_ID:
        await update.message.reply_text("You are not authorized to delete files.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /deletefiles <code>")
        return
    code = context.args[0]
    user_id = update.message.from_user.id
    count = files_collection.count_documents({"code": code, "user_id": user_id})
    if count == 0:
        await update.message.reply_text("Either the code is invalid or you are not the owner of these files.")
        return
    files_collection.delete_many({"code": code, "user_id": user_id})
    await update.message.reply_text("Files successfully deleted!")

async def view_files(update: Update, context: CallbackContext):
    # Check if the user is the owner
    if update.message.from_user.id != OWNER_ID:
        await update.message.reply_text("You are not authorized to view files.")
        return

    saved_files = list(files_collection.find({"user_id": OWNER_ID}))
    if not saved_files:
        await update.message.reply_text("No files found.")
        return

    response = "Files uploaded by you:\n"
    for file_entry in saved_files:
        code = file_entry["code"]
        file_id = file_entry["file_id"]
        file_type = file_entry["file_type"]
        caption = file_entry["caption"]
        response += f"Code: {code}, File ID: {file_id}, Type: {file_type}, Caption: {caption}\n"
    await update.message.reply_text(response)

def main():
    TOKEN = os.getenv("TOKEN")  # Get bot token from environment variables
    app = Application.builder().token(TOKEN).build()

    # Combined filter for all file types except stickers
    combined_filter = (
        filters.Document.ALL | filters.PHOTO | filters.AUDIO |
        filters.VIDEO | filters.VOICE | filters.VIDEO_NOTE | filters.ANIMATION
    )
    app.add_handler(MessageHandler(combined_filter, file_handler))
    
    # Handler for stickers using the built-in sticker filter
    app.add_handler(MessageHandler(filters.Sticker.ALL, file_handler))
    
    app.add_handler(CommandHandler("savefiles", save_files))
    app.add_handler(CommandHandler("deletefiles", delete_files))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("viewfiles", view_files))  # New command to view files

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
