import os
import io
import logging
import asyncio
from pathlib import Path
from typing import Dict, Tuple, Optional

from PIL import Image
from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from aiogram.types.input_file import BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 🔥 FIX: Get BOT_TOKEN with better error handling
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Print debug info to Railway logs
print("=" * 60)
print("🔍 DEBUG: Checking Environment Variables")
print("=" * 60)
print(f"BOT_TOKEN found: {'✅ YES' if BOT_TOKEN else '❌ NO'}")

if BOT_TOKEN:
    print(f"BOT_TOKEN starts with: {BOT_TOKEN[:15]}...")
    print(f"BOT_TOKEN length: {len(BOT_TOKEN)} characters")
else:
    print("\n❌ ERROR: BOT_TOKEN is MISSING!")
    print("\n📌 To fix this:")
    print("1. Go to Railway Dashboard")
    print("2. Click on your project")
    print("3. Click the 'Variables' tab")
    print("4. Click 'Add Variable'")
    print("5. Enter Key: BOT_TOKEN")
    print("6. Enter Value: Your bot token from @BotFather")
    print("7. Click 'Add'")
    print("8. Railway will auto-redeploy")
print("=" * 60)

if not BOT_TOKEN:
    raise ValueError(
        "\n❌ BOT_TOKEN environment variable is required!\n"
        "\nPlease add it in Railway Variables tab:\n"
        "1. Go to Railway Dashboard\n"
        "2. Click on your project\n"
        "3. Click 'Variables' tab\n"
        "4. Add BOT_TOKEN with your bot token\n"
        "5. Click Deploy\n"
    )

# Initialize bot and dispatcher
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
)
dp = Dispatcher()

# Supported formats
SUPPORTED_FORMATS: Dict[str, Tuple[str, str]] = {
    "png": ("PNG", "image/png"),
    "jpg": ("JPEG", "image/jpeg"),
    "jpeg": ("JPEG", "image/jpeg"),
    "webp": ("WEBP", "image/webp"),
    "gif": ("GIF", "image/gif"),
    "bmp": ("BMP", "image/bmp"),
    "tiff": ("TIFF", "image/tiff"),
    "ico": ("ICO", "image/x-icon")
}

# User state management
user_states: Dict[int, Dict] = {}

# ==================== Helper Functions ====================

def get_format_buttons() -> InlineKeyboardMarkup:
    """Generate inline keyboard with supported formats"""
    builder = InlineKeyboardBuilder()
    
    for fmt in SUPPORTED_FORMATS.keys():
        builder.button(text=fmt.upper(), callback_data=f"format_{fmt}")
    
    builder.button(text="❌ Cancel", callback_data="cancel")
    builder.adjust(4, 4, 4, 4, 1)
    
    return builder.as_markup()

async def convert_image(
    image_bytes: bytes,
    input_format: str,
    output_format: str,
    quality: int = 95
) -> Optional[bytes]:
    """Convert image from one format to another"""
    try:
        image = Image.open(io.BytesIO(image_bytes))
        
        # Convert RGBA to RGB for JPEG
        if output_format.lower() in ['jpg', 'jpeg'] and image.mode == 'RGBA':
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[3])
            image = background
        elif output_format.lower() in ['jpg', 'jpeg'] and image.mode not in ['RGB', 'L']:
            image = image.convert('RGB')
        
        # Handle GIF animation
        if input_format.lower() == 'gif' and output_format.lower() != 'gif':
            if getattr(image, 'is_animated', False):
                image.seek(0)
                image = image.convert('RGB')
        
        output_buffer = io.BytesIO()
        save_kwargs = {}
        
        if output_format.lower() in ['jpg', 'jpeg']:
            save_kwargs['quality'] = quality
            save_kwargs['optimize'] = True
        elif output_format.lower() == 'png':
            save_kwargs['optimize'] = True
            save_kwargs['compress_level'] = 6
        elif output_format.lower() == 'webp':
            save_kwargs['quality'] = quality
        
        if output_format.lower() == 'gif':
            if input_format.lower() == 'gif':
                image.save(output_buffer, format='GIF', save_all=True)
            else:
                image.save(output_buffer, format='GIF')
        else:
            image.save(output_buffer, format=SUPPORTED_FORMATS[output_format.lower()][0], **save_kwargs)
        
        output_buffer.seek(0)
        return output_buffer.getvalue()
    
    except Exception as e:
        logger.error(f"Conversion error: {e}")
        return None

def get_file_extension(filename: str) -> str:
    """Extract file extension from filename"""
    return Path(filename).suffix.lower().replace('.', '')

# ==================== Bot Handlers ====================

@dp.message(Command("start"))
async def start_command(message: Message):
    welcome_text = (
        "🎨 *Welcome to ImgPixieBot!*\n\n"
        "I can convert your images between different formats.\n"
        "📸 *Supported formats:* PNG, JPG, JPEG, WEBP, GIF, BMP, TIFF, ICO\n\n"
        "🔄 *How to use:*\n"
        "1. Send me an image\n"
        "2. Choose the format you want to convert to\n"
        "3. I'll send back the converted image!\n\n"
        "⚡ *Pro tip:* For best results, use high-quality images."
    )
    await message.reply(welcome_text)

@dp.message(Command("help"))
async def help_command(message: Message):
    help_text = (
        "📖 *Help & Commands*\n\n"
        "*/start* - Welcome message and instructions\n"
        "*/help* - Show this help message\n"
        "*/formats* - Show supported formats\n"
        "*/cancel* - Cancel current operation\n\n"
        "*💡 Quick Guide:*\n"
        "1. Send any image file\n"
        "2. Choose the output format from the buttons\n"
        "3. Wait for the converted image\n\n"
        "*⚠️ Notes:*\n"
        "- Maximum file size: 20MB\n"
        "- Animated GIFs will be converted to static images\n"
        "- For JPEG output, transparent backgrounds become white"
    )
    await message.reply(help_text)

@dp.message(Command("formats"))
async def formats_command(message: Message):
    formats_text = "📋 *Supported Formats:*\n\n"
    for fmt in SUPPORTED_FORMATS.keys():
        formats_text += f"• {fmt.upper()}\n"
    formats_text += "\n🔄 Send an image to get started!"
    await message.reply(formats_text)

@dp.message(Command("cancel"))
async def cancel_command(message: Message):
    user_id = message.from_user.id
    if user_id in user_states:
        del user_states[user_id]
        await message.reply("✅ Operation cancelled. You can start over anytime!")
    else:
        await message.reply("ℹ️ No active operation to cancel.")

@dp.message(lambda message: message.photo)
async def handle_photo(message: Message):
    user_id = message.from_user.id
    photo = message.photo[-1]
    file_info = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file_info.file_path)
    
    user_states[user_id] = {
        'image_bytes': file_bytes.getvalue(),
        'input_format': 'jpg'
    }
    
    await message.reply(
        "📸 Image received! Choose the format you want to convert to:",
        reply_markup=get_format_buttons()
    )

@dp.message(lambda message: message.document)
async def handle_document(message: Message):
    user_id = message.from_user.id
    document = message.document
    ext = get_file_extension(document.file_name or '')
    
    if ext not in SUPPORTED_FORMATS:
        await message.reply(
            f"❌ Unsupported file format: *{ext.upper()}*\n\n"
            f"Supported formats: {', '.join([f.upper() for f in SUPPORTED_FORMATS.keys()])}",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    if document.file_size > 20 * 1024 * 1024:
        await message.reply("❌ File is too large! Maximum size: 20MB")
        return
    
    try:
        file_info = await bot.get_file(document.file_id)
        file_bytes = await bot.download_file(file_info.file_path)
        
        user_states[user_id] = {
            'image_bytes': file_bytes.getvalue(),
            'input_format': ext,
            'filename': document.file_name
        }
        
        await message.reply(
            f"✅ *{document.file_name}* received!\n"
            f"📐 Size: {document.file_size / 1024:.1f}KB\n\n"
            "Choose the output format:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_format_buttons()
        )
    except Exception as e:
        logger.error(f"Error handling document: {e}")
        await message.reply("❌ Failed to process your image. Please try again.")

@dp.callback_query(lambda c: c.data and c.data.startswith('format_'))
async def process_format_selection(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    output_format = callback_query.data.replace('format_', '')
    
    if user_id not in user_states:
        await callback_query.answer("❌ Please send an image first!", show_alert=True)
        return
    
    user_data = user_states[user_id]
    image_bytes = user_data['image_bytes']
    input_format = user_data['input_format']
    original_filename = user_data.get('filename', 'image')
    
    if input_format == output_format:
        await callback_query.answer("⚠️ Image is already in this format!", show_alert=True)
        return
    
    await callback_query.answer(f"🔄 Converting to {output_format.upper()}...")
    await callback_query.message.edit_text(
        f"🔄 Converting from *{input_format.upper()}* to *{output_format.upper()}*...\n"
        f"⏳ Please wait...",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        converted_bytes = await convert_image(
            image_bytes,
            input_format,
            output_format,
            quality=90
        )
        
        if not converted_bytes:
            await callback_query.message.edit_text(
                f"❌ Failed to convert image to *{output_format.upper()}*.\n"
                f"Please try again with a different format.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        base_name = Path(original_filename).stem
        output_filename = f"{base_name}.{output_format}"
        input_file = BufferedInputFile(converted_bytes, filename=output_filename)
        
        await bot.send_document(
            chat_id=user_id,
            document=input_file,
            caption=f"✅ Converted *{input_format.upper()}* → *{output_format.upper()}*\n"
                    f"📦 Size: {len(converted_bytes) / 1024:.1f}KB",
            parse_mode=ParseMode.MARKDOWN
        )
        
        del user_states[user_id]
        
        await callback_query.message.edit_text(
            f"✅ Conversion complete! Check the image I just sent you.\n\n"
            f"🔄 Send another image to convert more!"
        )
        
    except Exception as e:
        logger.error(f"Conversion error: {e}")
        await callback_query.message.edit_text(
            "❌ An error occurred during conversion. Please try again."
        )

@dp.callback_query(lambda c: c.data == 'cancel')
async def cancel_callback(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if user_id in user_states:
        del user_states[user_id]
        await callback_query.answer("✅ Cancelled!")
        await callback_query.message.edit_text("✅ Operation cancelled. You can start over anytime!")
    else:
        await callback_query.answer("ℹ️ No active operation.")

@dp.message()
async def handle_unknown(message: Message):
    await message.reply(
        "🤔 I only work with images!\n\n"
        "Send me an image or a document (PNG, JPG, WEBP, GIF, etc.)\n"
        "Or use /help to see available commands."
    )

# ==================== Main Execution ====================

async def main():
    """Main function to start the bot"""
    logger.info("Starting ImgPixieBot...")
    logger.info(f"✅ Bot token loaded: {BOT_TOKEN[:15]}...")
    
    # Clear any existing webhook to avoid conflicts
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Webhook cleared successfully")
    except Exception as e:
        logger.warning(f"Could not clear webhook: {e}")
    
    # Start polling
    await dp.start_polling(
        bot,
        skip_updates=False,
        allowed_updates=["message", "callback_query"],
        stop_on_error=True
    )

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        raise
