"""Download raw FFSC data

- Up-to-date ranking URL:

https://www.ffsc.fr/classements.exporter.php?class=nat&date=YYYY-MM-DD

- Clubs:

https://www.ffsc.fr/clubs.php
https://www.ffsc.fr/clubs.php?comite=<ID>
"""

from datetime import date
from lxml import html
from pathlib import Path

import pandas as pd
import requests


RANKING_URL = "https://www.ffsc.fr/classements.exporter.php?class=nat&date={date}"
AREA_URL = "https://www.ffsc.fr/clubs.php"
CLUB_URL = "https://www.ffsc.fr/clubs.php?comite={region}"
DATADIR = Path("data")


def get_ranking(ranking_date):
    """Get ranking for the given date

    Parameters
    ----------
    ranking_date : datetime.date
        Date of the required ranking
    """
    ranking_date_str = ranking_date.strftime("%Y-%m-%d")
    url = RANKING_URL.format(date=ranking_date_str)
    output_rank_filepath = DATADIR / f"classement_{ranking_date_str}.csv"
    with open(output_rank_filepath, "wb") as fobj:
        resp = requests.get(url)
        fobj.write(resp.content)


def get_areas():
    """Get the list of areas as defined by the FFSC

    """
    resp = requests.get(AREA_URL)
    tree = html.fromstring(resp.content)
    area_list = tree.xpath("//ul[@class='menu_secondary']/li/*/text()")
    area_list = [area.split(" - ") for area in area_list]
    df_areas = pd.DataFrame(area_list, columns=["id", "area"])
    output_area_filepath = DATADIR / "areas.csv"
    df_areas.to_csv(output_area_filepath, index=False)


def get_clubs(area_id):
    """Get the list of Scrabble clubs in a specified area

    Parameters
    ----------
    area : str
        
    """
    resp = requests.get(CLUB_URL.format(region=area_id))
    tree = html.fromstring(resp.content)
    club_list = tree.xpath("//div[@class='main']/h3/*/text()")
    club_list = [club.split(" - ", 1) for club in club_list]
    df_clubs = pd.DataFrame(club_list, columns=["id", "area"])
    output_club_filepath = DATADIR / f"clubs_comite_{area_id}.csv"
    df_clubs.to_csv(output_club_filepath, index=False)
