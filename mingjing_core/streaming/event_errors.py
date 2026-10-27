"""Public errors deliberately omit event content and validation input."""


class EventValidationError(ValueError):
    def __init__(self, reason_code: str = "event_invalid") -> None:
        self.reason_code = reason_code
        super().__init__("运行事件格式无效")
