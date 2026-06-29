import os
import io
import logging
from typing import Optional, Dict
from PIL import Image
from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types.input_file import BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get token
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required!")

# Initialize bot and dispatcher
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
)
dp = Dispatcher()

# User state: store original image and settings
user_states: Dict[int, Dict] = {}

# Supported formats for compression
SUPPORTED_FORMATS = ["jpeg", "png", "webp"]

def get_compression_keyboard() -> InlineKeyboardMarkup:
    """Generate inline keyboard with quality options."""
    builder = InlineKeyboardBuilder()
    for quality in [30, 50, 70, 85, 95]:
        builder.button(text=f"{quality}%", callback_data=f"quality_{quality}")
    builder.button(text="🔁 Keep Original", callback_data="quality_original")
    builder.button(text="❌ Cancel", callback_data="cancel")
    builder.adjust(3, 3, 1, 1)
    return builder.as_markup()

def get_format_keyboard() -> InlineKeyboardMarkup:
    """Generate inline keyboard for format selection."""
    builder = InlineKeyboardBuilder()
    for fmt in SUPPORTED_FORMATS:
        builder.button(text=fmt.upper(), callback_data=f"format_{fmt}")
    builder.button(text="❌ Cancel", callback_data="cancel")
    builder.adjust(3, 1)
    return builder.as_markup()

async def compress_image(
    image_bytes: bytes,
    output_format: str,
    quality: Optional[int] = None
) -> Optional[bytes]:
    """
    Compress image using Pillow.
    If quality is None, keeps original quality (optimized).
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        output_buffer = io.BytesIO()

        # Convert RGBA to RGB for JPEG
        if output_format == "jpeg" and img.mode == "RGBA":
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            img = background
        elif output_format == "jpeg" and img.mode not in ["RGB", "L"]:
            img = img.convert("RGB")

        # Save with compression
        save_kwargs = {"optimize": True}
        if quality is not None:
            if output_format in ["jpeg", "webp"]:
                save_kwargs["quality"] = quality
            elif output_format == "png":
                save_kwargs["compress_level"] = 9 - (quality // 10)  # Rough mapping

        img.save(output_buffer, format=output_format.upper(), **save_kwargs)
        output_buffer.seek(0)
        return output_buffer.getvalue()

    except Exception as e:
        logger.error(f"Compression error: {e}")
        return None

# ==================== Handlers ====================

@dp.message(Command("start"))
async def start_command(message: Message):
    welcome = (
        "🖼️ *Welcome to SquooshImageBot!*\n\n"
        "I compress JPEG, PNG, and WEBP images.\n\n"
        "*How to use:*\n"
        "1. Send me an image (as a file for best quality)\n"
        "2. Choose output format\n"
        "3. Choose quality level\n"
        "4. Get your compressed image!\n\n"
        "Commands:\n"
        "/start - Show this message\n"
        "/help - More details\n"
        "/cancel - Cancel operation"
    )
    await message.reply(welcome)

@dp.message(Command("help"))
async def help_command(message: Message):
    help_text = (
        "📖 *Help*\n\n"
        "Send an image as a *File* (not as a photo) to keep original quality.\n\n"
        "*Quality options:*\n"
        "• 30% - Small file, lower quality\n"
        "• 50% - Balanced\n"
        "• 70% - Good quality\n"
        "• 85% - High quality (recommended)\n"
        "• 95% - Near original\n"
        "• Keep Original - Optimized with no quality loss\n\n"
        "*Formats:* JPEG, PNG, WEBP"
    )
    await message.reply(help_text)

@dp.message(Command("cancel"))
async def cancel_command(message: Message):
    user_id = message.from_user.id
    if user_id in user_states:
        del user_states[user_id]
        await message.reply("✅ Cancelled.")
    else:
        await message.reply("ℹ️ No active operation.")

@dp.message(lambda m: m.document)
async def handle_document(message: Message):
    """Handle document (image file)."""
    user_id = message.from_user.id
    doc = message.document

    # Check if it's an image
    ext = doc.file_name.split(".")[-1].lower() if doc.file_name else ""
    if ext not in ["jpg", "jpeg", "png", "webp", "gif", "bmp", "tiff"]:
        await message.reply("❌ Please send a supported image (JPEG, PNG, WEBP, GIF, BMP, TIFF).")
        return

    if doc.file_size > 20 * 1024 * 1024:
        await message.reply("❌ File too large (max 20MB).")
        return

    try:
        file_info = await bot.get_file(doc.file_id)
        file_bytes = await bot.download_file(file_info.file_path)

        user_states[user_id] = {
            "image_bytes": file_bytes.getvalue(),
            "filename": doc.file_name,
            "input_format": ext
        }

        await message.reply(
            f"✅ *{doc.file_name}* received!\n"
            f"Size: {doc.file_size / 1024:.1f} KB\n\n"
            "Select *output format*:",
            reply_markup=get_format_keyboard()
        )
    except Exception as e:
        logger.error(f"Document error: {e}")
        await message.reply("❌ Failed to process image.")

@dp.message(lambda m: m.photo)
async def handle_photo(message: Message):
    """Handle photo (compressed by Telegram)."""
    user_id = message.from_user.id
    photo = message.photo[-1]

    try:
        file_info = await bot.get_file(photo.file_id)
        file_bytes = await bot.download_file(file_info.file_path)

        user_states[user_id] = {
            "image_bytes": file_bytes.getvalue(),
            "filename": "image.jpg",
            "input_format": "jpeg"
        }

        await message.reply(
            "📸 Photo received!\n\n"
            "Select *output format*:",
            reply_markup=get_format_keyboard()
        )
    except Exception as e:
        logger.error(f"Photo error: {e}")
        await message.reply("❌ Failed to process image.")

@dp.callback_query(lambda c: c.data and c.data.startswith("format_"))
async def handle_format(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in user_states:
        await callback.answer("❌ Please send an image first!", show_alert=True)
        return

    output_format = callback.data.replace("format_", "")
    user_states[user_id]["output_format"] = output_format

    await callback.answer(f"Format: {output_format.upper()}")
    await callback.message.edit_text(
        f"📁 *Output format:* {output_format.upper()}\n\n"
        "Select *quality level*:",
        reply_markup=get_compression_keyboard()
    )

@dp.callback_query(lambda c: c.data and c.data.startswith("quality_"))
async def handle_quality(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in user_states:
        await callback.answer("❌ Please send an image first!", show_alert=True)
        return

    quality_str = callback.data.replace("quality_", "")
    user_data = user_states[user_id]

    if quality_str == "original":
        quality = None
        label = "Original (optimized)"
    else:
        quality = int(quality_str)
        label = f"{quality}%"

    await callback.answer(f"Quality: {label}")

    # Get data
    image_bytes = user_data["image_bytes"]
    output_format = user_data["output_format"]
    filename = user_data.get("filename", "image")

    # Show processing
    await callback.message.edit_text(
        f"🔄 Compressing...\n"
        f"Format: {output_format.upper()}\n"
        f"Quality: {label}\n\n"
        f"⏳ Please wait..."
    )

    # Compress
    compressed = await compress_image(image_bytes, output_format, quality)

    if not compressed:
        await callback.message.edit_text("❌ Compression failed. Try again.")
        return

    # Send result
    base = filename.rsplit(".", 1)[0]
    output_filename = f"{base}_compressed.{output_format}"

    input_file = BufferedInputFile(compressed, filename=output_filename)
    original_size_kb = len(image_bytes) / 1024
    compressed_size_kb = len(compressed) / 1024
    saved = ((original_size_kb - compressed_size_kb) / original_size_kb * 100) if original_size_kb > 0 else 0

    await bot.send_document(
        chat_id=user_id,
        document=input_file,
        caption=(
            f"✅ *Compressed!*\n"
            f"📁 {output_format.upper()} | Quality: {label}\n"
            f"📉 {original_size_kb:.1f} KB → {compressed_size_kb:.1f} KB\n"
            f"💾 Saved {saved:.1f}%"
        )
    )

    # Clean up
    del user_states[user_id]
    await callback.message.edit_text(
        "✅ Done! Send another image to compress again."
    )

@dp.callback_query(lambda c: c.data == "cancel")
async def cancel_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id in user_states:
        del user_states[user_id]
    await callback.answer("Cancelled")
    await callback.message.edit_text("✅ Cancelled.")

@dp.message()
async def unknown(message: Message):
    await message.reply(
        "🤔 Send me an image to compress!\n"
        "Use /help for instructions."
    )

# ==================== Main ====================

async def main():
    logger.info("Starting SquooshImageBot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
