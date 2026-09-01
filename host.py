import os
import sys
import subprocess
import threading
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ================= CONFIGURATION =================
TOKEN = "8250073152:AAHURmxKNhTDhwwsYz31uXMJWo7IsO5cYEo"          # <-- Put your BotFather token here
ADMIN_CHAT_ID =  8251667049        # <-- Put your numeric Telegram Admin Chat ID here
# =================================================

active_process = None

def is_admin(chat_id: int) -> bool:
    return chat_id == ADMIN_CHAT_ID

# --- Main Start Command & Menu ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(chat_id):
        await update.message.reply_text("⛔ Unauthorized: You are not allowed to use this bot.")
        return

    keyboard = [
        [InlineKeyboardButton("📂 Upload & Host Script", callback_data="menu_upload")],
        [InlineKeyboardButton("📦 Auto-Install Requirements", callback_data="menu_auto_req")],
        [InlineKeyboardButton("🛑 Stop Running Script", callback_data="menu_stop")],
        [InlineKeyboardButton("ℹ️ Status & Help", callback_data="menu_help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🤖 **Python Hosting Bot Control Panel**\n\nWelcome Admin! Choose an option below or send a `.py` file directly.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# --- Button Click Handler ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.message.chat.id):
        await query.edit_message_text("⛔ Unauthorized action.")
        return

    data = query.data

    if data == "menu_upload":
        await query.edit_message_text(
            "📤 **Send your Python (.py) file now.**\n\n"
            "Once uploaded, you can choose to auto-install requirements or run it directly."
        )
    elif data == "menu_auto_req":
        await query.edit_message_text(
            "📦 **Auto-Download Requirements**\n\n"
            "Upload a `requirements.txt` file or a `.py` script, and I will parse and install missing modules automatically."
        )
    elif data == "menu_stop":
        global active_process
        if active_process and active_process.poll() is None:
            active_process.terminate()
            active_process = None
            await query.edit_message_text("🛑 The running python script has been stopped successfully.")
        else:
            await query.edit_message_text("⚠️ No active python script is currently running.")
    elif data == "menu_help":
        help_text = (
            "🛠 **Admin Commands & Instructions:**\n\n"
            "• **Upload .py file:** Sends and prepares a script for hosting.\n"
            "• **Pip Command:** Type `pip install <package>` directly in chat to install dependencies.\n"
            "• **Stop Script:** Terminates any currently running background script.\n"
        )
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_main")]]
        await query.edit_message_text(help_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    elif data == "back_main":
        keyboard = [
            [InlineKeyboardButton("📂 Upload & Host Script", callback_data="menu_upload")],
            [InlineKeyboardButton("📦 Auto-Install Requirements", callback_data="menu_auto_req")],
            [InlineKeyboardButton("🛑 Stop Running Script", callback_data="menu_stop")],
            [InlineKeyboardButton("ℹ️ Status & Help", callback_data="menu_help")]
        ]
        await query.edit_message_text("🤖 **Python Hosting Bot Control Panel**\n\nChoose an option:", reply_markup=InlineKeyboardMarkup(keyboard))

# --- File Receiver & Execution Handler ---
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(chat_id):
        return

    doc = update.message.document
    file_name = doc.file_name
    file_unique_id = doc.file_unique_id

    # Download file locally
    file = await context.bot.get_file(doc.file_id)
    local_path = os.path.join(os.getcwd(), file_name)
    await file.download_to_drive(local_path)

    if file_name.endswith(".py"):
        # Automatically scan file content for imports to handle auto-requirement installation suggestion
        with open(local_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        
        keyboard = [
            [InlineKeyboardButton("🚀 Run Script", callback_data=f"run_{file_name}")],
            [InlineKeyboardButton("📦 Auto-Install Imports", callback_data=f"req_{file_name}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="back_main")]
        ]
        await update.message.reply_text(
            f"✅ File `{file_name}` uploaded successfully!\nWhat would you like to do?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    elif file_name == "requirements.txt":
        await update.message.reply_text(f"📦 Installing dependencies from `requirements.txt`...")
        process = subprocess.run([sys.executable, "-m", "pip", "install", "-r", local_path], capture_output=True, text=True)
        if process.returncode == 0:
            await update.message.reply_text(f"✅ Requirements installed successfully!\n```\n{process.stdout[-500:]}\n```", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"❌ Error installing requirements:\n```\n{process.stderr[-500:]}\n```", parse_mode="Markdown")
    else:
        await update.message.reply_text("📁 File saved, but it's not a recognized Python or requirements script.")

# --- Handle Inline Action Queries for Files ---
async def file_action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.message.chat.id):
        return

    data = query.data
    global active_process

    if data.startswith("run_"):
        filename = data.replace("run_", "")
        if active_process and active_process.poll() is None:
            await query.message.reply_text("⚠️ Another script is already running! Stop it first using the menu.")
            return

        def run_script():
            global active_process
            active_process = subprocess.Popen([sys.executable, filename], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        threading.Thread(target=run_script, daemon=True).start()
        await query.edit_message_text(f"🚀 Started hosting and executing `{filename}` in the background background process!")

    elif data.startswith("req_"):
        filename = data.replace("req_", "")
        try:
            with open(filename, "r", encoding="utf-8", errors="ignore") as f:
                code = f.read()
            
            # Simple regex search to find external third-party imports (e.g., 'import requests', 'from bs4 import ...')
            imports = set(re.findall(r'^(?:import|from)\s+([a-zA-Z0-9_]+)', code, re.MULTILINE))
            # Filter standard library modules roughly or pass them to pip (pip handles system modules gracefully or skips if built-in)
            standard_libs = {"os", "sys", "re", "math", "json", "time", "datetime", "subprocess", "threading", "random", "collections", "pathlib"}
            to_install = [imp for imp in imports if imp not in standard_libs]

            if not to_install:
                await query.edit_message_text(f"🔍 No external third-party dependencies automatically detected in `{filename}`.")
                return

            await query.edit_message_text(f"📦 Auto-downloading requirements: {', '.join(to_install)}...")
            process = subprocess.run([sys.executable, "-m", "pip", "install"] + to_install, capture_output=True, text=True)
            
            if process.returncode == 0:
                await query.message.reply_text(f"✅ Successfully installed requirements for `{filename}`!")
            else:
                await query.message.reply_text(f"⚠️ Pip output:\n```\n{process.stderr[-500:]}\n```", parse_mode="Markdown")
        except Exception as e:
            await query.message.reply_text(f"❌ Error processing requirements: {str(e)}")

# --- Direct Admin Pip Commands (e.g., pip install <package>) ---
async def handle_text_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(chat_id):
        return

    text = update.message.text.strip()
    if text.startswith("pip install "):
        package = text.replace("pip install", "").strip()
        await update.message.reply_text(f"⏳ Running: `pip install {package}`...", parse_mode="Markdown")
        
        process = subprocess.run([sys.executable, "-m", "pip", "install", package], capture_output=True, text=True)
        if process.returncode == 0:
            await update.message.reply_text(f"✅ Successfully installed `{package}`!\n```\n{process.stdout[-400:]}\n```", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"❌ Failed to install package:\n```\n{process.stderr[-400:]}\n```", parse_mode="Markdown")

# --- Main Application Setup ---
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^(menu_|back_)"))
    app.add_handler(CallbackQueryHandler(file_action_handler, pattern="^(run_|req_)"))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_commands))

    print("🤖 Hosting Bot is up and running securely...")
    app.run_polling()

if __name__ == "__main__":
    main()
