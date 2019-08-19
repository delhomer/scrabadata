"""Design a data pipeline by defining some Luigi tasks
"""

from datetime import date, timedelta
from pathlib import Path

import luigi
from luigi.format import MixedUnicodeBytes
import requests


RANKING_URL = "https://www.ffsc.fr/classements.exporter.php?class=nat&date={date}"
AREA_URL = "https://www.ffsc.fr/clubs.php"
CLUB_URL = "https://www.ffsc.fr/clubs.php?comite={region}"
DATADIR = Path("data")


class DownloadRanking(luigi.Task):
    """
    """
    date = luigi.DateParameter(default=date.today())

    @property
    def error_message(self):
        return """ERREUR : La date spécifiée est postérieure à la dernière date de calcul du classement national actualisé.""".encode("UTF-8").decode("LATIN1")

    def output(self):
        date_str = self.date.strftime("%Y%m%d")
        output_path = DATADIR / "classements" / f"classement_{date_str}.csv"
        return luigi.LocalTarget(output_path, format=MixedUnicodeBytes)

    def run(self):
        query_date = self.date
        while True:
            ranking_date_str = query_date.strftime("%Y-%m-%d")
            url = RANKING_URL.format(date=ranking_date_str)
            resp = requests.get(url)
            if self.error_message not in resp.content.decode(encoding="LATIN1"):
                break
            query_date = query_date - timedelta(1)
        with self.output().open("w") as fobj:
            fobj.write(resp.content)
