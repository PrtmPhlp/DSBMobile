#!/usr/bin/env python3
# ------------------------------------------------
"""
This script scrapes data from dsbmobile.com to retrieve class replacements.
The scraped data is then organized and saved to a JSON file.

__author__ = "PrtmPhlp"
__Contact__ = "contact@pertermann.de"
__Status__ = "Development"
"""
# ------------------------------------------------
# ! Imports

from os import getenv
from urllib.parse import urljoin
import logging
import argparse
import json
from dotenv import dotenv_values
import coloredlogs
import requests
from bs4 import BeautifulSoup
from PyDSB import PyDSB
# ------------------------------------------------

# Initialize logger globally
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.

    :return: An argparse.Namespace object containing the parsed arguments.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("verbose", type=int, nargs="?", default=1,
                        help="Set the verbosity level: 0 for CRITICAL, 1 for INFO, 2 for DEBUG")
    parser.add_argument("course", type=str, nargs="?", default="MSS11",
                        help="Select the course to scrape. Default: MSS11 ")
    return parser.parse_args()


def setup_logging(args: argparse.Namespace) -> None:
    """
    Set up logging based on parsed command-line arguments.

    :param args: An argparse.Namespace containing the verbosity level.
    """
    # Determine logging level based on args.verbose
    if args.verbose == 0:
        logging_level = logging.ERROR
    elif args.verbose == 2:
        logging_level = logging.DEBUG
        # prevent requests (urllib3) logging:
        logging.getLogger("urllib3").setLevel(logging.WARNING)
    else:
        logging_level = logging.INFO

    # Configure the root logger
    logging.basicConfig(level=logging_level)
    coloredlogs.install(
        fmt="%(asctime)s - %(levelname)s - \033[94m%(message)s\033[0m",
        datefmt="%H:%M:%S",
        level=logging_level,
    )


def load_env_credentials() -> dict[str, str | None]:
    """
    Load environment credentials from a .env file.

    :return: A dictionary containing the environment variables
    :raises FileNotFoundError: If the .env file does not exist.
    :raises ValueError: If .env file is empty, cannot be read, or required variables are missing.
    :raises Exception: If any other error occurs during loading of the .env file.
    """
    try:
        env_credentials: dict[str, str | None] = dotenv_values(".env")
        if not env_credentials:
            raise ValueError("Failed to load environment variables from .env file")

        if ("DSB_USERNAME" not in env_credentials or "DSB_PASSWORD" not in env_credentials):
            raise ValueError("DSB_USERNAME and DSB_PASSWORD must be set in the .env file")
        return env_credentials

    except FileNotFoundError:
        logger.warning("The .env file does not exist, falling back to OS environment")

    except ValueError:
        logger.warning("Failed to load variables from .env file, falling back to OS environment")

    # Fallback to load environment variables from OS environment
    dsb_username: str | None = getenv("DSB_USERNAME")
    dsb_password: str | None = getenv("DSB_PASSWORD")

    if not dsb_username or not dsb_password:
        logger.critical("DSB_USERNAME and DSB_PASSWORD must be set in the OS environment")
        raise ValueError("DSB_USERNAME and DSB_PASSWORD must be set in the OS environment")

    logger.info("OS environment Credentials:")
    logger.info("-----------------")
    logger.info("Username: %s", dsb_username)
    logger.info("Password: %s", dsb_password)

    return {
        "DSB_USERNAME": dsb_username,
        "DSB_PASSWORD": dsb_password
    }


def prepare_api_url(credentials: dict[str, str | None]) -> str:
    """
    Prepares the API URL for the "DaVinci Touch" section from the given credentials.

    :param credentials: Dictionary containing 'username' and 'password' for auth.
    :return: The base URL for "DaVinci Touch" section if found.
    :raises KeyError: If a required credential is missing.
    :raises Exception: For other unforeseen errors.
    :raises ValueError: If the "DaVinci Touch" section is not found.
    """
    if credentials["DSB_USERNAME"] is None or credentials["DSB_PASSWORD"] is None:
        raise ValueError("DSB_USERNAME and DSB_PASSWORD must not be None")

    logger.info("Sending API request")
    try:
        dsb = PyDSB(credentials["DSB_USERNAME"], credentials["DSB_PASSWORD"])
        data = dsb.get_postings()
    except requests.ConnectionError as e:
        logger.critical("No Internet Connection: %s", e)
        raise

    for section in data:
        if section["title"] == "DaVinci Touch":
            base_url = section["url"]
            logger.debug("URL for DaVinci Touch: %s", base_url)
            return base_url

    # This line is reached if no section titled "DaVinci Touch" is found
    raise ValueError("DaVinci Touch section not found.")


def request_url_data(url: str) -> BeautifulSoup:
    """
    Sends a GET request to the specified URL and returns a BeautifulSoup object parsed from the
    HTML response.

    :param url: The URL to send the request to.
    :return: A BeautifulSoup object of the parsed HTML document.
    :raises requests.exceptions.RequestException: If the request fails for any reason, including
    network issues, invalid URLs, or HTTP errors.
    """
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Raises HTTPError for bad responses
    except requests.exceptions.RequestException as e:
        logger.error("Failed to fetch data from %s: %s", url, e)
        raise

    html = response.content.decode("utf-8")
    soup = BeautifulSoup(html, "html.parser")
    return soup


def get_plans(base_url: str) -> dict[str, str]:
    """
    Extracts plans from the given base URL and organizes them in a dictionary.

    :param base_url: The base URL containing the plan information.
    :return: A dictionary mapping plan identifiers to their URLs.
    """
    logger.info("Extracting Posts")
    soup = request_url_data(base_url)

    try:
        links = soup.find(
            "ul", class_="day-index").find_all("a")  # type: ignore

    except AttributeError as e:
        logger.error("Error parsing HTML structure: %s", e)
        raise ValueError("Expected HTML structure not found.") from e

    logger.debug("<a> links in <ul>, found by soup: %s", links)

    # Extract href attributes and link text
    href_links = [link.get("href") for link in links]
    text_list = [link.text for link in links]

    weekdays = [
        "Montag",
        "Dienstag",
        "Mittwoch",
        "Donnerstag",
        "Freitag",
        "Samstag",
        "Sonntag",
    ]
    # Extract weekdays from text_list
    extracted_weekdays = [
        next((weekday for weekday in weekdays if weekday in text), None)
        for text in text_list
    ]

    # Construct posts dictionary
    posts_dict = {}
    for i, (href, weekday) in enumerate(zip(href_links, extracted_weekdays)):
        if weekday:  # Only include entries with a valid weekday
            full_url = urljoin(base_url, href)
            posts_dict[f"{i+1}_{weekday}"] = full_url
            logger.debug("Added %s to posts_dict: %s", weekday, full_url)
    logger.debug("Posts Dictionary: %s", json.dumps(posts_dict, indent=2))
    logger.info("Found %s", " and ".join(posts_dict.keys()))
    return posts_dict


def main_scraping(url: str, course: argparse.Namespace) -> tuple[list[list[str]], bool]:
    """
    Scrapes a given URL for specific table data related to 'course'.

    :param url: The URL to scrape data from.
    :return: A list of lists containing the scraped table data.
    """
    soup = request_url_data(url)
    success = False
    total_replacements = []

    try:
        table = soup.find("table")
        if not table:
            raise ValueError("Table element not found in the HTML.")

        for row in table.find_all("tr"):  # type: ignore
            columns = row.find_all("td")
            if columns and columns[0].get_text().strip() == course:
                success = True
                logger.debug("%s found", course)
                replacement = [col.get_text().strip() for col in columns]
                total_replacements.append(replacement)

                next_row = row.find_next_sibling("tr")
                while next_row and "\xa0" in next_row.find("td").get_text():
                    logger.debug("New row found!")
                    replacement = [
                        col.get_text().strip() for col in next_row.find_all("td")
                    ]
                    total_replacements.append(replacement)
                    next_row = next_row.find_next_sibling("tr")
    except Exception as e:
        logger.error("Error processing HTML: %s", e)
        raise
    logger.debug("Success Status: %s", success)
    return total_replacements, success


def run_main_scraping(posts_dict: dict[str, str], course) -> dict[str, list[list[str]]]:
    """
    Executes the main_scraping function for each URL in the given dictionary and updates the
    dictionary with the results.

    :param posts_dict: A dictionary mapping identifiers to URLs.
    :return: A dictionary mapping identifiers to the results of the scraping process.
    """
    scrape_dict = {}
    for key, url in posts_dict.items():
        try:
            scraped_data, success = main_scraping(url, course)
            scrape_dict[key] = scraped_data
            if success:
                logger.info("%s: found %s!", key, course)
            else:
                logger.warning("%s: class %s not found!", key, course)
        except Exception as e:  # pylint: disable=W0718
            logger.error("Failed to scrape %s: %s", url, e)
            scrape_dict[key] = []  # Assign an empty list in case of failure
    logger.debug(
        "%s",
        json.dumps(scrape_dict, indent=2, ensure_ascii=False)
        .encode("utf8")
        .decode("utf8"),
    )
    return scrape_dict


def main() -> None:
    """
    Main function that orchestrates the scraping process.

    Retrieves API URL using secret credentials, fetches plans from the API,
    runs the main scraping process on the fetched data, logs the results,
    and saves the scraped data to a JSON file.
    """
    args = parse_args()
    setup_logging(args)

    logger.info("Script started successfully.")

    env_credentials: dict[str, str | None] = load_env_credentials()

    base_url: str = prepare_api_url(env_credentials)

    posts_dict: dict[str, str] = get_plans(base_url)

    class_dict: dict[str, list[list[str]]] = run_main_scraping(posts_dict, args.course)

    with open("file.json", "w", encoding="utf8") as file_json:
        json.dump(class_dict, file_json, ensure_ascii=False)
        logger.info("saved to 'file.json'")


if __name__ == "__main__":
    main()
