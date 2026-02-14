from __future__ import annotations

import logging

from telegram import BotCommand, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from src.core.context_store import InMemoryContextStore
from src.services.ollama_client import (
    OllamaClient,
    OllamaConnectionError,
    OllamaError,
    OllamaTimeoutError,
)
from src.utils.telegram import split_message

logger = logging.getLogger(__name__)


class BotHandlers:
    def __init__(
        self,
        ollama_client: OllamaClient,
        context_store: InMemoryContextStore,
        default_model: str,
    ) -> None:
        self._ollama_client = ollama_client
        self._context_store = context_store
        self._default_model = default_model

    async def set_commands(self, application: Application) -> None:
        await application.bot.set_my_commands(
            [
                BotCommand(command="start", description="Start the bot"),
                BotCommand(command="help", description="Show available commands"),
                BotCommand(command="clear", description="Clear conversation context"),
            ]
        )

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        await update.effective_message.reply_text(
            "Welcome! Send a message and I will ask Ollama for a response.\n"
            "Use /clear to reset your conversation context."
        )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        await update.effective_message.reply_text(
            "Available commands:\n"
            "/start - Start the bot\n"
            "/help - Show this help\n"
            "/clear - Clear your context"
        )

    async def clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message or not update.effective_user:
            return
        self._context_store.clear(update.effective_user.id)
        await update.effective_message.reply_text("Your conversation context has been cleared.")

    async def on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message or not update.effective_user:
            return

        user_text = (update.effective_message.text or "").strip()
        if not user_text:
            await update.effective_message.reply_text("Please send a non-empty message.")
            return

        user_id = update.effective_user.id
        turns = self._context_store.get_turns(user_id)

        await update.effective_chat.send_action(action=ChatAction.TYPING)

        try:
            ollama_response = await self._ollama_client.generate(
                model=self._default_model,
                prompt=user_text,
                context_turns=turns,
            )
        except OllamaTimeoutError:
            await update.effective_message.reply_text(
                "Ollama is taking too long to respond. Please try again shortly."
            )
            return
        except OllamaConnectionError:
            await update.effective_message.reply_text(
                "I could not connect to Ollama. Please contact the bot administrator."
            )
            return
        except OllamaError as error:
            logger.warning("Ollama error: %s", error)
            await update.effective_message.reply_text(
                "Ollama returned an error. Please try again in a few moments."
            )
            return

        self._context_store.append(user_id, role="user", content=user_text)
        self._context_store.append(user_id, role="assistant", content=ollama_response.text)

        for chunk in split_message(ollama_response.text):
            await update.effective_message.reply_text(chunk, parse_mode=ParseMode.HTML)


def register_handlers(application: Application, handlers: BotHandlers) -> None:
    application.post_init = handlers.set_commands
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("help", handlers.help))
    application.add_handler(CommandHandler("clear", handlers.clear))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_text))
