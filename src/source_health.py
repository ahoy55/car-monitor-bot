from html import escape
from typing import Optional


class SourceHealth:
    """Состояние одного режима сбора одного источника.

    Сообщает только о смене состояния: "сломался" один раз, когда неудачных
    запусков подряд набралось достаточно, и "снова работает" один раз после
    первого удачного. Иначе ежеминутный поиск новых машин слал бы одно и то же
    каждую минуту, пока источник не починится.
    """

    def __init__(self, source_name: str, mode: str, failures_to_alert: int):
        self.source_name = source_name
        self.mode = mode
        self.failures_to_alert = failures_to_alert
        self.failures = 0
        self.alerted = False

    def record(self, problem: Optional[str]) -> Optional[str]:
        """Учитывает запуск. Возвращает текст алерта, если о нём пора сообщить."""
        if problem:
            self.failures += 1
            if not self.alerted and self.failures >= self.failures_to_alert:
                self.alerted = True
                return (
                    f"⚠️ <b>{escape(self.source_name)}</b>: {self.mode} не работает\n"
                    f"Неудачных запусков подряд: {self.failures}\n"
                    f"Причина: {escape(problem)}"
                )
            return None

        failures, alerted = self.failures, self.alerted
        self.failures = 0
        self.alerted = False
        if alerted:
            return (
                f"✅ <b>{escape(self.source_name)}</b>: {self.mode} снова работает\n"
                f"Неудачных запусков подряд было: {failures}"
            )
        return None
