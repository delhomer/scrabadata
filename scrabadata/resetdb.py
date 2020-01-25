"""Manage the connexion to database
"""

from configparser import ConfigParser
import os
import sys

import psycopg2

from scrabadata import config


def generate_db_string(db_config):
    """Build a database connection string starting from a config file

    Parameters
    ----------
    db_config : dict
        Database connexion parameters

    Returns
    -------
    str
        Database connexion string
    """
    user = db_config.get("user")
    if db_config.get("password"):
        user = user + ":" + config.get("password")
    db_string = "postgresql://{}@{}:{}/{}".format(
        user,
        db_config.get("host"),
        db_config.get("port"),
        db_config.get("dbname")
        )
    return db_string


def resetdb():
    """Reset the database declared in the configuration file, with the PostGIS
    extension.    
    """
    if not config.has_section("database"):
        raise ValueError("Missing 'database' section in config file.")
    db_string = generate_db_string(config["database"])
    db_name = db_string.split("/")[-1]

    # Reinitialize the database
    pg_conn = psycopg2.connect(db_string.replace(db_name, "postgres"))
    pg_conn.autocommit = True
    pg_cursor = pg_conn.cursor()
    pg_cursor.execute(
        "DROP DATABASE IF EXISTS {dbname};".format(dbname=db_name)
    )
    pg_cursor.execute(
        "CREATE DATABASE {dbname};".format(dbname=db_name)
    )
    pg_conn.close()
    db_conn = psycopg2.connect(db_string)
    db_cursor = db_conn.cursor()
    db_cursor.execute(
        "CREATE EXTENSION IF NOT EXISTS POSTGIS;"
    )
    db_conn.commit()
    db_conn.close()


if __name__ == "__main__":

    resetdb()
