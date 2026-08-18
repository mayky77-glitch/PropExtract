from pathlib import Path
from openpyxl import Workbook

def create_book(path: Path, row: int = 6) -> None:
    book=Workbook(); sheet=book.active; sheet.title="Реестр РНС"; sheet["A1"]="safe"; sheet["A4"]=1; sheet["Y4"]="=A4"; sheet.auto_filter.ref="A3:Z4"; book.create_sheet("Дашборд")["A1"]="=SUM('Реестр РНС'!A4:A4)"; book.save(path); book.close()
