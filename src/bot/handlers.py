from __future__ import annotations

import base64
import io
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
from src.core.user_assets_store import UserAsset, UserAssetsStore
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
WEB_MODEL_CALLBACK_PREFIX = "webmodel:"
FILE_CALLBACK_PREFIX = "file:"
CLEAR_CALLBACK_PREFIX = "clear:"
MODEL_REFRESH_ACTION = "__refresh__"
MODEL_DEFAULT_ACTION = "__default__"
MODEL_PAGE_ACTION_PREFIX = "__page__:"
MODEL_CLOSE_ACTION = "__close__"
WEB_MODEL_REFRESH_ACTION = "__refresh__"
WEB_MODEL_PAGE_ACTION_PREFIX = "__page__:"
WEB_MODEL_CLOSE_ACTION = "__close__"
FILE_PAGE_ACTION = "page"
FILE_TOGGLE_ACTION = "toggle"
FILE_DELETE_ACTION = "delete"
FILE_ASK_ACTION = "ask"
FILE_CLOSE_ACTION = "close"
ICON_INFO = "ℹ️"
ICON_SUCCESS = "✅"
ICON_WARNING = "⚠️"
ICON_ERROR = "❌"
MODELS_PAGE_SIZE = 8
WEB_MODELS_PAGE_SIZE = 8
FILES_PAGE_SIZE = 6
FILES_CONTEXT_MAX_ITEMS_DEFAULT = 3
FILES_CONTEXT_MAX_CHARS_DEFAULT = 6000


class BotHandlers:
    def __init__(
        self,
        ollama_client: OllamaClient,
        context_store: ContextStore,
        model_preferences_store: ModelPreferencesStore,
        user_assets_store: UserAssetsStore,
        default_model: str,
        use_chat_api: bool,
        keep_alive: str,
        image_max_bytes: int,
        document_max_bytes: int,
        document_max_chars: int,
        i18n: I18nService,
        files_context_max_items: int = FILES_CONTEXT_MAX_ITEMS_DEFAULT,
        files_context_max_chars: int = FILES_CONTEXT_MAX_CHARS_DEFAULT,
        allowed_user_ids: set[int] | None = None,
        rate_limiter: SlidingWindowRateLimiter | None = None,
    ) -> None:
        self._ollama_client = ollama_client
        self._context_store = context_store
        self._model_preferences_store = model_preferences_store
        self._user_assets_store = user_assets_store
        self._default_model = default_model
        self._use_chat_api = use_chat_api
        self._keep_alive = keep_alive
        self._image_max_bytes = image_max_bytes
        self._document_max_bytes = document_max_bytes
        self._document_max_chars = document_max_chars
        self._files_context_max_items = files_context_max_items
        self._files_context_max_chars = files_context_max_chars
        self._i18n = i18n
        self._allowed_user_ids = allowed_user_ids or set()
        self._rate_limiter = rate_limiter
        self._quick_action_map = self._build_quick_action_map()
        self._model_search_query_by_user: dict[int, str] = {}
        self._web_model_search_query_by_user: dict[int, str] = {}
        self._askfile_target_by_user: dict[int, int] = {}

    @staticmethod
    def required_i18n_keys() -> tuple[str, ...]:
        return (
            "commands.start",
            "commands.help",
            "commands.health",
            "commands.clear",
            "commands.models",
            "commands.webmodels",
            "commands.files",
            "commands.askfile",
            "commands.cancel",
            "commands.currentmodel",
            "ui.buttons.models",
            "ui.buttons.web_models",
            "ui.buttons.files",
            "ui.buttons.current_model",
            "ui.buttons.clear",
            "ui.buttons.help",
            "ui.buttons.open_models",
            "ui.buttons.use_default",
            "ui.buttons.refresh",
            "ui.buttons.refresh_models",
            "ui.buttons.prev_page",
            "ui.buttons.next_page",
            "ui.buttons.confirm",
            "ui.buttons.cancel",
            "ui.buttons.close",
            "ui.buttons.ask_file",
            "ui.input_placeholder",
            "messages.start_welcome",
            "messages.help",
            "messages.please_send_non_empty",
            "messages.askfile_usage",
            "messages.askfile_prompt",
            "messages.cancel_ask_done",
            "messages.cancel_nothing",
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
            "models.no_matches",
            "models.page_status",
            "models.updated",
            "models.reset_default",
            "models.not_found",
            "models.not_available_anymore",
            "models.no_models_available",
            "files.available_title",
            "files.empty",
            "files.page_status",
            "files.instructions",
            "files.deleted",
            "files.not_found",
            "web_models.available_title",
            "web_models.select_with",
            "web_models.install_hint",
            "web_models.page_status",
            "web_models.no_matches",
            "web_models.no_models_available",
            "image.default_prompt",
            "image.model_without_vision",
            "image.too_large",
            "image.invalid_file",
            "image.processing_error",
            "image.read_error",
            "document.added",
            "document.too_large",
            "document.unsupported",
            "document.empty",
            "document.processing_error",
            "errors.ollama_timeout",
            "errors.ollama_connection",
            "errors.ollama_list_models",
            "errors.ollama_list_web_models",
            "errors.ollama_validate_model",
            "errors.save_model_preference",
            "errors.save_default_model_preference",
            "errors.files_storage",
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
                    command="webmodels",
                    description=self._i18n.t("commands.webmodels", locale=locale),
                ),
                BotCommand(command="files", description=self._i18n.t("commands.files", locale=locale)),
                BotCommand(command="askfile", description=self._i18n.t("commands.askfile", locale=locale)),
                BotCommand(command="cancel", description=self._i18n.t("commands.cancel", locale=locale)),
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

    async def web_models(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard_access(update):
            return
        if not update.effective_message or not update.effective_user:
            return

        locale = self._locale(update)
        user_id = update.effective_user.id
        self._log_user_event("command_webmodels", update)
        search_query = " ".join(context.args).strip() if context.args else ""

        try:
            models = await self._ollama_client.list_web_models()
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
            logger.warning("Ollama error while listing web models: %s", error)
            await update.effective_message.reply_text(
                self._error(self._i18n.t("errors.ollama_list_web_models", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return

        if not models:
            await update.effective_message.reply_text(
                self._info(self._i18n.t("web_models.no_models_available", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return

        self._web_model_search_query_by_user[user_id] = search_query
        filtered_models = self._filter_models(models, search_query)
        if not filtered_models:
            await update.effective_message.reply_text(
                self._warning(self._i18n.t("web_models.no_matches", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return

        page = 1
        page_models, total_pages = self._paginate_items(filtered_models, page, WEB_MODELS_PAGE_SIZE)

        lines = [self._info(self._i18n.t("web_models.available_title", locale=locale))]
        for model in page_models:
            lines.append(f"- {model}")
        lines.append("")
        lines.append(self._i18n.t("web_models.page_status", locale=locale, page=page, pages=total_pages))
        lines.append(self._i18n.t("web_models.select_with", locale=locale))
        lines.append(self._i18n.t("web_models.install_hint", locale=locale))

        await update.effective_message.reply_text(
            "\n".join(lines),
            reply_markup=self._web_models_inline_keyboard(
                locale=locale,
                models=page_models,
                page=page,
                total_pages=total_pages,
            ),
        )

    async def files(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard_access(update):
            return
        if not update.effective_message or not update.effective_user:
            return

        locale = self._locale(update)
        user_id = update.effective_user.id
        self._log_user_event("command_files", update)

        try:
            assets = self._user_assets_store.list_assets(user_id)
        except Exception as error:
            logger.exception("Failed to list user assets: %s", error)
            await update.effective_message.reply_text(
                self._error(self._i18n.t("errors.files_storage", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return

        if not assets:
            await update.effective_message.reply_text(
                self._info(self._i18n.t("files.empty", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return

        page = 1
        page_assets, total_pages = self._paginate_assets(assets, page)
        text = self._files_page_text(locale=locale, assets=page_assets, page=page, total_pages=total_pages)
        await update.effective_message.reply_text(
            text,
            reply_markup=self._files_inline_keyboard(
                locale=locale,
                assets=page_assets,
                page=page,
                total_pages=total_pages,
            ),
        )

    async def askfile(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard_access(update, apply_rate_limit=True):
            return
        if not update.effective_message or not update.effective_user:
            return

        locale = self._locale(update)
        user_id = update.effective_user.id
        self._log_user_event("command_askfile", update)

        if not context.args or len(context.args) < 2:
            await update.effective_message.reply_text(
                self._warning(self._i18n.t("messages.askfile_usage", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return

        asset_id_raw = context.args[0].strip()
        prompt = " ".join(context.args[1:]).strip()
        if not asset_id_raw.isdigit() or not prompt:
            await update.effective_message.reply_text(
                self._warning(self._i18n.t("messages.askfile_usage", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return

        asset_id = int(asset_id_raw)
        try:
            asset = self._user_assets_store.get_asset(user_id, asset_id)
        except Exception as error:
            logger.exception("Failed to read askfile asset: %s", error)
            await update.effective_message.reply_text(
                self._error(self._i18n.t("errors.files_storage", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return

        if not asset:
            await update.effective_message.reply_text(
                self._warning(self._i18n.t("files.not_found", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return

        await self._answer_with_asset(
            update=update,
            locale=locale,
            user_id=user_id,
            asset=asset,
            prompt=prompt,
        )

    async def _answer_with_asset(
        self,
        *,
        update: Update,
        locale: str,
        user_id: int,
        asset: UserAsset,
        prompt: str,
    ) -> None:
        turns = self._context_store.get_turns(user_id)
        model = self._get_user_model(user_id)
        started_at = monotonic()
        agent_name = self._select_agent(prompt)
        system_instruction = self._agent_system_instruction(agent_name, locale)
        prompt_with_asset = self._augment_prompt_with_assets(
            prompt=prompt,
            assets=[asset],
            force_single=True,
        )

        await update.effective_chat.send_action(action=ChatAction.TYPING)
        try:
            ollama_response = await self._generate_response(
                user_id=user_id,
                model=model,
                prompt=prompt_with_asset,
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
            logger.warning("Ollama askfile error: %s", error)
            await update.effective_message.reply_text(
                self._error(self._i18n.t("errors.ollama_generic", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return

        self._context_store.append(user_id, role="user", content=f"[AskFile #{asset.id}] {prompt}")
        self._context_store.append(user_id, role="assistant", content=ollama_response.text)

        elapsed_ms = int((monotonic() - started_at) * 1000)
        logger.info(
            "askfile_completed user_id=%s model=%s file_id=%d agent=%s input_chars=%d output_chars=%d elapsed_ms=%d",
            user_id,
            model,
            asset.id,
            agent_name,
            len(prompt),
            len(ollama_response.text),
            elapsed_ms,
        )

        for chunk in split_message(ollama_response.text):
            await update.effective_message.reply_text(chunk, parse_mode=ParseMode.HTML)

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Cancel any pending interaction mode (e.g. inline ask)."""
        if not await self._guard_access(update):
            return
        if not update.effective_message or not update.effective_user:
            return
        locale = self._locale(update)
        user_id = update.effective_user.id
        pending = self._askfile_target_by_user.pop(user_id, None)
        if pending is not None:
            await update.effective_message.reply_text(
                self._i18n.t("messages.cancel_ask_done", locale=locale),
                reply_markup=self._main_keyboard(locale),
            )
        else:
            await update.effective_message.reply_text(
                self._i18n.t("messages.cancel_nothing", locale=locale),
                reply_markup=self._main_keyboard(locale),
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

        if requested_model and (
            requested_model in models or self._ollama_client.can_use_cloud_model(requested_model)
        ):
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
        search_query = requested_model if requested_model else ""
        self._model_search_query_by_user[user_id] = search_query

        filtered_models = self._filter_models(models, search_query)
        if not filtered_models:
            await update.effective_message.reply_text(
                self._warning(self._i18n.t("models.no_matches", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return

        page = 1
        page_models, total_pages = self._paginate_models(filtered_models, page)

        lines = [self._info(self._i18n.t("models.available_title", locale=locale))]
        for model in page_models:
            marker = self._i18n.t("models.current_marker", locale=locale) if model == current_model else ""
            lines.append(f"- {model}{marker}")
        lines.append("")
        lines.append(self._i18n.t("models.page_status", locale=locale, page=page, pages=total_pages))
        lines.append(self._i18n.t("models.select_with", locale=locale))
        lines.append(self._i18n.t("models.tap_button", locale=locale))

        inline_keyboard = self._models_inline_keyboard(
            locale,
            models=page_models,
            current_model=current_model,
            page=page,
            total_pages=total_pages,
        )
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
            self._model_search_query_by_user[update.effective_user.id] = ""
            await self._show_models_page(update, 1)
            return

        if selected_model == MODEL_CLOSE_ACTION:
            self._model_search_query_by_user.pop(update.effective_user.id, None)
            try:
                await query.message.delete()
            except Exception as error:
                logger.debug("Failed to delete local models message: %s", error)
                await query.edit_message_reply_markup(reply_markup=None)
            return

        if selected_model.startswith(MODEL_PAGE_ACTION_PREFIX):
            page_raw = selected_model.removeprefix(MODEL_PAGE_ACTION_PREFIX).strip()
            if not page_raw.isdigit():
                return
            await self._show_models_page(update, int(page_raw))
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

    async def select_web_model_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not await self._guard_access(update):
            return
        query = update.callback_query
        if not query or not update.effective_user or not query.message:
            return

        locale = self._locale(update)
        await query.answer()

        data = query.data or ""
        if not data.startswith(WEB_MODEL_CALLBACK_PREFIX):
            return

        action = data.removeprefix(WEB_MODEL_CALLBACK_PREFIX).strip()
        if action == WEB_MODEL_REFRESH_ACTION:
            self._web_model_search_query_by_user[update.effective_user.id] = ""
            await self._show_web_models_page(update, 1)
            return

        if action == WEB_MODEL_CLOSE_ACTION:
            self._web_model_search_query_by_user.pop(update.effective_user.id, None)
            try:
                await query.message.delete()
            except Exception as error:
                logger.debug("Failed to delete web models message: %s", error)
                await query.edit_message_reply_markup(reply_markup=None)
            return

        if action.startswith(WEB_MODEL_PAGE_ACTION_PREFIX):
            page_raw = action.removeprefix(WEB_MODEL_PAGE_ACTION_PREFIX).strip()
            if not page_raw.isdigit():
                return
            await self._show_web_models_page(update, int(page_raw))

    async def select_file_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard_access(update):
            return
        query = update.callback_query
        if not query or not update.effective_user or not query.message:
            return

        locale = self._locale(update)
        user_id = update.effective_user.id
        await query.answer()

        data = query.data or ""
        if not data.startswith(FILE_CALLBACK_PREFIX):
            return

        payload = data.removeprefix(FILE_CALLBACK_PREFIX).strip()
        parts = payload.split(":")
        if not parts:
            return

        action = parts[0]
        if action == FILE_CLOSE_ACTION:
            try:
                await query.message.delete()
            except Exception as error:
                logger.debug("Failed to delete files message: %s", error)
                await query.edit_message_reply_markup(reply_markup=None)
            return

        if action == FILE_PAGE_ACTION and len(parts) >= 2 and parts[1].isdigit():
            await self._show_files_page(update=update, page=int(parts[1]))
            return

        if action in {FILE_TOGGLE_ACTION, FILE_DELETE_ACTION} and len(parts) >= 3:
            asset_id_raw, page_raw = parts[1], parts[2]
            if not asset_id_raw.isdigit() or not page_raw.isdigit():
                return

            asset_id = int(asset_id_raw)
            page = int(page_raw)

            try:
                if action == FILE_TOGGLE_ACTION:
                    asset = self._user_assets_store.get_asset(user_id, asset_id)
                    if not asset:
                        await query.message.reply_text(
                            self._warning(self._i18n.t("files.not_found", locale=locale)),
                            reply_markup=self._main_keyboard(locale),
                        )
                        return
                    self._user_assets_store.set_selected(user_id, asset_id, not asset.is_selected)
                else:
                    deleted = self._user_assets_store.delete_asset(user_id, asset_id)
                    if not deleted:
                        await query.message.reply_text(
                            self._warning(self._i18n.t("files.not_found", locale=locale)),
                            reply_markup=self._main_keyboard(locale),
                        )
                        return
            except Exception as error:
                logger.exception("Failed to update file action=%s asset_id=%s error=%s", action, asset_id, error)
                await query.message.reply_text(
                    self._error(self._i18n.t("errors.files_storage", locale=locale)),
                    reply_markup=self._main_keyboard(locale),
                )
                return

            await self._show_files_page(update=update, page=page)
            return

        if action == FILE_ASK_ACTION and len(parts) >= 2:
            asset_id_raw = parts[1]
            if not asset_id_raw.isdigit():
                return
            asset_id = int(asset_id_raw)
            try:
                asset = self._user_assets_store.get_asset(user_id, asset_id)
            except Exception as error:
                logger.exception("Failed to fetch file for ask action: %s", error)
                await query.message.reply_text(
                    self._error(self._i18n.t("errors.files_storage", locale=locale)),
                    reply_markup=self._main_keyboard(locale),
                )
                return

            if not asset:
                await query.message.reply_text(
                    self._warning(self._i18n.t("files.not_found", locale=locale)),
                    reply_markup=self._main_keyboard(locale),
                )
                return

            self._askfile_target_by_user[user_id] = asset_id
            await query.message.reply_text(
                self._info(
                    self._i18n.t(
                        "messages.askfile_prompt",
                        locale=locale,
                        id=asset.id,
                        name=asset.asset_name,
                    )
                ),
                reply_markup=self._main_keyboard(locale),
            )

    async def _show_files_page(self, update: Update, page: int) -> None:
        query = update.callback_query
        if not query or not update.effective_user or not query.message:
            return

        locale = self._locale(update)
        user_id = update.effective_user.id
        try:
            assets = self._user_assets_store.list_assets(user_id)
        except Exception as error:
            logger.exception("Failed to list files for pagination: %s", error)
            await query.message.reply_text(
                self._error(self._i18n.t("errors.files_storage", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return

        if not assets:
            await self._edit_models_message(
                query=query,
                text=self._info(self._i18n.t("files.empty", locale=locale)),
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton(text=self._i18n.t("ui.buttons.close", locale=locale), callback_data=f"{FILE_CALLBACK_PREFIX}{FILE_CLOSE_ACTION}")]]
                ),
            )
            return

        page_assets, total_pages = self._paginate_assets(assets, page)
        safe_page = min(max(page, 1), total_pages)
        text = self._files_page_text(
            locale=locale,
            assets=page_assets,
            page=safe_page,
            total_pages=total_pages,
        )
        await self._edit_models_message(
            query=query,
            text=text,
            reply_markup=self._files_inline_keyboard(
                locale=locale,
                assets=page_assets,
                page=safe_page,
                total_pages=total_pages,
            ),
        )

    async def _show_web_models_page(self, update: Update, page: int) -> None:
        query = update.callback_query
        if not query or not update.effective_user or not query.message:
            return

        locale = self._locale(update)
        user_id = update.effective_user.id

        try:
            models = await self._ollama_client.list_web_models()
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
            logger.warning("Ollama error while paginating web models: %s", error)
            await query.message.reply_text(
                self._error(self._i18n.t("errors.ollama_list_web_models", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return

        search_query = self._web_model_search_query_by_user.get(user_id, "")
        filtered_models = self._filter_models(models, search_query)
        if not filtered_models:
            await query.message.reply_text(
                self._warning(self._i18n.t("web_models.no_matches", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return

        page_models, total_pages = self._paginate_items(filtered_models, page, WEB_MODELS_PAGE_SIZE)
        safe_page = min(max(page, 1), total_pages)

        lines = [self._info(self._i18n.t("web_models.available_title", locale=locale))]
        for model in page_models:
            lines.append(f"- {model}")
        lines.append("")
        lines.append(self._i18n.t("web_models.page_status", locale=locale, page=safe_page, pages=total_pages))
        lines.append(self._i18n.t("web_models.select_with", locale=locale))
        lines.append(self._i18n.t("web_models.install_hint", locale=locale))

        await self._edit_models_message(
            query=query,
            text="\n".join(lines),
            reply_markup=self._web_models_inline_keyboard(
                locale=locale,
                models=page_models,
                page=safe_page,
                total_pages=total_pages,
            ),
        )

    async def _show_models_page(self, update: Update, page: int) -> None:
        query = update.callback_query
        if not query or not update.effective_user or not query.message:
            return

        locale = self._locale(update)
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
            logger.warning("Ollama error while paginating models: %s", error)
            await query.message.reply_text(
                self._error(self._i18n.t("errors.ollama_list_models", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return

        search_query = self._model_search_query_by_user.get(user_id, "")
        filtered_models = self._filter_models(models, search_query)
        if not filtered_models:
            await query.message.reply_text(
                self._warning(self._i18n.t("models.no_matches", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
            return

        page_models, total_pages = self._paginate_models(filtered_models, page)
        safe_page = min(max(page, 1), total_pages)
        current_model = self._get_user_model(user_id)

        lines = [self._info(self._i18n.t("models.available_title", locale=locale))]
        for model in page_models:
            marker = self._i18n.t("models.current_marker", locale=locale) if model == current_model else ""
            lines.append(f"- {model}{marker}")
        lines.append("")
        lines.append(self._i18n.t("models.page_status", locale=locale, page=safe_page, pages=total_pages))
        lines.append(self._i18n.t("models.select_with", locale=locale))
        lines.append(self._i18n.t("models.tap_button", locale=locale))

        await self._edit_models_message(
            query=query,
            text="\n".join(lines),
            reply_markup=self._models_inline_keyboard(
                locale,
                models=page_models,
                current_model=current_model,
                page=safe_page,
                total_pages=total_pages,
            ),
        )

    async def _edit_models_message(
        self,
        *,
        query,
        text: str,
        reply_markup: InlineKeyboardMarkup,
    ) -> None:
        try:
            await query.edit_message_text(
                text=text,
                reply_markup=reply_markup,
            )
        except Exception as error:
            logger.debug("Failed to edit models message, sending new message instead: %s", error)
            if query.message:
                await query.message.reply_text(
                    text,
                    reply_markup=reply_markup,
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
        if action == "web_models":
            await self.web_models(update, context)
            return
        if action == "files":
            await self.files(update, context)
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
        pending_asset_id = self._askfile_target_by_user.pop(user_id, None)
        if pending_asset_id is not None:
            try:
                pending_asset = self._user_assets_store.get_asset(user_id, pending_asset_id)
            except Exception as error:
                logger.exception("Failed to load pending askfile asset: %s", error)
                await update.effective_message.reply_text(
                    self._error(self._i18n.t("errors.files_storage", locale=locale)),
                    reply_markup=self._main_keyboard(locale),
                )
                return

            if not pending_asset:
                await update.effective_message.reply_text(
                    self._warning(self._i18n.t("files.not_found", locale=locale)),
                    reply_markup=self._main_keyboard(locale),
                )
                return

            await self._answer_with_asset(
                update=update,
                locale=locale,
                user_id=user_id,
                asset=pending_asset,
                prompt=user_text,
            )
            return

        turns = self._context_store.get_turns(user_id)
        model = self._get_user_model(user_id)
        started_at = monotonic()
        agent_name = self._select_agent(user_text)
        system_instruction = self._agent_system_instruction(agent_name, locale)
        prompt_with_assets = self._augment_prompt_with_selected_assets(user_id=user_id, prompt=user_text)

        await update.effective_chat.send_action(action=ChatAction.TYPING)

        try:
            ollama_response = await self._generate_response(
                user_id=user_id,
                model=model,
                prompt=prompt_with_assets,
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
        user_prompt_with_assets = self._augment_prompt_with_selected_assets(
            user_id=user_id,
            prompt=user_prompt,
            asset_kinds={"document"},
        )
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
                prompt=user_prompt_with_assets,
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
        try:
            self._user_assets_store.add_asset(
                user_id=user_id,
                asset_kind="image",
                asset_name=(message.document.file_name if message.document else "telegram-photo"),
                mime_type=(message.document.mime_type if message.document else "image/jpeg") or "image/jpeg",
                size_bytes=image_bytes_size,
                content_text=ollama_response.text,
                is_selected=True,
            )
        except Exception as error:
            logger.warning("image_asset_save_failed user_id=%s error=%s", user_id, error)

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

    async def on_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard_access(update, apply_rate_limit=True):
            return
        if not update.effective_message or not update.effective_user:
            return

        locale = self._locale(update)
        message = update.effective_message
        document = message.document
        if not document:
            return

        user_id = update.effective_user.id
        file_name = document.file_name or "document"
        file_size = int(document.file_size or 0)
        mime_type = (document.mime_type or "").lower()

        if file_size > self._document_max_bytes:
            await message.reply_text(
                self._warning(
                    self._i18n.t(
                        "document.too_large",
                        locale=locale,
                        max_size=self._format_size(self._document_max_bytes),
                    )
                ),
                reply_markup=self._main_keyboard(locale),
            )
            return

        try:
            telegram_file = await document.get_file()
            raw_bytes = bytes(await telegram_file.download_as_bytearray())
            if len(raw_bytes) > self._document_max_bytes:
                await message.reply_text(
                    self._warning(
                        self._i18n.t(
                            "document.too_large",
                            locale=locale,
                            max_size=self._format_size(self._document_max_bytes),
                        )
                    ),
                    reply_markup=self._main_keyboard(locale),
                )
                return

            extracted_text = self._extract_document_text(
                content=raw_bytes,
                mime_type=mime_type,
                file_name=file_name,
            )
            if not extracted_text.strip():
                await message.reply_text(
                    self._warning(self._i18n.t("document.empty", locale=locale)),
                    reply_markup=self._main_keyboard(locale),
                )
                return

            trimmed_text = self._trim_document_text(extracted_text)
            caption = (message.caption or "").strip()

            asset_id: int | None = None
            try:
                asset_id = self._user_assets_store.add_asset(
                    user_id=user_id,
                    asset_kind="document",
                    asset_name=file_name,
                    mime_type=mime_type or "application/octet-stream",
                    size_bytes=len(raw_bytes),
                    content_text=trimmed_text,
                    is_selected=True,
                )
            except Exception as error:
                logger.warning("document_asset_save_failed user_id=%s file_name=%s error=%s", user_id, file_name, error)

            if not caption:
                self._context_store.append(
                    user_id,
                    role="user",
                    content=f"[Document: {file_name}]\n{trimmed_text}",
                )
                await message.reply_text(
                    self._success(self._i18n.t("document.added", locale=locale, name=file_name, id=asset_id or "?")),
                    reply_markup=self._main_keyboard(locale),
                )
                return

            turns = self._context_store.get_turns(user_id)
            model = self._get_user_model(user_id)
            agent_name = self._select_agent(caption)
            system_instruction = self._agent_system_instruction(agent_name, locale)
            started_at = monotonic()

            review_prompt = (
                f"Document name: {file_name}\n\n"
                f"Document content:\n{trimmed_text}\n\n"
                f"User request: {caption}"
            )

            await update.effective_chat.send_action(action=ChatAction.TYPING)
            ollama_response = await self._generate_response(
                user_id=user_id,
                model=model,
                prompt=review_prompt,
                turns=turns,
                system_instruction=system_instruction,
            )

            self._context_store.append(
                user_id,
                role="user",
                content=f"[Document review: {file_name}] {caption}",
            )
            self._context_store.append(user_id, role="assistant", content=ollama_response.text)

            elapsed_ms = int((monotonic() - started_at) * 1000)
            logger.info(
                "document_review_completed user_id=%s model=%s file_name=%s input_chars=%d output_chars=%d elapsed_ms=%d",
                user_id,
                model,
                file_name,
                len(review_prompt),
                len(ollama_response.text),
                elapsed_ms,
            )

            for chunk in split_message(ollama_response.text):
                await message.reply_text(chunk, parse_mode=ParseMode.HTML)
        except ValueError as error:
            logger.warning("document_unsupported user_id=%s file_name=%s error=%s", user_id, file_name, error)
            await message.reply_text(
                self._warning(self._i18n.t("document.unsupported", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
        except OllamaTimeoutError:
            await message.reply_text(
                self._warning(self._i18n.t("errors.ollama_timeout", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
        except OllamaConnectionError:
            await message.reply_text(
                self._error(self._i18n.t("errors.ollama_connection", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
        except OllamaError as error:
            logger.warning("document_ollama_error user_id=%s file_name=%s error=%s", user_id, file_name, error)
            await message.reply_text(
                self._error(self._i18n.t("document.processing_error", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )
        except Exception as error:
            logger.warning("document_processing_failed user_id=%s file_name=%s error=%s", user_id, file_name, error)
            await message.reply_text(
                self._error(self._i18n.t("document.processing_error", locale=locale)),
                reply_markup=self._main_keyboard(locale),
            )

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

    @staticmethod
    def _format_size_compact(num_bytes: int) -> str:
        if num_bytes < 1024:
            return f"{num_bytes} B"
        if num_bytes < 1024 * 1024:
            return f"{num_bytes / 1024:.0f} KB"
        return f"{num_bytes / (1024 * 1024):.1f} MB"

    @staticmethod
    def _truncate_text(text: str, *, max_chars: int) -> str:
        cleaned = text.strip()
        if len(cleaned) <= max_chars:
            return cleaned
        return f"{cleaned[: max_chars - 1]}…"

    def _asset_preview(self, asset: UserAsset) -> str:
        text = asset.content_text
        if not text.strip():
            return "—"

        if asset.asset_kind == "image":
            analysis_match = re.search(
                r"Image analysis result:\s*(.+)",
                text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if analysis_match:
                analysis_text = " ".join(analysis_match.group(1).split())
                if analysis_text:
                    return self._truncate_text(f"🖼️ {analysis_text}", max_chars=95)

            image_prompt_match = re.search(r"Image prompt:\s*(.+)", text, flags=re.IGNORECASE)
            if image_prompt_match:
                prompt = image_prompt_match.group(1).strip()
                if prompt:
                    return self._truncate_text(f"🖼️ {prompt}", max_chars=95)

            return "🖼️ Image asset"

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if lines:
            first_line = lines[0]
            if first_line.lower().startswith("document name:") and len(lines) > 1:
                first_line = lines[1]

            if len(first_line) > 8:
                return self._truncate_text(f"📄 {first_line}", max_chars=95)

        single_line = " ".join(text.split())
        return self._truncate_text(single_line, max_chars=95)

    def _trim_document_text(self, text: str) -> str:
        cleaned = text.strip()
        if len(cleaned) <= self._document_max_chars:
            return cleaned
        return f"{cleaned[:self._document_max_chars]}\n\n[...truncated...]"

    @staticmethod
    def _extract_document_text(*, content: bytes, mime_type: str, file_name: str) -> str:
        suffix = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
        text_extensions = {
            "txt",
            "md",
            "markdown",
            "csv",
            "json",
            "xml",
            "yml",
            "yaml",
            "log",
            "py",
            "js",
            "ts",
            "java",
            "c",
            "cpp",
            "html",
            "css",
            "sql",
            "rst",
        }

        if mime_type.startswith("text/") or suffix in text_extensions:
            return content.decode("utf-8", errors="replace")

        if mime_type == "application/pdf" or suffix == "pdf":
            try:
                from pypdf import PdfReader
            except Exception as error:
                raise ValueError("PDF extraction requires pypdf") from error

            reader = PdfReader(io.BytesIO(content))
            pages_text = [page.extract_text() or "" for page in reader.pages]
            return "\n\n".join(pages_text)

        docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if mime_type == docx_mime or suffix == "docx":
            try:
                from docx import Document as DocxDocument
            except Exception as error:
                raise ValueError("DOCX extraction requires python-docx") from error

            doc = DocxDocument(io.BytesIO(content))
            paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
            return "\n".join(paragraphs)

        xlsx_mimes = {
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel",
        }
        if mime_type in xlsx_mimes or suffix in ("xlsx", "xls"):
            try:
                import openpyxl
            except Exception as error:
                raise ValueError("XLSX extraction requires openpyxl") from error

            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            parts: list[str] = []
            for sheet in wb.worksheets:
                sheet_rows: list[str] = []
                for row in sheet.iter_rows(values_only=True):
                    row_text = "\t".join(str(cell) if cell is not None else "" for cell in row).rstrip()
                    if row_text.strip():
                        sheet_rows.append(row_text)
                if sheet_rows:
                    parts.append(f"[Sheet: {sheet.title}]\n" + "\n".join(sheet_rows))
            return "\n\n".join(parts)

        raise ValueError(f"Unsupported document format: {mime_type or suffix or 'unknown'}")

    def _locale(self, update: Update) -> str:
        language_code = update.effective_user.language_code if update.effective_user else None
        return self._i18n.resolve_locale(language_code)

    def _build_quick_action_map(self) -> dict[str, str]:
        quick_action_keys = {
            "models": "ui.buttons.models",
            "web_models": "ui.buttons.web_models",
            "files": "ui.buttons.files",
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

    def _filter_models(self, models: list[str], query: str) -> list[str]:
        search = query.strip().lower()
        if not search:
            return models
        return [model for model in models if search in model.lower()]

    def _paginate_models(self, models: list[str], page: int) -> tuple[list[str], int]:
        return self._paginate_items(models, page, MODELS_PAGE_SIZE)

    def _paginate_assets(self, assets: list[UserAsset], page: int) -> tuple[list[UserAsset], int]:
        if not assets:
            return [], 1

        total_pages = max(1, (len(assets) + FILES_PAGE_SIZE - 1) // FILES_PAGE_SIZE)
        safe_page = min(max(page, 1), total_pages)
        start = (safe_page - 1) * FILES_PAGE_SIZE
        end = start + FILES_PAGE_SIZE
        return assets[start:end], total_pages

    def _files_page_text(self, *, locale: str, assets: list[UserAsset], page: int, total_pages: int) -> str:
        lines = [self._info(self._i18n.t("files.available_title", locale=locale))]
        for asset in assets:
            selected_marker = "✅" if asset.is_selected else "☑️"
            kind = "doc" if asset.asset_kind == "document" else "img"
            asset_name = self._truncate_text(asset.asset_name, max_chars=38)
            size = self._format_size_compact(asset.size_bytes)
            preview = self._asset_preview(asset)
            lines.append(f"- #{asset.id} [{kind}] {asset_name} {selected_marker} ({size})")
            lines.append(f"  {preview}")
        lines.append("")
        lines.append(self._i18n.t("files.page_status", locale=locale, page=page, pages=total_pages))
        lines.append(self._i18n.t("files.instructions", locale=locale))
        return "\n".join(lines)

    def _files_inline_keyboard(
        self,
        *,
        locale: str,
        assets: list[UserAsset],
        page: int,
        total_pages: int,
    ) -> InlineKeyboardMarkup:
        rows: list[list[InlineKeyboardButton]] = []
        for asset in assets:
            toggle_label = f"✅ #{asset.id}" if asset.is_selected else f"☑️ #{asset.id}"
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"{self._i18n.t('ui.buttons.ask_file', locale=locale)} #{asset.id}",
                        callback_data=f"{FILE_CALLBACK_PREFIX}{FILE_ASK_ACTION}:{asset.id}",
                    ),
                    InlineKeyboardButton(
                        text=toggle_label,
                        callback_data=f"{FILE_CALLBACK_PREFIX}{FILE_TOGGLE_ACTION}:{asset.id}:{page}",
                    ),
                    InlineKeyboardButton(
                        text=f"🗑 #{asset.id}",
                        callback_data=f"{FILE_CALLBACK_PREFIX}{FILE_DELETE_ACTION}:{asset.id}:{page}",
                    ),
                ]
            )

        if total_pages > 1:
            nav_row: list[InlineKeyboardButton] = []
            if page > 1:
                nav_row.append(
                    InlineKeyboardButton(
                        text=self._i18n.t("ui.buttons.prev_page", locale=locale),
                        callback_data=f"{FILE_CALLBACK_PREFIX}{FILE_PAGE_ACTION}:{page - 1}",
                    )
                )
            if page < total_pages:
                nav_row.append(
                    InlineKeyboardButton(
                        text=self._i18n.t("ui.buttons.next_page", locale=locale),
                        callback_data=f"{FILE_CALLBACK_PREFIX}{FILE_PAGE_ACTION}:{page + 1}",
                    )
                )
            if nav_row:
                rows.append(nav_row)

        rows.append(
            [
                InlineKeyboardButton(
                    text=self._i18n.t("ui.buttons.close", locale=locale),
                    callback_data=f"{FILE_CALLBACK_PREFIX}{FILE_CLOSE_ACTION}",
                )
            ]
        )

        return InlineKeyboardMarkup(rows)

    def _augment_prompt_with_selected_assets(self, *, user_id: int, prompt: str, asset_kinds: set[str] | None = None) -> str:
        try:
            selected_assets = self._user_assets_store.search_selected_assets(
                user_id=user_id,
                query=prompt,
                limit=self._files_context_max_items,
                max_chars_total=self._files_context_max_chars,
                asset_kinds=asset_kinds,
            )
        except Exception as error:
            logger.warning("selected_assets_context_failed user_id=%s error=%s", user_id, error)
            return prompt

        if not selected_assets:
            return prompt

        return self._augment_prompt_with_assets(prompt=prompt, assets=selected_assets, force_single=False)

    def _augment_prompt_with_assets(
        self,
        *,
        prompt: str,
        assets: list[UserAsset],
        force_single: bool,
    ) -> str:
        if not assets:
            return prompt

        has_image_assets = any(asset.asset_kind == "image" for asset in assets)

        lines = [
            "=== STORED FILE CONTEXT ===",
        ]
        if has_image_assets:
            lines.append(
                "The following entries include visual analyses of images previously uploaded by the user. "
                "Treat this analysis data as your direct knowledge of the image content."
            )
        if force_single:
            lines.append("Answer exclusively based on the single file provided below.")
        lines.append("")

        for asset in assets:
            if asset.asset_kind == "image":
                # Strip legacy labels from old-format content_text
                clean_text = re.sub(
                    r"^(?:image prompt:[^\n]*\n+)?(?:image analysis result[^:\n]*:\n+)?",
                    "",
                    asset.content_text.strip(),
                    flags=re.IGNORECASE,
                ).strip() or asset.content_text.strip()
                lines.append(f"[Image #{asset.id}: {asset.asset_name} — visual analysis]")
                lines.append(clean_text)
            else:
                lines.append(f"[Document #{asset.id}: {asset.asset_name}]")
                lines.append(asset.content_text.strip())
            lines.append("")

        lines.append("=== END CONTEXT ===")
        lines.append("")
        lines.append(f"User request: {prompt}")
        return "\n".join(lines)

    def _paginate_items(self, items: list[str], page: int, page_size: int) -> tuple[list[str], int]:
        if not items:
            return [], 1

        total_pages = max(1, (len(items) + page_size - 1) // page_size)
        safe_page = min(max(page, 1), total_pages)
        start = (safe_page - 1) * page_size
        end = start + page_size
        return items[start:end], total_pages

    def _models_inline_keyboard(
        self,
        locale: str,
        models: list[str],
        current_model: str,
        page: int = 1,
        total_pages: int = 1,
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

        if total_pages > 1:
            nav_row: list[InlineKeyboardButton] = []
            if page > 1:
                nav_row.append(
                    InlineKeyboardButton(
                        text=self._i18n.t("ui.buttons.prev_page", locale=locale),
                        callback_data=f"{MODEL_CALLBACK_PREFIX}{MODEL_PAGE_ACTION_PREFIX}{page - 1}",
                    )
                )
            if page < total_pages:
                nav_row.append(
                    InlineKeyboardButton(
                        text=self._i18n.t("ui.buttons.next_page", locale=locale),
                        callback_data=f"{MODEL_CALLBACK_PREFIX}{MODEL_PAGE_ACTION_PREFIX}{page + 1}",
                    )
                )
            if nav_row:
                rows.append(nav_row)

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
                InlineKeyboardButton(
                    text=self._i18n.t("ui.buttons.close", locale=locale),
                    callback_data=f"{MODEL_CALLBACK_PREFIX}{MODEL_CLOSE_ACTION}",
                ),
            ]
        )

        return InlineKeyboardMarkup(rows)

    def _web_models_inline_keyboard(
        self,
        locale: str,
        models: list[str],
        page: int,
        total_pages: int,
    ) -> InlineKeyboardMarkup:
        rows: list[list[InlineKeyboardButton]] = []
        row: list[InlineKeyboardButton] = []

        for model in models:
            row.append(
                InlineKeyboardButton(
                    text=model,
                    url=f"https://ollama.com/library/{model}",
                )
            )
            if len(row) == 2:
                rows.append(row)
                row = []

        if row:
            rows.append(row)

        if total_pages > 1:
            nav_row: list[InlineKeyboardButton] = []
            if page > 1:
                nav_row.append(
                    InlineKeyboardButton(
                        text=self._i18n.t("ui.buttons.prev_page", locale=locale),
                        callback_data=f"{WEB_MODEL_CALLBACK_PREFIX}{WEB_MODEL_PAGE_ACTION_PREFIX}{page - 1}",
                    )
                )
            if page < total_pages:
                nav_row.append(
                    InlineKeyboardButton(
                        text=self._i18n.t("ui.buttons.next_page", locale=locale),
                        callback_data=f"{WEB_MODEL_CALLBACK_PREFIX}{WEB_MODEL_PAGE_ACTION_PREFIX}{page + 1}",
                    )
                )
            if nav_row:
                rows.append(nav_row)

        rows.append(
            [
                InlineKeyboardButton(
                    text=self._i18n.t("ui.buttons.refresh", locale=locale),
                    callback_data=f"{WEB_MODEL_CALLBACK_PREFIX}{WEB_MODEL_REFRESH_ACTION}",
                ),
                InlineKeyboardButton(
                    text=self._i18n.t("ui.buttons.close", locale=locale),
                    callback_data=f"{WEB_MODEL_CALLBACK_PREFIX}{WEB_MODEL_CLOSE_ACTION}",
                ),
            ]
        )

        return InlineKeyboardMarkup(rows)

    def _main_keyboard(self, locale: str) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(self._i18n.t("ui.buttons.models", locale=locale)),
                    KeyboardButton(self._i18n.t("ui.buttons.web_models", locale=locale)),
                ],
                [
                    KeyboardButton(self._i18n.t("ui.buttons.files", locale=locale)),
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
    application.add_handler(CommandHandler("webmodels", handlers.web_models))
    application.add_handler(CommandHandler("files", handlers.files))
    application.add_handler(CommandHandler("askfile", handlers.askfile))
    application.add_handler(CommandHandler("cancel", handlers.cancel))
    application.add_handler(CommandHandler("currentmodel", handlers.current_model))
    application.add_handler(CallbackQueryHandler(handlers.select_model_callback, pattern=r"^model:"))
    application.add_handler(CallbackQueryHandler(handlers.select_web_model_callback, pattern=r"^webmodel:"))
    application.add_handler(CallbackQueryHandler(handlers.select_file_callback, pattern=r"^file:"))
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
    application.add_handler(
        MessageHandler(filters.Document.ALL & ~filters.Document.IMAGE, handlers.on_document)
    )
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_text))
