from __future__ import annotations

import logging

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

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

BUTTON_MODELS = "🧠 Models"
BUTTON_CURRENT_MODEL = "📌 Current Model"
BUTTON_CLEAR = "🧹 Clear Context"
BUTTON_HELP = "❓ Help"
MODEL_CALLBACK_PREFIX = "model:"
CLEAR_CALLBACK_PREFIX = "clear:"
MODEL_REFRESH_ACTION = "__refresh__"
MODEL_DEFAULT_ACTION = "__default__"
ICON_INFO = "ℹ️"
ICON_SUCCESS = "✅"
ICON_WARNING = "⚠️"
ICON_ERROR = "❌"


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
            "✨ <b>Welcome!</b> Send a message and I will ask Ollama for a response.\n"
            "Use the buttons below or slash commands.",
            parse_mode=ParseMode.HTML,
            reply_markup=self._main_keyboard(),
        )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        await update.effective_message.reply_text(
            f"{ICON_INFO} Available commands:\n"
            "/start - Start the bot\n"
            "/help - Show this help\n"
            "/clear - Clear your context\n"
            "/models - List models or select one with /models <name>\n"
            "/currentmodel - Show your active model",
            reply_markup=self._main_keyboard(),
        )

    async def clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message or not update.effective_user:
            return
        await update.effective_message.reply_text(
            f"{ICON_WARNING} <b>Clear context?</b>\nThis will remove your current chat memory.",
            parse_mode=ParseMode.HTML,
            reply_markup=self._clear_inline_keyboard(),
        )

    async def models(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message or not update.effective_user:
            return

        user_id = update.effective_user.id
        requested_model = " ".join(context.args).strip() if context.args else ""

        try:
            models = await self._ollama_client.list_models()
        except OllamaTimeoutError:
            await update.effective_message.reply_text(
                self._warning("Ollama is taking too long to respond. Please try again shortly."),
                reply_markup=self._main_keyboard(),
            )
            return
        except OllamaConnectionError:
            await update.effective_message.reply_text(
                self._error("I could not connect to Ollama. Please contact the bot administrator."),
                reply_markup=self._main_keyboard(),
            )
            return
        except OllamaError as error:
            logger.warning("Ollama error while listing models: %s", error)
            await update.effective_message.reply_text(
                self._error("I could not load models from Ollama right now. Please try again later."),
                reply_markup=self._main_keyboard(),
            )
            return

        if not models:
            await update.effective_message.reply_text(
                self._info("No models are currently available in Ollama."),
                reply_markup=self._main_keyboard(),
            )
            return

        if requested_model:
            if requested_model not in models:
                await update.effective_message.reply_text(
                    self._warning("Model not found. Use /models to see available names."),
                    reply_markup=self._main_keyboard(),
                )
                return
            try:
                self._model_preferences_store.set_user_model(user_id, requested_model)
            except Exception as error:
                logger.exception("Failed to save user model preference: %s", error)
                await update.effective_message.reply_text(
                    self._error("I could not save your model preference. Please try again later."),
                    reply_markup=self._main_keyboard(),
                )
                return
            await update.effective_message.reply_text(
                self._success(f"Model updated to: {requested_model}"),
                reply_markup=self._main_keyboard(),
            )
            return

        current_model = self._get_user_model(user_id)
        lines = [self._info("Available models:")]
        for model in models:
            marker = " (current)" if model == current_model else ""
            lines.append(f"- {model}{marker}")
        lines.append("")
        lines.append("Select one with: /models <name>")
        lines.append("Or tap a button below.")

        inline_keyboard = self._models_inline_keyboard(models, current_model)
        await update.effective_message.reply_text(
            "\n".join(lines),
            reply_markup=inline_keyboard,
        )

    async def clear_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not update.effective_user:
            return
        if not query.message:
            return

        await query.answer()

        data = query.data or ""
        if not data.startswith(CLEAR_CALLBACK_PREFIX):
            return

        action = data.removeprefix(CLEAR_CALLBACK_PREFIX).strip()
        if action == "cancel":
            await query.message.reply_text(
                self._info("Clear cancelled."),
                reply_markup=self._main_keyboard(),
            )
            return

        if action == "confirm":
            self._context_store.clear(update.effective_user.id)
            await query.message.reply_text(
                self._success("Your conversation context has been cleared."),
                reply_markup=self._main_keyboard(),
            )

    async def select_model_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        if not query or not update.effective_user:
            return
        if not query.message:
            return

        await query.answer()

        data = query.data or ""
        if not data.startswith(MODEL_CALLBACK_PREFIX):
            return

        selected_model = data.removeprefix(MODEL_CALLBACK_PREFIX).strip()
        if not selected_model:
            return

        if selected_model == MODEL_REFRESH_ACTION:
            await self.models(update, context)
            return

        user_id = update.effective_user.id

        try:
            models = await self._ollama_client.list_models()
        except OllamaTimeoutError:
            await query.message.reply_text(
                self._warning("Ollama is taking too long to respond. Please try again shortly."),
                reply_markup=self._main_keyboard(),
            )
            return
        except OllamaConnectionError:
            await query.message.reply_text(
                self._error("I could not connect to Ollama. Please contact the bot administrator."),
                reply_markup=self._main_keyboard(),
            )
            return
        except OllamaError as error:
            logger.warning("Ollama error while selecting model: %s", error)
            await query.message.reply_text(
                self._error("I could not validate the selected model right now. Please try again later."),
                reply_markup=self._main_keyboard(),
            )
            return

        if selected_model not in models:
            if selected_model == MODEL_DEFAULT_ACTION:
                try:
                    self._model_preferences_store.set_user_model(user_id, self._default_model)
                except Exception as error:
                    logger.exception("Failed to save default model preference: %s", error)
                    await query.message.reply_text(
                        self._error(
                            "I could not save your default model preference. Please try again later."
                        ),
                        reply_markup=self._main_keyboard(),
                    )
                    return

                await query.message.reply_text(
                    self._success(f"Model reset to default: {self._default_model}"),
                    reply_markup=self._main_keyboard(),
                )
                return

            await query.message.reply_text(
                self._warning("Model is no longer available. Use /models to refresh the list."),
                reply_markup=self._main_keyboard(),
            )
            return

        try:
            self._model_preferences_store.set_user_model(user_id, selected_model)
        except Exception as error:
            logger.exception("Failed to save user model preference: %s", error)
            await query.message.reply_text(
                self._error("I could not save your model preference. Please try again later."),
                reply_markup=self._main_keyboard(),
            )
            return

        await query.message.reply_text(
            self._success(f"Model updated to: {selected_model}"),
            reply_markup=self._main_keyboard(),
        )

    async def current_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message or not update.effective_user:
            return

        user_id = update.effective_user.id
        current_model = self._get_user_model(user_id)
        await update.effective_message.reply_text(
            self._info(f"Current model: {current_model}"),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text="🧠 Open Models",
                            callback_data=f"{MODEL_CALLBACK_PREFIX}{MODEL_REFRESH_ACTION}",
                        ),
                        InlineKeyboardButton(
                            text="♻️ Use Default",
                            callback_data=f"{MODEL_CALLBACK_PREFIX}{MODEL_DEFAULT_ACTION}",
                        ),
                    ]
                ]
            ),
        )

    async def quick_actions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return

        text = (update.effective_message.text or "").strip()
        if text == BUTTON_MODELS:
            await self.models(update, context)
            return
        if text == BUTTON_CURRENT_MODEL:
            await self.current_model(update, context)
            return
        if text == BUTTON_CLEAR:
            await self.clear(update, context)
            return
        if text == BUTTON_HELP:
            await self.help(update, context)
            return

    async def on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message or not update.effective_user:
            return

        user_text = (update.effective_message.text or "").strip()
        if not user_text:
            await update.effective_message.reply_text(
                self._warning("Please send a non-empty message."),
                reply_markup=self._main_keyboard(),
            )
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
                self._warning("Ollama is taking too long to respond. Please try again shortly."),
                reply_markup=self._main_keyboard(),
            )
            return
        except OllamaConnectionError:
            await update.effective_message.reply_text(
                self._error("I could not connect to Ollama. Please contact the bot administrator."),
                reply_markup=self._main_keyboard(),
            )
            return
        except OllamaError as error:
            logger.warning("Ollama error: %s", error)
            await update.effective_message.reply_text(
                self._error("Ollama returned an error. Please try again in a few moments."),
                reply_markup=self._main_keyboard(),
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

    @staticmethod
    def _status(icon: str, text: str) -> str:
        return f"{icon} {text}"

    @staticmethod
    def _info(text: str) -> str:
        return BotHandlers._status(ICON_INFO, text)

    @staticmethod
    def _success(text: str) -> str:
        return BotHandlers._status(ICON_SUCCESS, text)

    @staticmethod
    def _warning(text: str) -> str:
        return BotHandlers._status(ICON_WARNING, text)

    @staticmethod
    def _error(text: str) -> str:
        return BotHandlers._status(ICON_ERROR, text)

    @staticmethod
    def _models_inline_keyboard(models: list[str], current_model: str) -> InlineKeyboardMarkup:
        rows: list[list[InlineKeyboardButton]] = []
        row: list[InlineKeyboardButton] = []

        for model in models:
            label = f"✅ {model}" if model == current_model else model
            callback_data = f"{MODEL_CALLBACK_PREFIX}{model}"

            if len(callback_data) > 64:
                continue

            row.append(InlineKeyboardButton(text=label, callback_data=callback_data))
            if len(row) == 2:
                rows.append(row)
                row = []

        if row:
            rows.append(row)

        if not rows:
            rows = [
                [
                    InlineKeyboardButton(
                        text="Refresh models",
                        callback_data=f"{MODEL_CALLBACK_PREFIX}{MODEL_REFRESH_ACTION}",
                    )
                ]
            ]

        rows.append(
            [
                InlineKeyboardButton(
                    text="♻️ Use default",
                    callback_data=f"{MODEL_CALLBACK_PREFIX}{MODEL_DEFAULT_ACTION}",
                ),
                InlineKeyboardButton(
                    text="🔄 Refresh",
                    callback_data=f"{MODEL_CALLBACK_PREFIX}{MODEL_REFRESH_ACTION}",
                ),
            ]
        )

        return InlineKeyboardMarkup(rows)

    @staticmethod
    def _main_keyboard() -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(BUTTON_MODELS), KeyboardButton(BUTTON_CURRENT_MODEL)],
                [KeyboardButton(BUTTON_CLEAR), KeyboardButton(BUTTON_HELP)],
            ],
            resize_keyboard=True,
            is_persistent=True,
            input_field_placeholder="Write a message or use buttons…",
        )

    @staticmethod
    def _clear_inline_keyboard() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        text="✅ Confirm",
                        callback_data=f"{CLEAR_CALLBACK_PREFIX}confirm",
                    ),
                    InlineKeyboardButton(
                        text="❌ Cancel",
                        callback_data=f"{CLEAR_CALLBACK_PREFIX}cancel",
                    ),
                ]
            ]
        )


def register_handlers(application: Application, handlers: BotHandlers) -> None:
    application.post_init = handlers.set_commands
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("help", handlers.help))
    application.add_handler(CommandHandler("clear", handlers.clear))
    application.add_handler(CommandHandler("models", handlers.models))
    application.add_handler(CommandHandler("currentmodel", handlers.current_model))
    application.add_handler(CallbackQueryHandler(handlers.select_model_callback, pattern=r"^model:"))
    application.add_handler(CallbackQueryHandler(handlers.clear_callback, pattern=r"^clear:"))
    application.add_handler(
        MessageHandler(
            filters.Regex(
                rf"^({BUTTON_MODELS}|{BUTTON_CURRENT_MODEL}|{BUTTON_CLEAR}|{BUTTON_HELP})$"
            ),
            handlers.quick_actions,
        )
    )
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_text))
