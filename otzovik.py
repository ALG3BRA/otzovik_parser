from bs4 import BeautifulSoup
from datetime import datetime
import os
import re
import requests
import fake_useragent
import logging
import random
import json
import time


def set_headers(ready=False):
    if not init_headers:
        headers = {"User-Agent": fake_useragent.UserAgent().random}
        print('Был установлен случайный User-Agent.\n'
              'Чтобы задать свои headers, поставь '
              'в конфиге значение "init_headers": true.')
        return

    if not ready:
        input("Введи любой символ, чтобы установить headers\n")

    global headers

    with open("headers.txt", "r+", encoding="UTF-8") as file:
        lines = file.read().strip().split('\n')
        new_headers = {}
        key = None
        for line in lines:
            if line.endswith(':'):
                key = line[:-1]
                new_headers[key] = ""
            elif key:
                new_headers[key] += line.strip()

        headers = new_headers


def wait_for_setting_capt4a():
    state = input("Введи 1, чтобы продолжить.\n"
                  "Введи 2, чтобы перезаписать headers и продолжить.\n")
    if state == "1":
        return
    if state == "2":
        set_headers(ready=True)


def get_next_filename(path, base_name, extension):
    pattern = re.compile(rf"{re.escape(base_name)} - \((\d+)\)\.{re.escape(extension)}$")

    existing_files = os.listdir(f"./{path}")

    max_version = 0
    for filename in existing_files:
        match = pattern.match(filename)
        if match:
            version = int(match.group(1))
            if version > max_version:
                max_version = version

    next_version = max_version + 1
    return f"{path}/{base_name} - ({next_version}).{extension}"


def find_region_and_city(arr):
    r, c = None, None
    for i in range(len(arr)):
        if arr[i] == "Регион (край, область, штат)":
            r = arr[i + 1]
        elif arr[i] == "Город или поселок":
            c = arr[i + 1]

    return r, c


def parse_reviews_from_one_page(reviews, page_number, count=0):
    r_number, review_response, review_url = None, None, None
    global need_to_stop

    data = list()
    for review in reviews:
        count += 1
        try:
            date: str = review.find("div", "review-postdate").get("content")
            year = int(date.split("-")[0])
            if year < min_year:
                need_to_stop = True
                break

            review_url = review.find("meta", itemprop="url").get("content")
            review_response = requests.get(review_url, headers=headers)

            print(f"[{page_number}.{count}]", review_response)

            if review_response.status_code == 507:
                wait_for_setting_capt4a()
                count -= 1
                continue

            r_number = int(review_url.split("/")[-1][7:-5])
            r_soup = BeautifulSoup(review_response.text, features="lxml")
            r_block = r_soup.find("div", class_="item review-wrap")

            stars = int(r_block.find("div", class_="rating-score tooltip-right").get_text())

            user_block = r_block.find("div", class_="user-info")
            user_name = (user_block.find("div", class_="login-col").
                         find("span", itemprop="name").
                         get_text())

            user_rep = int(user_block.
                           find("div", class_="karma-col").
                           get_text().
                           split("\n")[-2])

            user_rcnt = (int(user_block.
                             find("div", class_="reviews-col").
                             find("a", class_="reviews-counter").
                             get_text()))

            content_block = r_block.find("div", class_="item-right")

            title = content_block.find("h1").text.strip("Отзыв: ").strip()

            adv = ("".join(content_block.
                           find("div", class_="review-plus").
                           get_text().
                           split("Достоинства: ")[1]).
                   strip())

            disadv = ("".join(content_block.
                              find("div", class_="review-minus").
                              get_text().
                              split("Недостатки: ")[1]).
                      strip())

            text = (content_block.
                    find("div", "review-body description").
                    get_text().
                    replace("\n\n", ""))

            recs_and_comms = list(filter(lambda s: s != "",
                                         r_block.
                                         find("div", class_="review-bar").
                                         get_text().
                                         split("\n")))

            recs, comms = int(recs_and_comms[1]), int(recs_and_comms[2])
            user_meta = r_block.find("table", class_="product-props").get_text().split("\n")
            region, city = find_region_and_city(user_meta)

            data.append(
                {
                    "review_details": {
                        "review_number": r_number,
                        "url": review_url,
                        "stars": stars,
                        "client": user_name,
                        "rep": user_rep,
                        "rcnt": user_rcnt,
                        "date": datetime.fromisoformat(date).strftime("%d-%m-%Y"),
                        "title": title,
                        "adv": adv,
                        "disadv": disadv,
                        "review": text,
                        "recs": recs,
                        "comms": comms,
                        "region": region,
                        "city": city
                    }
                }
            )

        except Exception as err:
            if err == KeyboardInterrupt:
                raise KeyboardInterrupt

            path = f"log/{campaign}/html/review_{r_number}.html"

            with open(path, "w", encoding="UTF-8") as file:
                file.write(review_response.text)

            print(f"[REVIEW {page_number}.{count}] - ERROR. This review was skipped")

            logger.error("[REVIEW] Path to HTML file: %s. Number: %s. URL: %s. Exception: %s",
                         path, f"[{page_number}.{count}]", review_url, err)

        finally:
            time.sleep(random.randrange(3, 6))

    path = f"output_files/{campaign}/pages/{page_number}.json"
    with open(path, "w", encoding="UTF-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)

    return data


def parse_all_pages(page_number=0):
    reviews_response, reviews_url = None, None

    while True:
        page_number += 1
        if isinstance(finish_page, int) and page_number >= finish_page + 1:
            break
        try:
            reviews_url = f"https://otzovik.com/reviews/{campaign}/{page_number}/?order=date_desc"
            reviews_response = requests.get(reviews_url, headers=headers)
            time.sleep(random.randrange(3, 6))
            print(f"[{page_number}]", reviews_response)

            if reviews_response.status_code == 507:
                wait_for_setting_capt4a()
                page_number -= 1
                continue

            soup = BeautifulSoup(reviews_response.text, features="html.parser")
            reviews_block = soup.find("div", class_="review-list-2 review-list-chunk")
            reviews = reviews_block.find_all("div", class_="item status4 mshow0")

            parse_reviews_from_one_page(reviews, page_number)

            if need_to_stop:
                break

        except Exception as err:
            if err == KeyboardInterrupt:
                raise KeyboardInterrupt

            path = f"log/{campaign}/html/page_{page_number}.html"

            with open(path, "w", encoding="UTF-8") as file:
                file.write(reviews_response.text)

            print(f"[PAGE {page_number}] - ERROR. This page was skipped")

            logger.error("[PAGE] Path to HTML file: %s. Number: %s. URL: %s. Exception: %s",
                         path, f"[{page_number}]", reviews_url, err)

        finally:
            time.sleep(random.randrange(6, 11))


def create_result_file():
    input_files_path = f"output_files/{campaign}/pages"
    pages = sorted([f for f in os.listdir(input_files_path) if f.endswith('.json')])

    result_data = list()

    for file_name in pages:
        file_path = os.path.join(input_files_path, file_name)

        with open(file_path, 'r', encoding="UTF-8") as infile:
            data = json.load(infile)
            result_data.extend(data)

    output_file_path = get_next_filename(f"output_files/{campaign}", campaign, "json")

    with open(output_file_path, 'w', encoding="UTF-8") as outfile:
        json.dump(result_data, outfile, indent=4, ensure_ascii=False)


def main():
    try:
        set_headers()
        parse_all_pages(start_page - 1)
    finally:
        create_result_file()


def set_logger():
    _logger = logging.getLogger()
    _logger.setLevel(logging.DEBUG)
    file_handler = logging.FileHandler('log/app.log')
    file_handler.setLevel(logging.ERROR)

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)

    _logger.addHandler(file_handler)
    return _logger


if __name__ == "__main__":
    logger = set_logger()
    need_to_stop = False

    with open("config.json", "r", encoding="UTF-8") as file:
        config_data = json.load(file)

    campaign = config_data["campaign"]
    init_headers = config_data["init_headers"]
    min_year = config_data["min_year"]
    start_page = config_data["start_page"]
    start_page = start_page if isinstance(start_page, int) else 1
    finish_page = config_data["finish_page"]

    main()
