from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

CALL_OPERATOR_CALLBACK = "call_operator"


def call_operator_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🙋‍♂️ Позвать оператора",
                    callback_data=CALL_OPERATOR_CALLBACK,
                )
            ]
        ]
    )
