from __future__ import annotations

import logging

from telegram import BotCommand, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from src.core.context_store import InMemoryContextStore
from src.core.model_preferences_store import ModelPreferencesStore
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
        model_preferences_store: ModelPreferencesStore,
        default_model: str,
    ) -> None:
        self._ollama_client = ollama_client
        self._context_store = context_store
        self._model_preferences_store = model_preferences_store
        self._default_model = default_model

    async def set_commands(self, application: Application) -> None:
        await application.bot.set_my_commands(
            [
                BotCommand(command="start", description="Start the bot"),
                BotCommand(command="help", description="Show available commands"),
                BotCommand(command="clear", description="Clear conversation context"),
                BotCommand(command="models", description="List or select model"),
                BotCommand(command="currentmodel", description="Show your current model"),
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
            "/clear - Clear your context\n"
            "/models - List models or select one with /models <name>\n"
            "/currentmodel - Show your active model"
        )

    async def clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message or not update.effective_user:
            return
        self._context_store.clear(update.effective_user.id)
        await update.effective_message.reply_text("Your conversation context has been cleared.")

    async def models(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message or not update.effective_user:
            return

        user_id = update.effective_user.id
        requested_model = " ".join(context.args).strip() if context.args else ""

        try:
            models = await self._ollama_client.list_models()
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
            logger.warning("Ollama error while listing models: %s", error)
            await update.effective_message.reply_text(
                "I could not load models from Ollama right now. Please try again later."
            )
            return

        if not models:
            await update.effective_message.reply_text(
                "No models are currently available in Ollama."
            )
            return

        if requested_model:
            if requested_model not in models:
                await update.effective_message.reply_text(
                    "Model not found. Use /models to see available names."
                )
                return
            try:
                self._model_preferences_store.set_user_model(user_id, requested_model)
            except Exception as error:
                logger.exception("Failed to save user model preference: %s", error)
                await update.effective_message.reply_text(
                    "I could not save your model preference. Please try again later."
                )
                return
            await update.effective_message.reply_text(
                f"Model updated to: {requested_model}"
            )
            return

        current_model = self._get_user_model(user_id)
        lines = ["Available models:"]
        for model in models:
            marker = " (current)" if model == current_model else ""
            lines.append(f"- {model}{marker}")
        lines.append("")
        lines.append("Select one with: /models <name>")

        await update.effective_message.reply_text("\n".join(lines))

    async def current_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message or not update.effective_user:
            return

        user_id = update.effective_user.id
        current_model = self._get_user_model(user_id)
        await update.effective_message.reply_text(f"Current model: {current_model}")

    async def on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message or not update.effective_user:
            return

        user_text = (update.effective_message.text or "").strip()
        if not user_text:
            await update.effective_message.reply_text("Please send a non-empty message.")
            return

        user_id = update.effective_user.id
        turns = self._context_store.get_turns(user_id)
        model = self._get_user_model(user_id)

        await update.effective_chat.send_action(action=ChatAction.TYPING)

        try:
            ollama_response = await self._ollama_client.generate(
                model=model,
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

    def _get_user_model(self, user_id: int) -> str:
        try:
            selected_model = self._model_preferences_store.get_user_model(user_id)
        except Exception as error:
            logger.exception("Failed to load user model preference: %s", error)
            return self._default_model

        if not selected_model:
            return self._default_model
        return selected_model


def register_handlers(application: Application, handlers: BotHandlers) -> None:
    application.post_init = handlers.set_commands
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("help", handlers.help))
    application.add_handler(CommandHandler("clear", handlers.clear))
    application.add_handler(CommandHandler("models", handlers.models))
    application.add_handler(CommandHandler("currentmodel", handlers.current_model))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_text))
