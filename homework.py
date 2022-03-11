import os
import sys
import time
import logging
from http import HTTPStatus

import requests
from dotenv import load_dotenv
from telegram import Bot
from telegram.error import TelegramError

from exeptions import (
    SendMessageFailure, IncorrectApiAnswer, NoHomeworkInfo, WrongGetApiStatus,
    EmptyResponse, GetApiError,
)


load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(stream=sys.stdout)
logger.addHandler(handler)


def send_message(bot, message):
    """Отправка сообщения в Telegram чат."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        msg = f'Сообщение "{message}" отправлено в Telegram чат'
        logger.info(msg)
    except TelegramError as error:
        msg = f'Сбой при отправке сообщения: {error}'
        logger.error(msg)
        raise SendMessageFailure(msg)


def get_api_answer(current_timestamp):
    """Получение данных сервиса API Яндекс Практикум."""
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    try:
        homework_statuses = requests.get(
            ENDPOINT, headers=HEADERS, params=params,
        )
        if homework_statuses.status_code != HTTPStatus.OK:
            message = f'Статус код ответа на запрос к "{ENDPOINT}" равен '
            f'{homework_statuses.status_code}.'
            logger.error(message)
            raise WrongGetApiStatus(message)
    except Exception as error:
        message = f'Сбой в работе API сервиса: {error}'
        logger.error(message)
        raise GetApiError(message)
    response = homework_statuses.json()
    return response


def check_response(response):
    """Проверка ответа сервиса API на корректность."""
    if response is None:
        message = 'Нет данных в ответе сервиса API.'
        logger.error(message)
        raise EmptyResponse(message)
    if not isinstance(response, dict):
        message = 'Получен некорректный тип данных от сервиса API.'
        logger.error(message)
        raise TypeError(message)
    if 'homeworks' not in response or 'current_date' not in response:
        message = 'Получен некорректный ответ от сервиса API.'
        raise IncorrectApiAnswer(message)
    if not isinstance(response['homeworks'], list):
        message = 'В ответе сервиса API нет списка домашних работ.'
        logger.error(message)
        raise TypeError(message)
    homeworks_list = response['homeworks']
    return homeworks_list


def parse_status(homework):
    """Возвращает информацию об изменении статуса домашней работы."""
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    if homework_name is None:
        message = 'Не найдено имя домашней работы в ответе API.'
        logger.error(message)
        raise KeyError(message)
    if homework_status is None:
        message = 'Не найден статус домашней работы в ответе API.'
        logger.error(message)
        raise KeyError(message)
    verdict = HOMEWORK_STATUSES.get(homework_status)
    if verdict is None:
        message = 'Недокументированный статус домашней работы в ответе API.'
        logger.error(message)
        raise KeyError(message)
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверка доступности переменных окружения."""
    env_variables_available = all(
        [PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, ]
    )
    return env_variables_available


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logger.critical('Недоступна одна или несколько переменных окружения.')
        sys.exit('Работа программы завершена.')
    bot = Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    last_message = None
    last_error = None
    while True:
        try:
            response = get_api_answer(current_timestamp=current_timestamp)
            homeworks_list = check_response(response=response)
            if homeworks_list:
                homework = homeworks_list[0]
            else:
                message = 'Не найдено информации о домашней работе.'
                logger.info(message)
                raise NoHomeworkInfo(message)
            status_str = parse_status(homework=homework)
            if status_str != last_message:
                send_message(bot=bot, message=status_str)
                last_message = status_str
            else:
                message = 'Статус домашней работы не изменился.'
                logger.debug(message)
            current_timestamp = response.get('current_date')
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            if message != last_error:
                send_message(bot=bot, message=message)
                last_error = message
        else:
            message = 'Программа отработала без ошибок.'
            logger.info(message)
        finally:
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
