import os
import logging
import warnings
import re
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.warnings import PTBUserWarning
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler

from downloader import download_media
from ai_processor import process_media
from db_client import add_to_notion, check_if_exists
from keep_alive import keep_alive

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
warnings.filterwarnings("ignore", category=PTBUserWarning)

# States
CATEGORY, CONTENT_TYPE, EXTRACT_FRAMES, CUSTOM_INSTRUCTIONS, MANUAL_FALLBACK = range(5)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Hello! I am ScrollSaver. Send me an Instagram Reel or YouTube link to get started.')

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    
    if text.lower().startswith("custom"):
        tool_name = text[6:].strip()
        if not tool_name:
            await update.message.reply_text("Please provide the tool name: e.g., 'custom RouteLLM'")
            return ConversationHandler.END
            
        context.user_data['bulk_urls'] = []
        context.user_data['custom_direct'] = tool_name
    else:
        urls = re.findall(r'(https?://[^\s]+)', text)
        if not urls:
            await update.message.reply_text("Please send a valid URL, or type 'custom <tool name>'.")
            return ConversationHandler.END
        context.user_data['bulk_urls'] = urls
        context.user_data['custom_direct'] = None
    
    keyboard = [
        [
            InlineKeyboardButton("Tech Skills", callback_data='Tech'),
            InlineKeyboardButton("Recipes", callback_data='Recipe'),
            InlineKeyboardButton("General", callback_data='General'),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Where should I save this?', reply_markup=reply_markup)
    return CATEGORY



async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    category = query.data
    context.user_data['category'] = category
    
    keyboard = [
        [
            InlineKeyboardButton("🛠️ Specific Tool/Item", callback_data='Tool'),
            InlineKeyboardButton("📖 Step-by-Step Guide", callback_data='Guide'),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=f"Selected: {category}\nWhat type of content is this?",
        reply_markup=reply_markup
    )
    return CONTENT_TYPE

async def content_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    content_type = query.data
    context.user_data['content_type'] = content_type
    
    keyboard = [
        [InlineKeyboardButton("✅ Yes (Extract Frames)", callback_data='yes_frames')],
        [InlineKeyboardButton("⚡ No (Fast Audio Only)", callback_data='no_frames')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=f"Selected: {content_type}\n\nDo you want to extract text from the video frames? (Takes longer, but good for music-only reels)",
        reply_markup=reply_markup
    )
    return EXTRACT_FRAMES

async def extract_frames_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    extract_frames = (query.data == 'yes_frames')
    context.user_data['extract_frames'] = extract_frames
    
    keyboard = [[InlineKeyboardButton("⏭️ Skip Custom Instructions", callback_data='skip_instructions')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=f"Selected: {context.user_data['category']} -> {context.user_data['content_type']} -> {'Extract Frames' if extract_frames else 'Fast Audio'}\n\nAny custom instructions? (e.g., 'Only extract the dessert recipe').\n\nType your instructions below, or click Skip.",
        reply_markup=reply_markup
    )
    return CUSTOM_INSTRUCTIONS

async def handle_instructions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    
    if query:
        await query.answer()
        instructions = "Skip"
        await query.edit_message_text("Processing your video... This might take a minute.")
        target_msg = query.message
    else:
        instructions = update.message.text
        target_msg = await update.message.reply_text("Processing your video... This might take a minute.")
        
    context.user_data['instructions'] = instructions
    
    bulk_urls = context.user_data.get('bulk_urls', [])
    category = context.user_data['category']
    content_type = context.user_data['content_type']
    extract_frames = context.user_data.get('extract_frames', False)
    custom_direct = context.user_data.get('custom_direct')
    
    if custom_direct:
        try:
            await context.bot.edit_message_text(chat_id=target_msg.chat_id, message_id=target_msg.message_id, text="🧠 Analyzing custom entry with AI... (~5-10s)")
            instructions_final = f"The user manually inputted this: {custom_direct}. User custom instructions: {instructions}"
            data = process_media([], category, content_type, instructions_final, extract_frames=False)
            if check_if_exists(category, data.get("Name", "")):
                await context.bot.edit_message_text(chat_id=target_msg.chat_id, message_id=target_msg.message_id, text=f"⏭️ Skipped: '{data.get('Name')}' already exists in Notion.")
            else:
                await context.bot.edit_message_text(chat_id=target_msg.chat_id, message_id=target_msg.message_id, text=f"💾 Pushing '{data.get('Name')}' to Notion...")
                add_to_notion(category, data, "")
                await context.bot.edit_message_text(chat_id=target_msg.chat_id, message_id=target_msg.message_id, text=f"✅ Successfully saved '{data.get('Name')}' to Notion!")
        except Exception as e:
            logging.error(f"Manual Entry Error: {e}")
            await context.bot.edit_message_text(chat_id=target_msg.chat_id, message_id=target_msg.message_id, text=f"❌ Error: {str(e)}")
    else:
        total = len(bulk_urls)
        success_count = 0
        for i, url in enumerate(bulk_urls, 1):
            audio_paths = []
            try:
                await context.bot.edit_message_text(chat_id=target_msg.chat_id, message_id=target_msg.message_id, text=f"📥 Downloading media ({i}/{total})... (~10-15s)")
                audio_paths, caption_text = download_media(url)
                
                await context.bot.edit_message_text(chat_id=target_msg.chat_id, message_id=target_msg.message_id, text=f"🧠 Analyzing content with AI ({i}/{total})... (~5-10s)")
                data = process_media(audio_paths, category, content_type, instructions, caption_text, extract_frames)
                
                if check_if_exists(category, data.get("Name", "")):
                    await context.bot.edit_message_text(chat_id=target_msg.chat_id, message_id=target_msg.message_id, text=f"⏭️ Skipped: '{data.get('Name')}' already exists. ({i}/{total})")
                else:
                    await context.bot.edit_message_text(chat_id=target_msg.chat_id, message_id=target_msg.message_id, text=f"💾 Pushing '{data.get('Name')}' to Notion... ({i}/{total})")
                    add_to_notion(category, data, url)
                    success_count += 1
            except Exception as e:
                logging.error(f"Batch Error on {url}: {e}")
                await context.bot.send_message(chat_id=target_msg.chat_id, text=f"❌ Error on link {i}: {str(e)}")
            finally:
                for p in audio_paths:
                    if os.path.exists(p):
                        os.remove(p)
                        
        await context.bot.edit_message_text(chat_id=target_msg.chat_id, message_id=target_msg.message_id, text=f"✅ Batch complete! Saved {success_count}/{total} links.")
        
    return ConversationHandler.END

async def handle_manual_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    fallback_text = update.message.text
    target_msg = await update.message.reply_text("Searching for the tool/recipe and saving to Notion...")
    
    category = context.user_data['category']
    content_type = context.user_data['content_type']
    url = context.user_data.get('url', '')
    
    try:
        # Pass empty list for file_paths, pass the fallback_text as the custom_instruction
        data = process_media([], category, content_type, custom_instructions=f"The user manually inputted this: {fallback_text}")
        
        if check_if_exists(category, data.get("Name", "")):
            await context.bot.edit_message_text(chat_id=target_msg.chat_id, message_id=target_msg.message_id, text=f"✅ Skipped saving: '{data.get('Name')}' already exists in Notion.")
        else:
            await context.bot.edit_message_text(chat_id=target_msg.chat_id, message_id=target_msg.message_id, text=f"Pushing '{data.get('Name')}' to Notion...")
            add_to_notion(category, data, url)
            await context.bot.edit_message_text(chat_id=target_msg.chat_id, message_id=target_msg.message_id, text=f"✅ Successfully saved '{data.get('Name')}' to Notion!")
            
    except Exception as e:
        logging.error(f"Manual Fallback Error: {e}")
        await context.bot.edit_message_text(chat_id=target_msg.chat_id, message_id=target_msg.message_id, text=f"❌ Error occurred during manual fallback: {str(e)}")
        
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('Canceled.')
    return ConversationHandler.END

def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Please set TELEGRAM_BOT_TOKEN in .env")
        return
        
    application = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url)],
        states={
            CATEGORY: [CallbackQueryHandler(category_callback)],
            CONTENT_TYPE: [CallbackQueryHandler(content_type_callback)],
            EXTRACT_FRAMES: [CallbackQueryHandler(extract_frames_callback)],
            CUSTOM_INSTRUCTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_instructions),
                CallbackQueryHandler(handle_instructions, pattern='^skip_instructions$')
            ],
            MANUAL_FALLBACK: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_manual_fallback)]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)

    print("ScrollSaver Bot is running...")
    keep_alive()
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
