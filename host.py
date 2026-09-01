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
TOKEN = "8250073152:AAHURmxKNhTDhwwsYz31uXMJWo7IsO5cYEo"
ADMIN_CHAT_ID = 8251667049
# =================================================

active_process = None
active_filename = None
bot_app_context = None  # Used for sending background thread messages

def is_admin(chat_id: int) -> bool:
    return chat_id == ADMIN_CHAT_ID

def get_main_menu():
    return [
        [InlineKeyboardButton("📂 Upload & Host Script", callback_data="menu_upload")],
        [InlineKeyboardButton("📦 Auto-Install Requirements", callback_data="menu_auto_req")],
        [InlineKeyboardButton("📊 Status", callback_data="menu_status"), InlineKeyboardButton("💾 Storage", callback_data="menu_storage")],
        [InlineKeyboardButton("🛑 Stop Running Script", callback_data="menu_stop")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="menu_help")]
    ]

# --- Background Output Reader Thread ---
def monitor_process_output(process, filename, bot):
    global active_process, active_filename
    
    # Read stdout line by line and send to admin
    try:
        while process.poll() is None:
            output = process.stdout.readline()
            if output:
                # Send output line to admin via asyncio run or thread-safe method
                import asyncio
                asyncio.run_coroutine_threadsafe(
                    bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"💻 `[{filename}]`\n{output.strip()}", parse_mode="Markdown"),
                    bot_loop
                )
        
        # Read remaining stderr/stdout after process ends
        stderr_output = process.stderr.read()
        if stderr_output:
            import asyncio
            asyncio.run_coroutine_threadsafe(
                bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"⚠️ `[{filename}] Error/Exit:\n{stderr_output.strip()}`", parse_mode="Markdown"),
                bot_loop
            )
    except Exception as e:
        print(f"Monitor error: {e}")
    finally:
        if active_process == process:
            active_process = None
            active_filename = None

bot_loop = None

# --- Main Start Command & Menu ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(chat_id):
        await update.message.reply_text("⛔ Unauthorized: You are not allowed to use this bot.")
        return

    reply_markup = InlineKeyboardMarkup(get_main_menu())
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
            "Once uploaded, you can choose to auto-install requirements or run it directly.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_main")]])
        )
    elif data == "menu_auto_req":
        await query.edit_message_text(
            "📦 **Auto-Download Requirements**\n\n"
            "Upload a `requirements.txt` file or a `.py` script, and I will parse and install missing modules automatically.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_main")]])
        )
    elif data == "menu_status":
        global active_process, active_filename
        if active_process and active_process.poll() is None:
            status_msg = f"🟢 **Status:** Running\n📂 **Active Script:** `{active_filename}`\n\n*(Outputs and input requests will stream here automatically)*"
        else:
            status_msg = "🔴 **Status:** No script is currently running."
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_main")]]
        await query.edit_message_text(status_msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "menu_storage":
        files = [f for f in os.listdir(os.getcwd()) if f.endswith(".py") and f != "host_bot.py"]
        if not files:
            await query.edit_message_text(
                "💾 **Storage is Empty**\n\nNo saved Python files found.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_main")]])
            )
            return

        keyboard = []
        for file in files:
            keyboard.append([
                InlineKeyboardButton(f"📄 {file}", callback_data=f"noop_{file}"),
                InlineKeyboardButton("🚀 Run", callback_data=f"run_{file}"),
                InlineKeyboardButton("🗑 Delete", callback_data=f"del_{file}")
            ])
        keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="back_main")])
        
        await query.edit_message_text(
            "💾 **Storage Management**\n\nSelect an action for your saved scripts:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif data == "menu_stop":
        if active_process and active_process.poll() is None:
            active_process.terminate()
            active_process = None
            active_filename = None
            await query.edit_message_text("🛑 The running python script has been stopped successfully.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_main")]]))
        else:
            await query.edit_message_text("⚠️ No active python script is currently running.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_main")]]))
    elif data == "menu_help":
        help_text = (
            "🛠 **Admin Commands & Instructions:**\n\n"
            "• **Upload .py file:** Saves and prepares a script for hosting.\n"
            "• **Storage:** View, run, or delete all saved scripts on the bot.\n"
            "• **Interactive Input:** If a running script asks for `input()`, simply reply in chat to send values into it.\n"
            "• **Pip Command:** Type `pip install <package>` directly in chat to install dependencies.\n"
        )
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_main")]]
        await query.edit_message_text(help_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    elif data == "back_main":
        await query.edit_message_text("🤖 **Python Hosting Bot Control Panel**\n\nChoose an option:", reply_markup=InlineKeyboardMarkup(get_main_menu()))

# --- File Receiver & Execution Handler ---
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(chat_id):
        return

    doc = update.message.document
    file_name = doc.file_name

    file = await context.bot.get_file(doc.file_id)
    local_path = os.path.join(os.getcwd(), file_name)
    await file.download_to_drive(local_path)

    if file_name.endswith(".py"):
        keyboard = [
            [InlineKeyboardButton("🚀 Run Script", callback_data=f"run_{file_name}")],
            [InlineKeyboardButton("📦 Auto-Install Imports", callback_data=f"req_{file_name}")],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_main")]
        ]
        await update.message.reply_text(
            f"✅ File `{file_name}` uploaded & saved to storage successfully!\nWhat would you like to do?",
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
    global active_process, active_filename

    if data.startswith("run_"):
        filename = data.replace("run_", "")
        if active_process and active_process.poll() is None:
            await query.message.reply_text("⚠️ Another script is already running! Stop it first.")
            return

        try:
            active_process = subprocess.Popen(
                [sys.executable, filename],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            active_filename = filename

            # Start thread to listen to process prints/errors
            threading.Thread(target=monitor_process_output, args=(active_process, filename, context.bot), daemon=True).start()

            await query.edit_message_text(f"🚀 Started hosting and executing `{filename}`!\nOutputs will stream here. If it asks for input, just reply in chat.")
        except Exception as e:
            await query.edit_message_text(f"❌ Failed to start script: {str(e)}")

    elif data.startswith("del_"):
        filename = data.replace("del_", "")
        try:
            path = os.path.join(os.getcwd(), filename)
            if os.path.exists(path):
                os.remove(path)
                await query.edit_message_text(f"🗑 File `{filename}` deleted successfully from storage!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Storage", callback_data="menu_storage")]]))
            else:
                await query.edit_message_text("⚠️ File not found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Storage", callback_data="menu_storage")]]))
        except Exception as e:
            await query.edit_message_text(f"❌ Error deleting file: {str(e)}")

    elif data.startswith("req_"):
        filename = data.replace("req_", "")
        try:
            with open(filename, "r", encoding="utf-8", errors="ignore") as f:
                code = f.read()
            
            imports = set(re.findall(r'^(?:import|from)\s+([a-zA-Z0-9_]+)', code, re.MULTILINE))
            
            standard_libs = {
                "os", "sys", "re", "math", "json", "time", "datetime", 
                "subprocess", "threading", "random", "collections", "pathlib",
                "marshal", "zlib", "base64", "urllib", "hashlib", "io", "ast",
                "logging", "itertools", "functools", "shutil", "glob", "typing"
            }
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

# --- Direct Admin Text Messages & Interactive Inputs / Pip Commands ---
async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(chat_id):
        return

    text = update.message.text.strip()
    global active_process

    # 1. If a script is running and asking for input, forward this text into its stdin
    if active_process and active_process.poll() is None:
        try:
            active_process.stdin.write(text + "\n")
            active_process.stdin.flush()
            await update.message.reply_text("📤 Input sent to running script.")
            return
        except Exception as e:
            await update.message.reply_text(f"❌ Error sending input to script: {e}")
            return

    # 2. Handle Pip Command if no script is actively looking for input
    if text.startswith("pip install "):
        package = text.replace("pip install", "").strip()
        await update.message.reply_text(f"⏳ Running: `pip install {package}`...", parse_mode="Markdown")
        
        process = subprocess.run([sys.executable, "-m", "pip", "install", package], capture_output=True, text=True)
        if process.returncode == 0:
            await update.message.reply_text(f"✅ Successfully installed `{package}`!\n```\n{process.stdout[-400:]}\n```", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"❌ Failed to install package:\n```\n{process.stderr[-400:]}\n```", parse_mode="Markdown")
    else:
        await update.message.reply_text("ℹ️ No script is currently running. Use /start to open the control panel or type `pip install <package>`.")

# --- Main Application Setup ---
def main():
    global bot_loop
    import asyncio
    bot_loop = asyncio.get_event_loop()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^(menu_|back_)"))
    app.add_handler(CallbackQueryHandler(file_action_handler, pattern="^(run_|req_|del_)"))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))

    print("🤖 Hosting Bot is up and running securely...")
    app.run_polling()

if __name__ == "__main__":
    main()
            
