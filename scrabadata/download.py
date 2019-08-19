"""Download raw FFSC data

- Up-to-date ranking URL:

https://www.ffsc.fr/classements.exporter.php?class=nat&date=YYYY-MM-DD

- Clubs:

https://www.ffsc.fr/clubs.php
https://www.ffsc.fr/clubs.php?comite=<ID>

- French areas:

https://www.data.gouv.fr/fr/datasets/r/eb36371a-761d-44a8-93ec-3d728bec17ce
https://www.data.gouv.fr/fr/datasets/r/36390bfd-437b-4abd-9713-d33a1673a700
"""

from datetime import date
from lxml import html
from pathlib import Path

import geocoder
import pandas as pd
import requests
from shapely.geometry import Point


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
    resp = requests.get(url)
    with open(output_rank_filepath, "wb") as fobj:
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


def add_address(area):
    """Add an address column to a club dataframe identified by the area ID

    Parameters
    ----------
    area : str
        Area ID, as a single letter
    """
    df_filepath = DATADIR / f"clubs_comite_{area}.csv"
    df_clubs = pd.read_csv(df_filepath)
    df_clubs["address"] = ""
    df_clubs.to_csv(df_filepath, index=False)


def geocode(address):
    """Geocode a club place identified by the main available address on the
    FFSC website

    Parameters
    ----------
    address : str
        Main address of the club
    """
    if address == "":
        return None
    geocode = geocoder.osm(address)
    if geocode.status == "ERROR - No results found":
        return None
    return Point(geocode.latlng)
