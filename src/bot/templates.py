def format_new_car_message(car) -> str:
    """Форматирование сообщения о новом автомобиле"""
    return (
        "🆕 <b>Новый автомобиль!</b>\n\n"
        f"🖥️ Источник: <b>{car.source.name}</b>\n"
        f"🚗 <b>{car.title}</b>\n"
        f"🏙️ {car.city}\n"
        f"📏 {car.mileage}\n"
        f"📅 {car.year}\n"
        f"💰 {car.price}\n"
        f"📆 {car.monthly_payment}\n"
        f"🔗 <a href='{car.source.base_url}{car.detail_url}'>Посмотреть на сайте</a>"
    )


def format_price_drop_message(car, old_price: str, new_price: str) -> str:
    """Форматирование сообщения о снижении цены"""
    return (
        "💰 <b>Снижение цены!</b>\n\n"
        f"🖥️ Источник: <b>{car.source.name}</b>\n"
        f"🚗 <b>{car.title}</b>\n"
        f"🏙️ {car.city}\n"
        f"📏 {car.mileage}\n"
        f"📅 {car.year}\n\n"
        f"📉 <b>Цена снизилась на {_calculate_drop_percent(old_price, new_price):.01f}%</b>\n"
        f"❌ Было: {old_price}\n"
        f"✅ Стало: {new_price}\n\n"
        f"🔗 <a href='{car.source.base_url}{car.detail_url}'>Посмотреть на сайте</a>"
    )
