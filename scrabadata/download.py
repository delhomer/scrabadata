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


def get_ranking(ranking_date, ranking_url):
    """Get FFSC "duplicate" ranking for the given date

    Parameters
    ----------
    ranking_date : datetime.date
        Date of the required ranking

    Returns
    -------
    str
        Ranking as a big string response
    """
    ranking_date_str = ranking_date.strftime("%Y-%m-%d")
    url = ranking_url.format(date=ranking_date_str)
    return requests.get(url).content


def get_areas(area_url):
    """Get the list of areas as defined by the FFSC

    Parameters
    ----------
    area_url : str
        URL of the areas on the FFSC website

    Returns
    -------
    pandas.DataFrame
        Set of areas, identified by an ID and a name
    """
    resp = requests.get(area_url)
    tree = html.fromstring(resp.content)
    area_list = tree.xpath("//ul[@class='menu_secondary']/li/*/text()")
    area_list = [area.split(" - ") for area in area_list]
    df_areas = pd.DataFrame(area_list, columns=["id", "area"])
    return df_areas


def get_clubs(club_url, area_id):
    """Get the list of Scrabble clubs in a specified area

    Parameters
    ----------
    club_url : str
        URL of the clubs on the FFSC website
    area_id : str
        ID of the area of interest, as a letter of the alphabet (from A to Y)

    Returns
    -------
    pandas.DataFrame
        Set of clubs, identified by an ID and a name
    """
    resp = requests.get(club_url.format(region=area_id))
    tree = html.fromstring(resp.content)
    club_list = tree.xpath("//div[@class='main']/h3/*/text()")
    club_list = [club.split(" - ", 1) for club in club_list]
    df_clubs = pd.DataFrame(club_list, columns=["id", "area"])
    return df_clubs


def geocode(address):
    """Geocode a club place identified by the main available address on the
    FFSC website

    Parameters
    ----------
    address : str
        Main address of the club

    Returns
    -------
    shapely.geometry.Point
        (x, y) location corresponding to the provided address; None if the
    address is unknown in the Nominatim database
    """
    if address == "":
        return None
    geocode = geocoder.osm(address)
    if geocode.status == "ERROR - No results found":
        return None
    return Point(geocode.latlng)
