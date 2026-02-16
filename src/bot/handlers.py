from __future__ import annotations

import base64
import logging
import re
from time import monotonic

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

from src.core.context_store import ContextStore, ConversationTurn
from src.core.model_preferences_store import ModelPreferencesStore
from src.core.rate_limiter import SlidingWindowRateLimiter
from src.i18n import I18nService
from src.services.ollama_client import (
    OllamaClient,
    OllamaConnectionError,
    OllamaError,
    OllamaTimeoutError,
)
from src.utils.telegram import split_message

logger = logging.getLogger(__name__)

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
        context_store: ContextStore,
        model_preferences_store: ModelPreferencesStore,
        default_model: str,
        use_chat_api: bool,
        keep_alive: str,
        image_max_bytes: int,
        i18n: I18nService,
        allowed_user_ids: set[int] | None = None,
        rate_limiter: SlidingWindowRateLimiter | None = None,
    ) -> None:
        self._ollama_client = ollama_client
        self._context_store = context_store
        self._model_preferences_store = model_preferences_store
        self._default_model = default_model
        self._use_chat_api = use_chat_api
        self._keep_alive = keep_alive
        self._image_max_bytes = image_max_bytes
        self._i18n = i18n
        self._allowed_user_ids = allowed_user_ids or set()
        self._rate_limiter = rate_limiter
        self._quick_action_map = self._build_quick_action_map()

    @staticmethod
    def required_i18n_keys() -> tuple[str, ...]:
        return (
            "commands.start",
            "commands.help",
            "commands.health",
            "commands.clear",
            "commands.models",
            "commands.currentmodel",
            "ui.buttons.models",
            "ui.buttons.current_model",
            "ui.buttons.clear",
            "ui.buttons.help",
            "ui.buttons.open_models",
            "ui.buttons.use_default",
            "ui.buttons.refresh",
            "ui.buttons.refresh_models",
            "ui.buttons.confirm",
            "ui.buttons.cancel",
            "ui.input_placeholder",
            "messages.start_welcome",
            "messages.help",
            "messages.please_send_non_empty",
            "messages.voice_disabled",
            "messages.clear_confirm",
            "messages.clear_cancelled",
            "messages.clear_done",
            "messages.current_model",
            "messages.access_denied",
            "messages.access_denied_alert",
            "messages.rate_limit_exceeded",
            "messages.unexpected_error",
            "health.result",
            "health.ok",
            "health.degraded",
            "health.sqlite",
            "health.ollama",
            "health.ollama_ok_with_models",
            "health.runtime_ok",
            "health.latency",
            "models.available_title",
            "models.current_marker",
            "models.select_with",
            "models.tap_button",
            "models.updated",
            "models.reset_default",
            "models.not_found",
            "models.not_available_anymore",
            "models.no_models_available",
            "image.default_prompt",
            "image.model_without_vision",
            "image.too_large",
            "image.invalid_file",
            "image.processing_error",
            "image.read_error",
            "errors.ollama_timeout",
            "errors.ollama_connection",
            "errors.ollama_list_models",
            "errors.ollama_validate_model",
            "errors.save_model_preference",
            "errors.save_default_model_preference",
            "errors.ollama_generic",
            "agent.planner_instruction",
            "agent.analyst_instruction",
            "agent.chat_instruction",
        )

    async def set_commands(self, application: Application) -> None:
        for locale in self._i18n.available_locales:
            commands = [
                BotCommand(command="start", description=self._i18n.t("commands.start", locale=locale)),
                BotCommand(command="help", description=self._i18n.t("commands.help", locale=locale)),
                BotCommand(command="health", description=self._i18n.t("commands.health", locale=locale)),
                BotCommand(command="clear", description=self._i18n.t("commands.clear", locale=locale)),
                BotCommand(command="models", description=self._i18n.t("commands.models", locale=locale)),
                BotCommand(
                    command="currentmodel",
                    description=self._i18n.t("commands.currentmodel", locale=locale),
                ),
            ]
            if locale == self._i18n.default_locale:
                await application.bot.set_my_commands(commands)
            else:
                await application.bot.set_my_commands(commands, language_code=locale)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard_access(update):
            return
        if not update.effective_message:
            return
        locale = self._locale(update)
        self._log_user_event("command_start", update)
        await update.effective_message.reply_text(
            self._i18n.t("messages.start_welcome", locale=locale),
            parse_mode=ParseMode.HTML,
            reply_markup=self._main_keyboard(locale),
        )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard_access(update):
            return
        if not update.effective_message:
            return
        locale = self._locale(update)
        self._log_user_event("command_help", update)
        await update.effective_message.reply_text(
            self._i18n.t("messages.help", locale=locale),
            reply_markup=self._main_keyboard(locale),
        )

    async def health(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard_access(update):
            return
        if not update.effective_message or not update.effective_user:
            return
        locale = self._locale(update)

        self._log_user_event("command_health", update)
        started_at = monotonic()

        db_ok = True
        db_detail = "OK"
        try:
            self._model_preferences_store.healthcheck()
        except Exception as error:
            logger.exception("health_db_check_failed user_id=%s", update.effective_user.id)
            db_ok = False
            db_detail = str(error)

        ollama_ok = True
        ollama_detail = "OK"
        ollama_model_count = 0
        try:
            models = await self._ollama_client.list_models()
            ollama_model_count = len(models)
            ollama_detail = self._i18n.t(
                "health.ollama_ok_with_models",
                locale=locale,
                count=ollama_model_count,
            )
        except Exception as error:
            logger.exception("health_ollama_check_failed user_id=%s", update.effective_user.id)
            ollama_ok = False
            ollama_detail = str(error)

        elapsed_ms = int((monotonic() - started_at) * 1000)
        overall_ok = db_ok and ollama_ok
        overall_text = (
            self._i18n.t("health.ok", locale=locale)
            if overall_ok
            else self._i18n.t("health.degraded", locale=locale)
        )

        lines = [self._info(self._i18n.t("health.result", locale=locale, status=overall_text))]
        lines.append(
            f"{ICON_SUCCESS if db_ok else ICON_ERROR} "
            f"{self._i18n.t('health.sqlite', locale=locale, detail=db_detail)}"
        )
        lines.append(
            f"{ICON_SUCCESS if ollama_ok else ICON_ERROR} "
            f"{self._i18n.t('health.ollama', locale=locale, detail=ollama_detail)}"
        )
        lines.append(f"{ICON_INFO} {self._i18n.t('health.runtime_ok', locale=locale)}")
        lines.append(f"{ICON_INFO} {self._i18n.t('health.latency', locale=locale, ms=elapsed_ms)}")

        logger.info(
            "healthcheck_result user_id=%s overall_ok=%s db_ok=%s ollama_ok=%s ollama_models=%d elapsed_ms=%d",
            update.effective_user.id,
            overall_ok,
            db_ok,
            ollama_ok,
            ollama_model_count,
            elapsed_ms,
        )

        await update.effective_message.reply_text(
            "\n".join(lines), reply_markup=self._main_keyboard(locale)
        )

    async def clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard_access(update):
            return
        if not update.effective_message or not update.effective_user:
            return
        locale = self._locale(update)
        self._log_user_event("command_clear", update)
        await update.effective_message.reply_text(
            self._warning(self._i18n.t("messages.clear_confirm", locale=locale)),
            parse_mode=ParseMode.HTML,
            reply_markup=self._clear_inline_keyboard(locale),
        )

    async def models(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard_access(update):
            return
        if not update.effective_message or not update.effective_user:
            return

        locale = self._locale(update)
        user_id = update.effective_user.id
        self._log_user_event("command_models", update)
        requested_model = " ".join(context.args).strip() if context.args else ""

        try:
            models = await self._ollama_client.list_models()
        except OllamaTimeoutError:
            await update.effective_message.reply_text(
                self._warning(self._i18n.t("errors.ollama_timeout", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return
        except OllamaConnectionError:
            await update.effective_message.reply_text(
                self._error(self._i18n.t("errors.ollama_connection", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return
        except OllamaError as error:
            logger.warning("Ollama error while listing models: %s", error)
            await update.effective_message.reply_text(
                self._error(self._i18n.t("errors.ollama_list_models", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return

        if not models:
            await update.effective_message.reply_text(
                self._info(self._i18n.t("models.no_models_available", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return

        if requested_model:
            if requested_model not in models:
                await update.effective_message.reply_text(
                    self._warning(self._i18n.t("models.not_found", locale=locale)),
                    reply_markup=self._main_keyboard(locale),
                )
                return
            try:
                self._model_preferences_store.set_user_model(user_id, requested_model)
            except Exception as error:
                logger.exception("Failed to save user model preference: %s", error)
                await update.effective_message.reply_text(
                    self._error(self._i18n.t("errors.save_model_preference", locale=locale)),
                    reply_markup=self._main_keyboard(locale),
                )
                return
            await update.effective_message.reply_text(
                self._success(self._i18n.t("models.updated", locale=locale, model=requested_model)),
                reply_markup=self._main_keyboard(locale),
            )
            return

        current_model = self._get_user_model(user_id)
        lines = [self._info(self._i18n.t("models.available_title", locale=locale))]
        for model in models:
            marker = self._i18n.t("models.current_marker", locale=locale) if model == current_model else ""
            lines.append(f"- {model}{marker}")
        lines.append("")
        lines.append(self._i18n.t("models.select_with", locale=locale))
        lines.append(self._i18n.t("models.tap_button", locale=locale))

        inline_keyboard = self._models_inline_keyboard(locale, models, current_model)
        await update.effective_message.reply_text(
            "\n".join(lines),
            reply_markup=inline_keyboard,
        )

    async def clear_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard_access(update):
            return
        query = update.callback_query
        if not query or not update.effective_user:
            return
        if not query.message:
            return
        locale = self._locale(update)

        await query.answer()

        data = query.data or ""
        if not data.startswith(CLEAR_CALLBACK_PREFIX):
            return

        action = data.removeprefix(CLEAR_CALLBACK_PREFIX).strip()
        if action == "cancel":
            await query.message.reply_text(
                self._info(self._i18n.t("messages.clear_cancelled", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return

        if action == "confirm":
            self._context_store.clear(update.effective_user.id)
            await query.message.reply_text(
                self._success(self._i18n.t("messages.clear_done", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )

    async def select_model_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not await self._guard_access(update):
            return
        query = update.callback_query
        if not query or not update.effective_user:
            return
        if not query.message:
            return
        locale = self._locale(update)

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
                self._warning(self._i18n.t("errors.ollama_timeout", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return
        except OllamaConnectionError:
            await query.message.reply_text(
                self._error(self._i18n.t("errors.ollama_connection", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return
        except OllamaError as error:
            logger.warning("Ollama error while selecting model: %s", error)
            await query.message.reply_text(
                self._error(self._i18n.t("errors.ollama_validate_model", locale=locale)),
                reply_markup=self._main_keyboard(locale),
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
                            self._i18n.t("errors.save_default_model_preference", locale=locale)
                        ),
                        reply_markup=self._main_keyboard(locale),
                    )
                    return

                await query.message.reply_text(
                    self._success(
                        self._i18n.t("models.reset_default", locale=locale, model=self._default_model)
                    ),
                    reply_markup=self._main_keyboard(locale),
                )
                return

            await query.message.reply_text(
                self._warning(self._i18n.t("models.not_available_anymore", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return

        try:
            self._model_preferences_store.set_user_model(user_id, selected_model)
        except Exception as error:
            logger.exception("Failed to save user model preference: %s", error)
            await query.message.reply_text(
                self._error(self._i18n.t("errors.save_model_preference", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return

        await query.message.reply_text(
            self._success(self._i18n.t("models.updated", locale=locale, model=selected_model)),
            reply_markup=self._main_keyboard(locale),
        )

    async def current_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard_access(update):
            return
        if not update.effective_message or not update.effective_user:
            return

        locale = self._locale(update)
        self._log_user_event("command_currentmodel", update)
        user_id = update.effective_user.id
        current_model = self._get_user_model(user_id)
        await update.effective_message.reply_text(
            self._info(self._i18n.t("messages.current_model", locale=locale, model=current_model)),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text=self._i18n.t("ui.buttons.open_models", locale=locale),
                            callback_data=f"{MODEL_CALLBACK_PREFIX}{MODEL_REFRESH_ACTION}",
                        ),
                        InlineKeyboardButton(
                            text=self._i18n.t("ui.buttons.use_default", locale=locale),
                            callback_data=f"{MODEL_CALLBACK_PREFIX}{MODEL_DEFAULT_ACTION}",
                        ),
                    ]
                ]
            ),
        )

    async def quick_actions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard_access(update):
            return
        if not update.effective_message:
            return

        text = (update.effective_message.text or "").strip()
        action = self._quick_action_map.get(text)
        if action == "models":
            await self.models(update, context)
            return
        if action == "current_model":
            await self.current_model(update, context)
            return
        if action == "clear":
            await self.clear(update, context)
            return
        if action == "help":
            await self.help(update, context)
            return

    async def on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard_access(update, apply_rate_limit=True):
            return
        if not update.effective_message or not update.effective_user:
            return

        locale = self._locale(update)
        user_text = (update.effective_message.text or "").strip()
        self._log_user_event("message_received", update)
        if not user_text:
            await update.effective_message.reply_text(
                self._warning(self._i18n.t("messages.please_send_non_empty", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return

        user_id = update.effective_user.id
        turns = self._context_store.get_turns(user_id)
        model = self._get_user_model(user_id)
        started_at = monotonic()
        agent_name = self._select_agent(user_text)
        system_instruction = self._agent_system_instruction(agent_name, locale)

        await update.effective_chat.send_action(action=ChatAction.TYPING)

        try:
            ollama_response = await self._generate_response(
                user_id=user_id,
                model=model,
                prompt=user_text,
                turns=turns,
                system_instruction=system_instruction,
            )
        except OllamaTimeoutError:
            await update.effective_message.reply_text(
                self._warning(self._i18n.t("errors.ollama_timeout", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return
        except OllamaConnectionError:
            await update.effective_message.reply_text(
                self._error(self._i18n.t("errors.ollama_connection", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return
        except OllamaError as error:
            logger.warning("Ollama error: %s", error)
            await update.effective_message.reply_text(
                self._error(self._i18n.t("errors.ollama_generic", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return

        self._context_store.append(user_id, role="user", content=user_text)
        self._context_store.append(user_id, role="assistant", content=ollama_response.text)

        elapsed_ms = int((monotonic() - started_at) * 1000)
        logger.info(
            "message_completed user_id=%s model=%s agent=%s input_chars=%d output_chars=%d elapsed_ms=%d",
            user_id,
            model,
            agent_name,
            len(user_text),
            len(ollama_response.text),
            elapsed_ms,
        )

        for chunk in split_message(ollama_response.text):
            await update.effective_message.reply_text(chunk, parse_mode=ParseMode.HTML)

    async def on_image(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard_access(update, apply_rate_limit=True):
            return
        if not update.effective_message or not update.effective_user:
            return

        locale = self._locale(update)
        message = update.effective_message
        user_id = update.effective_user.id
        caption = (message.caption or "").strip()
        user_prompt = caption or self._i18n.t("image.default_prompt", locale=locale)
        model = self._get_user_model(user_id)
        turns = self._context_store.get_turns(user_id)
        agent_name = self._select_agent(user_prompt)
        system_instruction = self._agent_system_instruction(agent_name, locale)
        turns_for_model: list[ConversationTurn] = [
            ConversationTurn(role="system", content=system_instruction),
            *turns,
        ]
        image_bytes_size = 0

        try:
            vision_support = await self._ollama_client.supports_vision(model)
            if vision_support is False:
                await message.reply_text(
                    self._warning(
                        self._i18n.t("image.model_without_vision", locale=locale, model=model)
                    ),
                    reply_markup=self._main_keyboard(locale),
                )
                return

            photo_bytes: bytes | None = None
            if message.photo:
                image_bytes_size = int(message.photo[-1].file_size or 0)
                if image_bytes_size > self._image_max_bytes:
                    await message.reply_text(
                        self._warning(
                            self._i18n.t(
                                "image.too_large",
                                locale=locale,
                                max_size=self._format_size(self._image_max_bytes),
                            )
                        ),
                        reply_markup=self._main_keyboard(locale),
                    )
                    return
                file = await message.photo[-1].get_file()
                photo_bytes = bytes(await file.download_as_bytearray())
            elif message.document and (message.document.mime_type or "").startswith("image/"):
                image_bytes_size = int(message.document.file_size or 0)
                if image_bytes_size > self._image_max_bytes:
                    await message.reply_text(
                        self._warning(
                            self._i18n.t(
                                "image.too_large",
                                locale=locale,
                                max_size=self._format_size(self._image_max_bytes),
                            )
                        ),
                        reply_markup=self._main_keyboard(locale),
                    )
                    return
                file = await message.document.get_file()
                photo_bytes = bytes(await file.download_as_bytearray())

            if not photo_bytes:
                await message.reply_text(
                    self._warning(self._i18n.t("image.invalid_file", locale=locale)),
                    reply_markup=self._main_keyboard(locale),
                )
                return

            image_base64 = base64.b64encode(photo_bytes).decode("utf-8")
            if not image_bytes_size:
                image_bytes_size = len(photo_bytes)
            if image_bytes_size > self._image_max_bytes:
                await message.reply_text(
                    self._warning(
                        self._i18n.t(
                            "image.too_large",
                            locale=locale,
                            max_size=self._format_size(self._image_max_bytes),
                        )
                    ),
                    reply_markup=self._main_keyboard(locale),
                )
                return

            started_at = monotonic()
            await update.effective_chat.send_action(action=ChatAction.TYPING)

            ollama_response = await self._ollama_client.chat_with_image(
                model=model,
                prompt=user_prompt,
                image_base64=image_base64,
                context_turns=turns_for_model,
                keep_alive=self._keep_alive,
            )
        except OllamaTimeoutError:
            await message.reply_text(
                self._warning(self._i18n.t("errors.ollama_timeout", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return
        except OllamaConnectionError:
            await message.reply_text(
                self._error(self._i18n.t("errors.ollama_connection", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return
        except OllamaError as error:
            logger.warning("Ollama image error: %s", error)
            await message.reply_text(
                self._error(self._i18n.t("image.processing_error", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return
        except Exception as error:
            logger.warning("image_read_failed user_id=%s error=%s", user_id, error)
            await message.reply_text(
                self._warning(self._i18n.t("image.read_error", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return

        self._context_store.append(user_id, role="user", content=f"[Image] {user_prompt}")
        self._context_store.append(user_id, role="assistant", content=ollama_response.text)

        elapsed_ms = int((monotonic() - started_at) * 1000)
        logger.info(
            "image_completed user_id=%s model=%s agent=%s prompt_chars=%d output_chars=%d elapsed_ms=%d",
            user_id,
            model,
            agent_name,
            len(user_prompt),
            len(ollama_response.text),
            elapsed_ms,
        )

        for chunk in split_message(ollama_response.text):
            await message.reply_text(chunk, parse_mode=ParseMode.HTML)

    async def on_voice_or_audio(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard_access(update):
            return
        if not update.effective_message:
            return
        locale = self._locale(update)

        await update.effective_message.reply_text(
            self._warning(self._i18n.t("messages.voice_disabled", locale=locale)),
            reply_markup=self._main_keyboard(locale),
        )

    async def _generate_response(
        self,
        *,
        user_id: int,
        model: str,
        prompt: str,
        turns: list[ConversationTurn],
        system_instruction: str,
    ):
        turns_for_model: list[ConversationTurn] = [ConversationTurn(role="system", content=system_instruction)]
        turns_for_model.extend(turns)

        if self._use_chat_api:
            try:
                return await self._ollama_client.chat(
                    model=model,
                    prompt=prompt,
                    context_turns=turns_for_model,
                    keep_alive=self._keep_alive,
                )
            except OllamaError as error:
                logger.warning(
                    "ollama_chat_fallback_to_generate user_id=%s model=%s error=%s",
                    user_id,
                    model,
                    error,
                )

        return await self._ollama_client.generate(
            model=model,
            prompt=prompt,
            context_turns=turns_for_model,
        )

    @staticmethod
    def _select_agent(user_text: str) -> str:
        text = user_text.lower()

        planning_keywords = [
            "plan",
            "roadmap",
            "step by step",
            "paso a paso",
            "planifica",
            "estrategia",
        ]
        analysis_keywords = [
            "resume",
            "resumen",
            "analiza",
            "análisis",
            "extrae",
            "clasifica",
            "category",
            "sentiment",
        ]

        if any(keyword in text for keyword in planning_keywords):
            return "planner"
        if any(keyword in text for keyword in analysis_keywords):
            return "analyst"
        return "chat"

    def _agent_system_instruction(self, agent_name: str, locale: str) -> str:
        if agent_name == "planner":
            return self._i18n.t("agent.planner_instruction", locale=locale)
        if agent_name == "analyst":
            return self._i18n.t("agent.analyst_instruction", locale=locale)
        return self._i18n.t("agent.chat_instruction", locale=locale)

    def _get_user_model(self, user_id: int) -> str:
        try:
            selected_model = self._model_preferences_store.get_user_model(user_id)
        except Exception as error:
            logger.exception("Failed to load user model preference: %s", error)
            return self._default_model

        if not selected_model:
            return self._default_model
        return selected_model

    async def _guard_access(self, update: Update, apply_rate_limit: bool = False) -> bool:
        user = update.effective_user
        if not user:
            return False

        if self._allowed_user_ids and user.id not in self._allowed_user_ids:
            logger.warning("access_denied user_id=%s", user.id)
            await self._deny_access(update)
            return False

        if apply_rate_limit and self._rate_limiter and not self._rate_limiter.allow(user.id):
            logger.warning("rate_limit_exceeded user_id=%s", user.id)
            locale = self._locale(update)
            target_message = update.effective_message or (
                update.callback_query.message if update.callback_query else None
            )
            if target_message:
                await target_message.reply_text(
                    self._warning(self._i18n.t("messages.rate_limit_exceeded", locale=locale)),
                    reply_markup=self._main_keyboard(locale),
                )
            return False

        return True

    async def _deny_access(self, update: Update) -> None:
        locale = self._locale(update)
        denied_text = self._error(self._i18n.t("messages.access_denied", locale=locale))

        query = update.callback_query
        if query:
            await query.answer(self._i18n.t("messages.access_denied_alert", locale=locale), show_alert=True)

        target_message = update.effective_message or (query.message if query else None)
        if target_message:
            await target_message.reply_text(denied_text)

    @staticmethod
    def _log_user_event(event: str, update: Update) -> None:
        user_id = update.effective_user.id if update.effective_user else "unknown"
        chat_id = update.effective_chat.id if update.effective_chat else "unknown"
        logger.info("%s user_id=%s chat_id=%s", event, user_id, chat_id)

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
    def _format_size(num_bytes: int) -> str:
        mib = num_bytes / (1024 * 1024)
        return f"{mib:.1f} MB"

    def _locale(self, update: Update) -> str:
        language_code = update.effective_user.language_code if update.effective_user else None
        return self._i18n.resolve_locale(language_code)

    def _build_quick_action_map(self) -> dict[str, str]:
        quick_action_keys = {
            "models": "ui.buttons.models",
            "current_model": "ui.buttons.current_model",
            "clear": "ui.buttons.clear",
            "help": "ui.buttons.help",
        }
        mapping: dict[str, str] = {}
        for locale in self._i18n.available_locales:
            for action, key in quick_action_keys.items():
                mapping[self._i18n.t(key, locale=locale)] = action
        return mapping

    def quick_actions_regex(self) -> str:
        labels = sorted({re.escape(label) for label in self._quick_action_map})
        return rf"^({'|'.join(labels)})$"

    def _models_inline_keyboard(
        self,
        locale: str,
        models: list[str],
        current_model: str,
    ) -> InlineKeyboardMarkup:
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
                        text=self._i18n.t("ui.buttons.refresh_models", locale=locale),
                        callback_data=f"{MODEL_CALLBACK_PREFIX}{MODEL_REFRESH_ACTION}",
                    )
                ]
            ]

        rows.append(
            [
                InlineKeyboardButton(
                    text=self._i18n.t("ui.buttons.use_default", locale=locale),
                    callback_data=f"{MODEL_CALLBACK_PREFIX}{MODEL_DEFAULT_ACTION}",
                ),
                InlineKeyboardButton(
                    text=self._i18n.t("ui.buttons.refresh", locale=locale),
                    callback_data=f"{MODEL_CALLBACK_PREFIX}{MODEL_REFRESH_ACTION}",
                ),
            ]
        )

        return InlineKeyboardMarkup(rows)

    def _main_keyboard(self, locale: str) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(self._i18n.t("ui.buttons.models", locale=locale)),
                    KeyboardButton(self._i18n.t("ui.buttons.current_model", locale=locale)),
                ],
                [
                    KeyboardButton(self._i18n.t("ui.buttons.clear", locale=locale)),
                    KeyboardButton(self._i18n.t("ui.buttons.help", locale=locale)),
                ],
            ],
            resize_keyboard=True,
            is_persistent=True,
            input_field_placeholder=self._i18n.t("ui.input_placeholder", locale=locale),
        )

    def _clear_inline_keyboard(self, locale: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        text=self._i18n.t("ui.buttons.confirm", locale=locale),
                        callback_data=f"{CLEAR_CALLBACK_PREFIX}confirm",
                    ),
                    InlineKeyboardButton(
                        text=self._i18n.t("ui.buttons.cancel", locale=locale),
                        callback_data=f"{CLEAR_CALLBACK_PREFIX}cancel",
                    ),
                ]
            ]
        )


def register_handlers(application: Application, handlers: BotHandlers) -> None:
    application.post_init = handlers.set_commands
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("help", handlers.help))
    application.add_handler(CommandHandler("health", handlers.health))
    application.add_handler(CommandHandler("clear", handlers.clear))
    application.add_handler(CommandHandler("models", handlers.models))
    application.add_handler(CommandHandler("currentmodel", handlers.current_model))
    application.add_handler(CallbackQueryHandler(handlers.select_model_callback, pattern=r"^model:"))
    application.add_handler(CallbackQueryHandler(handlers.clear_callback, pattern=r"^clear:"))
    application.add_handler(
        MessageHandler(
            filters.Regex(handlers.quick_actions_regex()),
            handlers.quick_actions,
        )
    )
    application.add_handler(
        MessageHandler(filters.VOICE | filters.AUDIO | filters.VIDEO_NOTE, handlers.on_voice_or_audio)
    )
    application.add_handler(
        MessageHandler(filters.PHOTO | filters.Document.IMAGE, handlers.on_image)
    )
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_text))
