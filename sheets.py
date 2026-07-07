import os
import json
import logging
from datetime import datetime
from collections import defaultdict
import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

HEADERS = ["Дата", "Время", "Категория", "Описание", "Сумма (₽)"]


class SheetsManager:
    def __init__(self):
        self.spreadsheet_id = os.environ["GOOGLE_SPREADSHEET_ID"]
        self.sheet = self._connect()

    def _connect(self):
        """Подключение к Google Sheets"""
        try:
            creds_json = os.environ["GOOGLE_CREDENTIALS_JSON"]
            creds_dict = json.loads(creds_json)
            creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
            client = gspread.authorize(creds)
            spreadsheet = client.open_by_key(self.spreadsheet_id)
            
            # Получаем или создаём лист "Расходы"
            try:
                sheet = spreadsheet.worksheet("Расходы")
            except gspread.WorksheetNotFound:
                sheet = spreadsheet.add_worksheet("Расходы", rows=1000, cols=10)
                sheet.append_row(HEADERS)
                # Форматируем заголовки (жирный)
                sheet.format("A1:E1", {"textFormat": {"bold": True}})
            
            return sheet
        except Exception as e:
            logger.error(f"Ошибка подключения к Google Sheets: {e}")
            raise

    def add_expense(self, row: dict) -> bool:
        """Добавить запись о расходе"""
        try:
            self.sheet.append_row([
                row["date"],
                row["time"],
                row["category"],
                row["description"],
                row["amount"]
            ])
            return True
        except Exception as e:
            logger.error(f"Ошибка записи в Sheets: {e}")
            return False

    def get_all_records(self) -> list:
        """Получить все записи"""
        try:
            records = self.sheet.get_all_records()
            return records
        except Exception as e:
            logger.error(f"Ошибка чтения Sheets: {e}")
            return []

    def get_today_stats(self) -> dict:
        """Статистика за сегодня"""
        today = datetime.now().strftime("%d.%m.%Y")
        records = self.get_all_records()
        
        today_records = [r for r in records if r.get("Дата") == today]
        
        by_category = defaultdict(float)
        total = 0
        
        for r in today_records:
            try:
                amount = float(str(r.get("Сумма (₽)", 0)).replace(",", "."))
                cat = r.get("Категория", "Прочее")
                by_category[cat] += amount
                total += amount
            except (ValueError, TypeError):
                continue
        
        return {
            "date": today,
            "total": total,
            "by_category": dict(by_category)
        }

    def get_month_stats(self) -> dict:
        """Статистика за текущий месяц"""
        now = datetime.now()
        current_month = now.strftime("%m.%Y")
        month_name = now.strftime("%B %Y")
        
        records = self.get_all_records()
        
        month_records = [
            r for r in records
            if r.get("Дата", "")[-7:] == current_month
        ]
        
        by_category = defaultdict(float)
        total = 0
        
        for r in month_records:
            try:
                amount = float(str(r.get("Сумма (₽)", 0)).replace(",", "."))
                cat = r.get("Категория", "Прочее")
                by_category[cat] += amount
                total += amount
            except (ValueError, TypeError):
                continue
        
        return {
            "month": month_name,
            "total": total,
            "by_category": dict(by_category)
        }

    def get_recent_records(self, n: int = 10) -> list:
        """Последние N записей"""
        records = self.get_all_records()
        recent = records[-n:] if len(records) >= n else records
        recent.reverse()
        
        result = []
        for r in recent:
            try:
                result.append({
                    "date": r.get("Дата", ""),
                    "category": r.get("Категория", ""),
                    "description": r.get("Описание", ""),
                    "amount": float(str(r.get("Сумма (₽)", 0)).replace(",", "."))
                })
            except (ValueError, TypeError):
                continue
        
        return result
