#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# utprint.py
""" A simple CLI client for UT's Library Print System. """

# Copyright (c) 2017 Ryan Young (https://youngryan.com)

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.


from appdirs import user_config_dir
from base64 import b64encode
from collections import namedtuple
from getpass import getpass
from json import dumps
from mimetypes import guess_type
from time import sleep
from urllib.parse import quote
import argparse
import configparser
import os
import requests
import sys


CONFIG_DIR = user_config_dir("utprint", "YoRyan")
CONFIG_FILENAME = "config.ini"
JOB_PROCESSING_POLL_TIME = 3
BEVO_BUCKS_URL = "https://utdirect.utexas.edu/bevobucks/addBucks.WBX"

Config = namedtuple("Config", ["color", "sides", "pharos_user_token"])

class PrintCenter:
    """Library of functions that interact with the Pharos API."""

    PRINT_SERVER = "https://print.lib.utexas.edu/PharosAPI"

    Job = namedtuple("Job", ["uid", "state", "cost"])

    class Error(Exception):
        """Base class for exceptions."""
        pass

    class PharosAPIError(Error):
        """Error status returned by the Pharos API."""
        def __init__(self, error_json):
            self.status = error_json["Status"]
            self.user_message = error_json["UserMessage"]
            self.error_code = error_json["ErrorCode"]
            self.request_url = error_json["Request"]
            super().__init__("[Status " + str(self.status) + "] " +
                             self.user_message)

    def logon_with_cookie(pharos_user_token):
        """Resume a session with Pharos.

        pharos_user_token -- value of the PharosAPI.X-PHAROS-USER-TOKEN cookie

        Return a tuple with a Requests.Session to interact with the Pharos API
        and the available balance for printing.
        """
        session = requests.Session()
        session.cookies.set("PharosAPI.X-PHAROS-USER-TOKEN", pharos_user_token)
        response = session.get(PrintCenter.PRINT_SERVER + "/logon")
        response_json = response.json()
        if response.status_code == requests.codes.ok:
            # session now includes additional cookies set by Pharos
            balance = float(response_json["Balance"]["Amount"])
            return (session, balance)
        else:
            session.close()
            raise PrintCenter.PharosAPIError(response_json)

    def logon(credentials):
        """Initiate a session with Pharos.

        credentials -- (eid, password) tuple

        Return a tuple with a Requests.Session to interact with the Pharos API
        and the available balance for printing.
        """
        credentials = (encode_uricomp(credentials[0]),
                       encode_uricomp(credentials[1]))
        params = {}
        params["KeepMeLoggedIn"] = "yes"
        headers = {}
        headers["X-Authorization"] = ("PHAROS-USER " +
                                      encode_utf8_to_b64(credentials[0] + ":" +
                                                         credentials[1]))
        session = requests.Session()
        response = session.get(PrintCenter.PRINT_SERVER + "/logon",
                               params=params, headers=headers)
        response_json = response.json()
        if response.status_code == requests.codes.ok:
            balance = float(response_json["Balance"]["Amount"])
            return (session, balance)
        else:
            session.close()
            raise PrintCenter.PharosAPIError(response_json)

    def upload_file(session, options, filepath):
        """Upload a file to Pharos.

        session -- Request.Session from logon()
        options -- dictionary of document printing settings
        filepath -- path to document

        Return the parsed JSON response from the server.
        """
        files = [
            ("MetaData", (None, dumps(options))),
            ("content", (os.path.basename(filepath), open(filepath, "rb"),
                         mimetype(filepath)))
        ]
        response = session.post(PrintCenter._user_uri(session) + "/printjobs",
                                files=files)
        response_json = response.json()
        if response.status_code == requests.codes.created:
            return PrintCenter.Job(uid=response_json["Location"],
                                   state=response_json["Activity"]["State"],
                                   cost=0.0)
        else:
            raise PrintCenter.PharosAPIError(response_json)

    def get_jobs(session):
        """Get the list of all queued print jobs.

        session -- Request.Session from logon()
        """
        response = session.get(PrintCenter._user_uri(session) + "/printjobs")
        response_json = response.json()
        if response.status_code == requests.codes.ok:
            jobs = []
            for item in response_json["Items"]:
                job = PrintCenter.Job(uid=item["Location"],
                                      state=item["Activity"]["State"],
                                      cost=float(item.get("Cost", "0.0")))
                jobs.append(job)
            return jobs
        else:
            raise PrintCenter.PharosAPIError(response_json)

    def _user_uri(session):
        """Extract user's API endpoint from the cookie jar.

        session -- Requests.Session from logon()
        """
        return (PrintCenter.PRINT_SERVER +
                session.cookies["PharosAPI.X-PHAROS-USER-URI"])

def main():
    # read config file
    config = read_config_file()

    # command-line arguments
    parser = argparse.ArgumentParser(description=
                                     "Upload a document to UT's Library Print System.")
    parser.add_argument("--color", dest="color", choices=["full", "mono"], default=config.color,
                        help="print with or without color")
    parser.add_argument("--sides", dest="sides", type=int, choices=[1, 2], default=config.sides,
                        help="print single sided (simplex) or double sided (duplex)")
    parser.add_argument("--two-pps", dest="two_pages", action="store_true",
                        help="print two pages on each side of paper")
    parser.add_argument("--copies", dest="copies", type=int, default=1,
                        help="print multiple copies")
    parser.add_argument("--range", dest="range", default="",
                        help="print a specific set of pages (e.g. '1-5, 8, 11-13')")
    parser.add_argument("document",
                        help="a file (PDF, image, MS Office...) to print")
    args = parser.parse_args()

    # confirm settings and build JSON
    print("Print settings:")
    foptions = {}

    if args.color == "full":
        print("  - Full color")
        foptions["Mono"] = False
    elif args.color == "mono":
        print("  - Mono")
        foptions["Mono"] = True

    if args.sides == 1:
        print("  - Simplex")
        foptions["Duplex"] = False
    elif args.sides == 2:
        print("  - Duplex")
        foptions["Duplex"] = True

    if args.two_pages:
        print("  - 2 pages per side")
        foptions["PagesPerSide"] = "2"
    else:
        foptions["PagesPerSide"] = "1"

    print("  - Copies: " + str(args.copies))
    foptions["Copies"] = str(args.copies)

    if args.range == "":
        print("  - Page range: all")
        foptions["PageRange"] = ""
    else:
        print("  - Page range: " + args.range)
        foptions["PageRange"] = args.range

    foptions["DefaultPageSize"] = "Letter" # what's this? not in the web UI

    options = {
        "FinishingOptions": foptions,
        "PrinterName": None
    }

    session = None
    balance = 0.0

    # login, try saved cookie if it exists then prompt for credentials
    if config.pharos_user_token is not None:
        new_script_status("Logging in with saved token")
        try:
            logon = PrintCenter.logon_with_cookie(config.pharos_user_token)
            session = logon[0]
            balance = logon[1]
            end_script_status("done")
        except PrintCenter.PharosAPIError:
            end_script_status("expired")
    if session is None:
        creds = get_credentials()
        new_script_status("Logging in")
        logon = PrintCenter.logon(creds)
        session = logon[0]
        balance = logon[1]
        end_script_status("done")

    # save authentication cookie to config file
    new_config = Config(color=config.color, sides=config.sides, pharos_user_token=
                        session.cookies["PharosAPI.X-PHAROS-USER-TOKEN"])
    write_config_file(new_config)

    # upload document
    new_script_status("Uploading " + os.path.basename(args.document))
    job = PrintCenter.upload_file(session, options, args.document)
    end_script_status("done")

    # wait for document to process
    new_script_status("Processing")
    job_cost = 0.0
    job_processed = False
    while not job_processed:
        sleep(JOB_PROCESSING_POLL_TIME)
        jobs = PrintCenter.get_jobs(session)
        job_now = next((j for j in jobs if j.uid == job.uid), None)
        if job_now is not None and job_now.state == "Completed":
            job_cost = job_now.cost
            job_processed = True
    end_script_status("done")

    # show cost to print
    print("Finances:")
    print("    Available balance: " + money(balance))
    print("    Cost to print:     " + money(job_cost))
    print()
    if job_cost <= balance:
        print("    Remaining balance: " + money(balance - job_cost))
    else:
        print("  * Insufficent funds -- add Bevo Bucks at\n    " + BEVO_BUCKS_URL)

    session.close()
    return 0

def read_config_file():
    """Read user preferences from the configuration file.

    Return a Config tuple."""
    color = "full"
    sides = 1
    token = None
    parser = configparser.ConfigParser()
    parser.read(os.path.join(CONFIG_DIR, CONFIG_FILENAME))
    sections = parser.sections()
    if "PrintDefaults" in sections:
        fcolor = parser["PrintDefaults"].get("Color", None)
        if fcolor == "full" or fcolor == "mono":
            color = fcolor
        fsides = parser["PrintDefaults"].get("Sides", None)
        if fsides == "1" or fsides == "2":
            sides = int(fsides)
    if "PersistentAuth" in sections:
        token = parser["PersistentAuth"].get("Cookie", None)
    return Config(color=color, sides=sides, pharos_user_token=token)

def write_config_file(config):
    """Save user preferences to the configuration file.

    config -- Config tuple of stuff to save
    """
    writer = configparser.ConfigParser()
    writer["PrintDefaults"] = {}
    writer["PrintDefaults"]["Color"] = config.color
    writer["PrintDefaults"]["Sides"] = str(config.sides)
    writer["PersistentAuth"] = {}
    writer["PersistentAuth"]["Cookie"] = config.pharos_user_token
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(os.path.join(CONFIG_DIR, CONFIG_FILENAME), "w") as f:
        writer.write(f)

def new_script_status(status):
    """Print a new status message in progress."""
    print(status + " ... ", end="")
    sys.stdout.flush()

def end_script_status(result):
    """Resolve the last status."""
    print(result)
    sys.stdout.flush()

def get_credentials():
    """Prompt for the user's EID and password."""
    eid = input("\nEID: ")
    password = getpass()
    print()
    return (eid, password)

def encode_utf8_to_b64(s):
    """Emulates Pharos's DIY base-64 encoder."""
    return b64encode(bytes(s, "utf-8")).decode("ascii")

# https://stackoverflow.com/questions/946170/equivalent-javascript-functions-for-pythons-urllib-quote-and-urllib-unquote
def encode_uricomp(s):
    """Emulates JavaScript's encodeURIComponent()."""
    return quote(s, safe="~()*!.'")

def mimetype(filepath):
    """Guess the mimetype of a file."""
    t = guess_type(filepath)
    if t[0] is None:
        return "application/octet-stream"
    else:
        return t[0]

def money(f):
    """Format a float as a dollar amount."""
    return "${0:.2f}".format(f)

if __name__ == "__main__":
    sys.exit(main())
