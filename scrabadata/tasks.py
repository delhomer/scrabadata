"""Design a data pipeline in order to handle data from FFSC (Fédération
Française de Scrabble), i.e. "duplicate" rankings, areas and clubs.

Available Luigi tasks:
- CreateSchema
- DownloadRanking
- RankingToDB
- DownloadAreas
- AreasToDB
- DownloadClubs
- MergeClubs
- GeocodeClubs
- ClubsToDB
- Finalize
"""

from datetime import date, timedelta
from lxml import html
from pathlib import Path

import luigi
from luigi.contrib.postgres import CopyToTable, PostgresQuery
from luigi.format import MixedUnicodeBytes
import pandas as pd
import requests

from scrabadata import config, download

DATADIR = Path(config["main"]["datadir"])


class CreateSchema(PostgresQuery):
    """As this class inheritates from PostgresQuery, it must define host,
    database, user, password, schema and table attributes
    """
    host = config['database']['host']
    database = config['database']['dbname']
    user = config['database']['user']
    password = config['database'].get('password')
    table = luigi.Parameter(default="create_schema")
    query = "CREATE SCHEMA IF NOT EXISTS {schema};"
    schema = luigi.Parameter()

    def run(self):
        connection = self.output().connect()
        cursor = connection.cursor()
        sql = self.query.format(schema=self.schema)
        cursor.execute(sql)
        # Update marker table
        self.output().touch(connection)
        # commit and close connection
        connection.commit()
        connection.close()


class DownloadRanking(luigi.Task):
    """Download the most recent Scrabble duplicate ranking on the FFSC website
    with respect to the given date

    If there is no up-to-date ranking at the given date, one check on previous
    days iteratively until finding the most recent published ranking.

    Attributes
    ----------
    date : datetime.date
        Date of the ranking
    """
    date = luigi.DateParameter(default=date.today())

    @property
    def error_message(self):
        return """ERREUR : La date spécifiée est postérieure à la dernière date de calcul du classement national actualisé.""".encode("UTF-8").decode("LATIN1")

    def output(self):
        date_str = self.date.strftime("%Y%m%d")
        output_path = (
            DATADIR / "classements_bruts" / f"classement_{date_str}.csv"
            )
        output_path.parent.mkdir(exist_ok=True, parents=True)
        return luigi.LocalTarget(output_path, format=MixedUnicodeBytes)

    def run(self):
        query_date = self.date
        ranking_url = config["url"]["ranking"]
        while True:
            ranking = download.get_ranking(query_date, ranking_url)
            if self.error_message not in ranking.decode(encoding="LATIN1"):
                break
            query_date = query_date - timedelta(1)
        with self.output().open("w") as fobj:
            fobj.write(ranking)


class RankingToDB(CopyToTable):
    """Stores the up-to-date ranking to the application database, following the
    configuration defined in scrabadata/config.ini.

    Attributes
    ----------
    date : datetime.date
        Date to which the ranking must be downloaded
    """
    host = config['database']['host']
    database = config['database']['dbname']
    user = config['database']['user']
    password = config['database'].get('password')

    columns = [
        ('date', 'DATE'),
        ('place', 'INT'),
        ('joueur', 'VARCHAR(48)'),
        ('licence', 'INT'),
        ('categorie', 'VARCHAR(1)'),
        ('serie', 'VARCHAR(2)'),
        ('club', 'VARCHAR(4)'),
        ('point', 'INT'),
        ('ps1', 'NUMERIC'),
        ('ps2', 'NUMERIC'),
        ('ps3', 'NUMERIC'),
        ('pp4', 'INT'),
        ('serie_potentielle', 'VARCHAR(2)')
    ]

    date = luigi.DateParameter(default=date.today())

    @property
    def table(self):
        return "classements.classement_general"

    def requires(self):
        return {
            "schema": CreateSchema(schema="classements"),
            "ranking": DownloadRanking(self.date)
            }

    def rows(self):
        """overload the rows method to skip the first line (header)
        """
        with self.input()["ranking"].open('r') as fobj:
            df = pd.read_csv(fobj, encoding="LATIN1", sep=";")
            for _, row in df.iterrows():
                modified_row = list(row)
                modified_row.insert(0, self.date)
                yield modified_row


class DownloadAreas(luigi.Task):
    """Download french Scrabble areas following the FFSC spatial organization

    According to the FFSC website (*), there are 25 distinct areas, that
    are approximatively defined as administrative areas.

    (*) https://www.ffsc.fr/clubs.php
    """

    def output(self):
        output_path = DATADIR / "areas.csv"
        return luigi.LocalTarget(output_path)

    def run(self):
        df_areas = download.get_areas(config["url"]["area"])
        df_areas["geom"] = None
        df_areas.to_csv(self.output().path, index=False)


class AreasToDB(CopyToTable):
    """Stores the FFSC areas to the database, depending on the postgres access
    defined in scrabadata/config.ini

    This information is stored in the "areas.areas" table, that contains three
    columns: area IDs, names and locations.
    """
    host = config['database']['host']
    database = config['database']['dbname']
    user = config['database']['user']
    password = config['database'].get('password')

    columns = [
        ("area_id", "VARCHAR(1)"),
        ("name", "VARCHAR(48)"),
        ("geometry", "GEOMETRY")
    ]

    @property
    def table(self):
        return "areas.areas"

    def requires(self):
        return {
            "schema": CreateSchema(schema="areas"),
            "areas": DownloadAreas()
            }

    def rows(self):
        with self.input()["areas"].open('r') as fobj:
            df = pd.read_csv(fobj)
            for _, row in df.iterrows():
                yield row


class DownloadClubs(luigi.Task):
    """Download the list of clubs in a given area, and store them into a csv
    file.

    The clubs are stored into <DATADIR>/clubs/raw/ folder.

    *Disclaimer:* the club addresses are not parsed from the FFSC website due
    to a high degree of variability in the address definition. This task only
    prepares an empty "address" attribute; one has to manually feed the output
    csv with club addresses. The complete club data is expected to be stored
    into the <DATADIR>/clubs/located/ folder for further treatment.

    Attributes
    ----------
    area_id : str
        Area ID, as a letter of the alphabet (from A to Y)
    """
    area_id = luigi.Parameter()

    def output(self):
        output_path = (
            DATADIR / "clubs" / "raw" / f"clubs_comite_{self.area_id}.csv"
            )
        return luigi.LocalTarget(output_path)

    def run(self):
        df_clubs = download.get_clubs(config["url"]["club"], self.area_id)
        df_clubs["address"] = ""
        df_clubs.to_csv(self.output().path, index=False)


class MergeClubs(luigi.Task):
    """This class merges all the csv located into <DATADIR>/clubs/located
    folder, by making the assomption that it contains csv files with downloaded
    club lists.

    It is currently impossible to pipe this class with DownloadClubs task, as
    the club addresses are filled up manually.

    The output file is a csv file that contains all the downloaded clubs, with
    specified addresses. It is stored as <DATADIR>/clubs/located_clubs.csv.
    """

    @property
    def input_dir(self):
        return DATADIR / "clubs" / "located"

    def output(self):
        output_path = DATADIR / "clubs" / "located_clubs.csv"
        return luigi.LocalTarget(output_path)

    def run(self):
        df_clubs = pd.DataFrame({"club": [], "address": []})
        for area_input in self.input_dir.iterdir():
            area_clubs = pd.read_csv(area_input)
            if "area" in area_clubs.columns:
                area_clubs.rename({"area": "club"}, axis=1, inplace=True)
            area_clubs.set_index("id", inplace=True)
            df_clubs = pd.concat([df_clubs, area_clubs])
        df_clubs.to_csv(self.output().path, index_label="id")


class GeocodeClubs(luigi.Task):
    """Build a new version of FFSC clubs with georeferenced information
    (addresses and (x,y) coordinates), stored on the file system as
    <DATADIR>/clubs/geocoded_clubs.geojson.

    The class uses geopandas in order to do this job, by defining a "geometry"
    feature that contains shapely Points. The point coordinates are retrieved
    with the help of a geocoding tool that requests Nominatim API (OSM).
    """

    def requires(self):
        return MergeClubs()

    def output(self):
        output_path = DATADIR / "clubs" / "geocoded_clubs.geojson"
        return luigi.LocalTarget(output_path)

    def run(self):
        clubs = pd.read_csv(self.input())
        clubs.loc[:, "geometry"] = clubs["address"].apply(
            lambda x: download.geocode(x)
        )
        gdf.to_file(self.output().path, driver="GeoJSON")


class ClubsToDB(CopyToTable):
    """Stores the FFSC clubs to the database, depending on the postgres access
    defined in scrabadata/config.ini

    This information is stored in the "areas.clubs" table, that contains four
    columns: club IDs, names, addresses, and geographical location following a
    (x, y) referential.
    """
    host = config['database']['host']
    database = config['database']['dbname']
    user = config['database']['user']
    password = config['database'].get('password')

    columns = [
        ("club_id", "VARCHAR(3)"),
        ("name", "VARCHAR(48)"),
        ("address", "VARCHAR(100)"),
        ("geometry", "GEOMETRY")
    ]

    @property
    def table(self):
        return "areas.clubs"

    def requires(self):
        return {
            "schema": CreateSchema(schema="areas"),
            "clubs": MergeClubs()
            }

    def rows(self):
        with self.input()["clubs"].open('r') as fobj:
            df = pd.read_csv(fobj)
            for _, row in df.iterrows():
                yield row


class Finalize(luigi.Task):
    """Master task which ensures that up-to-date ranking, clubs and areas are
    stored into the application database

    Attributes
    ----------
    date : datetime.date
        Date to which the ranking must be downloaded
    """

    date = luigi.DateParameter(default=date.today())

    def requires(self):
        yield RankingToDB(date=self.date)
        yield ClubsToDB()
        yield AreasToDB()
