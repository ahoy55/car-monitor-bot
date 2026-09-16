import logging


def initialize():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            # logging.FileHandler('logs/monitor.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    logging.getLogger().setLevel(logging.INFO)
    logging.getLogger('apscheduler').setLevel(logging.WARNING)
    # httpx пишет каждый запрос с полным URL, а в URL Bot API — токен бота
    logging.getLogger('httpx').setLevel(logging.WARNING)
