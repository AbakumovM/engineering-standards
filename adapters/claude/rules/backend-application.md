---
paths:
  - "**/application/**/*.py"
---
# Слой application

- Interactor: один агрегат, один Gateway; возвращает frozen `Info` (APP-01, APP-02).
- Своего View в Interactor нет; данные для решения — через Gateway (APP-03).
- Коммит явный в конце метода, исход без записи — `rollback()` (TX-01).
- Внутри транзакции — никаких внешних вызовов (TX-02); `publish()` не вызывать (TX-09).
- Сценарий соседа не вызывать: две фазы или Service (APP-04, APP-05).
- Настройки — `{Что}Config` из `config.py`, не `Settings` (DEP-03).
- Сценарий по id принимает субъекта и проверяет право на объект (SEC-01).
- Время — `datetime.now(UTC)`, деньги — не `float` (OPS-01, OPS-02).
- Писать несколько доменов в одной транзакции — прочитать `backend-guide/transactions.md`.
