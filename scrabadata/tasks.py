"""Design a data pipeline by defining some Luigi tasks
"""

from datetime import date, timedelta
from lxml import html
from pathlib import Path

import luigi
from luigi.contrib.postgres import CopyToTable, PostgresQuery
from luigi.format import MixedUnicodeBytes
import pandas as pd
import requests

from scrabadata import config

DATADIR = Path(config["main"]["datadir"])


class DownloadRanking(luigi.Task):
    """
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
        while True:
            ranking_date_str = query_date.strftime("%Y-%m-%d")
            url = config["url"]["ranking"].format(date=ranking_date_str)
            resp = requests.get(url)
            if self.error_message not in resp.content.decode(encoding="LATIN1"):
                break
            query_date = query_date - timedelta(1)
        with self.output().open("w") as fobj:
            fobj.write(resp.content)


class DownloadZipfile(luigi.Task):
    """
    """

    name = luigi.Parameter()
    url = luigi.Parameter()

    def output(self):
        output_path = DATADIR / self.name + ".zip"
        return luigi.LocalTarget(self.path, format=MixedUnicodeBytes)

    def run(self):
        with self.output().open('w') as fobj:
            resp = requests.get(self.url)
            resp.raise_for_status()
            fobj.write(resp.content)


class UnzipShapeFile(luigi.Task):
    """Task dedicated to unzip file

    To get trace that the task has be done, the task creates a text file with
    the same same of the input zip file with the '.done' suffix. This generated
    file contains the path of the zipfile and all extracted files.
    """

    name = luigi.Parameter()
    url = luigi.Parameter()

    def requires(self):
        return DownloadZipfile(self.name, self.url)

    def output(self):
        filepath = DATADIR / self.name + "-unzip.done"
        return luigi.LocalTarget(filepath)

    def run(self):
        with self.output().open('w') as fobj:
            fobj.write("unzip file {}\n".format(self.name))
            zip_path = DATADIR / self.name + ".zip"
            zip_ref = zipfile.ZipFile(zip_path)
            fobj.write("\n".join(elt.filename for elt in zip_ref.filelist))
            fobj.write("\n")
            zip_ref.extractall(os.path.dirname(self.input().path))
            zip_ref.close()


class DownloadAreas(luigi.Task):
    """
    """

    def output(self):
        output_path = DATADIR / "areas.csv"
        return luigi.LocalTarget(output_path)

    def run(self):
        resp = requests.get(config["url"]["area"])
        tree = html.fromstring(resp.content)
        area_list = tree.xpath("//ul[@class='menu_secondary']/li/*/text()")
        area_list = [area.split(" - ") for area in area_list]
        df_areas = pd.DataFrame(area_list, columns=["id", "area"])
        df_areas["geom"] = None
        df_areas.to_csv(self.output().path, index=False)


class DownloadClubs(luigi.Task):
    """
    """
    area_id = luigi.Parameter()

    def output(self):
        output_path = DATADIR / "clubs" / f"clubs_comite_{self.area_id}.csv"
        return luigi.LocalTarget(output_path)

    def run(self):
        resp = requests.get(config["url"]["club"].format(region=self.area_id))
        tree = html.fromstring(resp.content)
        club_list = tree.xpath("//div[@class='main']/h3/*/text()")
        club_list = [club.split(" - ", 1) for club in club_list]
        df_clubs = pd.DataFrame(club_list, columns=["id", "club"])
        df_clubs["address"] = ""
        df_clubs.to_csv(self.output().path, index=False)


class MergeClubs(luigi.Task):
    """
    """

    def requires(self):
        club_dir = DATADIR / "clubs"
        required = {}
        areas = pd.read_csv(DATADIR / "areas.csv")
        for area_id in areas["id"]:
            required[area_id] = DownloadClubs(area_id)
        return required

    def output(self):
        output_path = DATADIR / "clubs.csv"
        return luigi.LocalTarget(output_path)

    def run(self):
        df_clubs = pd.DataFrame({"club": [], "address": []})
        for area_id, area_input in self.input().items():
            area_clubs = pd.read_csv(area_input.path)
            if "area" in area_clubs.columns:
                area_clubs.rename({"area": "club"}, axis=1, inplace=True)
            area_clubs.set_index("id", inplace=True)
            df_clubs = pd.concat([df_clubs, area_clubs])
        df_clubs.to_csv(self.output().path, index_label="id")


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


class RankingToDB(CopyToTable):
    """
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


class ClubsToDB(CopyToTable):
    """
    """
    host = config['database']['host']
    database = config['database']['dbname']
    user = config['database']['user']
    password = config['database'].get('password')

    columns = [
        ("club_id", "VARCHAR(3)"),
        ("address", "VARCHAR(100)"),
        ("name", "VARCHAR(48)")
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


class AreasToDB(CopyToTable):
    """
    """
    host = config['database']['host']
    database = config['database']['dbname']
    user = config['database']['user']
    password = config['database'].get('password')

    columns = [
        ("area_id", "VARCHAR(1)"),
        ("name", "VARCHAR(48)")
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


class Finalize(luigi.Task):
    """
    """

    date = luigi.DateParameter(default=date.today())

    def requires(self):
        yield RankingToDB(date=self.date)
        yield ClubsToDB()
        yield AreasToDB()
